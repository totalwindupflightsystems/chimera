"""Tests for the formation engine — DAG execution, tracing, and answer selection."""

from __future__ import annotations

import json

import pytest

from chimera.engine import Engine
from chimera.gateway import GatewayError
from tests.conftest import FakeGateway, dispatch_json, resp


def _engine_responder(config, payload: str | None = None):  # type: ignore[no-untyped-def]
    """Responder that distinguishes dispatcher / worker / aggregator calls.

    Dispatcher calls carry ``response_format``; aggregator calls contain
    "Upstream outputs"; everything else is a worker.
    """
    _payload = payload or dispatch_json(
        workers=[("worker_1", "deepseek/deepseek-chat"),
                 ("worker_2", "openrouter/google/gemini-2.5-flash")],
        aggregator_instructions="Merge code (worker_1) and design (worker_2).",
    )

    def _responder(model, messages, response_format=None, **kw):
        if response_format is not None:  # dispatcher
            return resp(_payload, model, tok_in=120, tok_out=180)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:  # aggregator/merge/audit
            return resp(f"[FINAL MERGED ANSWER from {model}]", model, tok_in=60, tok_out=90)
        return resp(f"[worker output {model}]", model, tok_in=25, tok_out=35)

    return _responder


@pytest.mark.asyncio
async def test_full_auto_deliberation(config) -> None:  # type: ignore[no-untyped-def]
    gw = FakeGateway(_engine_responder(config))
    result = await Engine(config, gw).deliberate("Design + build a service", "auto")

    # answer comes from the aggregator stage
    assert result.answer == "[FINAL MERGED ANSWER from zai-coding-plan/glm-5.2]"
    trace = result.trace
    assert trace.formation == "auto"
    assert trace.dispatch.kind == "dispatch"
    assert len(trace.workers) == 2
    assert trace.aggregator is not None
    assert trace.aggregator.kind == "aggregator"
    # answer stage is the aggregator
    assert trace.answer_stage_id == "aggregator"

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
    all_spans = [trace.dispatch, *trace.workers, trace.aggregator]
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
    judges = [s for s in trace.stages if s.kind == "aggregator"]
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
        def __init__(self):
            super().__init__()
            self._dispatch_calls = 0
        async def complete(self, model, messages, response_format=None, **kw):
            if response_format is not None:
                self._dispatch_calls += 1
                if self._dispatch_calls == 1:
                    raise GatewayError("dispatcher down")
                # Subsequent structured calls (aggregator) produce a normal answer
                return resp(f"output from {model}", model, 10, 10)
            return resp(f"output from {model}", model)
    gw = FlakyGateway()
    result = await Engine(config, gw).deliberate("task", "auto")
    assert result.trace.source == "fallback"
    # still got a aggregator-merged answer
    assert result.answer.startswith("output from")


@pytest.mark.asyncio
async def test_worker_failure_degrades_instead_of_crashing(config) -> None:  # type: ignore[no-untyped-def]
    class PartialGateway(FakeGateway):
        async def complete(self, model, messages, response_format=None, **kw):
            if response_format is not None:
                return resp(dispatch_json(), model, 10, 10)
            if "Upstream outputs" in json.dumps(messages):  # aggregator
                return resp("AGGREGATOR ANSWER", model, 10, 10)
            # workers fail
            raise GatewayError(f"{model} unavailable")

    gw = PartialGateway()
    result = await Engine(config, gw).deliberate("task", "auto")
    # pipeline completed despite all workers failing; aggregator still answered
    assert result.answer == "AGGREGATOR ANSWER"
    for w in result.trace.workers:
        assert "unavailable" in w.response
        assert w.cost == 0.0


@pytest.mark.asyncio
async def test_aggregator_failure_retries_with_default_aggregator(config) -> None:  # type: ignore[no-untyped-def]
    # Dispatcher picks a aggregator model that fails; engine should retry with the
    # default aggregator (zai-coding-plan/glm-5.2) so the user still gets an answer.
    failing_aggregator = "openrouter/anthropic/claude-sonnet-4"
    payload = dispatch_json(
        workers=[("worker_1", "deepseek/deepseek-chat")],
        aggregator=failing_aggregator,
    )
    default_aggregator = config.defaults.default_aggregator

    class RetryGateway(FakeGateway):
        async def complete(self, model, messages, response_format=None, **kw):
            if response_format is not None:
                return resp(payload, model, 10, 10)
            if model == failing_aggregator:
                raise GatewayError(f"{model} down")
            if "Upstream outputs" in json.dumps(messages):  # aggregator retry on default
                return resp("RECOVERED ANSWER", default_aggregator, 10, 10)
            return resp("worker output", model, 10, 10)

    gw = RetryGateway()
    result = await Engine(config, gw).deliberate("task", "auto")
    assert result.answer == "RECOVERED ANSWER"
    # trace records the fallback aggregator model that actually produced the answer
    assert result.trace.aggregator.model == default_aggregator
    assert result.trace.aggregator.response == "RECOVERED ANSWER"


