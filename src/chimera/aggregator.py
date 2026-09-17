"""The Aggregator — merges worker outputs using dispatcher-written instructions.

The aggregator is a "dumb executor": it receives the dispatcher's merge instructions
plus each worker's output (and what that worker was asked to do) and produces
the final merged answer. Different stage kinds (``aggregator``, ``merge``, ``audit``)
only differ in how their instructions are sourced; the call is identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from chimera.config import ChimeraConfig
from chimera.dispatcher import DispatchResult, Stage
from chimera.gateway import (
    FormatCapability,
    Gateway,
    GatewayResponse,
    _get_format_capability,
)

if TYPE_CHECKING:
    pass

log = structlog.get_logger("chimera.aggregator")


@dataclass(slots=True)
class StageResult:
    """The outcome of executing one DAG stage (input to the aggregator)."""

    stage_id: str
    model: str
    prompt: str
    response: GatewayResponse
    degraded: bool = False


#: Heuristic: 1 token ≈ 4 characters. Good enough for prompt-size budgeting
#: without taking a real tokenizer as a dependency.
_CHARS_PER_TOKEN = 4

#: Marker appended to truncated worker outputs so the aggregator model can
#: see it lost tail content (rather than silently misquoting something
#: shorter than reality).
_TRUNCATION_MARKER = "…[truncated to fit prompt budget]"


def _estimate_tokens(text: str) -> int:
    """Estimate the token cost of a chunk of text.

    Uses the ``~4 chars per token`` heuristic; deliberately over-estimates on
    long words so we never silently overflow the budget.
    """
    if not text:
        return 0
    # Round up so an empty string still costs 0, a single char costs 1, etc.
    return (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN


def _truncate_to_char_budget(text: str, char_budget: int) -> str:
    """Truncate ``text`` to fit ``char_budget`` and append a marker.

    The marker is included in the character budget so the returned string
    is at most ``char_budget`` chars long. If the original text already
    fits, it's returned unchanged.
    """
    if char_budget <= 0 or len(text) <= char_budget:
        return text
    keep = max(0, char_budget - len(_TRUNCATION_MARKER))
    return text[:keep].rstrip() + _TRUNCATION_MARKER


def _schema_enforceable_on_wire(config: ChimeraConfig, model: str) -> bool:
    """Whether the gateway can ENFORCE a ``json_schema`` format for *model*.

    Mirrors the provider resolution the gateway performs for a stage call
    (:meth:`chimera.gateway.LiteLLMGateway.complete`): the catalog entry's
    ``provider``, including the F8 reroute that sends an anthropic model
    through OpenRouter when no Anthropic credential is configured — OpenRouter
    is a :attr:`FormatCapability.NONE` provider too, so a schema is no more
    enforceable there.  The capability table is never re-implemented:
    :func:`chimera.gateway._get_format_capability` is the single source of
    truth, the same helper :func:`chimera.gateway.negotiate_response_format`
    consults before it strips ``response_format``.

    An unknown model is treated as NOT enforceable — the prompt-side
    restatement is harmless when the schema would have been enforced anyway,
    whereas skipping it when it was needed is the bug being fixed.
    """
    try:
        provider = config.get_model(model).provider
    except KeyError:
        return False

    if provider == "anthropic":
        # F8, as the gateway applies it: an Anthropic model is served by
        # OpenRouter when Anthropic itself has no credential (neither the
        # ``api_keys`` shortcut nor the provider entry) AND an OpenRouter
        # shortcut key exists.  ``provider_credential_resolved`` cannot answer
        # this — it deliberately folds the F8 fallback into the Anthropic view,
        # so it reports True for a native-key-less Anthropic whenever only an
        # OpenRouter key is configured (the very case that needs the reroute).
        native = config.api_keys.get("anthropic")
        if not native:
            anthropic_cfg = config.providers.get("anthropic")
            native = anthropic_cfg.api_key if anthropic_cfg is not None else None
        if not native and config.api_keys.get("openrouter"):
            provider = "openrouter"

    return _get_format_capability(provider) == FormatCapability.JSON_SCHEMA


def _schema_restatement(schema: dict[str, Any]) -> str:
    """Short prompt-side restatement of a dispatcher-authored output schema.

    Appended only when the wire cannot enforce the schema (a
    ``FormatCapability.NONE`` provider has ``response_format`` stripped), which
    is exactly when the model has to be TOLD the shape instead of being
    constrained to it. Names the required keys, the declared type of each
    property, and — the failure this exists for — that an array-of-strings
    property must be a JSON array, never a comma-joined string.
    """
    properties = (
        schema.get("properties")
        if isinstance(schema.get("properties"), dict)
        else {}
    )
    required = [r for r in (schema.get("required") or []) if isinstance(r, str)]

    described: list[str] = []
    array_of_strings: list[str] = []
    for name, subschema in properties.items():
        if not isinstance(subschema, dict):
            continue
        declared = subschema.get("type")
        if declared == "array":
            items = subschema.get("items")
            item_type = items.get("type") if isinstance(items, dict) else None
            declared = f"array of {item_type}s" if isinstance(item_type, str) else "array"
            if item_type == "string":
                array_of_strings.append(name)
        if not isinstance(declared, str):
            continue
        described.append(f"{name}: {declared}")

    lines = [
        "## Required output shape",
        "Reply with a single JSON object and nothing else — no prose, no code fences.",
    ]
    if required:
        lines.append("Required keys: " + ", ".join(required) + ".")
    if described:
        lines.append("Field types: " + "; ".join(described) + ".")
    if array_of_strings:
        lines.append(
            f"{', '.join(array_of_strings)} MUST be a JSON ARRAY of strings, "
            'e.g. ["worker_1", "worker_2"] — never a comma-joined string like '
            '"worker_1, worker_2".'
        )
    return "\n".join(lines)


def build_merge_prompt(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
    *,
    max_prompt_tokens: int | None = None,
    output_schema: dict[str, Any] | None = None,
    wire_enforces_schema: bool = True,
) -> list[dict[str, str]]:
    """Build the message list for an aggregator / merge / audit stage.

    Parameters
    ----------
    stage, dispatch, dependencies, user_prompt
        As before.
    max_prompt_tokens
        Optional soft cap on the *total* size of the produced prompt
        (system + user) measured in estimated tokens (~4 chars/token).
        When provided and the natural prompt would exceed it, the
        longest worker outputs are truncated (preserving shorter, more
        focused ones) until the prompt fits. ``None`` (default) means
        no truncation — preserves backward compatibility.
    output_schema
        Optional JSON Schema the final answer must conform to.  When
        provided, the "Respond in valid JSON format." hint is
        suppressed — the ``response_format`` parameter on the gateway
        call handles schema enforcement so the prompt should not add
        conflicting JSON instructions.
    wire_enforces_schema
        Whether the wire can actually enforce *output_schema* (the
        stage's provider supports ``json_schema``).  Defaults to
        ``True`` — the historical assumption, which holds for the
        providers that support it.  When ``False`` for a
        ``FormatCapability.NONE`` provider, ``response_format`` is
        stripped by :func:`chimera.gateway.negotiate_response_format`
        and the model never sees the schema, so a short textual
        restatement of the required shape (see
        :func:`_schema_restatement`) is appended instead.  It has no
        effect without *output_schema* or when the wire enforces it.
    """
    instructions = _stage_instructions(stage, dispatch)

    # Build the per-dep blocks, but keep both the raw text and the
    # rendered block so we can re-render with truncation later.
    dep_blocks: list[tuple[StageResult, str, bool]] = []  # (dep, raw_output, degraded)
    degraded_count = 0
    for dep in dependencies:
        if dep.degraded:
            degraded_count += 1
            dep_blocks.append((dep, dep.response.text, True))
        else:
            dep_blocks.append((dep, dep.response.text, False))

    if degraded_count > 0:
        log.warning(
            "aggregator_partial_inputs",
            stage=stage.id,
            total_deps=len(dependencies),
            degraded=degraded_count,
            healthy=len(dependencies) - degraded_count,
        )

    truncated_outputs: set[str] = set()

    def _shell_for(dep: StageResult, output: str, degraded: bool) -> str:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        if dep.stage_id in truncated_outputs:
            tag = " [DEGRADED]" if degraded else ""
            return (
                f"### {dep.stage_id} (model: {dep.model}){tag} [TRUNCATED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output (truncated to fit aggregator prompt budget):\n{output}"
            )
        if degraded:
            return (
                f"### {dep.stage_id} (model: {dep.model}) [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{output}\n"
                f"Note: This stage failed to produce valid output."
            )
        return (
            f"### {dep.stage_id} (model: {dep.model})\n"
            f"Was asked to: {asked}\n\n"
            f"Output:\n{output}"
        )

    def _render_prompt() -> tuple[str, str]:
        section = "\n\n".join(
            _shell_for(d, o, g) for d, o, g in dep_blocks
        ) if dep_blocks else "(no upstream outputs)"
        kind_label = stage.kind
        system = (
            f"You are the Chimera {kind_label}. "
            "Your job is to produce the single best answer to the user's request "
            "using the upstream outputs and the dispatcher's instructions.\n"
        )
        json_hint = (
            " Respond in valid JSON format."
            if output_schema is None
            else ""
        )
        # The wire can only enforce a schema for json_schema-capable
        # providers; everywhere else response_format is stripped, so the
        # shape has to be stated in the prompt or the model guesses it.
        schema_note = (
            "\n\n" + _schema_restatement(output_schema)
            if output_schema is not None and not wire_enforces_schema
            else ""
        )
        user = (
            f"## Original user request\n{user_prompt}\n\n"
            f"## Dispatcher's instructions for you ({stage.id})\n{instructions}\n\n"
            f"## Upstream outputs\n{section}\n\n"
            "## Your job\n"
            "Following the instructions above, combine these into the final answer "
            f"for the user. Output only the final answer.{json_hint}{schema_note}"
        )
        return system, user

    # ── Optional truncation pass ──
    if max_prompt_tokens is not None and dep_blocks:
        system, user = _render_prompt()
        total_tokens = _estimate_tokens(system) + _estimate_tokens(user)

        if total_tokens > max_prompt_tokens:
            # How much character budget is left for *all* output text combined?
            # total_chars - sum(output lengths) = chars used by everything else.
            total_chars = len(system) + len(user)
            output_chars = sum(len(o) for _, o, _ in dep_blocks)
            non_output_chars = total_chars - output_chars
            remaining_tokens = max(
                0, max_prompt_tokens - _estimate_tokens("x" * non_output_chars)
            )
            remaining_chars = remaining_tokens * _CHARS_PER_TOKEN

            # Sort by output length, longest first — truncate the longest
            # outputs to preserve shorter, more focused ones.
            indexed = sorted(
                enumerate(dep_blocks),
                key=lambda pair: len(pair[1][1]),
                reverse=True,
            )
            current_output_chars = output_chars
            for idx, (dep, output, degraded) in indexed:
                if current_output_chars <= remaining_chars:
                    break
                over = current_output_chars - remaining_chars
                new_len = max(len(_TRUNCATION_MARKER), len(output) - over)
                if new_len >= len(output):
                    # Already small enough — the marker would make it longer.
                    continue
                dep_blocks[idx] = (
                    dep, _truncate_to_char_budget(output, new_len), degraded,
                )
                truncated_outputs.add(dep.stage_id)
                current_output_chars = sum(len(o) for _, o, _ in dep_blocks)

            if truncated_outputs:
                log.warning(
                    "aggregator_prompt_truncated",
                    stage=stage.id,
                    truncated=sorted(truncated_outputs),
                    n_truncated=len(truncated_outputs),
                    n_total=len(dep_blocks),
                    max_prompt_tokens=max_prompt_tokens,
                    estimated_total_tokens=total_tokens,
                )

    # ── Final render ──
    system, user = _render_prompt()
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _stage_instructions(stage: Stage, dispatch: DispatchResult) -> str:
    if stage.id in dispatch.stage_instructions:
        return dispatch.stage_instructions[stage.id]
    if stage.kind == "aggregator":
        return dispatch.aggregator_instructions or _default_aggregator_instructions()
    if stage.kind == "merge":
        return (
            "Multiple aggregators produced the outputs above. Merge them into one "
            "authoritative final answer, preserving the strongest content from each "
            "and resolving any contradictions."
        )
    if stage.kind == "audit":
        return (
            "Audit the upstream answer for correctness, completeness, and safety. "
            "Return the final, corrected answer (not a critique)."
        )
    return "Produce the final answer from the upstream outputs."


def _default_aggregator_instructions() -> str:
    return (
        "Merge the worker outputs into a single coherent final answer. "
        "Each worker handled a different part of the task — combine them so the "
        "result fully addresses the user's request."
    )


def _what_worker_was_asked(stage_id: str, dispatch: DispatchResult) -> str:
    wp = dispatch.worker_prompt_for(stage_id)
    if wp and wp.prompt:
        return wp.prompt
    return "Solve the user's request."


class Aggregator:
    """Executes a non-worker stage (aggregator / merge / audit).

    When ``output_schema`` is provided, the aggregator uses provider-aware structured
    output to ensure the final response matches the requested schema exactly.
    """

    def __init__(self, config: ChimeraConfig, gateway: Gateway) -> None:
        self.config = config
        self.gateway = gateway

    async def execute(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dependencies: list[StageResult],
        user_prompt: str,
        *,
        output_schema: dict[str, Any] | None = None,
        max_prompt_tokens: int | None = None,
        max_tokens: int | None = None,
    ) -> GatewayResponse:
        if max_prompt_tokens is None:
            max_prompt_tokens = getattr(
                self.config, "max_aggregator_context_tokens", None,
            )
        messages = build_merge_prompt(
            stage, dispatch, dependencies, user_prompt,
            max_prompt_tokens=max_prompt_tokens,
            output_schema=output_schema,
            # Only a json_schema-capable provider actually receives the
            # schema (`negotiate_response_format` strips `response_format`
            # for everyone else), so the prompt has to carry the shape
            # wherever the wire cannot.
            wire_enforces_schema=_schema_enforceable_on_wire(
                self.config, stage.model,
            ),
        )
        log.info(
            "aggregator_execute",
            stage=stage.id,
            kind=stage.kind,
            model=stage.model,
            n_inputs=len(dependencies),
            structured=output_schema is not None,
            max_prompt_tokens=max_prompt_tokens,
        )
        response_format = None
        if output_schema is not None:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "chimera_output",
                    "strict": True,
                    "schema": output_schema,
                },
            }
        # CH-GAP-031: honor OpenAI-compat max_tokens on the aggregator call —
        # the final answer must respect the client's output cap.
        kwargs: dict[str, Any] = {"temperature": 0.2, "response_format": response_format}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return await self.gateway.complete(stage.model, messages, **kwargs)


__all__ = ["Aggregator", "StageResult", "build_merge_prompt"]
