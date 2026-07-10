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
from chimera.gateway import Gateway, GatewayResponse

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


def build_merge_prompt(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
    *,
    max_prompt_tokens: int | None = None,
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
    """
    instructions = _stage_instructions(stage, dispatch)

    # Build the per-dep blocks, but keep both the raw text and the
    # rendered block so we can re-render with truncation later.
    dep_blocks: list[tuple[StageResult, str, bool]] = []  # (dep, raw_output, degraded)
    degraded_count = 0
    for dep in dependencies:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
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
        user = (
            f"## Original user request\n{user_prompt}\n\n"
            f"## Dispatcher's instructions for you ({stage.id})\n{instructions}\n\n"
            f"## Upstream outputs\n{section}\n\n"
            "## Your job\n"
            "Following the instructions above, combine these into the final answer "
            "for the user. Output only the final answer."
            " Respond in valid JSON format."
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
    ) -> GatewayResponse:
        if max_prompt_tokens is None:
            max_prompt_tokens = getattr(
                self.config, "max_aggregator_context_tokens", None,
            )
        messages = build_merge_prompt(
            stage, dispatch, dependencies, user_prompt,
            max_prompt_tokens=max_prompt_tokens,
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
        return await self.gateway.complete(
            stage.model, messages, temperature=0.2, response_format=response_format,
        )


__all__ = ["Aggregator", "StageResult", "build_merge_prompt"]
