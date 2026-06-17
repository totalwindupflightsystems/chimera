"""Tests for the formation engine — DAG execution, tracing, and answer selection."""

from __future__ import annotations

import json

import pytest

from chimera.engine import Engine
from chimera.gateway import GatewayError
from tests.conftest import FakeGateway, dispatch_json, resp


def _engine_responder(config, payload: str | None = None):  # type: ignore[no-untyped-def]
    """Responder that distinguishes dispatcher / worker / judge calls.

    Dispatcher calls carry ``response_format``; judge calls contain
    "Upstream outputs"; everything else is a worker.
    """
    _payload = payload or dispatch_json(
        workers=[("worker_1", "deepseek/deepseek-chat"),
                 ("worker_2", "openrouter/google/gemini-2.5-flash")],
        judge_instructions="Merge code (worker_1) and design (worker_2).",
    )

    def _responder(model, messages, response_format=None, **kw):
        if response_format is not None:  # dispatcher
            return resp(_payload, model, tok_in=120, tok_out=180)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:  # judge/merge/audit
            return resp(f"[FINAL MERGED ANSWER from {model}]", model, tok_in=60, tok_out=90)
        return resp(f"[worker output {model}]", model, tok_in=25, tok_out=35)

    return _responder


@pytest.mark.asyncio
async def test_full_auto_deliberation(config) -> None:  # type: ignore[no-untyped-def]
    gw = FakeGateway(_engine_responder(config))
    result = await Engine(config, gw).deliberate("Design + build a service", "auto")

    # answer comes from the judge stage
    assert result.answer == "[FINAL MERGED ANSWER from zai-coding-plan/glm-5.2]"
    trace = result.trace
    assert trace.formation == "auto"
    assert trace.dispatch.kind == "dispatch"
    assert len(trace.workers) == 2
    assert trace.judge is not None
    assert trace.judge.kind == "judge"
    # answer stage is the judge
    assert trace.answer_stage_id == "judge"

    # category-weighted routing: dispatcher assigned different worker models
    worker_models = sorted(w.model for w in trace.workers)
    assert worker_models == ["deepseek/deepseek-chat", "openrouter/google/gemini-2.5-flash"]

    # custom prompts were passed through (not identical)
    prompts = {w.stage_id: w.prompt for w in trace.workers}
    assert "Custom subtask for worker_1" in prompts["worker_1"]
    assert "Custom subtask for worker_2" in prompts["worker_2"]
    assert prompts["worker_1"] != prompts["worker_2"]


@pytest.mark.asyncio
async def test_trace_totals_aggregate(config) -> None:  # type: ignore[no-untyped-def]
    gw = FakeGateway(_engine_responder(config))
    result = await Engine(config, gw).deliberate("task", "auto")
    trace = result.trace
    all_spans = [trace.dispatch, *trace.workers, trace.judge]
    expected_tokens = sum(s.tokens_input + s.tokens_output for s in all_spans)
    assert trace.total_tokens == expected_tokens
    expected_cost = round(sum(s.cost for s in all_spans), 6)
    assert trace.total_cost == expected_cost
    assert trace.total_duration_ms >= 0


@pytest.mark.asyncio
async def test_workers_get_custom_prompts_and_dispatcher_called_once(config) -> None:  # type: ignore[no-untyped-def]
    gw = FakeGateway(_engine_responder(config))
    await Engine(config, gw).deliberate("task", "auto")
    dispatcher_calls = [c for c in gw.calls if c[2].get("response_format")]
    assert len(dispatcher_calls) == 1
    worker_calls = [
        c for c in gw.calls
        if not c[2].get("response_format") and "Your assigned task" in c[1][0]["content"]
    ]
    assert len(worker_calls) == 2


@pytest.mark.asyncio
async def test_debate_formation_merges_multiple_judges(config) -> None:  # type: ignore[no-untyped-def]
    # dispatcher payload is ignored for preset structures, but must parse
    gw = FakeGateway(_engine_responder(config))
    result = await Engine(config, gw).deliberate("controversial claim", "debate")
    trace = result.trace
    # answer is produced by the merge stage
    assert trace.answer_stage_id == "merge"
    assert result.answer.startswith("[FINAL MERGED ANSWER")
    judges = [s for s in trace.stages if s.kind == "judge"]
    assert len(judges) == 2
    merge = [s for s in trace.stages if s.kind == "merge"]
    assert len(merge) == 1


