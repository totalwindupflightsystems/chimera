"""The formation engine — runs the dispatcher-designed DAG.

Executes stages in dependency waves: all stages whose dependencies are met run
concurrently via :func:`asyncio.gather`. Every call is traced into a
:class:`DeliberationTrace` (prompt, response, tokens, latency, cost).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

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
#: Tests monkeypatch this module global to exercise the timeout path quickly.
DEFAULT_STAGE_TIMEOUT_S: float = 120.0


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
        stage = dispatch.formation.stage(stage_id)
        stage.model = model
        if stage.kind == "worker":
            wp = dispatch.worker_prompt_for(stage_id)
            if wp is not None:
                wp.model = model


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
            outcome.result, user_prompt, request_id, effective_schema
        )

        answer, answer_stage_id = self._select_answer(outcome.result.formation, stage_results)
        trace = self._assemble_trace(
            request_id=request_id,
            formation=formation,
            dispatch=outcome.result,
            dispatch_span=dispatch_span,
            stage_spans=stage_spans,
            answer_stage_id=answer_stage_id,
            started=started,
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
    ) -> tuple[dict[str, StageSpan], dict[str, StageResult]]:
        dag = dispatch.formation
        topo = dag.topo_order()
        spans: dict[str, StageSpan] = {}
        results: dict[str, StageResult] = {}

        remaining = list(topo)
        while remaining:
            ready = [s for s in remaining if all(d in results for d in s.depends_on)]
            if not ready:
                raise RuntimeError("DAG has unresolvable dependencies")
            outcomes = await asyncio.gather(
                *(self._execute_stage(s, dispatch, results, user_prompt, output_schema) for s in ready)
            )
            for stage, (result, span) in zip(ready, outcomes, strict=False):
                results[stage.id] = result
                spans[stage.id] = span
                log.info(
                    "engine_stage_done",
                    stage=stage.id,
                    kind=stage.kind,
                    model=span.model,
                    latency_ms=span.latency_ms,
                    tokens=span.tokens_input + span.tokens_output,
                )
            remaining = [s for s in remaining if s not in ready]

        return spans, results

    async def _execute_stage(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        results: dict[str, StageResult],
        user_prompt: str,
        output_schema: dict[str, Any] | None = None,
    ) -> tuple[StageResult, StageSpan]:
        dep_results = [results[d] for d in stage.depends_on if d in results]

        start = time.monotonic()
        messages: list[dict[str, str]] = []
        try:
            messages, response = await asyncio.wait_for(
                self._call_stage(stage, dispatch, dep_results, user_prompt, output_schema),
                timeout=DEFAULT_STAGE_TIMEOUT_S,
            )
        except TimeoutError:
            latency_ms = int((time.monotonic() - start) * 1000)
            log.warning(
                "engine_stage_timeout",
                stage=stage.id,
                model=stage.model,
                timeout=DEFAULT_STAGE_TIMEOUT_S,
            )
            return self._degraded_stage(
                stage,
                GatewayError(f"timed out after {DEFAULT_STAGE_TIMEOUT_S}s"),
                [],
                latency_ms,
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
            return self._degraded_stage(stage, exc, [], latency_ms)

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
            return self._degraded_stage(stage, exc2, [], latency_ms)

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
    ) -> tuple[list[dict[str, str]], GatewayResponse]:
        """Make the actual model call for a stage; returns (messages, response)."""
        if stage.kind == "worker":
            messages = self._worker_messages(stage, dispatch, user_prompt)
            response = await self.gateway.complete(stage.model, messages, temperature=0.3)
            return messages, response
        response = await self.aggregator.execute(
            stage, dispatch, dep_results, user_prompt, output_schema=output_schema,
        )
        return [], response

    def _degraded_stage(
        self,
        stage: Stage,
        error: Exception,
        messages: list[dict[str, str]],
        latency_ms: int,
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
        )
        result = StageResult(
            stage_id=stage.id,
            model=stage.model,
            prompt=prompt_text,
            response=degraded_response,
            degraded=True,
        )
        return result, span

    def _worker_messages(
        self,
        stage: Stage,
        dispatch: DispatchResult,
        user_prompt: str,
    ) -> list[dict[str, str]]:
        wp = dispatch.worker_prompt_for(stage.id)
        task = wp.prompt if wp and wp.prompt else "Solve the user's request."
        return [
            {
                "role": "user",
                "content": f"## User request\n{user_prompt}\n\n## Your assigned task\n{task}",
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
