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

from chimera.aggregator import Aggregator, StageResult
from chimera.config import ChimeraConfig, DeliberationOverrides
from chimera.dispatcher import (
    Dispatcher,
    DispatchOutcome,
    DispatchResult,
    FormationDAG,
    Stage,
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


class DeliberationResult(BaseModel):
    """The user-facing result of a deliberation."""

    answer: str
    trace: DeliberationTrace


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
        outcome = await self.dispatcher.dispatch(
            user_prompt, formation, custom_dag=custom_formation
        )
        dispatch_span = self._build_dispatch_span(outcome, formation)

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
        )

        # Extract iteration count from the results sentinel (stored by _run_dag).
        iteration_count: int = stage_results.pop("_iteration_count", 1)  # type: ignore[misc]

        answer, answer_stage_id = self._select_answer(outcome.result.formation, stage_results)
        answer = self._maybe_unwrap_envelope(answer)
        trace = self._assemble_trace(
            request_id=request_id,
            formation=formation,
            dispatch=outcome.result,
            dispatch_span=dispatch_span,
            stage_spans=stage_spans,
            answer_stage_id=answer_stage_id,
            started=started,
            iteration_count=iteration_count,
        )
        _maybe_langfuse(trace, user_prompt)
        structlog.contextvars.unbind_contextvars("request_id", "formation")
        return DeliberationResult(answer=answer, trace=trace)

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
                                 iteration_feedback=iteration_feedback),
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
        span = StageSpan(
            stage_id=stage.id,
            kind=stage.kind,
            model=response.model,
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
            response = await self.gateway.complete(stage.model, messages, temperature=0.3)
            return messages, response
        response = await self.aggregator.execute(
            stage, dispatch, dep_results, user_prompt,
            output_schema=output_schema,
            max_prompt_tokens=self.config.max_aggregator_context_tokens,
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
        )
        ended = time.monotonic()
        start_ts = started_at if started_at is not None else ended - (latency_ms / 1000.0)
        span = StageSpan(
            stage_id=stage.id,
            kind=stage.kind,
            model=stage.model,
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
        """
        try:
            instance = json.loads(output)
        except (json.JSONDecodeError, TypeError) as exc:
            return {"passed": False, "errors": [f"Output is not valid JSON: {exc}"]}
        try:
            jsonschema.validate(instance=instance, schema=schema)
        except jsonschema.ValidationError as exc:
            return {"passed": False, "errors": [str(exc)]}
        return None  # passed

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
        return StageSpan(
            stage_id="dispatch",
            kind="dispatch",
            model=self.config.defaults.dispatcher,
            prompt=prompt_text,
            response=resp.text,
            tokens_input=resp.tokens_input,
            tokens_output=resp.tokens_output,
            latency_ms=outcome.latency_ms,
            cost=_stage_cost(
                self.config.defaults.dispatcher,
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
    def _maybe_unwrap_envelope(text: str) -> str:
        """If text is a Chimera API response envelope, extract the answer field.

        Checks for a JSON dict with an ``answer`` key — if the value under
        ``answer`` is itself valid JSON, it is extracted (double-unwrap).
        Otherwise the raw ``answer`` value is returned.
        """
        import json as _json
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
                return inner
        except (_json.JSONDecodeError, TypeError, KeyError):
            pass
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
        )


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
]
