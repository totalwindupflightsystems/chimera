"""The Aggregator — merges worker outputs using dispatcher-written instructions.

The aggregator is a "dumb executor": it receives the dispatcher's merge instructions
plus each worker's output (and what that worker was asked to do) and produces
the final merged answer. Different stage kinds (``aggregator``, ``merge``, ``audit``)
only differ in how their instructions are sourced; the call is identical.

Rank-then-fuse (DF-CHIMERA-V2-102, LLM-Blender PairRanker class) adds ONE optional
pre-merge step: when the formation sets ``rank: true``, a cheap scorer call scores
every upstream output, the candidates are sorted, and only the top ``kappa`` reach
the merge prompt. Every candidate's rank and score is returned to the caller so the
trace can carry them; the scorer is best-effort (a failed pass feeds all outputs).
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from chimera.config import ChimeraConfig
from chimera.dispatcher import DispatchResult, Stage, _strip_fences
from chimera.exceptions import BudgetExhaustedError
from chimera.gateway import (
    FormatCapability,
    Gateway,
    GatewayError,
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


@dataclass(slots=True)
class RankPolicy:
    """Rank-then-fuse settings for one aggregator stage (DF-CHIMERA-V2-102).

    Presence of a policy means "rank before you merge". ``kappa`` is how many
    of the scored candidates are handed to the merge prompt; ``model`` is the
    scorer model, and ``None`` means "score with the aggregator stage's own
    model" (the engine resolves a configured ``rank_model`` first).
    """

    kappa: int = 3
    model: str | None = None


@dataclass(slots=True)
class RankedCandidate:
    """One scored candidate from a pre-merge ranking pass.

    ``score`` is ``None`` for a candidate the scorer did not return a number
    for — such candidates sort AFTER every scored one (never silently assumed
    to be good) and the absence travels into the trace as ``null``.
    ``rank`` is 1-based over the full candidate list, ``kept`` says whether
    this candidate's output reached the merge prompt.
    """

    stage_id: str
    model: str
    score: float | None
    rank: int
    kept: bool


@dataclass(slots=True)
class RankPass:
    """The executed scorer pass for one stage (or its recorded failure).

    ``candidates`` is empty and ``error`` set when the pass could not rank
    (upstream failure or an unparseable scorer answer); the caller then merges
    every upstream output exactly as it would have without ranking.
    """

    model: str
    kappa: int
    candidates: list[RankedCandidate] = field(default_factory=list)
    tokens_input: int = 0
    tokens_output: int = 0
    error: str | None = None


#: Heuristic: 1 token ≈ 4 characters. Good enough for prompt-size budgeting
#: without taking a real tokenizer as a dependency.
_CHARS_PER_TOKEN = 4

#: Marker appended to truncated worker outputs so the aggregator model can
#: see it lost tail content (rather than silently misquoting something
#: shorter than reality).
_TRUNCATION_MARKER = "…[truncated to fit prompt budget]"

#: Character cap per candidate in the SCORER prompt. The scorer only has to
#: judge quality, not reproduce the answer, so its prompt is deliberately
#: bounded (a "cheap" pass must stay cheap even with five long worker outputs).
_RANK_CANDIDATE_CHAR_CAP = 6000

#: System prompt for the cheap pre-merge scorer.
_RANK_SYSTEM_PROMPT = (
    "You are a cheap pre-merge scorer for a multi-model deliberation. "
    "You do not answer the user's request. You score candidate answers so a "
    "stronger model can merge only the best ones."
)


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
    raw_properties = schema.get("properties")
    properties: dict[Any, Any] = raw_properties if isinstance(raw_properties, dict) else {}
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


def build_rank_prompt(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
    *,
    candidate_char_cap: int = _RANK_CANDIDATE_CHAR_CAP,
) -> list[dict[str, str]]:
    """Build the message list for the pre-merge SCORER call.

    One bounded call over every upstream candidate: each is shown with its
    stage id, what it was asked to do, and its output (capped per candidate at
    *candidate_char_cap* so the "cheap" pass stays cheap). The requested answer
    is a single JSON object mapping candidate id → 0-10 score, which is the
    shape :func:`parse_rank_scores` reads back.
    """
    blocks: list[str] = []
    for dep in dependencies:
        output = dep.response.text or ""
        if candidate_char_cap > 0:
            output = _truncate_to_char_budget(output, candidate_char_cap)
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        blocks.append(
            f"### candidate {dep.stage_id} (model: {dep.model})\nWas asked to: {asked}\n\nOutput:\n{output}"
        )
    section = "\n\n".join(blocks) if blocks else "(no candidates)"
    ids = ", ".join(dep.stage_id for dep in dependencies)
    user = (
        f"## Original user request\n{user_prompt}\n\n"
        f"## Candidate outputs to score\n{section}\n\n"
        "## Your job\n"
        "Score every candidate from 0 to 10 for how well it answers the "
        "user's request (correctness, completeness, usefulness). Judge the "
        "content, not the length, and do not answer the request yourself.\n"
        f"Score every candidate: {ids}.\n"
        "Reply with exactly one JSON object and nothing else, using the "
        'candidate ids verbatim: {"scores": {"<candidate id>": <number>, ...}}'
    )
    return [
        {"role": "system", "content": _RANK_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _load_json_payload(text: str) -> Any | None:
    """Pull the first JSON value (object or array) out of a model answer.

    Models wrap JSON in prose or code fences; a scorer that answers correctly
    but chattily must still rank. Returns ``None`` when no JSON value can be
    decoded at all.
    """
    cleaned = _strip_fences(text or "").strip()
    if not cleaned:
        return None
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    starts = [pos for pos in (cleaned.find("{"), cleaned.find("[")) if pos != -1]
    if not starts:
        return None
    decoder = json.JSONDecoder()
    try:
        value, _end = decoder.raw_decode(cleaned[min(starts) :])
    except json.JSONDecodeError:
        return None
    return value


def _coerce_score(value: Any) -> float | None:
    """Read a numeric score out of a number, numeric string, or record."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    if isinstance(value, dict):
        for key in ("score", "Score", "value", "rating"):
            if key in value:
                return _coerce_score(value[key])
    return None


