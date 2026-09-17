"""The formation engine — runs the dispatcher-designed DAG.

Executes stages in dependency waves: all stages whose dependencies are met run
concurrently via :func:`asyncio.gather`. Every call is traced into a
:class:`DeliberationTrace` (prompt, response, tokens, latency, cost).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from typing import Any

import jsonschema
import structlog
from pydantic import BaseModel, Field

from chimera import blocked_models
from chimera.aggregator import Aggregator, StageResult
from chimera.config import (
    ChimeraConfig,
    DeliberationOverrides,
    credentialed_enabled_models,
    model_credential_fingerprint,
    provider_credential_resolved,
)
from chimera.dispatcher import (
    Dispatcher,
    DispatchOutcome,
    DispatchResult,
    FormationDAG,
    Stage,
    _repair_formation,
    build_dag_from_dict,
)
from chimera.exceptions import BudgetExhaustedError
from chimera.gateway import Gateway, GatewayError, GatewayResponse
from chimera.observability import get_langfuse

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


class StageSpan(BaseModel):
    """One traced stage execution."""

    stage_id: str
    kind: str
    model: str
    provider: str = ""
    """The provider that actually SERVED this stage's call — the gateway's
    resolved ``effective_provider`` after credential fallbacks — or ``""``
    when no provider route was resolved at all (the internal dispatch span, a
    degraded stage, a gateway stub that carries no attribution).  Never
    derived from ``model``: a catalog id's prefix can name a provider other
    than the one that served the call (QA-CHIMERA-V2-16)."""
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
    dispatch: StageSpan
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
    worker_failures: list[WorkerFailure] = Field(default_factory=list)
    """Worker (and other) stages that degraded with an upstream error — the
    machine-readable form of the CLI's dropped-worker warning. Empty when
    every stage succeeded."""


class DeliberationResult(BaseModel):
    """The user-facing result of a deliberation."""

    answer: str
    trace: DeliberationTrace
    answer_degraded: bool = False
    """True when the selected answer stage failed and the answer is a
    degraded placeholder — the API layer translates this into HTTP 502."""
    answer_error: str | None = None
    """Upstream failure reason for a degraded answer, when known."""


def _stage_cost(model: str, config: ChimeraConfig, tokens_input: int, tokens_output: int) -> float:
    try:
        entry = config.get_model(model)
    except KeyError:
        return 0.0
    return (
        entry.cost_rate_input() * tokens_input / 1000.0
        + entry.cost_rate_output() * tokens_output / 1000.0
    )


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

    * Unknown stage ids are logged as warnings and skipped (never fatal).
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
            log.warning("stage_model_unknown_stage", stage_id=stage_id)
            continue
        if model not in config.models:
            raise ValueError(
                f"stage_models references unknown model for stage "
                f"{stage_id!r}: {model!r}"
            )
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
) -> None:
    """Apply progressive prompting settings to all worker stages.

    When ``wait_messages`` is provided, every worker stage gets
    ``progressive=True`` with the given messages and trigger.
    Non-worker stages (aggregator, audit, merge) are left unchanged.
    """
    if not wait_messages:
        return
    for stage in dispatch.formation.stages:
        if stage.kind == "worker":
            stage.progressive = True
            stage.wait_messages = list(wait_messages)
            stage.trigger = trigger or ""


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
                stage=stage.id, original=stage.model, remapped=default,
            )
            stage.model = default
            wp = dispatch.worker_prompt_for(stage.id)
            if wp is not None:
                wp.model = default


def _apply_credentialed_worker_models(
    dispatch: DispatchResult,
    config: ChimeraConfig,
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
    * Remap target: ``defaults.default_worker`` when usable, else the first
      credentialed enabled model in catalog order.  Aggregator/merge/audit
      stages and the dispatcher model are untouched — the engine already
      retries a failed aggregator with ``defaults.default_aggregator``.
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
    usable = credentialed_enabled_models(config)
    if not usable:
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
    registry = blocked_models.shared_registry
    blocked_stages = [
        stage
        for stage in dispatch.formation.stages
        if stage.kind == "worker"
        and _credential_block_active(registry, config, stage.model)
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
        dispatch.dispatch_note = (
            f"{dispatch.dispatch_note}; {note}" if dispatch.dispatch_note else note
        )


class Engine:
    """Runs the full pipeline: dispatcher → workers → aggregator → (merge/audit).

    On construction the config is deep-copied into an immutable snapshot.
    All in-flight requests read from the snapshot, not the caller's live
    object, so configuration is stable for the lifetime of the Engine instance.

    Mutation checks on the caller's original config object are logged as
    warnings so operators know when a change they made won't take effect.
    """

    # Fast checksum of struct fields to detect external mutations.
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

    def __init__(self, config: ChimeraConfig, gateway: Gateway) -> None:
        self._config_original = config
        self._config = config.model_copy(deep=True)
        self._config_checksum = self._compute_config_checksum(self._config_original)
        self.gateway = gateway
        self.dispatcher = Dispatcher(self._config, gateway)
        self.aggregator = Aggregator(self._config, gateway)

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

    async def deliberate(
        self,
        user_prompt: str,
        formation: str = "auto",
        overrides: DeliberationOverrides | None = None,
        *,
        output_schema: dict[str, Any] | None = None,
        dag: dict[str, Any] | None = None,
        allow_custom_dag: bool = False,
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
                ``ValueError`` is raised. When enabled, the dispatcher skips the
                DESIGN pass and only fills in per-stage prompts/instructions.
            allow_custom_dag: Must be True for ``dag`` to be accepted.
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
            if (
                overrides
                and overrides.dispatcher_model
                and not self.config.defaults.lock_dispatcher
            )
            else None
        )
        outcome = await self.dispatcher.dispatch(
            user_prompt, formation,
            custom_dag=custom_formation, model_override=disp_override,
        )
        dispatch_span = self._build_dispatch_span(outcome, formation)

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
        # custom DAGs keep their configured structure).
        _apply_credentialed_worker_models(outcome.result, self.config)

        # Global request-level overrides (worker/aggregator models). Config
        # locks (defaults.lock_aggregator / lock_dispatcher) take precedence:
        # a locked role keeps its configured default and the discarded
        # override is recorded in the trace via dispatch_note.
        _apply_global_model_overrides(outcome.result, overrides, self.config)

        # Apply per-stage model overrides (Feature 2). Unknown stages warn;
        # unknown models raise ValueError. Done after dispatch so it applies to
        # auto, preset, and custom DAGs alike.
        stage_models = overrides.stage_models if overrides else None
        _apply_stage_models(outcome.result, stage_models, self.config)
        if overrides:
            _apply_allowed_models(outcome.result, overrides.allowed_models, self.config)
            _apply_progressive(
                outcome.result, overrides.wait_messages, overrides.trigger,
            )

        # DF-CHIMERA-V2-6: a model whose provider credential was rejected
        # (present-but-invalid key → 401) is durably blocked, so it must not
        # reach a worker stage again — not even when a preset or an explicit
        # stage_models override names it. Runs last so the block outranks the
        # explicit choice; self-clears when the key is replaced.
        _apply_unblocked_worker_models(outcome.result, self.config)

        log.info(
            "engine_dispatched",
            source=outcome.result.source,
            stages=outcome.result.formation.stage_ids(),
        )

        # Client-provided schema wins; dispatcher's is the fallback.
        effective_schema = (
            output_schema
            or (overrides.output_schema if overrides else None)
            or outcome.result.output_schema
        )

        stage_spans, stage_results = await self._run_dag(
            outcome.result, user_prompt, request_id, effective_schema,
            timeout_total_s=overrides.timeout_total_s if overrides else None,
            timeout_per_stage_s=overrides.timeout_per_stage_s if overrides else None,
            max_tokens=overrides.max_tokens if overrides else None,
        )

        # Extract iteration count from the results sentinel (stored by _run_dag).
        iteration_count: int = stage_results.pop("_iteration_count", 1)  # type: ignore[misc]

        answer, answer_stage_id = self._select_answer(outcome.result.formation, stage_results)
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
        return DeliberationResult(
            answer=answer,
            trace=trace,
            answer_degraded=answer_degraded,
            answer_error=answer_error,
        )

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
                    )
                )
                for s in ready
            ]
            outcomes = await asyncio.gather(*tasks)
            for stage, (result, span) in zip(ready, outcomes, strict=False):
                span.iteration = iteration_counts.get(stage.id, 0) + 1
                results[stage.id] = result
                spans[stage.id] = span

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
                span = spans.get(stage.id)
                if span is None or not self._check_iteration_needed(stage, span):
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
                        stage, dispatch, results, spans,
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
    ) -> tuple[StageResult, StageSpan]:
        dep_results = [results[d] for d in stage.depends_on if d in results]

        # Resolve per-stage timeout: request → config → code default
        cfg_timeout = self._config.timeout
        per_stage = (
            timeout_per_stage_s
            if timeout_per_stage_s is not None
            else cfg_timeout.per_stage_s
        )
        # Clamp per-stage to total if total is set
        if timeout_total_s is not None and timeout_total_s > 0:
            per_stage = min(per_stage, timeout_total_s) if per_stage > 0 else timeout_total_s
        if per_stage <= 0:
            per_stage = None  # unlimited

        start = time.monotonic()
        messages: list[dict[str, str]] = []
        try:
            messages, response = await asyncio.wait_for(
                self._call_stage(stage, dispatch, dep_results, user_prompt, output_schema,
                                 iteration_feedback=iteration_feedback, max_tokens=max_tokens),
                timeout=per_stage,
            )
        except TimeoutError:
            latency_ms = int((time.monotonic() - start) * 1000)
            log.warning(
                "engine_stage_timeout",
                stage=stage.id,
                model=stage.model,
                timeout_s=per_stage or 0,
            )
            return self._degraded_stage(
                stage,
                GatewayError(f"timed out after {per_stage or 0:.0f}s"),
                [],
                latency_ms,
                started_at=start,
            )
        except (GatewayError, BudgetExhaustedError) as exc:
            return await self._handle_stage_failure(
                stage, dispatch, dep_results, user_prompt, output_schema, exc, start,
            )

        return self._build_stage_result(stage, response, messages, start, user_prompt,
                                        dispatch, dep_results)

    async def _handle_stage_failure(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        dep_results: list[StageResult],
        user_prompt: str,
        output_schema: dict[str, Any] | None,
        exc: Exception,
        start: float,
    ) -> tuple[StageResult, StageSpan]:
        """Retry aggregator/merge/audit stages: model fallback → plain-text fallback."""
        latency_ms = int((time.monotonic() - start) * 1000)
        log.warning("engine_stage_failed", stage=stage.id, model=stage.model, error=str(exc))

        if stage.kind not in {"aggregator", "merge", "audit"}:
            return self._degraded_stage(stage, exc, [], latency_ms, started_at=start)

        fallback_model = self.config.defaults.default_aggregator

        # Retry 1: different model, same output_schema (if model differs)
        if stage.model != fallback_model:
            retry_stage = stage.model_copy(update={"model": fallback_model})
            try:
                messages, response = await self._call_stage(
                    retry_stage, dispatch, dep_results, user_prompt, output_schema,
                )
                log.info(
                    "engine_stage_retry_ok",
                    stage=stage.id, original=stage.model, fallback=fallback_model,
                )
                return self._build_stage_result(stage, response, messages, start,
                                                user_prompt, dispatch, dep_results)
            except GatewayError:
                pass  # fall through to plain-text retry

        # Retry 2: plain text (no output_schema) — catches json_schema/json_object
        # provider incompatibilities (e.g. DeepSeek requires "json" in prompt).
        try:
            messages, response = await self._call_stage(
                stage, dispatch, dep_results, user_prompt, output_schema=None,
            )
            log.info(
                "engine_stage_retry_plaintext",
                stage=stage.id, model=stage.model,
            )
            return self._build_stage_result(stage, response, messages, start,
                                            user_prompt, dispatch, dep_results)
        except GatewayError as exc2:
            return self._degraded_stage(stage, exc2, [], latency_ms, started_at=start)

    def _build_stage_result(
        self,
        stage: Stage,
        response: GatewayResponse,
        messages: list[dict[str, str]],
        start: float,
        user_prompt: str,
        dispatch: DispatchResult,
        dep_results: list[StageResult],
    ) -> tuple[StageResult, StageSpan]:
        """Build a (StageResult, StageSpan) pair for a successful stage call."""
        latency_ms = int((time.monotonic() - start) * 1000)
        prompt_text = _last_user_content(messages) if messages else _aggregator_prompt_summary(
            stage, dispatch, dep_results
        )
        ended = time.monotonic()
        # QA-CHIMERA-V2-16: the route the gateway resolved for this call, read
        # off the response's metadata side-band (empty for a gateway that
        # carries none, e.g. a test double).
        provider, wire_model, api_base = _route_attribution(response)
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
    ) -> tuple[list[dict[str, str]], GatewayResponse]:
        """Make the actual model call for a stage; returns (messages, response)."""
        if stage.kind == "worker":
            messages = self._worker_messages(stage, dispatch, user_prompt,
                                             iteration_feedback=iteration_feedback)
            # Progressive prompting: feed context piece-by-piece before the real call.
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
            return messages, response
        response = await self.aggregator.execute(
            stage, dispatch, dep_results, user_prompt,
            output_schema=output_schema,
            max_prompt_tokens=self.config.max_aggregator_context_tokens,
            max_tokens=max_tokens,
        )

        # ── Mechanical schema validation for AUDIT stages ──────────
        if stage.kind == "audit" and output_schema is not None:
            validation_error = self._validate_against_schema(
                output_schema, response.text,
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

        return [], response

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
            _last_user_content(messages)
            if messages
            else f"(degraded {stage.kind} stage '{stage.id}')"
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
    def _validate_against_schema(
        schema: dict[str, Any], output: str
    ) -> dict[str, Any] | None:
        """Mechanically validate *output* against *schema*.

        Returns ``None`` on success (output is valid), or a dict suitable
        for embedding in the audit response::

            {"passed": false, "errors": [...]}

        Only the EXTRACTION of the instance is tolerant: a model answer
        that wraps its JSON in a code fence or in prose is recovered by
        :meth:`_extract_json_value`. The schema check itself is unchanged —
        the extracted instance faces the same strict
        :func:`jsonschema.validate` call, with no coercion or defaults.
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
        try:
            jsonschema.validate(instance=instance, schema=schema)
        except jsonschema.ValidationError as exc:
            return {"passed": False, "errors": [str(exc)]}
        return None  # passed

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
            starts = [
                idx
                for idx in (candidate.find("{"), candidate.find("["))
                if idx != -1
            ]
            if not starts:
                continue
            try:
                value, _end = json.JSONDecoder().raw_decode(candidate[min(starts):])
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
            parts.append(
                f"## Re-iteration feedback from {trigger.id}\n"
                f"{trigger_span.response[:2000]}"
            )
        # Include all direct upstream results for context
        for dep_id in trigger.depends_on:
            dep_result = results.get(dep_id)
            if dep_result is not None:
                parts.append(
                    f"## Context from upstream {dep_id}\n"
                    f"{dep_result.response.text[:1000]}"
                )
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
        # QA-CHIMERA-V2-16: the dispatch span is an INTERNAL pipeline stage, not
        # a provider route of its own, so it deliberately carries no route
        # attribution (provider/wire_model/api_base keep their empty defaults).
        # Attribution is never fabricated here.
        return StageSpan(
            stage_id="dispatch",
            kind="dispatch",
            model=dispatch_model,
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
        )

    def _select_answer(
        self, dag: FormationDAG, results: dict[str, StageResult]
    ) -> tuple[str, str]:
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
        body = stripped[first_nl + 1:]
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
        dispatch_span: StageSpan,
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
        all_spans: list[StageSpan] = [dispatch_span, *stage_spans.values()]
        total_cost = round(sum(s.cost for s in all_spans), 6)
        total_tokens = sum(s.tokens_input + s.tokens_output for s in all_spans)
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
            worker_failures=list(worker_failures or []),
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
            failures.append(
                WorkerFailure(stage_id=stage_id, model=result.model, error=error)
            )
            blocked_models.shared_registry.record_failure(
                result.model,
                error,
                credential_fingerprint=(
                    model_credential_fingerprint(config, result.model)
                    if config is not None
                    else None
                ),
            )
        return failures


def _aggregator_prompt_summary(
    stage: Stage, dispatch: DispatchResult, deps: list[StageResult]
) -> str:
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
