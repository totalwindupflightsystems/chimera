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
    from chimera.dispatcher import DispatchResult, FormationDAG, Stage

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


    # Shrink the timeout so the test is fast; workers sleep past it.
    monkeypatch.setattr(config.timeout, "per_stage_s", 0.05)

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


# --------------------------------------------------------------------------- #
# C2 — Partial worker failure resilience
# --------------------------------------------------------------------------- #

_THREE_WORKER_DISPATCH = dispatch_json(
    workers=[
        ("worker_1", "deepseek/deepseek-chat"),
        ("worker_2", "openrouter/google/gemini-2.5-flash"),
        ("worker_3", "deepseek/deepseek-chat"),
    ],
)


def _three_worker_responder(config, fail_workers: set[str] | None = None):
    """Responder for 3-worker dispatch. Workers in ``fail_workers`` raise errors."""
    fail = fail_workers or set()

    def _responder(model, messages, response_format=None, **kw):
        if response_format is not None:  # dispatcher
            return resp(_THREE_WORKER_DISPATCH, model, tok_in=120, tok_out=200)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:  # aggregator
            return resp("[FINAL MERGED ANSWER]", model, tok_in=60, tok_out=90)
        # Determine which worker from the messages
        for wid in ("worker_1", "worker_2", "worker_3"):
            if wid in joined and "Your assigned task" in joined:
                if wid in fail:
                    raise GatewayError(f"{wid} unavailable")
                return resp(f"[{wid} output]", model, tok_in=25, tok_out=35)
        return resp("[generic output]", model, tok_in=10, tok_out=20)

    return _responder


class _PartialFailureGateway(FakeGateway):
    """Gateway that fails specific workers by stage_id detection."""

    def __init__(self, config, fail_workers: set[str]):
        super().__init__()
        self._fail = fail_workers
        self._dispatch_sent = False

    async def complete(self, model, messages, response_format=None, **kw):
        self.calls.append((model, messages, {"temperature": kw.get("temperature", 0.2),
                                              "response_format": response_format, **kw}))
        if response_format is not None:  # dispatcher
            self._dispatch_sent = True
            return resp(_THREE_WORKER_DISPATCH, model, tok_in=120, tok_out=200)

        joined = json.dumps(messages)
        if "Upstream outputs" in joined:  # aggregator
            return resp("[FINAL MERGED ANSWER]", model, tok_in=60, tok_out=90)

        # Worker detection
        for wid in ("worker_1", "worker_2", "worker_3"):
            if wid in joined and "Your assigned task" in joined:
                if wid in self._fail:
                    raise GatewayError(f"{wid} unavailable")
                return resp(f"[{wid} output]", model, tok_in=25, tok_out=35)
        return resp("[generic output]", model, tok_in=10, tok_out=20)


@pytest.mark.asyncio
async def test_one_of_three_workers_fails_deliberation_completes(config) -> None:
    """C2: 1 of 3 workers fails → deliberation still completes with valid output."""
    gw = _PartialFailureGateway(config, fail_workers={"worker_1"})
    result = await Engine(config, gw).deliberate("task", "auto")
    # Deliberation completes successfully
    assert result.answer == "[FINAL MERGED ANSWER]"
    # Trace shows 3 workers: 1 degraded, 2 healthy
    assert len(result.trace.workers) == 3
    degraded = [w for w in result.trace.workers if "unavailable" in w.response]
    healthy = [w for w in result.trace.workers if "unavailable" not in w.response]
    assert len(degraded) == 1
    assert len(healthy) == 2


@pytest.mark.asyncio
async def test_two_of_three_workers_fail_degraded_answer(config) -> None:
    """C2: 2 of 3 workers fail → deliberation still completes with degraded
    worker inputs, aggregator produces an answer."""
    gw = _PartialFailureGateway(config, fail_workers={"worker_1", "worker_2"})
    result = await Engine(config, gw).deliberate("task", "auto")
    # Deliberation still completes (aggregator runs with partial inputs)
    assert result.answer == "[FINAL MERGED ANSWER]"
    assert len(result.trace.workers) == 3
    degraded = [w for w in result.trace.workers if "unavailable" in w.response]
    assert len(degraded) == 2


@pytest.mark.asyncio
async def test_three_of_three_workers_fail_clear_error(config) -> None:
    """C2: 3 of 3 workers fail → deliberation completes; aggregator receives
    all-degraded inputs and produces a clear response."""
    gw = _PartialFailureGateway(config, fail_workers={"worker_1", "worker_2", "worker_3"})
    result = await Engine(config, gw).deliberate("task", "auto")
    # Aggregator still runs and produces an answer
    assert result.answer == "[FINAL MERGED ANSWER]"
    # All 3 workers are degraded
    assert all("unavailable" in w.response for w in result.trace.workers)
    assert result.trace.aggregator is not None