@pytest.mark.asyncio
async def test_cost_reflects_tiers(config) -> None:  # type: ignore[no-untyped-def]
    gw = FakeGateway(_engine_responder(config))
    result = await Engine(config, gw).deliberate("task", "auto")
    # premium dispatcher/aggregator cost per token exceeds budget worker cost per token
    dispatch_rate = config.get_model(result.trace.dispatch.model).cost_rate_output()
    worker_rate = config.get_model(result.trace.workers[0].model).cost_rate_output()
    assert dispatch_rate > worker_rate
    assert result.trace.dispatch.cost > 0
    assert result.trace.workers[0].cost > 0


@pytest.mark.asyncio
async def test_multi_level_aggregation_dag(config) -> None:  # type: ignore[no-untyped-def]
    """The dispatcher can design worker→aggregator→worker→aggregator chains."""
    from chimera.dispatcher import build_preset_dag
    # Use the debate preset which has 3 workers + 2 aggregators + merge
    dag = build_preset_dag(config.formations["debate"], config)
    kinds = {s.kind for s in dag.stages}
    assert "worker" in kinds
    assert "aggregator" in kinds
    aggregators = [s for s in dag.stages if s.kind == "aggregator"]
    assert len(aggregators) == 2, f"debate formation should have 2 aggregators, got {len(aggregators)}"
    # Verify merge stage exists (multi-level aggregation proof)
    merge_stages = [s for s in dag.stages if s.kind == "merge"]
    assert len(merge_stages) == 1, "debate formation should have 1 merge stage"


@pytest.mark.asyncio
async def test_output_schema_passed_to_aggregator(config) -> None:  # type: ignore[no-untyped-def]
    """The aggregator passes the output_schema as response_format to the gateway."""
    from chimera.aggregator import Aggregator
    from chimera.dispatcher import Stage, DispatchResult, FormationDAG
    
    client_schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}, "score": {"type": "integer"}},
        "required": ["summary", "score"],
    }
    captured_rf = []

    class CaptureGateway(FakeGateway):
        async def complete(self, model, messages, **kw):
            rf = kw.get("response_format")
            if rf is not None:
                captured_rf.append(rf)
            return resp('{"summary":"test","score":42}', model)

    gw = CaptureGateway()
    agg = Aggregator(config, gw)
    
    # Minimal dispatch + stage
    stage = Stage(id="aggregator", kind="aggregator", model=config.defaults.default_aggregator)
    dag = FormationDAG(stages=[stage], edges=[])
    dispatch = DispatchResult(
        formation=dag,
        worker_prompts=[],
        aggregator_instructions="Merge the worker outputs.",
        source="auto",
    )
    
    await agg.execute(stage, dispatch, [], "task", output_schema=client_schema)
    
    assert len(captured_rf) == 1, f"Expected 1 captured response_format, got {len(captured_rf)}"
    rf = captured_rf[0]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["schema"]["required"] == ["summary", "score"]


# --------------------------------------------------------------------------- #
# Per-stage model selection (Feature 2)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stage_models_override_applied_correctly(config) -> None:  # type: ignore[no-untyped-def]
    """stage_models forces a specific model onto a stage after dispatch."""
    from chimera.config import DeliberationOverrides

    gw = FakeGateway(_engine_responder(config))
    overrides = DeliberationOverrides(
        stage_models={"worker_1": "zai-coding-plan/glm-5.2"}
    )
    result = await Engine(config, gw).deliberate("task", "auto", overrides=overrides)
    worker_models = {w.stage_id: w.model for w in result.trace.workers}
    # worker_1 forced to glm-5.2; worker_2 untouched (gemini-flash from dispatcher)
    assert worker_models["worker_1"] == "zai-coding-plan/glm-5.2"
    assert worker_models["worker_2"] == "openrouter/google/gemini-2.5-flash"


@pytest.mark.asyncio
async def test_stage_models_unknown_stage_warns_not_crash(config) -> None:  # type: ignore[no-untyped-def]
    """An unknown stage id in stage_models is warned and skipped, not fatal."""
    from chimera.config import DeliberationOverrides

    gw = FakeGateway(_engine_responder(config))
    overrides = DeliberationOverrides(
        stage_models={
            "worker_1": "zai-coding-plan/glm-5.2",
            "does_not_exist": "deepseek/deepseek-chat",
        }
    )
    result = await Engine(config, gw).deliberate("task", "auto", overrides=overrides)
    # Still completes; the known override was applied, the unknown ignored.
    worker_models = {w.stage_id: w.model for w in result.trace.workers}
    assert worker_models["worker_1"] == "zai-coding-plan/glm-5.2"