def _collect_scores(payload: Any, known: set[str], scores: dict[str, float]) -> None:
    """Walk a decoded scorer answer and collect ``stage_id -> score`` pairs.

    Tolerates the shapes models actually emit: ``{"scores": {...}}``, a bare
    ``{id: score}`` map, a bare ``{id: {"score": n}}`` map, and lists of
    either. Unknown ids are ignored (a hallucinated candidate cannot be
    ranked) and the first numeric score seen for an id wins.
    """
    if isinstance(payload, list):
        for item in payload:
            _collect_scores(item, known, scores)
        return
    if not isinstance(payload, dict):
        return
    scores_field = payload.get("scores")
    if isinstance(scores_field, dict | list):
        _collect_scores(scores_field, known, scores)
    # A single candidate record: {"stage_id"/"id"/"candidate": "worker_2", "score": 7}
    record_id = payload.get("stage_id") or payload.get("id") or payload.get("candidate")
    if isinstance(record_id, str) and record_id in known:
        score = _coerce_score(payload)
        if score is not None and record_id not in scores:
            scores[record_id] = score
    # A map keyed by candidate id.
    for key, value in payload.items():
        if isinstance(key, str) and key in known:
            score = _coerce_score(value)
            if score is not None and key not in scores:
                scores[key] = score


def parse_rank_scores(text: str, stage_ids: Sequence[str]) -> dict[str, float]:
    """Parse a scorer answer into ``{stage_id: score}``.

    JSON first (any of the tolerated shapes), then a per-id ``id: number``
    regex sweep over the raw text for a scorer that answered in prose. A
    candidate with no recoverable score is simply ABSENT from the result —
    callers rank those last rather than inventing a number for them.
    """
    known = set(stage_ids)
    scores: dict[str, float] = {}
    payload = _load_json_payload(text)
    if payload is not None:
        _collect_scores(payload, known, scores)
    if not scores:
        for stage_id in stage_ids:
            match = re.search(
                rf'["\']?{re.escape(stage_id)}["\']?\s*[:=]\s*(-?\d+(?:\.\d+)?)',
                text or "",
            )
            if match is not None:
                scores[stage_id] = float(match.group(1))
    # Ids the model invented can never rank a real candidate.
    return {stage_id: score for stage_id, score in scores.items() if stage_id in known}


