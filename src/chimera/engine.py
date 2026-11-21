"""The formation engine — runs the dispatcher-designed DAG.

Executes stages in dependency waves: all stages whose dependencies are met run
concurrently via :func:`asyncio.gather`. Every call is traced into a
:class:`DeliberationTrace` (prompt, response, tokens, latency, cost).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import time
import uuid
from collections.abc import Callable, Mapping
from typing import Any

import jsonschema
import structlog
from pydantic import BaseModel, Field

from chimera import blocked_models
from chimera.aggregator import Aggregator, RankPass, RankPolicy, StageResult
from chimera.config import (
    ChimeraConfig,
    DeliberationOverrides,
    credentialed_enabled_models,
    model_credential_fingerprint,
    provider_api_key_env,
    provider_credential_resolved,
    resolve_aggregator_fallbacks,
)
from chimera.dispatcher import (
    Dispatcher,
    DispatchOutcome,
    DispatchRepair,
    DispatchResult,
    FormationDAG,
    Stage,
    _repair_formation,
    blocked_catalog_models,
    build_dag_from_dict,
)
from chimera.exceptions import BudgetExhaustedError, LaneUnreachableError, NoHealthyCandidateError
from chimera.gateway import Gateway, GatewayError, GatewayResponse
from chimera.observability import apply_config_observability, get_langfuse

log = structlog.get_logger("chimera.engine")

#: Per-stage wall-clock timeout (seconds). A stage that exceeds this is cancelled
#: and recorded as degraded so one slow worker cannot block the deliberation.
#: This is the code-level fallback — prefer the config ``timeout.per_stage_s``
#: or the per-request ``X-Chimera-Timeout`` header.
DEFAULT_STAGE_TIMEOUT_S: float = 120.0

#: Regex to detect a failure signal in a stage's JSON output.  A stage with
#: ``iterate_on`` triggers re-iteration when its response contains
#: ``"passed": false`` (case-insensitive, allowing whitespace).
_RE_ITERATION_SIGNAL = re.compile(r'"passed"\s*:\s*false\s*[,}]', re.IGNORECASE)


class RankedCandidateSpan(BaseModel):
    """One traced candidate from a rank-then-fuse pre-merge pass.

    ``rank`` is 1-based over every candidate the scorer saw and ``kept`` says
    whether its output reached the merge prompt — a dropped candidate is
    traced, not erased, so a run's ranking decision is auditable after the
    fact (DF-CHIMERA-V2-102). ``score`` is ``None`` when the scorer returned no
    number for that candidate (it is then ranked after every scored one).
    """

    stage_id: str
    model: str
    score: float | None = None
    rank: int
    kept: bool


class AggregatorFallbackAttempt(BaseModel):
    """One entry of the merge fallback chain and what happened to it.

    DF-CHIMERA-V2-120 (measured): the merge was a single point of failure — one
    dead aggregator model (``Insufficient Balance``) discarded three already
    paid worker outputs and the run exited rc=2 with no answer.  The engine now
    walks an ordered fallback chain and records every entry here, so a run's
    substitution is auditable after the fact instead of being inferred from the
    answer text.

    ``status`` is one of:

    * ``served`` — this model produced the merge (exactly one entry per run
      normally carries it). No ``error``/``reason``.
    * ``failed`` — the call was attempted and raised; ``error`` is the upstream
      text and ``error_class`` its shared classification
      (``quota`` / ``credential`` / ``timeout`` ...).
    * ``skipped`` — the entry was NOT called because it provably could not
      help; ``reason`` says why (unknown/disabled model, uncredentialed
      provider, quota-dead account, the failed model itself, or the attempt
      budget).
    """

    model: str
    status: str
    reason: str | None = None
    error: str | None = None
    error_class: str | None = None
    source: str | None = None


class StageSpan(BaseModel):
    """One traced stage execution."""

    stage_id: str
    kind: str
    model: str
    provider: str = ""
    """The provider that actually SERVED this stage's call — the gateway's
    resolved ``effective_provider`` after credential fallbacks — or ``""``
    when no provider route was resolved at all (a degraded stage, a gateway
    stub that carries no attribution, or a dispatcher call that failed and
    returned its ``{}`` fallback).  Never derived from ``model``: a catalog
    id's prefix can name a provider other than the one that served the call
    (QA-CHIMERA-V2-16).  The dispatch span IS a provider call and carries the
    route the gateway resolved for it (CH-GAP-056)."""
    wire_model: str = ""
    """The model id actually sent to that provider (the gateway's wire model
    string), or ``""`` when nothing was sent."""
    api_base: str = ""
    """The base URL the call was sent to, or ``""`` for routes that use the
    provider's own default endpoint."""
    prompt: str
    response: str
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: int = 0
    cost: float = 0.0
    depends_on: list[str] = Field(default_factory=list)
    iteration: int = 1
    """Which attempt this span belongs to (1 for the first pass, 2+ for re-iterations)."""
    started_at: float = 0.0
    """``time.monotonic()`` when the stage began (for wave overlap checks)."""
    ended_at: float = 0.0
    """``time.monotonic()`` when the stage finished."""
    finish_reason: str = ""
    """The finish reason the gateway reported for THIS stage's call, read off
    its ``GatewayResponse`` (``"length"`` when the call hit its ``max_tokens``
    cap, ``"stop"`` on a normal completion, ``""`` when the provider reported
    none — a degraded placeholder or a dispatcher fallback).  The API layer
    surfaces any answer-contributing stage's ``"length"`` as the OpenAI
    response's ``finish_reason`` (DF-CHIMERA-V2-54)."""
    negotiated_format: dict[str, Any] | None = None
    """The response_format negotiation outcome THIS call's gateway recorded
    (``{"requested": <type>, "served": <type-or-None>}`` from
    ``GatewayResponse.metadata["format_negotiation"]``) — present only when
    the provider could not honor the requested format, i.e. the call is less
    constrained than requested (DF-CHIMERA-V2-53). ``None`` for pass-through
    routes, plain calls, and gateways that carry no side-band (test doubles);
    never guessed from the model or provider name."""

    ranked_candidates: list[RankedCandidateSpan] = Field(default_factory=list)
    """Every candidate scored by a rank-then-fuse pre-merge pass
    (DF-CHIMERA-V2-102), in rank order — INCLUDING the ones dropped from the
    merge prompt (``kept: false``). Empty when the stage did no ranking, so
    the field is additive and un-ranked runs serialize exactly as before.

    The span's ``prompt`` is the merge input that was actually sent, i.e. the
    top-``rank_kappa`` candidates only: the two together are the evidence that
    a run ranked five outputs and fed two of them."""
    rank_kappa: int | None = None
    """How many candidates the merge prompt was allowed to keep, or ``None``
    when this stage did not rank."""
    rank_model: str = ""
    """Model that served the scorer call (``""`` when no ranking ran)."""
    rank_tokens_input: int = 0
    rank_tokens_output: int = 0
    """Tokens spent by the scorer call — counted in the run totals (the
    scorer is real provider spend), never folded into this stage's own
    ``tokens_*``."""
    rank_cost: float = 0.0
    """Cost of the scorer call, priced with the same catalog rates as any
    other stage (0.0 when no ranking ran)."""
    rank_error: str | None = None
    """Why the pre-merge ranking did NOT take effect, when it was attempted and
    failed (scorer upstream error / unparseable answer). ``None`` for a
    successful pass and for a stage that never ranked. On a failed pass every
    upstream output still reached the merge prompt — the run degrades to the
    un-ranked behaviour rather than dropping a worker's work."""

    degraded: bool = False
    """True when this span is the engine's failure placeholder rather than a
    real provider call (``_degraded_stage``). No model served a degraded
    stage, which is why ``trace.aggregator_model`` stays ``null`` for one
    (DF-CHIMERA-V2-120)."""
    fallback_attempts: list[AggregatorFallbackAttempt] = Field(default_factory=list)
    """The merge fallback chain this stage walked, in order, with a per-entry
    outcome (``served`` / ``failed`` / ``skipped`` + the reason) — empty for a
    stage that answered on its first model and for worker stages
    (DF-CHIMERA-V2-120). Mirrored at trace level as
    ``trace.aggregator_fallbacks`` for the span that produced the answer."""


#: Constant for the metadata key carrying a lossy format-negotiation outcome.
FORMAT_NEGOTIATION_KEY = "format_negotiation"


def _format_negotiation(response: GatewayResponse) -> dict[str, Any] | None:
    """Read the format-negotiation outcome off *response*'s metadata side-band.

    ``LiteLLMGateway.complete`` stamps a lossy outcome (a downgrade or removal
    of the requested ``response_format``, DF-CHIMERA-V2-53) next to the route
    attribution it already writes. Responses that never went through a
    resolved route — engine-fabricated degraded placeholders, test doubles —
    carry no such key, so this stays ``None``; the absence is meaningful (the
    call's format was honored or none was requested) and is never inferred
    from the model/provider name.
    """
    metadata = response.metadata or {}
    return metadata.get(FORMAT_NEGOTIATION_KEY)


def _route_attribution(response: GatewayResponse) -> tuple[str, str, str]:
    """Read the gateway's resolved-route attribution off *response*.

    ``LiteLLMGateway.complete`` stamps the route it actually resolved onto the
    response's ``metadata`` side-band (``provider`` / ``wire_model`` /
    ``api_base``) — the only place that knows which provider serves a call,
    since a credential fallback (F8 anthropic→openrouter) or a generic
    ``base_url`` provider can serve a catalog id whose prefix names a
    different provider.

    This reads that channel and nothing else: a response that never went
    through a resolved route — an engine-fabricated degraded placeholder, a
    test double — simply has no such keys, so the attribution is empty.  It is
    never guessed from ``response.model`` (QA-CHIMERA-V2-16).
    """
    metadata = response.metadata or {}
    return (
        str(metadata.get("provider") or ""),
        str(metadata.get("wire_model") or ""),
        str(metadata.get("api_base") or ""),
    )


class WorkerFailure(BaseModel):
    """One dropped worker stage — surfaced to the user and the API trace.

    Populated when a stage degrades with an upstream error (gateway failure,
    timeout, budget exhaustion). ``error`` is the upstream failure reason.
    """

    stage_id: str
    model: str
    error: str


class DeliberationTrace(BaseModel):
    """Full trace of a deliberation run."""

    request_id: str
    formation: str
    source: str
    dispatch: StageSpan | None = None
    """The dispatcher's own call span — ``None`` when there was NO dispatcher
    call (PERF-2): an explicit formation (config-defined DAG or a named
    non-auto preset without ``dispatch_prompts``) has its plan synthesized
    deterministically, so there is no call to attribute, and this stays
    ``null`` in the JSON rather than an empty span with fake numbers. A
    ``None`` dispatch contributes nothing to ``total_cost`` / ``total_tokens``
    (they are computed over the stage spans alone in that case)."""
    workers: list[StageSpan] = Field(default_factory=list)
    aggregator: StageSpan | None = None
    stages: list[StageSpan] = Field(default_factory=list)
    answer_stage_id: str = ""
    total_duration_ms: int = 0
    total_cost: float = 0.0
    total_tokens: int = 0
    iteration_count: int = 1
    """How many iteration passes were executed (1 = single pass, 2+ = looped)."""
    dispatch_note: str | None = None
    """Dispatch fallback reason or repair note (e.g. ``"malformed_json"``,
    ``"repaired: added aggregator stage for 2 worker terminals"``). ``None``
    for a clean auto/preset/custom dispatch."""
    dispatch_fallback_reason: str | None = None
    """Why the dispatcher's DESIGN was discarded — ``"malformed_json"`` or
    ``"invalid_dag: <error>"`` — with the stage prompts/instructions falling
    back to templates. ``None`` for a clean or merely repaired dispatch.

    ``source`` names the FORMATION the run used (``auto`` / ``preset`` /
    ``custom`` / ``fallback``), so on a preset or custom DAG the dispatcher's
    own collapse used to be masked by the formation type: the run answered
    normally with no warning in any CLI mode (DF-CHIMERA-V2-34). This field is
    the unambiguous marker, set whenever the dispatcher built its plan through
    ``_fallback_result`` regardless of which formation ran.
    """
    dispatch_repairs: list[DispatchRepair] = Field(default_factory=list)
    """Machine-readable form of the repairs summarised by ``dispatch_note``:
    one :class:`~chimera.dispatcher.DispatchRepair` per structural repair the
    dispatcher applied (kind, action, stage ids, reason). Empty for a clean
    dispatch and for a fallback — a fallback discards the design rather than
    repairing it (DF-CHIMERA-V2-5)."""
    worker_failures: list[WorkerFailure] = Field(default_factory=list)
    """Worker (and other) stages that degraded with an upstream error — the
    machine-readable form of the CLI's dropped-worker warning. Empty when
    every stage succeeded."""
    credential_sources: dict[str, str] = Field(default_factory=dict)
    """Which source satisfied each provider's API key at config-load time
    (DF-CHIMERA-V2-90): provider name → ``process_env`` /
    ``repo_dotenv`` / ``hermes_dotenv_fallback`` / ``missing``.

    A deliberation that only succeeds because a host-level
    ``~/.hermes/.env`` quietly supplied the key used to be
    indistinguishable from a properly-configured one — this map is the
    user-visible answer to "did I configure credentials?".  Additive and
    empty on programmatically built configs (no provenance recorded);
    only labels travel here, never key values."""
    degraded_reasons: list[str] = Field(default_factory=list)
    """Stage truncations that silently degrade the merged answer — one
    ``"<stage_id>: token_limit"`` entry per stage span whose call ended with
    ``finish_reason == "length"`` (its ``max_tokens`` cap cut the output off).
    Empty when no stage was truncated. A truncated worker's fragment still
    reaches the aggregator, so the final answer can read as clean prose while
    silently lacking whatever the truncated stage never produced — this list
    is the machine-readable marker that distinguishes such a merge from a
    good one (DF-CHIMERA-V2-55). The dispatch span never contributes: its
    small structured design call is uncapped and produces no answer text."""

    aggregator_model: str | None = None
    """The model that ACTUALLY served the merge (DF-CHIMERA-V2-120).

    ``None`` when no model served it — the answer stage degraded, or the
    formation has no aggregator/merge/audit stage at all.  When the configured
    aggregator failed and a chain entry answered, this names the fallback, so
    a consumer never has to infer the substitution from the answer text or
    from the stage span's model (which reports the CONFIGURED model on a
    degraded stage).  Healthy runs report their configured aggregator here.
    """
    aggregator_fallbacks: list[AggregatorFallbackAttempt] = Field(default_factory=list)
    """Every entry of the merge fallback chain, in the order the engine walked
    it — including the ones SKIPPED without a call, each with its reason
    (DF-CHIMERA-V2-120). Empty when the configured aggregator answered on the
    first call (nothing to skip) and for a formation with no merge stage."""