# --------------------------------------------------------------------------- #
# Progressive prompting tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_progressive_worker_sends_wait_messages_then_trigger(config) -> None:
    """Progressive worker: wait_messages sent first, then trigger replaces prompt."""
    gw = FakeGateway(None)  # default responder, no custom logic needed

    dag = {
        "stages": [
            {
                "id": "thinker",
                "kind": "worker",
                "model": "deepseek/deepseek-chat",
                "depends_on": [],
                "progressive": True,
                "wait_messages": ["MSG-A: study this context", "MSG-B: absorb rules"],
                "trigger": "SIMON SAYS: now produce output",
            },
            {
                "id": "agg",
                "kind": "aggregator",
                "model": "zai-coding-plan/glm-5.2",
                "depends_on": ["thinker"],
            },
        ],
        "edges": [["thinker", "agg"]],
    }

    result = await Engine(config, gw).deliberate(
        "a test task", "auto", dag=dag, allow_custom_dag=True,
    )

    assert result.answer is not None

    # Calls: dispatcher + wait_msg_A + wait_msg_B + trigger_worker + aggregator
    # The dispatcher call has response_format, progressive calls have temperature=0.3
    all_calls = gw.calls
    assert len(all_calls) >= 5, f"Expected 5+ calls (dispatch + 2 wait + trigger + agg), got {len(all_calls)}"

    # Find all progressive/worker calls with temperature=0.3 (wait + trigger)
    temp03_calls = [
        c for c in all_calls
        if c[2].get("temperature") == 0.3
    ]
    # 2 wait calls + 1 trigger call = 3
    assert len(temp03_calls) == 3, f"Expected 3 temp=0.3 calls (2 wait + 1 trigger), got {len(temp03_calls)}"

    # Distinguish: wait-message calls have content matching wait_messages
    wait_calls = [
        c for c in temp03_calls
        if c[1] == [{"role": "user", "content": "MSG-A: study this context"}]
        or c[1] == [{"role": "user", "content": "MSG-B: absorb rules"}]
    ]
    assert len(wait_calls) == 2, f"Expected 2 wait-message calls, got {len(wait_calls)}"

    # The trigger call has the SIMON SAYS content
    trigger_calls = [
        c for c in temp03_calls
        if c[1] == [{"role": "user", "content": "SIMON SAYS: now produce output"}]
    ]
    assert len(trigger_calls) == 1, "Expected exactly 1 trigger call with SIMON SAYS message"


@pytest.mark.asyncio
async def test_progressive_without_trigger_keeps_original_prompt(config) -> None:
    """Progressive without trigger: wait_messages sent, original prompt kept."""
    gw = FakeGateway(None)

    dag = {
        "stages": [
            {
                "id": "thinker",
                "kind": "worker",
                "model": "deepseek/deepseek-chat",
                "depends_on": [],
                "progressive": True,
                "wait_messages": ["STEP 1: load context"],
                "trigger": "",  # empty — use original prompt
            },
            {
                "id": "agg",
                "kind": "aggregator",
                "model": "zai-coding-plan/glm-5.2",
                "depends_on": ["thinker"],
            },
        ],
        "edges": [["thinker", "agg"]],
    }

    result = await Engine(config, gw).deliberate(
        "test task", "auto", dag=dag, allow_custom_dag=True,
    )

    assert result.answer is not None

    # One wait call (temp=0.3) + one real worker call (temp=0.3)
    temp03_calls = [c for c in gw.calls if c[2].get("temperature") == 0.3]
    assert len(temp03_calls) == 2, f"Expected 2 temp=0.3 calls (1 wait + 1 real), got {len(temp03_calls)}"

    # Wait call has the STEP 1 content
    wait_calls = [c for c in temp03_calls if c[1] == [{"role": "user", "content": "STEP 1: load context"}]]
    assert len(wait_calls) == 1
    assert wait_calls[0][1] == [{"role": "user", "content": "STEP 1: load context"}]

    # The real worker call should have the dispatcher-assigned prompt, not just the trigger
    real_calls = [c for c in temp03_calls if c[1] != [{"role": "user", "content": "STEP 1: load context"}]]
    assert len(real_calls) == 1
    # Should contain the user's task, not just an empty trigger
    real_msgs = real_calls[0][1]
    assert len(real_msgs) >= 1
    user_content = " ".join(m["content"] for m in real_msgs if m["role"] == "user")
    assert "test task" in user_content, f"Expected user task in prompt, got: {user_content[:100]}"