def build_merge_prompt(
    stage: Stage,
    dispatch: DispatchResult,
    dependencies: list[StageResult],
    user_prompt: str,
    *,
    max_prompt_tokens: int | None = None,
    output_schema: dict[str, Any] | None = None,
    wire_enforces_schema: bool = True,
    candidates: Sequence[RankedCandidate] = (),
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
    candidates
        Optional pre-merge ranking result (rank-then-fuse,
        DF-CHIMERA-V2-102). When non-empty, each upstream block is annotated
        with its ``rank``/``score`` and — when the ranking kept fewer
        candidates than it scored — a note states how many were omitted. The
        omitted outputs are NOT in *dependencies*, so their content never
        reaches the merge prompt. Empty (default) renders the prompt exactly
        as before.
    """
    instructions = _stage_instructions(stage, dispatch)
    ranked_by_stage = {candidate.stage_id: candidate for candidate in candidates}
    ranked_total = len(candidates)

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

    def _rank_tag(dep: StageResult) -> str:
        candidate = ranked_by_stage.get(dep.stage_id)
        if candidate is None:
            return ""
        score = "n/a" if candidate.score is None else f"{candidate.score:g}"
        return f" [rank {candidate.rank}/{ranked_total}, score {score}]"

    def _shell_for(dep: StageResult, output: str, degraded: bool) -> str:
        asked = _what_worker_was_asked(dep.stage_id, dispatch)
        tag = _rank_tag(dep)
        if dep.stage_id in truncated_outputs:
            degraded_tag = " [DEGRADED]" if degraded else ""
            return (
                f"### {dep.stage_id} (model: {dep.model}){tag}{degraded_tag} [TRUNCATED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output (truncated to fit aggregator prompt budget):\n{output}"
            )
        if degraded:
            return (
                f"### {dep.stage_id} (model: {dep.model}){tag} [DEGRADED]\n"
                f"Was asked to: {asked}\n\n"
                f"Output:\n{output}\n"
                f"Note: This stage failed to produce valid output."
            )
        return f"### {dep.stage_id} (model: {dep.model}){tag}\nWas asked to: {asked}\n\nOutput:\n{output}"

    def _render_prompt() -> tuple[str, str]:
        section = (
            "\n\n".join(_shell_for(d, o, g) for d, o, g in dep_blocks)
            if dep_blocks
            else "(no upstream outputs)"
        )
        omitted = sum(1 for candidate in candidates if not candidate.kept)
        omitted_note = (
            f"\n\nNote: {omitted} lower-ranked candidate(s) were scored and "
            f"omitted from this prompt by pre-merge ranking — the top "
            f"{ranked_total - omitted} of {ranked_total} candidates by score."
            if omitted
            else ""
        )
        kind_label = stage.kind
        system = (
            f"You are the Chimera {kind_label}. "
            "Your job is to produce the single best answer to the user's request "
            "using the upstream outputs and the dispatcher's instructions.\n"
        )
        json_hint = " Respond in valid JSON format." if output_schema is None else ""
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
            f"## Upstream outputs\n{section}{omitted_note}\n\n"
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
            remaining_tokens = max(0, max_prompt_tokens - _estimate_tokens("x" * non_output_chars))
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
                    dep,
                    _truncate_to_char_budget(output, new_len),
                    degraded,
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

    With a :class:`RankPolicy`, :meth:`execute_ranked` first runs ONE cheap
    scorer call over the upstream outputs (rank-then-fuse), sorts them, and
    merges only the top ``kappa``. :meth:`execute` keeps the pre-existing
    signature (no ranking) for every caller that does not opt in.
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
        """Merge the upstream outputs (no pre-merge ranking)."""
        response, _rank_pass, _messages = await self.execute_ranked(
            stage,
            dispatch,
            dependencies,
            user_prompt,
            output_schema=output_schema,
            max_prompt_tokens=max_prompt_tokens,
            max_tokens=max_tokens,
        )
        return response

    async def execute_ranked(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dependencies: list[StageResult],
        user_prompt: str,
        *,
        output_schema: dict[str, Any] | None = None,
        max_prompt_tokens: int | None = None,
        max_tokens: int | None = None,
        rank: RankPolicy | None = None,
    ) -> tuple[GatewayResponse, RankPass | None, list[dict[str, str]]]:
        """Merge the upstream outputs, optionally ranking them first.

        Returns ``(response, rank_pass, messages)``. ``rank_pass`` is ``None``
        when no ranking was attempted (no policy, or no more candidates than
        ``kappa``); otherwise it carries every scored candidate — including
        the ones that were dropped from the merge prompt — plus the scorer's
        token usage so the caller can trace the extra call honestly.
        ``messages`` is the merge prompt that was ACTUALLY sent, so a ranked
        run can record exactly which outputs reached the model.
        """
        rank_pass: RankPass | None = None
        merge_inputs = dependencies
        if rank is not None and len(dependencies) > max(1, rank.kappa):
            rank_pass, merge_inputs = await self._rank_candidates(
                stage,
                dispatch,
                dependencies,
                user_prompt,
                rank,
            )
        response, messages = await self._merge(
            stage,
            dispatch,
            merge_inputs,
            user_prompt,
            output_schema=output_schema,
            max_prompt_tokens=max_prompt_tokens,
            max_tokens=max_tokens,
            rank_pass=rank_pass,
        )
        return response, rank_pass, messages

    async def _rank_candidates(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dependencies: list[StageResult],
        user_prompt: str,
        rank: RankPolicy,
    ) -> tuple[RankPass, list[StageResult]]:
        """Score every upstream output with ONE cheap call; keep the top *kappa*.

        Best-effort by design: a scorer call that fails, or answers in a shape
        no score can be recovered from, returns a failed :class:`RankPass` and
        the FULL candidate list, so the merge degrades to the un-ranked
        behaviour instead of losing a worker's output. The failure is visible
        in the trace (``rank_error``) — never silent.
        """
        scorer_model = rank.model or stage.model
        messages = build_rank_prompt(stage, dispatch, dependencies, user_prompt)
        try:
            response = await self.gateway.complete(scorer_model, messages, temperature=0.0)
        except (GatewayError, BudgetExhaustedError) as exc:
            log.warning(
                "aggregator_rank_failed",
                stage=stage.id,
                model=scorer_model,
                error=str(exc),
            )
            return RankPass(model=scorer_model, kappa=rank.kappa, error=str(exc)), dependencies

        stage_ids = [dep.stage_id for dep in dependencies]
        scores = parse_rank_scores(response.text, stage_ids)
        if not scores:
            log.warning(
                "aggregator_rank_unparsed",
                stage=stage.id,
                model=scorer_model,
                stage_ids=stage_ids,
            )
            return (
                RankPass(
                    model=scorer_model,
                    kappa=rank.kappa,
                    tokens_input=response.tokens_input,
                    tokens_output=response.tokens_output,
                    error="unparseable scorer response",
                ),
                dependencies,
            )

        def _sort_key(pair: tuple[int, StageResult]) -> tuple[int, float, int]:
            index, dep = pair
            score = scores.get(dep.stage_id)
            # Scored candidates first (highest score wins); unscored ones keep
            # their original order behind every scored candidate — an absent
            # score is never treated as a good score.
            if score is None:
                return (1, 0.0, index)
            return (0, -score, index)

        ordered = sorted(enumerate(dependencies), key=_sort_key)
        candidates: list[RankedCandidate] = []
        merge_inputs: list[StageResult] = []
        for position, (_index, dep) in enumerate(ordered, start=1):
            kept = position <= rank.kappa
            candidates.append(
                RankedCandidate(
                    stage_id=dep.stage_id,
                    model=dep.model,
                    score=scores.get(dep.stage_id),
                    rank=position,
                    kept=kept,
                )
            )
            if kept:
                merge_inputs.append(dep)

        log.info(
            "aggregator_rank_applied",
            stage=stage.id,
            model=scorer_model,
            kappa=rank.kappa,
            n_candidates=len(candidates),
            n_kept=len(merge_inputs),
            scores={candidate.stage_id: candidate.score for candidate in candidates},
        )
        return (
            RankPass(
                model=scorer_model,
                kappa=rank.kappa,
                candidates=candidates,
                tokens_input=response.tokens_input,
                tokens_output=response.tokens_output,
            ),
            merge_inputs,
        )

    async def _merge(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dependencies: list[StageResult],
        user_prompt: str,
        *,
        output_schema: dict[str, Any] | None = None,
        max_prompt_tokens: int | None = None,
        max_tokens: int | None = None,
        rank_pass: RankPass | None = None,
    ) -> tuple[GatewayResponse, list[dict[str, str]]]:
        if max_prompt_tokens is None:
            max_prompt_tokens = getattr(
                self.config,
                "max_aggregator_context_tokens",
                None,
            )
        messages = build_merge_prompt(
            stage,
            dispatch,
            dependencies,
            user_prompt,
            max_prompt_tokens=max_prompt_tokens,
            output_schema=output_schema,
            # Only a json_schema-capable provider actually receives the
            # schema (`negotiate_response_format` strips `response_format`
            # for everyone else), so the prompt has to carry the shape
            # wherever the wire cannot.
            wire_enforces_schema=_schema_enforceable_on_wire(
                self.config,
                stage.model,
            ),
            candidates=rank_pass.candidates if rank_pass is not None else (),
        )
        log.info(
            "aggregator_execute",
            stage=stage.id,
            kind=stage.kind,
            model=stage.model,
            n_inputs=len(dependencies),
            structured=output_schema is not None,
            max_prompt_tokens=max_prompt_tokens,
            ranked=rank_pass is not None,
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
        return await self.gateway.complete(stage.model, messages, **kwargs), messages


__all__ = [
    "Aggregator",
    "RankPass",
    "RankPolicy",
    "RankedCandidate",
    "StageResult",
    "build_merge_prompt",
    "build_rank_prompt",
    "parse_rank_scores",
]