class DeliberationResult(BaseModel):
    """The user-facing result of a deliberation."""

    answer: str
    trace: DeliberationTrace
    answer_degraded: bool = False
    """True when the answer did NOT come from the configured lane cleanly.

    Two distinct situations share the flag (DF-CHIMERA-V2-120):

    * the answer stage FAILED and the answer is the engine's failure
      placeholder — the historical meaning; the REST layer answers HTTP 502
      and the CLI exits 2 because there is no usable answer;
    * a fallback model served the merge because the configured aggregator
      failed — the answer IS usable, and
      :attr:`answer_degraded_reason` says so. Consumers must use
      :attr:`answer_usable` (which distinguishes the two) rather than the raw
      flag.
    """
    answer_error: str | None = None
    """Upstream failure reason for a degraded answer, when known."""
    answer_degraded_reason: str | None = None
    """Machine-readable reason for :attr:`answer_degraded` (DF-CHIMERA-V2-120).

    ``"aggregator_substituted"`` — a fallback model produced the merge; the
    answer is usable and :attr:`trace.aggregator_model` names the model that
    served it.

    ``"workers_preserved"`` — no model could serve the merge, but at least one
    worker succeeded; the worker outputs are carried in
    :attr:`worker_outputs` so paid work is never silently discarded, and the
    run still FAILS (no usable answer).

    ``None`` — degraded with no more specific reason available (a bare test
    double, or an answer stage that failed with nothing to preserve).
    """
    worker_outputs: dict[str, str] = Field(default_factory=dict)
    """Worker stage outputs preserved on a run whose merge could not be served
    (DF-CHIMERA-V2-120): ``{stage_id: response_text}`` for every worker that
    SUCCEEDED. Populated only for the ``"workers_preserved"`` case — empty on
    healthy runs and on runs where the merge produced an answer, so existing
    payloads are unchanged. The CLI's ``--json`` payload carries this map at
    top level; it is what the pre-DF-CHIMERA-V2-120 shape threw away."""

    @property
    def answer_usable(self) -> bool:
        """True when ``answer`` is a real product, not a failure placeholder.

        A fallback-served merge is usable (degraded, but the answer is real);
        every other degraded outcome is not. Kept as a computed property so a
        result built without this field (a test double, an older serialized
        payload) can never be mistaken for a usable one: an unknown degraded
        state defaults to NOT usable, which is the fail-closed direction.
        """
        if not self.answer_degraded:
            return True
        return self.answer_degraded_reason == ANSWER_DEGRADED_SUBSTITUTED


#: ``DeliberationResult.answer_degraded_reason`` values (DF-CHIMERA-V2-120).
#: ``"aggregator_substituted"`` marks a USABLE answer produced by the merge
#: fallback chain; ``"workers_preserved"`` marks an unusable merge whose worker
#: outputs are carried in ``worker_outputs``.
ANSWER_DEGRADED_SUBSTITUTED = "aggregator_substituted"
ANSWER_DEGRADED_WORKERS_PRESERVED = "workers_preserved"


def _stage_cost(model: str, config: ChimeraConfig, tokens_input: int, tokens_output: int) -> float:
    try:
        entry = config.get_model(model)
    except KeyError:
        return 0.0
    return entry.cost_rate_input() * tokens_input / 1000.0 + entry.cost_rate_output() * tokens_output / 1000.0