@pytest.mark.asyncio
async def test_non_progressive_worker_skips_wait_messages(config) -> None:
    """Worker without progressive flag: no wait messages, no trigger substitution."""
    gw = FakeGateway(None)

    dag = {
        "stages": [
            {
                "id": "worker_1",
                "kind": "worker",
                "model": "deepseek/deepseek-chat",
                "depends_on": [],
                "progressive": False,
                "wait_messages": ["SHOULD NOT BE SENT"],
                "trigger": "SHOULD NOT BE USED",
            },
            {
                "id": "agg",
                "kind": "aggregator",
                "model": "zai-coding-plan/glm-5.2",
                "depends_on": ["worker_1"],
            },
        ],
        "edges": [["worker_1", "agg"]],
    }

    result = await Engine(config, gw).deliberate(
        "test", "auto", dag=dag, allow_custom_dag=True,
    )

    assert result.answer is not None

    # For non-progressive workers, the real call still uses temperature=0.3
    # But there should be NO calls matching wait_messages or trigger content
    temp03_calls = [c for c in gw.calls if c[2].get("temperature") == 0.3]

    # None of the calls should have wait_message or trigger content
    for call in temp03_calls:
        for msg in call[1]:
            if msg["role"] == "user":
                assert "SHOULD NOT BE SENT" not in msg["content"], (
                    f"Wait message leaked into non-progressive call: {msg['content'][:80]}"
                )
                assert "SHOULD NOT BE USED" not in msg["content"], (
                    f"Trigger leaked into non-progressive call: {msg['content'][:80]}"
                )


@pytest.mark.asyncio
async def test_progressive_via_overrides_applies_to_workers(config) -> None:
    """Progressive settings via DeliberationOverrides apply to all worker stages."""
    gw = FakeGateway(None)

    from chimera.config import DeliberationOverrides

    overrides = DeliberationOverrides(
        progressive=True,
        wait_messages=["OVERRIDE MSG 1", "OVERRIDE MSG 2"],
        trigger="OVERRIDE TRIGGER: answer now",
    )

    # Use a DAG without progressive — rely on overrides to apply it.
    dag = {
        "stages": [
            {
                "id": "w1",
                "kind": "worker",
                "model": "deepseek/deepseek-chat",
                "depends_on": [],
                "progressive": False,
            },
            {
                "id": "agg",
                "kind": "aggregator",
                "model": "zai-coding-plan/glm-5.2",
                "depends_on": ["w1"],
            },
        ],
        "edges": [["w1", "agg"]],
    }

    result = await Engine(config, gw).deliberate(
        "test", "auto", dag=dag, allow_custom_dag=True, overrides=overrides,
    )

    assert result.answer is not None

    # Progressive should have been applied: 2 wait calls + 1 trigger call + dispatcher + aggregator
    all_calls = gw.calls
    assert len(all_calls) >= 5, f"Expected 5+ calls, got {len(all_calls)}"

    temp03_calls = [c for c in all_calls if c[2].get("temperature") == 0.3]
    assert len(temp03_calls) == 3, f"Expected 3 temp=0.3 calls (2 wait + 1 trigger), got {len(temp03_calls)}"

    # Check the two wait message calls
    wait_calls = [
        c for c in temp03_calls
        if c[1] == [{"role": "user", "content": "OVERRIDE MSG 1"}]
        or c[1] == [{"role": "user", "content": "OVERRIDE MSG 2"}]
    ]
    assert len(wait_calls) == 2, f"Expected 2 wait-message calls, got {len(wait_calls)}"

    # Check the trigger call
    trigger_calls = [
        c for c in temp03_calls
        if c[1] == [{"role": "user", "content": "OVERRIDE TRIGGER: answer now"}]
    ]
    assert len(trigger_calls) == 1, "Expected exactly 1 trigger call with override trigger"


# ─────────────────────────────────────────────────────────────────────
# Validation-as-code: schema extraction + mechanical audit validation
# ─────────────────────────────────────────────────────────────────────