@pytest.mark.asyncio
async def test_audit_formation_answer_from_audit(config) -> None:  # type: ignore[no-untyped-def]
    gw = FakeGateway(_engine_responder(config))
    result = await Engine(config, gw).deliberate("risky task", "audit")
    trace = result.trace
    assert trace.answer_stage_id == "audit"
    audit = [s for s in trace.stages if s.kind == "audit"]
    assert len(audit) == 1
    assert audit[0].model == "openrouter/anthropic/claude-sonnet-4"


@pytest.mark.asyncio
async def test_dispatcher_failure_still_produces_answer(config) -> None:  # type: ignore[no-untyped-def]
    class FlakyGateway(FakeGateway):
        async def complete(self, model, messages, response_format=None, **kw):
            if response_format is not None:
                raise GatewayError("dispatcher down")
            return resp(f"output from {model}", model)
    gw = FlakyGateway()
    result = await Engine(config, gw).deliberate("task", "auto")
    assert result.trace.source == "fallback"
    # still got a judge-merged answer
    assert result.answer.startswith("output from")


@pytest.mark.asyncio
async def test_worker_failure_degrades_instead_of_crashing(config) -> None:  # type: ignore[no-untyped-def]
    class PartialGateway(FakeGateway):
        async def complete(self, model, messages, response_format=None, **kw):
            if response_format is not None:
                return resp(dispatch_json(), model, 10, 10)
            if "Upstream outputs" in json.dumps(messages):  # judge
                return resp("JUDGE ANSWER", model, 10, 10)
            # workers fail
            raise GatewayError(f"{model} unavailable")

    gw = PartialGateway()
    result = await Engine(config, gw).deliberate("task", "auto")
    # pipeline completed despite all workers failing; judge still answered
    assert result.answer == "JUDGE ANSWER"
    for w in result.trace.workers:
        assert "unavailable" in w.response
        assert w.cost == 0.0


@pytest.mark.asyncio
async def test_judge_failure_retries_with_default_judge(config) -> None:  # type: ignore[no-untyped-def]
    # Dispatcher picks a judge model that fails; engine should retry with the
    # default judge (zai-coding-plan/glm-5.2) so the user still gets an answer.
    failing_judge = "openrouter/anthropic/claude-sonnet-4"
    payload = dispatch_json(
        workers=[("worker_1", "deepseek/deepseek-chat")],
        judge=failing_judge,
    )
    default_judge = config.defaults.default_judge

    class RetryGateway(FakeGateway):
        async def complete(self, model, messages, response_format=None, **kw):
            if response_format is not None:
                return resp(payload, model, 10, 10)
            if model == failing_judge:
                raise GatewayError(f"{model} down")
            if "Upstream outputs" in json.dumps(messages):  # judge retry on default
                return resp("RECOVERED ANSWER", default_judge, 10, 10)
            return resp("worker output", model, 10, 10)

    gw = RetryGateway()
    result = await Engine(config, gw).deliberate("task", "auto")
    assert result.answer == "RECOVERED ANSWER"
    # trace records the fallback judge model that actually produced the answer
    assert result.trace.judge.model == default_judge
    assert result.trace.judge.response == "RECOVERED ANSWER"


@pytest.mark.asyncio
async def test_cost_reflects_tiers(config) -> None:  # type: ignore[no-untyped-def]
    gw = FakeGateway(_engine_responder(config))
    result = await Engine(config, gw).deliberate("task", "auto")
    # premium dispatcher/judge cost per token exceeds budget worker cost per token
    dispatch_rate = config.get_model(result.trace.dispatch.model).cost_rate_output()
    worker_rate = config.get_model(result.trace.workers[0].model).cost_rate_output()
    assert dispatch_rate > worker_rate
    assert result.trace.dispatch.cost > 0
    assert result.trace.workers[0].cost > 0