@pytest.mark.asyncio
async def test_stage_models_unknown_model_rejected(config) -> None:  # type: ignore[no-untyped-def]
    """An unknown model name in stage_models raises ValueError (validated)."""
    from chimera.config import DeliberationOverrides

    gw = FakeGateway(_engine_responder(config))
    overrides = DeliberationOverrides(
        stage_models={"worker_1": "no/such/model"}
    )
    with pytest.raises(ValueError, match="unknown model"):
        await Engine(config, gw).deliberate("task", "auto", overrides=overrides)


@pytest.mark.asyncio
async def test_stage_models_overrides_aggregator_too(config) -> None:  # type: ignore[no-untyped-def]
    """stage_models can also retarget non-worker (aggregator) stages."""
    from chimera.config import DeliberationOverrides

    gw = FakeGateway(_engine_responder(config))
    overrides = DeliberationOverrides(
        stage_models={"aggregator": "deepseek/deepseek-chat"}
    )
    result = await Engine(config, gw).deliberate("task", "auto", overrides=overrides)
    assert result.trace.aggregator is not None
    assert result.trace.aggregator.model == "deepseek/deepseek-chat"


# --------------------------------------------------------------------------- #
# Client-defined DAG (Feature 1) via the engine
# --------------------------------------------------------------------------- #


def _client_dag_dict() -> dict[str, object]:
    return {
        "stages": [
            {"id": "researcher", "kind": "worker",
             "model": "deepseek/deepseek-chat"},
            {"id": "finalizer", "kind": "aggregator",
             "model": "zai-coding-plan/glm-5.2", "depends_on": ["researcher"]},
        ],
        "edges": [["researcher", "finalizer"]],
    }


@pytest.mark.asyncio
async def test_client_dag_accepted_with_allow_custom_dag(config) -> None:  # type: ignore[no-untyped-def]
    """allow_custom_dag=True: engine runs the client DAG, source == 'custom'."""
    gw = FakeGateway(_engine_responder(config))
    result = await Engine(config, gw).deliberate(
        "task", "auto", dag=_client_dag_dict(), allow_custom_dag=True
    )
    assert result.trace.source == "custom"
    stage_ids = {s.stage_id for s in result.trace.stages}
    assert stage_ids == {"researcher", "finalizer"}
    # Answer is produced by the terminal aggregator stage
    assert result.trace.answer_stage_id == "finalizer"
    assert result.answer.startswith("[FINAL MERGED ANSWER")


@pytest.mark.asyncio
async def test_client_dag_rejected_without_allow_custom_dag(config) -> None:  # type: ignore[no-untyped-def]
    """allow_custom_dag=False (default): supplying a dag raises ValueError."""
    gw = FakeGateway(_engine_responder(config))
    with pytest.raises(ValueError, match="allow_custom_dag=True"):
        await Engine(config, gw).deliberate(
            "task", "auto", dag=_client_dag_dict(), allow_custom_dag=False
        )


@pytest.mark.asyncio
async def test_client_dag_invalid_model_rejected_at_engine(config) -> None:  # type: ignore[no-untyped-def]
    """Invalid model in client DAG is rejected when building the DAG."""
    bad_dag = {
        "stages": [
            {"id": "w", "kind": "worker", "model": "no/such/model"},
            {"id": "a", "kind": "aggregator", "model": "zai-coding-plan/glm-5.2",
             "depends_on": ["w"]},
        ],
        "edges": [["w", "a"]],
    }
    gw = FakeGateway(_engine_responder(config))
    with pytest.raises(ValueError, match="unknown model"):
        await Engine(config, gw).deliberate(
            "task", "auto", dag=bad_dag, allow_custom_dag=True
        )


# --------------------------------------------------------------------------- #
# Per-stage timeout (Fix 3)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stage_timeout_produces_degraded_result(config, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    """A worker exceeding the stage timeout is cancelled and degraded; the
    deliberation still completes via the aggregator."""
    import asyncio
    import chimera.engine as engine_mod

    # Shrink the timeout so the test is fast; workers sleep past it.
    monkeypatch.setattr(engine_mod, "DEFAULT_STAGE_TIMEOUT_S", 0.05)

    class SlowWorkerGateway(FakeGateway):
        async def complete(self, model, messages, response_format=None, **kw):
            if response_format is not None:  # dispatcher
                return resp(dispatch_json(), model, 10, 10)
            if "Upstream outputs" in json.dumps(messages):  # aggregator
                return resp("AGG ANSWER", model, 10, 10)
            await asyncio.sleep(1.0)  # worker exceeds timeout
            return resp("never returns", model)

    gw = SlowWorkerGateway()
    result = await Engine(config, gw).deliberate("task", "auto")

    # Aggregator still answered despite every worker timing out.
    assert result.answer == "AGG ANSWER"
    for w in result.trace.workers:
        assert "timed out" in w.response
        assert w.cost == 0.0