class TestSchemaExtraction:
    """Tests for Engine._extract_output_schema()."""

    def test_extracts_schema_field(self):
        from chimera.engine import Engine

        response = json.dumps({
            "strategy": "generate a user profile",
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer"},
                },
                "required": ["name", "age"],
            },
        })
        result = Engine._extract_output_schema(response)
        assert result is not None
        assert result["type"] == "object"
        assert "name" in result["properties"]

    def test_extracts_whole_schema_if_no_field(self):
        from chimera.engine import Engine

        response = json.dumps({
            "type": "object",
            "properties": {"x": {"type": "number"}},
        })
        result = Engine._extract_output_schema(response)
        assert result is not None
        assert result["type"] == "object"

    def test_returns_none_for_plain_text(self):
        from chimera.engine import Engine

        assert Engine._extract_output_schema("Just some thoughts...") is None
        assert Engine._extract_output_schema("") is None

    def test_returns_none_for_json_without_schema(self):
        from chimera.engine import Engine

        response = json.dumps({"plan": "do X then Y", "workers": 3})
        assert Engine._extract_output_schema(response) is None

    def test_schema_field_wins_over_heuristic(self):
        from chimera.engine import Engine

        # Response has BOTH a top-level type=object AND a nested schema field
        response = json.dumps({
            "type": "object",
            "properties": {"outer": {"type": "string"}},
            "schema": {"type": "object", "properties": {"inner": {"type": "integer"}}},
        })
        result = Engine._extract_output_schema(response)
        assert result is not None
        # The explicit schema field should win
        assert "inner" in result.get("properties", {})


class TestSchemaValidation:
    """Tests for Engine._validate_against_schema()."""

    def test_valid_output_passes(self):
        from chimera.engine import Engine

        schema = {"type": "object", "properties": {"x": {"type": "number"}}}
        output = json.dumps({"x": 42})
        assert Engine._validate_against_schema(schema, output) is None

    def test_invalid_output_fails(self):
        from chimera.engine import Engine

        schema = {"type": "object", "properties": {"x": {"type": "number"}}}
        output = json.dumps({"x": "not-a-number"})
        result = Engine._validate_against_schema(schema, output)
        assert result is not None
        assert result["passed"] is False
        assert len(result["errors"]) > 0
        assert "not-a-number" in str(result["errors"][0]) or "string" in str(result["errors"][0])

    def test_missing_required_fails(self):
        from chimera.engine import Engine

        schema = {
            "type": "object",
            "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
            "required": ["a", "b"],
        }
        output = json.dumps({"a": "hello"})
        result = Engine._validate_against_schema(schema, output)
        assert result is not None
        assert result["passed"] is False

    def test_non_json_output_fails(self):
        from chimera.engine import Engine

        schema = {"type": "object"}
        result = Engine._validate_against_schema(schema, "not valid json {{{")
        assert result is not None
        assert result["passed"] is False
        assert "not valid JSON" in result["errors"][0]

    def test_validation_error_has_passed_false_signal(self):
        from chimera.engine import _RE_ITERATION_SIGNAL, Engine

        schema = {"type": "object", "properties": {"x": {"type": "number"}}}
        output = json.dumps({"x": "bad"})
        result = Engine._validate_against_schema(schema, output)
        error_json = json.dumps(result)
        # The iteration loop should detect this as a failure
        assert _RE_ITERATION_SIGNAL.search(error_json) is not None


class TestMaybeUnwrapEnvelope:
    """Test _maybe_unwrap_envelope coercion of non-string answer values."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            # String answers pass through unchanged
            ('{"answer": "hello"}', "hello"),
            ('{"answer": "42"}', "42"),
            # Int/float/bool/None answers get JSON-serialized to string
            ('{"answer": 4}', "4"),
            ('{"answer": 3.14}', "3.14"),
            ('{"answer": true}', "true"),
            ('{"answer": false}', "false"),
            ('{"answer": null}', "null"),
            # Lists and dicts get JSON-serialized
            ('{"answer": [1, 2, 3]}', "[1, 2, 3]"),
            ('{"answer": {"k": "v"}}', '{"k": "v"}'),
            # Double-unwrap: string-encoded JSON inside answer
            ('{"answer": "{\\"k\\": \\"v\\"}"}', '{"k": "v"}'),
            # Non-envelope: plain text passes through
            ("hello world", "hello world"),
            ("42", "42"),
            # Non-envelope JSON without answer key passes through
            ('{"sources": ["x"]}', '{"sources": ["x"]}'),
        ],
    )
    def test_non_string_coercion(self, text, expected):
        from chimera.engine import Engine
        result = Engine._maybe_unwrap_envelope(text)
        assert isinstance(result, str), f"Expected str, got {type(result)}: {result!r}"
        assert result == expected, f"Expected {expected!r}, got {result!r}"
