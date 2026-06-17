"""The formation engine — runs the dispatcher-designed DAG.

Executes stages in dependency waves: all stages whose dependencies are met run
concurrently via :func:`asyncio.gather`. Every call is traced into a
:class:`DeliberationTrace` (prompt, response, tokens, latency, cost).
"""

from __future__ import annotations

import asyncio
import time
import uuid

import structlog
from pydantic import BaseModel, Field

from chimera.config import ChimeraConfig, DeliberationOverrides
from chimera.dispatcher import (
    DispatchOutcome,
    DispatchResult,
    Dispatcher,
    FormationDAG,
    Stage,
)
from chimera.gateway import Gateway, GatewayError, GatewayResponse
from chimera.judge import Judge, StageResult
from chimera.observability import get_langfuse

log = structlog.get_logger("chimera.engine")


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
    judge: StageSpan | None = None
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


class Engine:
    """Runs the full pipeline: dispatcher → workers → judge → (merge/audit)."""

    def __init__(self, config: ChimeraConfig, gateway: Gateway) -> None:
        self.config = config
        self.gateway = gateway
        self.dispatcher = Dispatcher(config, gateway)
        self.judge = Judge(config, gateway)

    async def deliberate(
        self,
        user_prompt: str,
        formation: str = "auto",
        overrides: DeliberationOverrides | None = None,
    ) -> DeliberationResult:
        """Run the full deliberation pipeline and return the merged answer + trace.
        
        Args:
            user_prompt: The user's query.
            formation: Formation name or 'auto'.
            overrides: Request-level model overrides (allowed/disallowed/force models).
        """
        request_id = uuid.uuid4().hex[:16]
        structlog.contextvars.bind_contextvars(request_id=request_id, formation=formation)
        started = time.monotonic()

        outcome = await self.dispatcher.dispatch(user_prompt, formation)
        dispatch_span = self._build_dispatch_span(outcome, formation)

        log.info(
            "engine_dispatched",
            source=outcome.result.source,
            stages=outcome.result.formation.stage_ids(),
        )

        stage_spans, stage_results = await self._run_dag(
            outcome.result, user_prompt, request_id
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

    # ------------------------------------------------------------------ #
    # DAG execution
    # ------------------------------------------------------------------ #

    async def _run_dag(
        self,
        dispatch: DispatchResult,
        user_prompt: str,
        request_id: str,
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
                *(self._execute_stage(s, dispatch, results, user_prompt) for s in ready)
            )
            for stage, (result, span) in zip(ready, outcomes):
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
    ) -> tuple[StageResult, StageSpan]:
        dep_results = [results[d] for d in stage.depends_on if d in results]

        start = time.monotonic()
        messages: list[dict[str, str]] = []
        try:
            messages, response = await self._call_stage(stage, dispatch, dep_results, user_prompt)
        except GatewayError as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            log.warning("engine_stage_failed", stage=stage.id, model=stage.model, error=str(exc))
            # Answer-producing stages retry once with the default judge so the user
            # still gets a real answer if the dispatcher picked an unavailable judge.
            fallback_model = self.config.defaults.default_judge
            if stage.kind in {"judge", "merge", "audit"} and stage.model != fallback_model:
                retry_stage = stage.model_copy(update={"model": fallback_model})
                try:
                    messages, response = await self._call_stage(
                        retry_stage, dispatch, dep_results, user_prompt
                    )
                    log.info(
                        "engine_stage_retry_ok",
                        stage=stage.id, original=stage.model, fallback=fallback_model,
                    )
                except GatewayError as exc2:
                    return self._degraded_stage(stage, exc2, [], latency_ms)
            else:
                return self._degraded_stage(stage, exc, [], latency_ms)

        latency_ms = int((time.monotonic() - start) * 1000)

        prompt_text = _last_user_content(messages) if messages else _judge_prompt_summary(
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
    ) -> tuple[list[dict[str, str]], GatewayResponse]:
        """Make the actual model call for a stage; returns (messages, response)."""
        if stage.kind == "worker":
            messages = self._worker_messages(stage, dispatch, user_prompt)
            response = await self.gateway.complete(stage.model, messages, temperature=0.3)
            return messages, response
        response = await self.judge.execute(stage, dispatch, dep_results, user_prompt)
        return [], response

    def _degraded_stage(
        self,
        stage: Stage,
        error: GatewayError,
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
        primary_judge = next(
            (s for s in stage_spans.values() if s.kind in {"judge", "merge", "audit"}),
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
            judge=primary_judge,
            stages=list(stage_spans.values()),
            answer_stage_id=answer_stage_id,
            total_duration_ms=int((time.monotonic() - started) * 1000),
            total_cost=total_cost,
            total_tokens=total_tokens,
        )


def _judge_prompt_summary(
    stage: Stage, dispatch: DispatchResult, deps: list[StageResult]
) -> str:
    """Compact prompt string for judge spans (whose messages are built internally)."""
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