def _last_user_content(messages: list[dict[str, str]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return messages[-1].get("content", "") if messages else ""


def _apply_stage_models(
    dispatch: DispatchResult,
    stage_models: dict[str, str] | None,
    config: ChimeraConfig,
) -> None:
    """Force per-stage models (stage_id → model) onto a dispatch plan.

    * Unknown stage ids raise ``ValueError`` naming the offending id AND the
      valid stage ids (DF-CHIMERA-V2-32) — a typoed id must never silently
      drop its override behind an apparently-normal run.
    * Unknown model names raise ``ValueError`` (validated against the catalog).
    * Worker prompt model entries are kept in sync with the stage model.
    * Applies to ``auto``, ``preset`` and ``custom`` DAGs uniformly. Per-stage
      overrides take precedence over global request overrides.
    """
    if not stage_models:
        return
    stage_ids = set(dispatch.formation.stage_ids())
    for stage_id, model in stage_models.items():
        if stage_id not in stage_ids:
            raise ValueError(
                f"stage_models references unknown stage {stage_id!r}; valid stages: {sorted(stage_ids)}"
            )
        if model not in config.models:
            raise ValueError(f"stage_models references unknown model for stage {stage_id!r}: {model!r}")
        entry = config.models[model]
        if not entry.enabled:
            raise ValueError(
                f"stage_models references disabled model for stage "
                f"{stage_id!r}: {model!r}. "
                f"Set enabled: true in chimera.yaml to re-enable it."
            )
        stage = dispatch.formation.stage(stage_id)
        stage.model = model
        if stage.kind == "worker":
            wp = dispatch.worker_prompt_for(stage_id)
            if wp is not None:
                wp.model = model


def _apply_progressive(
    dispatch: DispatchResult,
    wait_messages: list[str] | None,
    trigger: str | None,
    *,
    progressive: bool = False,
) -> None:
    """Apply progressive prompting settings to all worker stages.

    ``progressive`` (the caller's explicit flag) and ``wait_messages`` are two
    independent inputs and BOTH are honored (CH-GAP-058). Before that fix the
    caller's flag was accepted by the API/MCP surfaces and never read: only a
    non-empty ``wait_messages`` turned progressive prompting on, so
    ``progressive=True`` alone was a silent no-op and ``wait_messages`` alone
    switched a stage on that the caller never asked for.

    Shipped semantics, in full:

    * ``progressive=True`` (with or without ``wait_messages``) turns progressive
      prompting ON for every worker stage — including stages a preset or a
      client DAG declared ``progressive=False``. It never turns it OFF, and
      non-worker stages (aggregator, audit, merge) are never touched.
    * ``wait_messages`` additionally arms the context-feeding path and implies
      ``progressive=True``, because feeding discarded context messages only
      makes sense as progressive prompting (unchanged pre-CH-GAP-058
      behaviour, so callers that only pass ``wait_messages`` are unaffected).
      A caller-supplied list REPLACES whatever the DAG declared on that stage.
    * ``trigger`` overrides the stage's own trigger — the message that requests
      the real output. It is only consumed when the stage ends up with
      non-empty ``wait_messages`` (the engine gate); when a caller supplies
      ``wait_messages`` but no ``trigger``, the stage's own trigger is cleared
      so the stage prompt is used, which is the pre-CH-GAP-058 rule.
    * Neither set → the whole function is a no-op and every stage keeps what
      the config/DAG declared (non-progressive by default).
    """
    if not progressive and not wait_messages:
        return
    messages = list(wait_messages) if wait_messages else None
    for stage in dispatch.formation.stages:
        if stage.kind != "worker":
            continue
        stage.progressive = True
        if messages is not None:
            stage.wait_messages = list(messages)
        if trigger:
            stage.trigger = trigger
        elif messages is not None:
            stage.trigger = ""


def _apply_allowed_models(
    dispatch: DispatchResult,
    allowed_models: list[str] | None,
    config: ChimeraConfig,
) -> None:
    """Remap worker models to only use models from ``allowed_models`` list.

    Runs after dispatch so it applies uniformly to ``auto``, preset, and
    custom DAGs.  Workers whose model falls outside the allowed list are
    remapped to the first entry in ``allowed_models``.
    """
    if not allowed_models:
        return
    allowed_set = set(allowed_models)
    default = allowed_models[0]
    for stage in dispatch.formation.stages:
        if stage.kind == "worker" and stage.model not in allowed_set:
            log.info(
                "engine_allowed_models_remap",
                stage=stage.id,
                original=stage.model,
                remapped=default,
            )
            stage.model = default
            wp = dispatch.worker_prompt_for(stage.id)
            if wp is not None:
                wp.model = default


#: Health-snapshot ``error_class`` meaning "the account behind this provider has
#: no budget left".  The same string the quota block class uses, so the two
#: signals share one vocabulary instead of drifting (DF-CHIMERA-V2-130).
_QUOTA_ERROR_CLASS = blocked_models.REASON_QUOTA


def _health_quota_providers(
    provider_health: Callable[[], Mapping[str, Mapping[str, Any]] | None] | None,
) -> dict[str, str]:
    """Providers the live ``/v1/health`` snapshot reports as quota-exhausted.

    Returns ``{provider: error_text}``.  A missing snapshot (no probe has run
    yet, or the cache entry expired) yields ``{}`` — the engine never invents a
    verdict, and it never probes providers itself (a probe burns tokens; the
    health endpoint owns that job).  A snapshot shaped unexpectedly is logged
    and ignored rather than trusted, so a broken seam degrades to the
    pre-existing behaviour instead of failing a deliberation.
    """
    if provider_health is None:
        return {}
    try:
        snapshot = provider_health()
    except Exception as exc:  # noqa: BLE001 — the seam must never break a run
        log.warning("engine_provider_health_unavailable", error=str(exc)[:200])
        return {}
    if not isinstance(snapshot, Mapping):
        return {}
    # The same set ``/v1/health`` publishes as ``unhealthy_providers``; named
    # identically here so the selection path and the health surface never read
    # as two different concepts (DF-CHIMERA-V2-130).
    unhealthy_providers: dict[str, str] = {}
    for provider, info in snapshot.items():
        if not isinstance(info, Mapping):
            continue
        if info.get("healthy") is False and info.get("error_class") == _QUOTA_ERROR_CLASS:
            unhealthy_providers[str(provider)] = str(
                info.get("error") or info.get("note") or _QUOTA_ERROR_CLASS
            )
    return unhealthy_providers


def _quota_excluded_models(
    config: ChimeraConfig,
    registry: blocked_models.ModelBlockRegistry,
    provider_health: Callable[[], Mapping[str, Mapping[str, Any]] | None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Enabled, credentialed models unusable right now because of quota exhaustion.

    Two independent signals feed one set (DF-CHIMERA-V2-130):

    * the live health snapshot — ``error_class: quota`` for a provider means
      "reachable, authenticated, refusing to serve" (this is the signal the
      selection path used to ignore entirely), and
    * a quota block recorded from a real failed call
      (:data:`chimera.blocked_models.REASON_QUOTA`), which covers the window
      between a failure and the next health probe.

    Quota exhaustion is an ACCOUNT-level condition, so a block or verdict on one
    model covers every model of that provider — otherwise a dead provider with
    five models would be re-selected four more times before the registry caught
    up.  Both signals are TTL-bounded (the block expires; the health cache has
    its own TTL), and this function re-reads them on EVERY call, which is what
    "re-evaluate at run start" means: a long-lived process never serves a stale
    exclusion set.

    Returns ``{model: {"provider", "error_class", "retry_after_s", "detail"}}``
    — the machine-readable attempts list the no-healthy-candidate error needs.
    """
    unhealthy_providers = _health_quota_providers(provider_health)
    details = registry.blocked_detail()
    quota_blocked: dict[str, dict[str, Any]] = {
        model: entry for model, entry in details.items() if entry.get("reason") == _QUOTA_ERROR_CLASS
    }
    blocked_provider_names = {
        config.models[model].provider for model in quota_blocked if model in config.models
    }

    excluded: dict[str, dict[str, Any]] = {}
    for name, entry in config.enabled_models.items():
        if not provider_credential_resolved(config, entry.provider):
            continue
        retry_after_s: float | None = None
        detail = ""
        if entry.provider in unhealthy_providers:
            detail = unhealthy_providers[entry.provider]
        elif name in quota_blocked:
            detail = f"quota block recorded for {name}"
            retry_after_s = quota_blocked[name].get("expires_in_s")
        elif entry.provider in blocked_provider_names:
            for model, blocked in quota_blocked.items():
                if config.models[model].provider == entry.provider:
                    retry_after_s = blocked.get("expires_in_s")
                    break
            detail = f"quota block recorded for provider {entry.provider}"
        else:
            continue
        excluded[name] = {
            "provider": entry.provider,
            "error_class": _QUOTA_ERROR_CLASS,
            "retry_after_s": retry_after_s,
            "detail": detail,
        }
    return excluded


def _healthy_models(
    config: ChimeraConfig,
    excluded: Mapping[str, Any],
) -> list[str]:
    """Enabled, credentialed models that are NOT quota-excluded, in catalog order.

    Catalog order is the config's declaration order, so the "next healthy
    candidate" is deterministic and operator-controllable instead of whichever
    key happens to come first out of a set.
    """
    return [
        name
        for name, entry in config.enabled_models.items()
        if name not in excluded and provider_credential_resolved(config, entry.provider)
    ]


def _quota_fallback_model(
    config: ChimeraConfig,
    excluded: Mapping[str, Any],
    *,
    preferred: str,
    avoid: str | None = None,
    avoid_providers: frozenset[str] = frozenset(),
) -> str | None:
    """The single replacement for a stage whose model is quota-excluded.

    ONE bounded escalation step, exactly like the credential pass: the role's
    configured default when it is healthy, else the first healthy catalog
    model.  ``None`` when nothing healthy exists (the caller then raises the
    machine-readable no-candidate error rather than calling a dead provider).

    *avoid_providers* carries the provider of a model that JUST failed with a
    quota error: quota exhaustion is account-level, so retrying a sibling model
    on the same account is a guaranteed second failure.  It is honoured while
    any other provider remains and dropped only as a last resort (a sibling
    model still beats no attempt at all).
    """

    def _ok(name: str, *, require_credential: bool) -> bool:
        if not name or name == avoid:
            return False
        entry = config.models.get(name)
        if entry is None or not entry.enabled:
            return False
        if name in excluded or entry.provider in avoid_providers:
            return False
        return not (require_credential and not provider_credential_resolved(config, entry.provider))

    # 1. The role's configured default (what the pre-DF-CHIMERA-V2-130 retry
    #    used unconditionally — the credential gate is deliberately NOT applied
    #    here, or a fixture/deployment with no resolvable keys would lose the
    #    retry it had before).
    if _ok(preferred, require_credential=False):
        return preferred
    # 2. Another provider's credentialed model (quota is account-level).
    for name in config.enabled_models:
        if _ok(name, require_credential=True):
            return name
    # 3. Last resort: any enabled catalog model — same provider, unknown
    #    credentials. Preserves the legacy "retry something" behaviour.
    for name in config.enabled_models:
        if _ok(name, require_credential=False):
            return name
    return None


def _apply_quota_blocked_models(
    dispatch: DispatchResult,
    config: ChimeraConfig,
    registry: blocked_models.ModelBlockRegistry,
    provider_health: Callable[[], Mapping[str, Mapping[str, Any]] | None] | None = None,
) -> None:
    """Keep a quota-exhausted provider out of EVERY stage — workers and aggregator.

    The measured defect (DF-CHIMERA-V2-130): ``/v1/health`` truthfully reported
    ``error_class: quota`` while the selection path built its candidate set from
    credential PRESENCE only, so the dead provider was chosen again, every call
    failed, and the run answered 502 — three of four live deliberations.

    This pass runs LAST (after ``stage_models`` / ``allowed_models`` / the
    credential pass), for the same reason the credential pass does: the call
    cannot succeed, so a block outranks an explicit model choice.  Unlike that
    pass it covers every stage KIND — the live failure also lost its aggregator,
    which was a quota-dead ``defaults.default_aggregator``.

    When nothing healthy is left it raises
    :class:`~chimera.exceptions.NoHealthyCandidateError` naming every skipped
    candidate (provider + model + failure class) instead of spending calls on a
    known-dead provider and returning a bare 502.
    """
    excluded = _quota_excluded_models(config, registry, provider_health)
    if not excluded:
        return
    healthy = _healthy_models(config, excluded)
    if not healthy:
        attempts = [
            {"model": model, **{k: v for k, v in entry.items() if k != "detail"}, "detail": entry["detail"]}
            for model, entry in sorted(excluded.items())
        ]
        log.error("engine_no_healthy_candidate", attempts=attempts)
        raise NoHealthyCandidateError(attempts=attempts)

    for stage in dispatch.formation.stages:
        if stage.model not in excluded:
            continue
        preferred = (
            config.defaults.default_worker if stage.kind == "worker" else config.defaults.default_aggregator
        )
        replacement = _quota_fallback_model(config, excluded, preferred=preferred)
        if replacement is None or replacement == stage.model:  # pragma: no cover - guarded above
            continue
        log.warning(
            "engine_quota_blocked_remap",
            stage=stage.id,
            kind=stage.kind,
            original=stage.model,
            remapped=replacement,
            provider=excluded[stage.model]["provider"],
            reason=_QUOTA_ERROR_CLASS,
            msg=(
                "stage model skipped: its provider is out of quota/budget "
                "(insufficient_quota / 402). The block clears on its own after "
                "the provider is topped up; meanwhile the run is served by a "
                "healthy candidate."
            ),
        )
        stage.model = replacement
        wp = dispatch.worker_prompt_for(stage.id)
        if wp is not None:
            wp.model = replacement


def _apply_aggregator_fallbacks(dispatch: DispatchResult, chain: list[str]) -> None:
    """Carry the merge-fallback chain onto every aggregator/merge/audit stage.

    DF-CHIMERA-V2-120: the chain is a DAG-level fact (``defaults`` or the
    formation's override) but it is walked per stage when that stage's own call
    fails, so it travels on the stage objects — same place
    ``_apply_quota_blocked_models`` puts its remapped models, which keeps
    ``_handle_stage_failure`` free of a config lookup and lets a plain
    :class:`~chimera.dispatcher.FormationDAG` behave identically.

    An EMPTY chain is written as an empty list, i.e. "this formation has no
    fallback" is expressed by leaving it empty rather than by omitting the
    attribute — the difference between inheriting the defaults and disabling
    them is resolved earlier, in
    :func:`chimera.config.resolve_aggregator_fallbacks`.
    """
    if not chain:
        return
    for stage in dispatch.formation.stages:
        if stage.kind in {"aggregator", "merge", "audit"} and not stage.aggregator_fallbacks:
            stage.aggregator_fallbacks = list(chain)


#: How many merge-fallback candidates one failed aggregator call may actually
#: CALL (criterion 4 of DF-CHIMERA-V2-120).  Bounded on purpose: candidates that
#: are provably unusable (unknown/disabled model, uncredentialed provider,
#: quota-dead account, the failed model itself) are skipped WITHOUT a call, so
#: this only caps the genuinely-unknown ones and keeps a dead chain to a
#: handful of calls instead of the measured 83-187 s retry tail.
MAX_AGGREGATOR_FALLBACK_ATTEMPTS: int = 4

#: ``AggregatorFallbackAttempt.status`` values.
FALLBACK_SERVED = "served"
FALLBACK_FAILED = "failed"
FALLBACK_SKIPPED = "skipped"


def _credential_remedy(config: ChimeraConfig, provider: str) -> str:
    """The operator-facing hint for a provider with no resolved credential."""
    env = provider_api_key_env(config, provider)
    return f"set {env}" if env else "configure provider credentials"


def _provider_of(config: ChimeraConfig, model: str) -> str | None:
    """The catalog provider behind *model*, or ``None`` for an unknown id."""
    entry = config.models.get(model)
    return entry.provider if entry is not None else None


def _stage_unreachable_blocker(
    config: ChimeraConfig,
    registry: blocked_models.ModelBlockRegistry,
    model: str,
    *,
    credentials_configured: bool,
) -> dict[str, object] | None:
    """The blocker entry for a stage model whose provider provably cannot serve.

    ``None`` means "reachable enough to try" — the caller must never use this to
    refuse a call on a guess.  The credential branch fires only in a deployment
    that resolves SOME credential (``credentials_configured``): with no keys
    anywhere the documented behaviour is one auth error per stage
    (DF-CHIMERA-V2-71), not a pre-emptive refusal.
    """
    entry = config.models.get(model)
    if entry is None:
        # An id outside the catalog is NOT refused here: provider/model strings
        # resolve at the gateway (litellm), so "not in models:" is not proof the
        # call cannot work. Only credentials are provable.
        return None
    if not entry.enabled:
        return None
    if not credentials_configured:
        return None
    env = provider_api_key_env(config, entry.provider)
    if env is None:
        return None  # keyless/local provider — nothing to resolve
    if _credential_block_active(registry, config, model):
        return {
            "provider": entry.provider,
            "model": model,
            "error_class": blocked_models.REASON_CREDENTIAL,
            "remedy": f"the provider rejected its credential in a recent call; set {env}",
        }
    if not provider_credential_resolved(config, entry.provider):
        return {
            "provider": entry.provider,
            "model": model,
            "error_class": blocked_models.REASON_CREDENTIAL,
            "remedy": f"set {env}",
        }
    return None


def _lane_unreachable_blockers(
    config: ChimeraConfig,
    registry: blocked_models.ModelBlockRegistry,
    dispatch: DispatchResult,
    *,
    credentials_configured: bool,
) -> list[dict[str, object]]:
    """Blockers for EVERY stage model in this run's DAG, or ``[]`` if any is fine.

    All-or-nothing on purpose (DF-CHIMERA-V2-120 criterion 4): one reachable
    stage means the run must still be attempted — the workers may well answer
    even if the merge cannot — so the fast-fail only fires when there is
    provably nothing to call.
    """
    blockers: list[dict[str, object]] = []
    for model in dict.fromkeys(stage.model for stage in dispatch.formation.stages):
        blocker = _stage_unreachable_blocker(
            config, registry, model, credentials_configured=credentials_configured
        )
        if blocker is None:
            return []
        blockers.append(blocker)
    return blockers


def _merge_fallback_skip_reason(
    config: ChimeraConfig,
    model: str,
    *,
    registry: blocked_models.ModelBlockRegistry,
    excluded: Mapping[str, Any],
    failed_model: str,
    credentials_configured: bool,
    proven_live: bool = False,
) -> str | None:
    """Why *model* cannot serve the merge, or ``None`` when it can be tried.

    Every branch here is a NO-CALL decision, which is what makes a dead chain
    cheap: the alternative (call the candidate, read a second identical 402)
    is exactly the 83-187 s retry tail the board row measured.  Returning a
    string is not an error path — the caller records it as a ``skipped``
    fallback entry so the operator sees WHY an entry was passed over, which is
    the trace-side half of acceptance criterion 1.
    """
    if model == failed_model:
        return "the configured aggregator itself (its call just failed)"
    entry = config.models.get(model)
    if entry is None:
        return "unknown model (not in the models: catalog)"
    if not entry.enabled:
        return "model disabled in the models: catalog (enabled: false)"
    quota_dead_providers = {str(details.get("provider", "")) for details in excluded.values()}
    if model in excluded or entry.provider in quota_dead_providers:
        return (
            f"provider {entry.provider!r} is out of quota/budget "
            "(insufficient_quota / 402; the block clears when the account is topped up)"
        )
    if not proven_live and _credential_block_active(registry, config, model):
        return (
            f"provider {entry.provider!r} rejected its credential in a recent call "
            f"(authentication error; {_credential_remedy(config, entry.provider)})"
        )
    if credentials_configured and not provider_credential_resolved(config, entry.provider):
        return f"no credential for provider {entry.provider!r} ({_credential_remedy(config, entry.provider)})"
    return None


def _apply_credentialed_worker_models(
    dispatch: DispatchResult,
    config: ChimeraConfig,
    registry: blocked_models.ModelBlockRegistry | None = None,
    provider_health: Callable[[], Mapping[str, Mapping[str, Any]] | None] | None = None,
) -> None:
    """Remap auto-formation worker stages whose provider has no credentials.

    Safety net for the dispatcher's credential-filtered catalog
    (DF-CHIMERA-0906-3): even if the dispatcher emits a model outside the
    filtered catalog (hallucinated name that fuzzy-matches an uncredentialed
    catalog entry), no uncredentialed model reaches a default auto worker
    stage, so the dispatcher prompt and the executed DAG cannot disagree.

    * Runs ONLY for dispatcher-generated auto formations
      (``dispatch.source == "auto"``) when
      ``auto_formation.restrict_to_credentialed_providers`` is on.  Preset
      and custom DAGs are never rewritten by this pass.
    * "Usable" means credentialed AND not quota-exhausted
      (DF-CHIMERA-V2-130): a provider whose balance is empty satisfies the
      credential check while refusing every call, so it must never become the
      default worker of a freshly designed DAG.
    * Remap target: ``defaults.default_worker`` when usable, else the first
      usable enabled model in catalog order.  Aggregator/merge/audit
      stages and the dispatcher model are untouched here — the quota pass
      (:func:`_apply_quota_blocked_models`) and the aggregator retry cover
      them.
    * Explicit request overrides (``worker_model`` / ``stage_models`` /
      ``allowed_models``) are applied AFTER this pass in
      :meth:`Engine.deliberate`, so they remain authoritative.
    * Worker prompt model entries are kept in sync with the stage model.
    * When no model is credentialed at all, nothing is remapped and an
      actionable warning is logged (every provider call will surface a
      real auth error).
    """
    if dispatch.source != "auto":
        return
    if not config.auto_formation.restrict_to_credentialed_providers:
        return
    if registry is None:
        registry = blocked_models.shared_registry
    credentialed = credentialed_enabled_models(config)
    if not credentialed:
        log.warning(
            "engine_auto_no_credentialed_models",
            msg=(
                "No enabled catalog model has resolved provider credentials; "
                "auto worker stages are left as dispatched and provider calls "
                "will fail with auth errors. Set at least one provider API "
                "key (e.g. DEEPSEEK_API_KEY) or set "
                "auto_formation.restrict_to_credentialed_providers: false "
                "in chimera.yaml."
            ),
        )
        return
    excluded = _quota_excluded_models(config, registry, provider_health)
    usable = {name: entry for name, entry in credentialed.items() if name not in excluded}
    if not usable:
        # Every credentialed model is out of quota.  Leave the stages alone and
        # let the quota pass raise the machine-readable no-candidate error —
        # remapping here would only swap one dead provider for another.
        return
    default_worker = config.defaults.default_worker
    fallback = default_worker if default_worker in usable else next(iter(usable))
    for stage in dispatch.formation.stages:
        if stage.kind == "worker" and stage.model not in usable:
            log.info(
                "engine_auto_credentialed_remap",
                stage=stage.id,
                original=stage.model,
                remapped=fallback,
            )
            stage.model = fallback
            wp = dispatch.worker_prompt_for(stage.id)
            if wp is not None:
                wp.model = fallback


def _credential_block_active(
    registry: blocked_models.ModelBlockRegistry,
    config: ChimeraConfig,
    model: str,
) -> bool:
    """True when *model* is credential-blocked against the CURRENT key.

    Positive evidence is required on purpose: the block must be
    credential-class, carry a stored fingerprint, and that fingerprint must
    still match the credential the config resolves today.  A stale block (the
    key was replaced) is not "active" — ``is_blocked`` clears it — and a
    credential block recorded with no fingerprint at all (legacy state file)
    is left alone rather than silently rewriting a configured model
    (DF-CHIMERA-V2-6).
    """
    if registry.block_reason(model) != blocked_models.REASON_CREDENTIAL:
        return False
    stored = registry.credential_fingerprint(model)
    if stored is None:
        return False
    return stored == model_credential_fingerprint(config, model)


def _is_usable_worker_model(
    registry: blocked_models.ModelBlockRegistry,
    config: ChimeraConfig,
    model: str,
) -> bool:
    """A model that may replace a credential-blocked worker stage."""
    entry = config.models.get(model)
    if entry is None or not entry.enabled:
        return False
    if not provider_credential_resolved(config, entry.provider):
        return False
    return not _credential_block_active(registry, config, model)


def _unblocked_worker_fallback(
    registry: blocked_models.ModelBlockRegistry, config: ChimeraConfig
) -> str | None:
    """Best replacement model for a worker whose provider key failed auth.

    Preference order: the configured default worker, the configured default
    aggregator (which just answered successfully in the run that recorded the
    block), then the first credentialed, enabled, unblocked catalog model.
    ``None`` when nothing qualifies — the caller then leaves the stage alone
    and warns instead of guessing.
    """
    for candidate in (config.defaults.default_worker, config.defaults.default_aggregator):
        if _is_usable_worker_model(registry, config, candidate):
            return candidate
    for name in config.enabled_models:
        if _is_usable_worker_model(registry, config, name):
            return name
    return None


def _apply_unblocked_worker_models(
    dispatch: DispatchResult,
    config: ChimeraConfig,
) -> None:
    """Replace worker-stage models whose provider credential failed auth.

    The model block registry (DF-CHIMERA-V2-1) keeps a model that failed a
    guardrail/privacy rejection out of the dispatcher's *catalog* — which only
    helps formations the dispatcher designs (``auto``).  A named preset or an
    explicit ``stage_models`` override names its model directly, so a
    present-but-invalid provider key used to be re-tried on every run for the
    whole block window: every worker call 401s, the run still exits 0, and the
    answer silently degrades to a single model (DF-CHIMERA-V2-6).

    Runs LAST (after ``stage_models`` / ``allowed_models``), so a credential
    block is the one thing that outranks an explicit model choice: the choice
    cannot be honored — the key is known-bad — and burning the call would only
    produce another degraded stage.  It applies only when the block is
    credential-class AND the stored fingerprint still matches the resolved key,
    so replacing the key restores the configured model on the very next run.
    Non-worker stages are untouched (the engine already retries a failed
    aggregator with ``defaults.default_aggregator``).
    """
    # PERF-2: with the dispatcher model call skipped for explicit formations,
    # the catalog freshness sweep that used to run inside
    # ``build_dispatcher_prompt`` (via ``blocked_catalog_models``) would never
    # fire there. Run it here — every run, every formation — so a replaced
    # provider key still clears its stale credential block (the DF-CHIMERA-V2-6
    # self-heal) instead of only when a dispatcher prompt happens to be built.
    blocked_catalog_models(config)
    registry = blocked_models.shared_registry
    blocked_stages = [
        stage
        for stage in dispatch.formation.stages
        if stage.kind == "worker" and _credential_block_active(registry, config, stage.model)
    ]
    if not blocked_stages:
        return
    fallback = _unblocked_worker_fallback(registry, config)
    if fallback is None:
        log.warning(
            "engine_blocked_worker_no_fallback",
            models=sorted({s.model for s in blocked_stages}),
            msg=(
                "worker models are blocked by a rejected provider credential "
                "and no credentialed, unblocked replacement model is "
                "available; every worker call will fail with an auth error "
                "until a valid provider key is set."
            ),
        )
        return
    for stage in blocked_stages:
        if stage.model == fallback:
            continue
        log.warning(
            "engine_blocked_worker_remap",
            stage=stage.id,
            original=stage.model,
            remapped=fallback,
            msg=(
                "worker model blocked: its provider credential was rejected "
                "(auth/401). Set a valid key to restore it."
            ),
        )
        stage.model = fallback
        wp = dispatch.worker_prompt_for(stage.id)
        if wp is not None:
            wp.model = fallback


def _apply_global_model_overrides(
    dispatch: DispatchResult,
    overrides: DeliberationOverrides | None,
    config: ChimeraConfig,
) -> None:
    """Apply request-level worker/aggregator model overrides post-dispatch.

    * ``worker_model`` forces every worker stage (and its WorkerPrompt).
    * ``aggregator_model`` forces every aggregator/merge/audit stage — unless
      ``defaults.lock_aggregator`` is set, in which case the override is
      discarded and the discard is recorded in ``dispatch.dispatch_note``.
    * ``dispatcher_model`` is NOT applied here (it is passed to the
      dispatcher before the DAG exists); when ``defaults.lock_dispatcher``
      discards it, the discard is recorded here because the engine owns the
      lock decision.
    * Per-stage ``stage_models`` (applied after this) take precedence over
      these global overrides.
    * Unknown or disabled models raise ``ValueError`` before any mutation.
    """
    if overrides is None:
        return

    discards: list[str] = []

    apply_worker = overrides.worker_model
    apply_aggregator: str | None = None
    if overrides.aggregator_model:
        if config.defaults.lock_aggregator:
            discards.append(
                f"override discarded: aggregator_model={overrides.aggregator_model!r} "
                f"ignored (lock_aggregator=true)"
            )
        else:
            apply_aggregator = overrides.aggregator_model
    if overrides.dispatcher_model and config.defaults.lock_dispatcher:
        discards.append(
            f"override discarded: dispatcher_model={overrides.dispatcher_model!r} "
            f"ignored (lock_dispatcher=true)"
        )

    # Validate everything that will be applied BEFORE mutating the DAG.
    for field, model in (
        ("worker_model", apply_worker),
        ("aggregator_model", apply_aggregator),
    ):
        if model is None:
            continue
        if model not in config.models:
            raise ValueError(f"{field} references unknown model {model!r}")
        if not config.models[model].enabled:
            raise ValueError(
                f"{field} references disabled model {model!r}. "
                f"Set enabled: true in chimera.yaml to re-enable it."
            )

    if apply_worker is not None:
        for stage in dispatch.formation.stages:
            if stage.kind == "worker":
                stage.model = apply_worker
                wp = dispatch.worker_prompt_for(stage.id)
                if wp is not None:
                    wp.model = apply_worker

    if apply_aggregator is not None:
        for stage in dispatch.formation.stages:
            if stage.kind in {"aggregator", "merge", "audit"}:
                stage.model = apply_aggregator

    if discards:
        note = "; ".join(discards)
        dispatch.dispatch_note = f"{dispatch.dispatch_note}; {note}" if dispatch.dispatch_note else note


class Engine:
    """Runs the full pipeline: dispatcher → workers → aggregator → (merge/audit).

    On construction the config is deep-copied into an immutable snapshot.
    All in-flight requests read from the snapshot, not the caller's live
    object, so configuration is stable for the lifetime of the Engine instance.

    Mutation checks on the caller's original config object are logged as
    warnings so operators know when a change they made won't take effect.
    """

    #: Fast checksum of struct fields to detect external mutations.
    _CONFIG_CHECK_FIELDS = (
        "defaults.dispatcher",
        "defaults.default_worker",
        "defaults.default_aggregator",
        "defaults.lock_dispatcher",
        "defaults.lock_aggregator",
        "models",
        "formations",
        "providers",
        "api_keys",
    )

    def __init__(
        self,
        config: ChimeraConfig,
        gateway: Gateway,
        *,
        provider_health: Callable[[], Mapping[str, Mapping[str, Any]] | None] | None = None,
    ) -> None:
        """Build an engine over *config* and *gateway*.

        *provider_health* is an optional zero-arg callable returning the
        provider-health snapshot (``{provider: {"healthy": bool,
        "error_class": str, ...}}``) — the API layer passes the
        ``/v1/health`` probe cache's read-through getter.  Model selection
        consults it on EVERY deliberation to skip providers that are out of
        quota (DF-CHIMERA-V2-130).  ``None`` (the default, used by the CLI/MCP
        and by tests) means "no live snapshot": selection then relies only on
        quota blocks recorded from real failed calls.  The seam never raises
        into a run — a broken callable is logged and treated as no signal.
        """
        # DF-CHIMERA-V2-113: apply the config's observability (level + sink)
        # so the in-process library path honours observability.log_level /
        # use_stdout — the CLI/API/MCP surfaces configure logging explicitly
        # before building an Engine, and their force_stderr pins win over this
        # apply (see apply_config_observability). Idempotent via the
        # (stream, level) once-guard in configure_logging.
        apply_config_observability(config.observability)
        self._config_original = config
        self._config = config.model_copy(deep=True)
        self._config_checksum = self._compute_config_checksum(self._config_original)
        self.gateway = gateway
        #: Live provider-health snapshot seam (see the class docstring above).
        self._provider_health = provider_health
        self.dispatcher = Dispatcher(self._config, gateway)
        self.aggregator = Aggregator(self._config, gateway)
        # Awaitable tasks spawned by the stage observer; drained at the end of
        # each deliberate() so a fire-and-forget observer can never outlive the
        # request or leak an un-retrieved exception into the task machinery.
        self._observer_tasks: list[asyncio.Task[None]] = []

    @property
    def config(self) -> ChimeraConfig:
        """The frozen config snapshot, safe from external mutation."""
        return self._config

    # ------------------------------------------------------------------ #
    # Config mutation detection
    # ------------------------------------------------------------------ #

    @staticmethod
    def _compute_config_checksum(cfg: ChimeraConfig) -> int:
        """Compute a fast structural checksum of key config fields.

        Pydantic model_dump with sort_keys=True produces a stable string
        that changes when any nested field is mutated.
        """
        raw = cfg.model_dump(mode="python", exclude={"observability", "server"})
        return hash(json.dumps(raw, sort_keys=True, default=str))

    def _check_config_mutation(self) -> None:
        """Log a warning if the caller's original config was mutated since init."""
        current = self._compute_config_checksum(self._config_original)
        if current != self._config_checksum:
            log.warning(
                "config_mutated_after_snapshot",
                msg=(
                    "The ChimeraConfig object passed to Engine() has been mutated "
                    "since the Engine was constructed. In-flight requests use the "
                    "frozen snapshot, so external mutations will NOT take effect "
                    "until a new Engine instance is created."
                ),
            )

    # ------------------------------------------------------------------ #
    # Stage observer plumbing (DF-CHIMERA-V2-18)
    # ------------------------------------------------------------------ #

    def _notify_stage(
        self,
        observer: Callable[[dict[str, Any]], Any] | None,
        payload: dict[str, Any],
    ) -> None:
        """Deliver a stage event to *observer* without ever breaking the run.

        The observer is a best-effort debug/observability hook: any exception
        it raises is logged and swallowed, and the deliberation continues.
        A sync callable runs inline; an awaitable return is scheduled on the
        running loop as a task (so a slow observer never blocks a stage) and
        recorded for the ``deliberate`` epilogue to drain.
        """
        if observer is None:
            return
        try:
            outcome = observer(payload)
        except Exception:  # noqa: BLE001 — the hook must never break the run
            log.warning("stage_observer_error", stage=payload.get("stage"), phase=payload.get("phase"))
            return
        if inspect.isawaitable(outcome):
            task = asyncio.ensure_future(outcome)
            self._observer_tasks.append(task)

    async def _drain_observer_tasks(self) -> None:
        """Await and clear observer tasks spawned during this deliberation."""
        tasks, self._observer_tasks = self._observer_tasks, []
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — observer failures never break the run
                log.warning("stage_observer_task_error")

    async def deliberate(
        self,
        user_prompt: str,
        formation: str = "auto",
        overrides: DeliberationOverrides | None = None,
        *,
        output_schema: dict[str, Any] | None = None,
        dag: dict[str, Any] | None = None,
        allow_custom_dag: bool = False,
        stage_observer: Callable[[dict[str, Any]], Any] | None = None,
    ) -> DeliberationResult:
        """Run the full deliberation pipeline and return the merged answer + trace.

        Args:
            user_prompt: The user's query.
            formation: Formation name or 'auto'.
            overrides: Request-level model overrides (allowed/disallowed/force models,
                per-stage model overrides via ``stage_models``).
            output_schema: Optional JSON Schema the final answer must conform to.
                If omitted, the dispatcher provides one. If the client provides one,
                it overrides the dispatcher's.
            dag: Optional client-defined DAG definition (a mapping with ``stages``
                and ``edges``). Requires ``allow_custom_dag=True``; otherwise a
                ``ValueError`` is raised. Since PERF-2 the dispatcher model call
                is skipped entirely for an explicit structure: the plan is
                synthesized deterministically (templated worker prompts,
                aggregator defaults) and ``trace.dispatch`` is None. A config
                preset with ``dispatch_prompts: true`` named as ``formation``
                opts back into the dispatcher-authored fill-in pass.
            allow_custom_dag: Must be True for ``dag`` to be accepted.
            stage_observer: Optional per-call callback invoked as
                ``observer(payload_dict)`` when a worker/aggregator/merge/audit
                stage starts and finishes, so callers (e.g. the web SSE layer)
                can stream live progress. Payloads carry ``phase``
                (``started``/``completed``), ``stage``, ``kind``, and — on
                completion — ``model``, ``tokens_input``/``tokens_output``,
                ``latency_ms``, ``cost``, ``degraded``, and ``iteration``.
                May be sync or async; any exception it raises is logged and
                swallowed. Defaults to None (zero behaviour change for the
                REST/CLI/MCP callers).
        """
        request_id = uuid.uuid4().hex[:16]
        structlog.contextvars.bind_contextvars(request_id=request_id, formation=formation)
        started = time.monotonic()

        # Warn if the caller's original config has been mutated since Engine init.
        self._check_config_mutation()

        custom_formation = self._resolve_custom_dag(dag, allow_custom_dag)

        # Request-level dispatcher_model override — honored unless the config
        # locks the dispatcher role (lock_dispatcher=true discards it; the
        # discard is recorded in the trace by _apply_global_model_overrides).
        disp_override = (
            overrides.dispatcher_model
            if (overrides and overrides.dispatcher_model and not self.config.defaults.lock_dispatcher)
            else None
        )
        outcome = await self.dispatcher.dispatch(
            user_prompt,
            formation,
            custom_dag=custom_formation,
            model_override=disp_override,
        )
        # PERF-2: an explicit formation (config DAG / named non-auto preset)
        # is synthesized without a dispatcher model call; there is no call to
        # attribute, so no dispatch span is fabricated for it and the trace's
        # ``dispatch`` stays None.
        dispatch_span = None if outcome.skipped else self._build_dispatch_span(outcome, formation)

        # CH-GAP-044: engine-side repair safety net. The dispatcher sometimes
        # emits edges referencing an aggregator/merge stage it omitted from
        # the stages list (e.g. edges [[worker_1, aggregator],
        # [worker_2, aggregator]] with a worker-only stages list). Without a
        # repair the engine would silently degrade to the generic 1-worker
        # fallback (trace.source=fallback, invisible to the user). The parse
        # path repairs this already; this second pass is idempotent and
        # guarantees any dispatcher-produced DAG reaching the engine is
        # structurally sound, so a phantom-edge DAG can never collapse or
        # crash answer selection. Runs BEFORE model overrides so an
        # aggregator_model override also applies to an injected stage.
        _repair_formation(outcome.result, self.config)

        # DF-CHIMERA-0906-3: credential-derived safety net for default auto
        # formations. Runs BEFORE the explicit request overrides below so
        # allowed_models / worker_model / stage_models remain authoritative,
        # and only touches dispatcher-generated auto DAGs (presets and
        # custom DAGs keep their configured structure).  DF-CHIMERA-V2-130:
        # "usable" here also excludes quota-exhausted providers.
        _apply_credentialed_worker_models(
            outcome.result,
            self.config,
            blocked_models.shared_registry,
            self._provider_health,
        )

        # Global request-level overrides (worker/aggregator models). Config
        # locks (defaults.lock_aggregator / lock_dispatcher) take precedence:
        # a locked role keeps its configured default and the discarded
        # override is recorded in the trace via dispatch_note.
        _apply_global_model_overrides(outcome.result, overrides, self.config)

        # Apply per-stage model overrides (Feature 2). Unknown stages and
        # unknown/disabled models alike raise ValueError (DF-CHIMERA-V2-32).
        # Done after dispatch so it applies to auto, preset, and custom DAGs
        # alike.
        stage_models = overrides.stage_models if overrides else None
        _apply_stage_models(outcome.result, stage_models, self.config)
        if overrides:
            _apply_allowed_models(outcome.result, overrides.allowed_models, self.config)
            # CH-GAP-058: pass the caller's explicit ``progressive`` flag too —
            # it used to be dropped here (only ``wait_messages`` was read), so
            # ``progressive=True`` alone was a silent no-op.
            _apply_progressive(
                outcome.result,
                overrides.wait_messages,
                overrides.trigger,
                progressive=overrides.progressive,
            )

        # DF-CHIMERA-V2-6: a model whose provider credential was rejected
        # (present-but-invalid key → 401) is durably blocked, so it must not
        # reach a worker stage again — not even when a preset or an explicit
        # stage_models override names it. Runs last so the block outranks the
        # explicit choice; self-clears when the key is replaced.
        _apply_unblocked_worker_models(outcome.result, self.config)

        # DF-CHIMERA-V2-130: a provider that answered "insufficient_quota" is
        # just as unusable as one with a bad key, but the registry is not the
        # only signal — the live /v1/health snapshot is consulted too, on EVERY
        # run (both are TTL-bounded, so neither can go stale inside a long-lived
        # process).  This runs LAST, after every explicit override, for the same
        # reason the credential pass does: the call cannot succeed, so it
        # outranks the choice.  It covers worker AND aggregator/merge/audit
        # stages — the measured failure lost its aggregator to the same dead
        # provider.  Raises NoHealthyCandidateError when nothing healthy is
        # left, naming every skipped candidate instead of answering a bare 502.
        _apply_quota_blocked_models(
            outcome.result,
            self.config,
            blocked_models.shared_registry,
            self._provider_health,
        )

        # DF-CHIMERA-V2-120: the ordered merge-fallback chain, carried on the
        # merge stage(s) so a failed aggregator call can walk it.  Resolved
        # AFTER every model choice, so the chain reflects the models this run
        # can actually reach (an entry a pass above already abandoned is
        # recorded as skipped, never silently re-tried).  A named formation's
        # own list REPLACES the defaults; an explicit empty list switches the
        # chain off for that formation; unset inherits the defaults.
        _apply_aggregator_fallbacks(
            outcome.result,
            resolve_aggregator_fallbacks(self.config, formation),
        )

        # DF-CHIMERA-V2-120 criterion 4: if NO stage in this run can reach its
        # provider (no credential in a deployment that resolves credentials
        # elsewhere, a provider that already rejected its key, or an
        # unknown/disabled model), say so NOW. The measured failure spent
        # 83-187 s of provider retries to learn exactly this and then exited
        # rc=2 with nothing; there is nothing to bill or to wait for, so the
        # actionable line (provider + the env var to set) is the whole answer.
        # One reachable stage means the run proceeds — the workers may answer
        # even if the merge cannot.
        credentials_configured = any(
            provider_credential_resolved(self.config, entry.provider)
            for entry in self.config.enabled_models.values()
        )
        blockers = _lane_unreachable_blockers(
            self.config,
            blocked_models.shared_registry,
            outcome.result,
            credentials_configured=credentials_configured,
        )
        if blockers:
            log.error("engine_lane_unreachable", attempts=blockers)
            raise LaneUnreachableError(blockers)

        log.info(
            "engine_dispatched",
            source=outcome.result.source,
            stages=outcome.result.formation.stage_ids(),
        )

        # Client-provided schema wins; dispatcher's is the fallback.
        effective_schema = (
            output_schema or (overrides.output_schema if overrides else None) or outcome.result.output_schema
        )

        # DF-CHIMERA-V2-102: rank-then-fuse. A formation that sets
        # ``rank: true`` ranks its upstream outputs before the merge; every
        # other formation gets ``None`` and merges exactly as before.
        rank_policy = self._resolve_rank_policy(formation)

        stage_spans, stage_results = await self._run_dag(
            outcome.result,
            user_prompt,
            request_id,
            effective_schema,
            timeout_total_s=overrides.timeout_total_s if overrides else None,
            timeout_per_stage_s=overrides.timeout_per_stage_s if overrides else None,
            max_tokens=overrides.max_tokens if overrides else None,
            stage_observer=stage_observer,
            rank=rank_policy,
        )

        # Extract iteration count from the results sentinel (stored by _run_dag).
        # ``stage_results`` is typed for stage outputs, so the int sentinel is
        # narrowed explicitly rather than cast away.
        sentinel = stage_results.pop("_iteration_count", 1)
        iteration_count: int = sentinel if isinstance(sentinel, int) else 1

        answer, answer_stage_id = self._select_answer(outcome.result.formation, stage_results)
        # Drain any tasks spawned by an async stage observer before returning,
        # so none of them outlive the request or leak an unretrieved exception.
        await self._drain_observer_tasks()
        # Strip a wrapping markdown code fence BEFORE envelope unwrap so a
        # fenced {"answer": ...} envelope still unwraps correctly.
        answer = self._strip_final_answer_fences(answer)
        answer = self._maybe_unwrap_envelope(answer)
        answer_stage = stage_results.get(answer_stage_id)
        worker_failures = self._collect_worker_failures(stage_results, self.config)
        trace = self._assemble_trace(
            request_id=request_id,
            formation=formation,
            dispatch=outcome.result,
            dispatch_span=dispatch_span,
            stage_spans=stage_spans,
            answer_stage_id=answer_stage_id,
            started=started,
            iteration_count=iteration_count,
            worker_failures=worker_failures,
        )
        _maybe_langfuse(trace, user_prompt)
        structlog.contextvars.unbind_contextvars("request_id", "formation")
        answer_degraded = answer_stage.degraded if answer_stage is not None else False
        answer_error = (
            answer_stage.response.metadata.get("error")
            if answer_stage is not None and answer_degraded
            else None
        )
        # DF-CHIMERA-V2-120: two different situations must not be conflated.
        # (a) A fallback SERVED the merge — the answer is real and usable, and
        #     the substitution is described in ``answer_degraded_reason`` /
        #     ``trace.aggregator_model``; the run exits 0.
        # (b) No model served it — the answer is the failure placeholder. When
        #     workers succeeded, their paid output is preserved on the result
        #     instead of being thrown away with the error.
        answer_degraded_reason: str | None = None
        worker_outputs: dict[str, str] = {}
        answer_span = stage_spans.get(answer_stage_id) if answer_stage_id is not None else None
        fallback_served_the_answer = answer_span is not None and any(
            entry.status == FALLBACK_SERVED for entry in answer_span.fallback_attempts
        )
        if fallback_served_the_answer:
            answer_degraded = True
            answer_degraded_reason = ANSWER_DEGRADED_SUBSTITUTED
        elif answer_degraded:
            worker_outputs = self._preserved_worker_outputs(stage_spans, stage_results)
            if worker_outputs:
                answer_degraded_reason = ANSWER_DEGRADED_WORKERS_PRESERVED
        return DeliberationResult(
            answer=answer,
            trace=trace,
            answer_degraded=answer_degraded,
            answer_error=answer_error,
            answer_degraded_reason=answer_degraded_reason,
            worker_outputs=worker_outputs,
        )

    @staticmethod
    def _preserved_worker_outputs(
        stage_spans: Mapping[str, StageSpan],
        stage_results: Mapping[str, StageResult],
    ) -> dict[str, str]:
        """The worker outputs a failed merge must not discard (DF-CHIMERA-V2-120).

        Measured defect: three workers had answered (and been paid for) while
        the single aggregator model died, and rc=2 returned nothing at all.  A
        run whose merge cannot be served now carries every SUCCEEDED worker's
        text on the ``--json`` payload, so the work is recoverable even though
        the run still fails (there is no merged answer, and pretending
        otherwise would be worse).

        Only real worker output qualifies: a degraded worker produced no text
        of its own, and the dispatch/aggregator stages are not worker work.
        """
        preserved: dict[str, str] = {}
        for stage_id, span in stage_spans.items():
            if span.kind != "worker" or span.degraded:
                continue
            result = stage_results.get(stage_id)
            text = result.response.text.strip() if result is not None else span.response.strip()
            if text:
                preserved[stage_id] = text
        return preserved

    def _resolve_custom_dag(
        self,
        dag: dict[str, Any] | None,
        allow_custom_dag: bool,
    ) -> FormationDAG | None:
        """Validate and build a client-defined DAG, or return None.

        Raises ``ValueError`` if a DAG was supplied without opting in, or if the
        DAG fails validation (unknown model, cycle, missing worker/aggregator, ...).
        """
        if dag is None:
            return None
        if not allow_custom_dag:
            raise ValueError("Custom DAG requires allow_custom_dag=True")
        return build_dag_from_dict(dag, self.config)

    def _resolve_rank_policy(self, formation: str) -> RankPolicy | None:
        """Build the rank-then-fuse policy for *formation*, or ``None``.

        Only a named formation preset can carry the flag (``rank: true``); the
        ``auto`` formation and client-supplied DAGs have no preset to read it
        from and therefore never rank. The scorer model is the preset's
        ``rank_model`` when it resolves to a live catalog entry, else the
        aggregator stage's own model — an unknown/disabled scorer must degrade
        to "score with the stage model", never fail the deliberation.
        """
        preset = self.config.formations.get(formation)
        if preset is None or not preset.rank:
            return None

        scorer_model: str | None = None
        if preset.rank_model:
            resolved = self.config.resolve_model_alias(preset.rank_model)
            entry = self.config.models.get(resolved)
            if entry is None or not entry.enabled:
                log.warning(
                    "rank_model_unusable",
                    formation=formation,
                    rank_model=preset.rank_model,
                    resolved=resolved,
                    fallback="aggregator stage model",
                )
            else:
                scorer_model = resolved
        return RankPolicy(kappa=preset.kappa, model=scorer_model)

    # ------------------------------------------------------------------ #
    # DAG execution
    # ------------------------------------------------------------------ #

    async def _run_dag(
        self,
        dispatch: DispatchResult,
        user_prompt: str,
        request_id: str,
        output_schema: dict[str, Any] | None = None,
        *,
        timeout_total_s: float | None = None,
        timeout_per_stage_s: float | None = None,
        max_tokens: int | None = None,
        stage_observer: Callable[[dict[str, Any]], Any] | None = None,
        rank: RankPolicy | None = None,
    ) -> tuple[dict[str, StageSpan], dict[str, StageResult]]:
        dag = dispatch.formation
        topo = dag.topo_order()
        spans: dict[str, StageSpan] = {}
        results: dict[str, StageResult] = {}

        #: Tracks how many times each ``iterate_on`` trigger stage has fired.
        iteration_counts: dict[str, int] = {}
        #: Accumulated feedback text for each re-run worker stage.
        feedback_map: dict[str, str] = {}
        #: Which iteration pass the overall DAG execution is on (1 = first).
        iteration_pass: int = 1

        remaining = list(topo)
        while remaining:
            ready = [s for s in remaining if all(d in results for d in s.depends_on)]
            if not ready:
                raise RuntimeError("DAG has unresolvable dependencies")
            if len(ready) > 1:
                log.info(
                    "engine_wave_parallel",
                    stages=[s.id for s in ready],
                    wave_size=len(ready),
                )
            # Explicit create_task so independent stages start immediately and
            # truly overlap (gather on bare coroutines is equivalent, but
            # create_task makes concurrency intent unmistakable).
            tasks = [
                asyncio.create_task(
                    self._execute_stage(
                        s,
                        dispatch,
                        results,
                        user_prompt,
                        output_schema,
                        timeout_total_s=timeout_total_s,
                        timeout_per_stage_s=timeout_per_stage_s,
                        max_tokens=max_tokens,
                        iteration_feedback=feedback_map.get(s.id),
                        stage_observer=stage_observer,
                        rank=rank,
                    )
                )
                for s in ready
            ]
            outcomes = await asyncio.gather(*tasks)
            for stage, (result, span) in zip(ready, outcomes, strict=False):
                span.iteration = iteration_counts.get(stage.id, 0) + 1
                results[stage.id] = result
                spans[stage.id] = span

                self._notify_stage(
                    stage_observer,
                    {
                        "phase": "completed",
                        "stage": stage.id,
                        "kind": stage.kind,
                        "model": span.model,
                        "tokens_input": span.tokens_input,
                        "tokens_output": span.tokens_output,
                        "latency_ms": span.latency_ms,
                        "cost": span.cost,
                        "degraded": result.degraded,
                        "iteration": span.iteration,
                    },
                )

                # ── Schema extraction from STRUCTURE stages ──────────
                if not output_schema and stage.kind == "worker":
                    extracted = self._extract_output_schema(span.response)
                    if extracted is not None:
                        output_schema = extracted
                        log.info(
                            "engine_schema_extracted",
                            stage=stage.id,
                            schema_keys=list(extracted.keys()),
                        )

                log.info(
                    "engine_stage_done",
                    stage=stage.id,
                    kind=stage.kind,
                    model=span.model,
                    latency_ms=span.latency_ms,
                    tokens=span.tokens_input + span.tokens_output,
                    started_at=span.started_at,
                    ended_at=span.ended_at,
                )
            remaining = [s for s in remaining if s not in ready]

            # ── Iteration loop check ──────────────────────────────────
            # After a wave completes, check whether any finished stage's
            # output signals failure and should trigger re-iteration of its
            # ``iterate_on`` targets.
            iteration_triggered = False
            for stage in ready:
                if not stage.iterate_on:
                    continue
                stage_span = spans.get(stage.id)
                if stage_span is None or not self._check_iteration_needed(stage, stage_span):
                    continue
                count = iteration_counts.get(stage.id, 0)
                if count >= stage.iteration_limit:
                    log.info(
                        "engine_iteration_limit_reached",
                        stage=stage.id,
                        limit=stage.iteration_limit,
                    )
                    continue
                # ── Fire re-iteration ──
                iteration_counts[stage.id] = count + 1
                iteration_pass += 1
                to_rerun: set[str] = set(stage.iterate_on)

                # Collect all downstream stages that depend on the re-run targets
                # so they are also cleared and re-executed.
                for s in topo:
                    if s.id in to_rerun:
                        continue
                    if any(d in to_rerun for d in s.depends_on):
                        to_rerun.add(s.id)
                # The trigger stage must also be re-run: it needs to evaluate
                # the new output from the re-run workers.  Clearing its
                # result puts it back in ``remaining``.
                to_rerun.add(stage.id)
                # Prepare feedback for re-run workers.
                for sid in stage.iterate_on:
                    feedback_map[sid] = self._collect_feedback(
                        stage,
                        dispatch,
                        results,
                        spans,
                    )
                    log.info(
                        "engine_iteration_feedback",
                        trigger=stage.id,
                        target=sid,
                        attempt=iteration_counts[stage.id],
                    )

                # Clear stale results so the DAG re-executes from the
                # re-run stages forward.
                for sid in to_rerun:
                    results.pop(sid, None)
                    spans.pop(sid, None)

                remaining = [s for s in topo if s.id not in results]
                iteration_triggered = True
                break

            if iteration_triggered:
                continue  # re-enter the while loop with remaining rebuilt

        # Stamp the overall iteration count on the results dict for
        # trace assembly to pick up.
        results["_iteration_count"] = iteration_pass  # type: ignore[assignment]
        return spans, results

    async def _execute_stage(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        results: dict[str, StageResult],
        user_prompt: str,
        output_schema: dict[str, Any] | None = None,
        *,
        timeout_total_s: float | None = None,
        timeout_per_stage_s: float | None = None,
        max_tokens: int | None = None,
        iteration_feedback: str | None = None,
        stage_observer: Callable[[dict[str, Any]], Any] | None = None,
        rank: RankPolicy | None = None,
    ) -> tuple[StageResult, StageSpan]:
        dep_results = [results[d] for d in stage.depends_on if d in results]

        # Resolve per-stage timeout: request → config → code default
        cfg_timeout = self._config.timeout
        per_stage = timeout_per_stage_s if timeout_per_stage_s is not None else cfg_timeout.per_stage_s
        # Clamp per-stage to total if total is set
        if timeout_total_s is not None and timeout_total_s > 0:
            per_stage = min(per_stage, timeout_total_s) if per_stage > 0 else timeout_total_s
        # ``None`` means "no per-stage timeout" for the call sites below, which is
        # a different state from a non-positive configured limit.
        stage_timeout: float | None = None if per_stage <= 0 else per_stage

        # DF-CHIMERA-V2-18: the web layer's live DAG needs stage progress DURING
        # the run, so this fires before the model call is awaited. Best-effort:
        # _notify_stage swallows observer failures, and no observer is attached
        # on the REST/CLI/MCP paths (the default), so this is a no-op there.
        self._notify_stage(
            stage_observer,
            {"phase": "started", "stage": stage.id, "kind": stage.kind, "model": stage.model},
        )
        start = time.monotonic()
        messages: list[dict[str, str]] = []
        rank_pass: RankPass | None = None
        try:
            messages, response, rank_pass = await asyncio.wait_for(
                self._call_stage(
                    stage,
                    dispatch,
                    dep_results,
                    user_prompt,
                    output_schema,
                    iteration_feedback=iteration_feedback,
                    max_tokens=max_tokens,
                    rank=rank,
                ),
                timeout=stage_timeout,
            )
        except TimeoutError:
            latency_ms = int((time.monotonic() - start) * 1000)
            log.warning(
                "engine_stage_timeout",
                stage=stage.id,
                model=stage.model,
                timeout_s=stage_timeout or 0,
            )
            return self._degraded_stage(
                stage,
                GatewayError(f"timed out after {stage_timeout or 0:.0f}s"),
                [],
                latency_ms,
                started_at=start,
            )
        except (GatewayError, BudgetExhaustedError) as exc:
            return await self._handle_stage_failure(
                stage,
                dispatch,
                dep_results,
                user_prompt,
                output_schema,
                exc,
                start,
                rank=rank,
                run_results=results,
            )

        return self._build_stage_result(
            stage,
            response,
            messages,
            start,
            user_prompt,
            dispatch,
            dep_results,
            rank_pass=rank_pass,
        )

    async def _handle_stage_failure(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dep_results: list[StageResult],
        user_prompt: str,
        output_schema: dict[str, Any] | None,
        exc: Exception,
        start: float,
        *,
        rank: RankPolicy | None = None,
        run_results: Mapping[str, StageResult] | None = None,
    ) -> tuple[StageResult, StageSpan]:
        """Retry aggregator/merge/audit stages: fallback chain → plain-text → degraded.

        DF-CHIMERA-V2-120 (measured: 3 of 4 live runs exited rc=2 after 83-187 s
        with no answer while all three workers had already succeeded and been
        paid for): the merge used to have exactly one replacement candidate.
        When that candidate was the same dead account — or when the chain had
        no healthy entry at all — the workers' output was thrown away.

        The retry now walks an ORDERED fallback chain carried on the stage
        (``defaults.aggregator_fallbacks``, or the formation's own list).  Every
        entry that provably cannot serve is SKIPPED WITHOUT A CALL and recorded
        with its reason, so a dead chain costs zero extra provider latency
        instead of the measured retry tail.  A served fallback returns a real
        stage result; only an exhausted chain falls through to the schema-free
        retry and finally to the degraded placeholder (whose worker outputs the
        result object preserves).
        """
        latency_ms = int((time.monotonic() - start) * 1000)
        log.warning("engine_stage_failed", stage=stage.id, model=stage.model, error=str(exc))

        if stage.kind not in {"aggregator", "merge", "audit"}:
            return self._degraded_stage(stage, exc, [], latency_ms, started_at=start)

        # A quota-class failure condemns the whole ACCOUNT, so the whole chain
        # must abandon that provider (sibling models share the empty balance).
        excluded = _quota_excluded_models(self.config, blocked_models.shared_registry, self._provider_health)
        failed_entry = self.config.models.get(stage.model)
        failed_provider = failed_entry.provider if failed_entry is not None else None
        avoid_providers: frozenset[str] = frozenset()
        if blocked_models.classify_error(exc) == blocked_models.REASON_QUOTA and failed_provider is not None:
            avoid_providers = frozenset({failed_provider})
        # Credential gating is only meaningful in a deployment that resolves
        # SOME credential: a fixture/deployment with no keys at all must keep
        # the pre-existing "retry something" behaviour rather than skip every
        # candidate for lacking a key it never had.
        credentials_configured = any(
            provider_credential_resolved(self.config, entry.provider)
            for entry in self.config.enabled_models.values()
        )

        attempts: list[AggregatorFallbackAttempt] = []
        called = 0
        chain = self._merge_fallback_chain(stage, excluded=excluded, avoid_providers=avoid_providers)
        kinds = {item.id: item.kind for item in dispatch.formation.stages}
        survivors = list(
            dict.fromkeys(
                result.model
                for result in (run_results or {}).values()
                if not result.degraded
                and kinds.get(result.stage_id) in {"worker", "dispatcher"}
                and result.model != stage.model
            )
        )
        # Reserve one extra call beyond the ordinary cap for a proven survivor.
        survivor_called = False
        called_models: set[str] = set()
        for candidate, is_survivor in [(name, False) for name in chain] + [
            (name, True) for name in survivors
        ]:
            if is_survivor and candidate in called_models:
                continue
            reason = _merge_fallback_skip_reason(
                self.config,
                candidate,
                registry=blocked_models.shared_registry,
                excluded=excluded,
                failed_model=stage.model,
                credentials_configured=credentials_configured and not is_survivor,
                proven_live=is_survivor,
            )
            if reason is not None:
                attempts.append(
                    AggregatorFallbackAttempt(
                        model=candidate,
                        status=FALLBACK_SKIPPED,
                        reason=reason,
                        source="this_run_survivor" if is_survivor else None,
                    )
                )
                log.warning(
                    "engine_aggregator_fallback_skipped", stage=stage.id, model=candidate, reason=reason
                )
                continue
            if (is_survivor and survivor_called) or (
                not is_survivor and called >= MAX_AGGREGATOR_FALLBACK_ATTEMPTS
            ):
                attempts.append(
                    AggregatorFallbackAttempt(
                        model=candidate,
                        status=FALLBACK_SKIPPED,
                        source="this_run_survivor" if is_survivor else None,
                        reason=(
                            "survivor attempt budget exhausted (one merge call already spent)"
                            if is_survivor
                            else "attempt budget exhausted "
                            f"({MAX_AGGREGATOR_FALLBACK_ATTEMPTS} merge calls already spent)"
                        ),
                    )
                )
                continue
            if is_survivor:
                survivor_called = True
            else:
                called += 1
            called_models.add(candidate)
            retry_stage = stage.model_copy(update={"model": candidate})
            try:
                messages, response, rank_pass = await self._call_stage(
                    retry_stage,
                    dispatch,
                    dep_results,
                    user_prompt,
                    output_schema,
                )
            except (GatewayError, BudgetExhaustedError) as fallback_exc:
                attempts.append(
                    AggregatorFallbackAttempt(
                        model=candidate,
                        status=FALLBACK_FAILED,
                        source="this_run_survivor" if is_survivor else None,
                        error=str(fallback_exc),
                        error_class=blocked_models.classify_error(fallback_exc),
                    )
                )
                log.warning(
                    "engine_aggregator_fallback_failed",
                    stage=stage.id,
                    model=candidate,
                    error=str(fallback_exc),
                )
                continue
            attempts.append(
                AggregatorFallbackAttempt(
                    model=candidate,
                    status=FALLBACK_SERVED,
                    source="this_run_survivor" if is_survivor else None,
                )
            )
            log.info(
                "engine_aggregator_fallback_served",
                stage=stage.id,
                original=stage.model,
                fallback=candidate,
                skipped=[entry.model for entry in attempts if entry.status == FALLBACK_SKIPPED],
            )
            result, span = self._build_stage_result(
                retry_stage,
                response,
                messages,
                start,
                user_prompt,
                dispatch,
                dep_results,
                rank_pass=rank_pass,
            )
            span.fallback_attempts = attempts
            return result, span

        # Retry 2: plain text (no output_schema) — catches json_schema/json_object
        # provider incompatibilities (e.g. DeepSeek requires "json" in prompt).
        # DF-CHIMERA-V2-130: when the original model is quota-excluded, this
        # schema-free attempt runs on a healthy candidate instead — dropping the
        # schema does not make a dead account answer.
        plain_target: str | None = None
        if failed_provider not in avoid_providers and stage.model not in excluded:
            plain_target = stage.model
        else:
            plain_target = next(
                (entry.model for entry in attempts if entry.status == FALLBACK_FAILED),
                None,
            )
        if plain_target is not None:
            plain_stage = stage.model_copy(update={"model": plain_target})
            try:
                messages, response, rank_pass = await self._call_stage(
                    plain_stage,
                    dispatch,
                    dep_results,
                    user_prompt,
                    output_schema=None,
                )
            except (GatewayError, BudgetExhaustedError) as exc2:
                attempts.append(
                    AggregatorFallbackAttempt(
                        model=plain_target,
                        status=FALLBACK_FAILED,
                        error=str(exc2),
                        error_class=blocked_models.classify_error(exc2),
                    )
                )
                result, span = self._degraded_stage(stage, exc2, [], latency_ms, started_at=start)
                span.fallback_attempts = attempts
                return result, span
            log.info("engine_stage_retry_plaintext", stage=stage.id, model=plain_target)
            result, span = self._build_stage_result(
                plain_stage,
                response,
                messages,
                start,
                user_prompt,
                dispatch,
                dep_results,
                rank_pass=rank_pass,
            )
            span.fallback_attempts = attempts
            return result, span

        result, span = self._degraded_stage(stage, exc, [], latency_ms, started_at=start)
        span.fallback_attempts = attempts
        return result, span

    def _merge_fallback_chain(
        self,
        stage: Stage,
        *,
        excluded: Mapping[str, Any],
        avoid_providers: frozenset[str] = frozenset(),
    ) -> list[str]:
        """The ordered merge-fallback candidates for *stage*, deduplicated.

        The configured chain first (the formation's own list, else
        ``defaults.aggregator_fallbacks``), then the two implicit candidates
        the engine had before this row: the configured default aggregator and
        the single healthy replacement chosen by
        :func:`_quota_fallback_model`.  Keeping the implicit tail means an
        EMPTY chain can never be WORSE than the pre-DF-CHIMERA-V2-120
        behaviour — the fallback chain only ever adds resilience.

        *avoid_providers* (the provider of a model that just failed with a
        quota error) does NOT disqualify a candidate, it only DEMOTES it:
        quota exhaustion is account-level, so a sibling model is a wasted call
        while any other provider remains — but a sibling model still beats no
        attempt at all, which is the documented DF-CHIMERA-V2-130 behaviour
        this must not regress.  Stable partition keeps the declared order
        inside each group.

        Every entry is still screened by
        :func:`_merge_fallback_skip_reason`; a candidate listed twice, or one
        that is the failed model itself, is recorded as ``skipped`` with its
        reason rather than silently dropped.
        """
        chain: list[str] = []
        for model in stage.aggregator_fallbacks:
            if model and model not in chain:
                chain.append(model)
        implicit = [
            self.config.defaults.default_aggregator,
            _quota_fallback_model(
                self.config,
                excluded,
                preferred=self.config.defaults.default_aggregator,
                avoid=stage.model,
                # Pre-DF-CHIMERA-V2-120 candidate choice, preserved: a
                # quota-class failure steers the implicit replacement off the
                # dead ACCOUNT (its siblings share the empty balance).
                avoid_providers=avoid_providers,
            ),
        ]
        for implicit_model in implicit:
            if implicit_model and implicit_model not in chain:
                chain.append(implicit_model)
        if avoid_providers and len(chain) > 1:
            chain.sort(key=lambda name: _provider_of(self.config, name) in avoid_providers)
        return chain

    def _build_stage_result(
        self,
        stage: Stage,
        response: GatewayResponse,
        messages: list[dict[str, str]],
        start: float,
        user_prompt: str,
        dispatch: DispatchResult,
        dep_results: list[StageResult],
        *,
        rank_pass: RankPass | None = None,
    ) -> tuple[StageResult, StageSpan]:
        """Build a (StageResult, StageSpan) pair for a successful stage call."""
        latency_ms = int((time.monotonic() - start) * 1000)
        prompt_text = (
            _last_user_content(messages)
            if messages
            else _aggregator_prompt_summary(stage, dispatch, dep_results)
        )
        ended = time.monotonic()
        # QA-CHIMERA-V2-16: the route the gateway resolved for this call, read
        # off the response's metadata side-band (empty for a gateway that
        # carries none, e.g. a test double).
        provider, wire_model, api_base = _route_attribution(response)
        rank_fields: dict[str, Any] = {}
        if rank_pass is not None:
            rank_fields = {
                "ranked_candidates": [
                    RankedCandidateSpan(
                        stage_id=candidate.stage_id,
                        model=candidate.model,
                        score=candidate.score,
                        rank=candidate.rank,
                        kept=candidate.kept,
                    )
                    for candidate in rank_pass.candidates
                ],
                "rank_kappa": rank_pass.kappa,
                "rank_model": rank_pass.model,
                "rank_tokens_input": rank_pass.tokens_input,
                "rank_tokens_output": rank_pass.tokens_output,
                "rank_cost": _stage_cost(
                    rank_pass.model,
                    self.config,
                    rank_pass.tokens_input,
                    rank_pass.tokens_output,
                )
                if rank_pass.tokens_input or rank_pass.tokens_output
                else 0.0,
                "rank_error": rank_pass.error,
            }
        span = StageSpan(
            stage_id=stage.id,
            kind=stage.kind,
            model=response.model,
            provider=provider,
            wire_model=wire_model,
            api_base=api_base,
            prompt=prompt_text,
            response=response.text,
            tokens_input=response.tokens_input,
            tokens_output=response.tokens_output,
            latency_ms=latency_ms,
            cost=_stage_cost(response.model, self.config, response.tokens_input, response.tokens_output),
            depends_on=list(stage.depends_on),
            started_at=start,
            ended_at=ended,
            finish_reason=response.finish_reason,
            negotiated_format=_format_negotiation(response),
            **rank_fields,
        )
        result = StageResult(
            stage_id=stage.id,
            model=response.model,
            prompt=prompt_text,
            response=response,
        )
        return result, span

    async def _call_stage(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dep_results: list[StageResult],
        user_prompt: str,
        output_schema: dict[str, Any] | None = None,
        *,
        iteration_feedback: str | None = None,
        max_tokens: int | None = None,
        rank: RankPolicy | None = None,
    ) -> tuple[list[dict[str, str]], GatewayResponse, RankPass | None]:
        """Make the actual model call for a stage. Returns (messages, response, rank_pass)."""
        if stage.kind == "worker":
            messages = self._worker_messages(
                stage, dispatch, user_prompt, iteration_feedback=iteration_feedback
            )
            # Progressive prompting: feed context piece-by-piece before the real call.
            # CH-GAP-058: a caller-supplied ``progressive=True`` now reaches these
            # stages on its own (``_apply_progressive``), so the gate below is the
            # real contract for BOTH ways the flag can be set:
            #   * progressive=True + wait_messages -> messages are fed one at a
            #     time (each response discarded); a non-empty ``trigger`` then
            #     REPLACES the stage prompt, an empty one leaves it intact.
            #   * progressive=True with NO wait_messages -> there is nothing to
            #     feed before the call, so the flag is a documented no-op on the
            #     wire (``messages`` is already final) — never a second or
            #     repeated prompt.
            if stage.progressive and stage.wait_messages:
                for msg in stage.wait_messages:
                    await self.gateway.complete(
                        stage.model,
                        [{"role": "user", "content": msg}],
                        temperature=0.3,
                    )
                trigger = stage.trigger or messages[-1]["content"]
                if stage.trigger:
                    messages = [{"role": "user", "content": trigger}]
            # CH-GAP-031: honor OpenAI-compat max_tokens — the cap is applied to
            # every answer-producing call (workers + aggregator), so a drop-in
            # client bounding cost gets a real bound, not a silent no-op.
            kwargs: dict[str, Any] = {"temperature": 0.3}
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            response = await self.gateway.complete(stage.model, messages, **kwargs)
            return messages, response, None
        response, rank_pass, merge_messages = await self.aggregator.execute_ranked(
            stage,
            dispatch,
            dep_results,
            user_prompt,
            output_schema=output_schema,
            max_prompt_tokens=self.config.max_aggregator_context_tokens,
            max_tokens=max_tokens,
            rank=rank,
        )

        # ── Mechanical schema validation for AUDIT stages ──────────
        if stage.kind == "audit" and output_schema is not None:
            validation_error = self._validate_against_schema(
                output_schema,
                response.text,
            )
            if validation_error is not None:
                log.info(
                    "engine_audit_validation_failed",
                    stage=stage.id,
                    errors=validation_error.get("errors", []),
                )
                # Replace response text so the iteration loop sees the
                # ``"passed": false`` signal and triggers re-iteration.
                response = GatewayResponse(
                    text=json.dumps(validation_error),
                    model=response.model,
                    tokens_input=response.tokens_input,
                    tokens_output=response.tokens_output,
                )
            else:
                log.info("engine_audit_validation_passed", stage=stage.id)

        # A ranked run records the merge prompt it ACTUALLY sent, so the trace
        # proves which outputs survived ranking (DF-CHIMERA-V2-102). Un-ranked
        # runs keep their compact summary unchanged.
        if rank is not None:
            return merge_messages, response, rank_pass
        return [], response, rank_pass

    def _degraded_stage(
        self,
        stage: Stage,
        error: Exception,
        messages: list[dict[str, str]],
        latency_ms: int,
        *,
        started_at: float | None = None,
    ) -> tuple[StageResult, StageSpan]:
        prompt_text = (
            _last_user_content(messages) if messages else f"(degraded {stage.kind} stage '{stage.id}')"
        )
        degraded_response = GatewayResponse(
            text=f"[stage {stage.id} ({stage.model}) unavailable: {error}]",
            model=stage.model,
            tokens_input=0,
            tokens_output=0,
            metadata={"degraded": True, "stage_id": stage.id, "error": str(error)},
        )
        ended = time.monotonic()
        start_ts = started_at if started_at is not None else ended - (latency_ms / 1000.0)
        # QA-CHIMERA-V2-16: no provider route ran for a degraded stage, so the
        # placeholder response's metadata carries no attribution and these stay
        # empty — read from the same metadata channel, never guessed from
        # ``stage.model`` (its prefix can name a provider that never served).
        provider, wire_model, api_base = _route_attribution(degraded_response)
        span = StageSpan(
            stage_id=stage.id,
            kind=stage.kind,
            model=stage.model,
            provider=provider,
            wire_model=wire_model,
            api_base=api_base,
            prompt=prompt_text,
            response=degraded_response.text,
            tokens_input=0,
            tokens_output=0,
            latency_ms=latency_ms,
            cost=0.0,
            depends_on=list(stage.depends_on),
            started_at=start_ts,
            ended_at=ended,
            finish_reason=degraded_response.finish_reason,
            negotiated_format=_format_negotiation(degraded_response),
            # DF-CHIMERA-V2-120: no model served this stage, which is how the
            # trace tells a substituted-but-real merge (``degraded=False``,
            # ``trace.aggregator_model`` set) from a placeholder one.
            degraded=True,
        )
        result = StageResult(
            stage_id=stage.id,
            model=stage.model,
            prompt=prompt_text,
            response=degraded_response,
            degraded=True,
        )
        return result, span

    # ------------------------------------------------------------------ #
    # Iteration helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _check_iteration_needed(stage: Stage, span: StageSpan) -> bool:
        """Check whether *stage*'s output signals that re-iteration is needed.

        Returns ``True`` when the response contains ``"passed": false``
        (case-insensitive JSON fragment) — the conventional signal used by
        audit/refine stages to indicate the result failed quality checks.
        """
        return bool(_RE_ITERATION_SIGNAL.search(span.response))

    # ------------------------------------------------------------------ #
    # Schema-driven validation (Validation-as-code)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_output_schema(response_text: str) -> dict[str, Any] | None:
        """Extract a JSON Schema from a STRUCTURE stage response.

        The STRUCTURE stage can emit a ``schema`` field containing a valid
        JSON Schema.  This schema is then used for mechanical validation
        in downstream AUDIT stages instead of (or in addition to) LLM review.
        """
        try:
            data = json.loads(response_text)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        # Explicit ``schema`` field — canonical STRUCTURE output shape
        schema = data.get("schema")
        if isinstance(schema, dict):
            return schema
        # Heuristic: the whole response might BE a JSON Schema
        if data.get("type") == "object" and "properties" in data:
            return data
        return None

    @staticmethod
    def _validate_against_schema(schema: dict[str, Any], output: str) -> dict[str, Any] | None:
        """Mechanically validate *output* against *schema*.

        Returns ``None`` on success (output is valid), or a dict suitable
        for embedding in the audit response::

            {"passed": false, "errors": [...]}

        Two steps are tolerant, and both exist because the
        dispatcher-authored schema cannot always be ENFORCED on the wire: a
        provider with no structured-output support (
        :class:`~chimera.gateway.FormatCapability.NONE`, e.g. deepseek) has
        ``response_format`` stripped by
        :func:`chimera.gateway.negotiate_response_format`, so the model never
        sees the schema and answers in whatever shape it guesses.

        1. EXTRACTION — an answer that wraps its JSON in a code fence or in
           prose is recovered by :meth:`_extract_json_value`.
        2. ONE documented coercion — a property the schema declares as an
           array of strings whose value came back as a single delimited
           string (``"sources": "worker_1, worker_2"``) is split by
           :meth:`_normalize_delimited_string_arrays`.

        Nothing else is coerced: no defaults, no scalar→array widening for
        non-string items, no ``required`` relaxation, and the *schema* is
        never mutated. Everything else faces the same strict
        :func:`jsonschema.validate` call as before.
        """
        try:
            instance = json.loads(output)
        except (json.JSONDecodeError, TypeError) as exc:
            found, instance = Engine._extract_json_value(output)
            if not found:
                return {
                    "passed": False,
                    "errors": [f"Output is not valid JSON: {exc}"],
                }
        instance = Engine._normalize_delimited_string_arrays(schema, instance)
        try:
            jsonschema.validate(instance=instance, schema=schema)
        except jsonschema.ValidationError as exc:
            return {"passed": False, "errors": [str(exc)]}
        return None  # passed

    @staticmethod
    def _normalize_delimited_string_arrays(schema: dict[str, Any], instance: Any) -> Any:
        """Split a comma-joined string where the schema wants an array of strings.

        The dispatcher authors the output schema, but the wire cannot always
        enforce it (see :meth:`_validate_against_schema`): a model that never
        saw the schema often collapses a list into one string —
        ``"sources": "worker_1, worker_2"`` for a property the schema declares
        as ``{"type": "array", "items": {"type": "string"}}``. Failing the
        audit on that is a formatting disagreement, not a wrong answer, so the
        engine repairs exactly that shape before validating.

        This is the ONE coercion the engine performs, and it is deliberately
        narrow:

        * only TOP-LEVEL properties of a dict instance are considered (no
          recursion into nested objects or array items);
        * only when the property's subschema says ``type: array`` **and**
          ``items.type: string``;
        * only when the instance's value is a ``str`` (an already-correct
          list, a number, ``None`` — all untouched, so no double
          normalization is possible);
        * only when the split yields at least one non-empty part.

        Parts are stripped of surrounding whitespace and empty parts are
        dropped (``"a, , b"`` → ``["a", "b"]``). A string that yields nothing
        (``""``, ``"   "``, ``", ,"``) is LEFT ALONE rather than becoming a
        fabricated ``[]``: it carries no list information, so it still fails
        the type check and the audit degrades loudly instead of silently
        inventing "no sources". The instance dict is modified in place and
        returned; the schema is only read.
        """
        if not isinstance(instance, dict):
            return instance
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return instance
        for name, subschema in properties.items():
            if not isinstance(subschema, dict):
                continue
            if subschema.get("type") != "array":
                continue
            items = subschema.get("items")
            if not isinstance(items, dict) or items.get("type") != "string":
                continue
            value = instance.get(name)
            if not isinstance(value, str):
                continue
            parts = [part.strip() for part in value.split(",")]
            parts = [part for part in parts if part]
            if not parts:
                continue
            instance[name] = parts
            log.info(
                "engine_schema_array_normalized",
                property=name,
                items=len(parts),
            )
        return instance

    @staticmethod
    def _extract_json_value(text: str) -> tuple[bool, Any]:
        """Recover a JSON value from an answer that wrapped it in prose.

        Fallback for the schema-validation path, which is handed whatever
        the model replied with: a fenced ```json block, a sentence before
        the object, a trailing remark after it, or all three. Two
        conservative steps, in order:

        1. parse the text as-is, then — if that fails — parse it with a
           single markdown code fence wrapping the *whole* text removed by
           :meth:`_strip_final_answer_fences`;
        2. decode the first complete JSON value with
           :meth:`json.JSONDecoder.raw_decode`, starting at the first
           ``{`` or ``[`` — whichever appears earliest. Only object/array
           openers are scanned, so prose like "I found 5 issues" is never
           mined for a number, and the decoded value is used alone (any
           trailing text is discarded, never concatenated).

        Returns ``(found, value)``; ``found`` is False when neither step
        yields a JSON value, leaving the caller to report its own parse
        failure against the original text.
        """
        if not isinstance(text, str):
            return False, None
        candidates = [text]
        unfenced = Engine._strip_final_answer_fences(text)
        if unfenced != text:
            candidates.append(unfenced)
        for candidate in candidates:
            try:
                return True, json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                continue
        for candidate in candidates:
            starts = [idx for idx in (candidate.find("{"), candidate.find("[")) if idx != -1]
            if not starts:
                continue
            try:
                value, _end = json.JSONDecoder().raw_decode(candidate[min(starts) :])
            except json.JSONDecodeError:
                continue
            return True, value
        return False, None

    @staticmethod
    def _collect_feedback(
        trigger: Stage,
        dispatch: DispatchResult,
        results: dict[str, StageResult],
        spans: dict[str, StageSpan],
    ) -> str:
        """Build a feedback string for re-run workers after a failed iteration.

        Collects the output of the trigger stage and any upstream stages
        that contributed to the failure signal so workers can understand
        what went wrong and what to improve.
        """
        parts: list[str] = []
        trigger_span = spans.get(trigger.id)
        if trigger_span is not None:
            parts.append(f"## Re-iteration feedback from {trigger.id}\n{trigger_span.response[:2000]}")
        # Include all direct upstream results for context
        for dep_id in trigger.depends_on:
            dep_result = results.get(dep_id)
            if dep_result is not None:
                parts.append(f"## Context from upstream {dep_id}\n{dep_result.response.text[:1000]}")
        return "\n\n".join(parts) if parts else "The previous output needs improvement."

    # ------------------------------------------------------------------ #
    # Worker prompt assembly
    # ------------------------------------------------------------------ #

    def _worker_messages(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        user_prompt: str,
        *,
        iteration_feedback: str | None = None,
    ) -> list[dict[str, str]]:
        wp = dispatch.worker_prompt_for(stage.id)
        task = wp.prompt if wp and wp.prompt else "Solve the user's request."
        content = f"## User request\n{user_prompt}\n\n## Your assigned task\n{task}"
        if iteration_feedback:
            content += f"\n\n## Previous attempt feedback\n{iteration_feedback}"
        return [
            {
                "role": "user",
                "content": content,
            }
        ]

    # ------------------------------------------------------------------ #
    # Trace assembly
    # ------------------------------------------------------------------ #

    def _build_dispatch_span(self, outcome: DispatchOutcome, formation: str) -> StageSpan:
        resp = outcome.response
        prompt_text = _last_user_content(outcome.messages)
        # The response carries the model actually invoked (which may be a
        # request-level dispatcher_model override); fall back to the config
        # default when the response doesn't identify one.
        dispatch_model = resp.model or self.config.defaults.dispatcher
        # CH-GAP-056: the dispatch stage IS a provider route — the dispatcher
        # model call is a real gateway completion (Dispatcher._call_dispatcher
        # → Gateway.complete), so its span carries the same resolved-route
        # attribution a worker span does, read off the response's metadata
        # side-band. It stays empty exactly when no route was resolved (the
        # dispatcher's own `{}` fallback response after a GatewayError), never
        # guessed from the model id. The timestamps are the dispatcher's own
        # monotonic readings (`DispatchOutcome.started_at` / `ended_at`) — the
        # call is already over here, so re-timing it would be a fabrication.
        provider, wire_model, api_base = _route_attribution(resp)
        return StageSpan(
            stage_id="dispatch",
            kind="dispatch",
            model=dispatch_model,
            provider=provider,
            wire_model=wire_model,
            api_base=api_base,
            prompt=prompt_text,
            response=resp.text,
            tokens_input=resp.tokens_input,
            tokens_output=resp.tokens_output,
            latency_ms=outcome.latency_ms,
            cost=_stage_cost(
                dispatch_model,
                self.config,
                resp.tokens_input,
                resp.tokens_output,
            ),
            depends_on=[],
            started_at=outcome.started_at,
            ended_at=outcome.ended_at,
            finish_reason=resp.finish_reason,
            negotiated_format=_format_negotiation(resp),
        )

    def _select_answer(self, dag: FormationDAG, results: dict[str, StageResult]) -> tuple[str, str]:
        terminals = dag.terminals()
        if not terminals:
            # fall back to last stage in topo order
            last = dag.topo_order()[-1]
            return results[last.id].response.text, last.id
        if len(terminals) == 1:
            t = terminals[0]
            return results[t.id].response.text, t.id
        parts = [
            f"### {t.id} ({results[t.id].model})\n{results[t.id].response.text}"
            for t in terminals
            if t.id in results
        ]
        return "\n\n".join(parts), terminals[0].id

    @staticmethod
    def _strip_final_answer_fences(text: str) -> str:
        """Remove a single markdown code fence wrapping the whole final answer.

        Conservative by design: stripping only triggers when the ENTIRE
        (whitespace-stripped) text is wrapped in one fence — an opening
        fence line (triple backtick, optional bare language tag) and a
        closing fence line as the last content. Plain answers, and JSON
        content that merely *contains* backticks, pass through completely
        unmodified.

        Unlike :func:`chimera.dispatcher._strip_fences` (which aggressively
        strips fence-looking lines anywhere, for parsing dispatcher JSON),
        this helper never mutates interior content.

        Non-string input is coerced to a JSON string so
        ``DeliberationResult(answer: str)`` never fails Pydantic validation
        (mirrors :meth:`_maybe_unwrap_envelope`).
        """
        if not isinstance(text, str):
            return json.dumps(text) if text is not None else ""
        stripped = text.strip()
        if not stripped.startswith("```"):
            return text
        first_nl = stripped.find("\n")
        if first_nl == -1:
            # Single line starting with ``` — not a wrapping fence.
            return text
        opener = stripped[3:first_nl].strip()
        # Language tag must be a bare word (json, python, ...) or empty.
        if opener and not re.fullmatch(r"[A-Za-z0-9_+-]+", opener):
            return text
        body = stripped[first_nl + 1 :]
        if not body.rstrip().endswith("```"):
            return text
        body = body.rstrip()[:-3]
        return body.strip()

    @staticmethod
    def _maybe_unwrap_envelope(text: str) -> str:
        """If text is a Chimera API response envelope, extract the answer field.

        Checks for a JSON dict with an ``answer`` key — if the value under
        ``answer`` is itself valid JSON, it is extracted (double-unwrap).
        Otherwise the raw ``answer`` value is returned.

        Always returns a ``str``, coercing non-string inputs and fall-through
        values so that ``DeliberationResult(answer: str)`` never fails Pydantic
        validation.
        """
        import json as _json

        # Belt: coerce non-string input immediately (defensive — all callers
        # should pass str, but a raw int/float from a misbehaving gateway
        # would bypass json.loads and escape as the original value).
        if not isinstance(text, str):
            return _json.dumps(text) if text is not None else ""

        try:
            data = _json.loads(text)
            if isinstance(data, dict) and "answer" in data:
                inner = data["answer"]
                # If the value is a JSON-encoded string, parse it out.
                if isinstance(inner, str):
                    try:
                        parsed = _json.loads(inner)
                        if isinstance(parsed, (dict, list)):
                            return _json.dumps(parsed)
                    except (_json.JSONDecodeError, TypeError):
                        pass
                # Coerce non-string values (int, float, bool, None) to string
                # so that DeliberationResult(answer: str) always receives a string.
                if not isinstance(inner, str):
                    return _json.dumps(inner)
                return inner
        except (_json.JSONDecodeError, TypeError, KeyError):
            pass

        # Suspenders: ensure the fall-through value is always a string.
        # json.loads on a raw number/boolean string returns the parsed
        # Python value, which would be returned as-is without this guard.
        if not isinstance(text, str):
            return _json.dumps(text) if text is not None else ""
        return text

    def _assemble_trace(
        self,
        *,
        request_id: str,
        formation: str,
        dispatch: DispatchResult,
        dispatch_span: StageSpan | None,
        stage_spans: dict[str, StageSpan],
        answer_stage_id: str,
        started: float,
        iteration_count: int = 1,
        worker_failures: list[WorkerFailure] | None = None,
    ) -> DeliberationTrace:
        workers = [s for s in stage_spans.values() if s.kind == "worker"]
        primary_aggregator = next(
            (s for s in stage_spans.values() if s.kind in {"aggregator", "merge", "audit"}),
            None,
        )
        # PERF-2: a skipped dispatch contributes no span, so the run totals
        # are computed over the stage spans alone — cost/tokens still add up
        # exactly (nothing is double-counted or invented).
        all_spans: list[StageSpan] = ([dispatch_span] if dispatch_span is not None else []) + list(
            stage_spans.values()
        )
        # DF-CHIMERA-V2-102: the pre-merge scorer call is real provider spend,
        # so it is counted in the run totals (kept separate from the stage's
        # own ``tokens_*``/``cost``, which stay the merge call's numbers).
        total_cost = round(sum(s.cost + s.rank_cost for s in all_spans), 6)
        total_tokens = sum(
            s.tokens_input + s.tokens_output + s.rank_tokens_input + s.rank_tokens_output for s in all_spans
        )
        # DF-CHIMERA-V2-55: name every stage the token cap cut off. A capped
        # worker's fragment still reaches the aggregator and the merged answer
        # reads as clean prose — these entries are the visible marker that it
        # is silently incomplete. The dispatch span is excluded by construction
        # (it is not in ``stage_spans``): its design call produces no answer
        # text.
        degraded_reasons = [
            f"{span.stage_id}: token_limit" for span in stage_spans.values() if span.finish_reason == "length"
        ]
        # DF-CHIMERA-V2-120: name the model that ACTUALLY served the merge, and
        # the whole fallback chain it walked. A degraded aggregator span is a
        # placeholder — no model served it — so ``aggregator_model`` stays None
        # instead of echoing a model that never answered (the span's own
        # ``model`` field keeps the CONFIGURED model for diagnostics).
        aggregator_model = (
            primary_aggregator.model
            if primary_aggregator is not None and not primary_aggregator.degraded
            else None
        )
        return DeliberationTrace(
            request_id=request_id,
            formation=formation,
            source=dispatch.source,
            dispatch=dispatch_span,
            workers=workers,
            aggregator=primary_aggregator,
            stages=list(stage_spans.values()),
            answer_stage_id=answer_stage_id,
            total_duration_ms=int((time.monotonic() - started) * 1000),
            total_cost=total_cost,
            total_tokens=total_tokens,
            iteration_count=iteration_count,
            dispatch_note=dispatch.fallback_reason or dispatch.dispatch_note,
            # DF-CHIMERA-V2-34: the structured form of the discard. On a preset
            # or custom DAG `source` is the formation type, not the dispatch
            # outcome, so the collapse needs its own field to stay visible.
            dispatch_fallback_reason=dispatch.fallback_reason,
            dispatch_repairs=list(dispatch.dispatch_repairs),
            worker_failures=list(worker_failures or []),
            # DF-CHIMERA-V2-90: make the credential SOURCE visible on every
            # deliberation — a run that succeeded only because a host-level
            # ~/.hermes/.env supplied the key reads exactly like a
            # properly-configured one everywhere else.
            credential_sources=dict(self.config.credential_sources),
            degraded_reasons=degraded_reasons,
            aggregator_model=aggregator_model,
            aggregator_fallbacks=(
                list(primary_aggregator.fallback_attempts) if primary_aggregator is not None else []
            ),
        )

    @staticmethod
    def _collect_worker_failures(
        stage_results: dict[str, StageResult],
        config: ChimeraConfig | None = None,
    ) -> list[WorkerFailure]:
        """Build the dropped-worker list from degraded stage results.

        Every degraded stage carries its upstream error in
        ``response.metadata["error"]`` (stamped by :meth:`_degraded_stage`).
        Guardrail-class and credential-class errors are also recorded in the
        shared block registry so the dispatcher stops selecting that model for
        the cooldown window.

        ``config`` is optional so callers that predate DF-CHIMERA-V2-6 keep
        working; without it a credential-class failure is still recorded, just
        without the fingerprint that lets the block self-clear when the key is
        replaced.
        """
        failures: list[WorkerFailure] = []
        for stage_id, result in stage_results.items():
            if not isinstance(result, StageResult) or not result.degraded:
                continue
            error = str(result.response.metadata.get("error") or "unknown error")
            failures.append(WorkerFailure(stage_id=stage_id, model=result.model, error=error))
            blocked_models.shared_registry.record_failure(
                result.model,
                error,
                credential_fingerprint=(
                    model_credential_fingerprint(config, result.model) if config is not None else None
                ),
            )
        return failures


def _aggregator_prompt_summary(stage: Stage, dispatch: DispatchResult, deps: list[StageResult]) -> str:
    """Compact prompt string for aggregator spans (whose messages are built internally)."""
    deps_desc = ", ".join(d.stage_id for d in deps) or "(none)"
    return f"merge stage '{stage.id}' over upstream: {deps_desc}"


def _maybe_langfuse(trace: DeliberationTrace, user_prompt: str) -> None:
    client = get_langfuse()
    if client is None:
        return
    # Langfuse is best-effort telemetry: it must never break a deliberation.
    try:
        trace_obj = client.trace(id=trace.request_id, name="chimera.deliberation")
        # PERF-2: an explicit formation has no dispatcher call, so there is no
        # dispatch generation to export.
        if trace.dispatch is not None:
            trace_obj.generation(
                name="dispatch",
                model=trace.dispatch.model,
                input=user_prompt,
                output=trace.dispatch.response,
                usage={
                    "prompt": trace.dispatch.tokens_input,
                    "completion": trace.dispatch.tokens_output,
                },
            )
        for span in trace.stages:
            trace_obj.generation(
                name=span.stage_id,
                model=span.model,
                input=span.prompt,
                output=span.response,
                usage={"prompt": span.tokens_input, "completion": span.tokens_output},
            )
    except (
        ConnectionError,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
    ) as exc:
        log.warning("langfuse_trace_failed", error=str(exc))


__all__ = [
    "DeliberationResult",
    "DeliberationTrace",
    "Engine",
    "StageSpan",
    "WorkerFailure",
]
