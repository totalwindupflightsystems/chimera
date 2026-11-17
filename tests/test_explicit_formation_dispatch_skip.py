"""PERF-2: explicit formations must not pay the dispatcher LLM call.

An explicit formation (a config-defined DAG, or a named non-auto preset) has
its full structure and every model fixed by configuration. The dispatcher's
only remaining contribution was prose — per-worker prompts and merge
instructions — billed as a real provider call (measured on the run-30 budget
panel: 14.5 s of a 22.5 s wall and 100 % of the run's cost).

These tests pin the contract introduced by the fix:

* a config-DAG formation, a named structural preset, and a request-level
  custom DAG all run with NO dispatcher model call (the gateway sees exactly
  the stage calls, none carrying the dispatcher's ``response_format``);
* ``trace.dispatch`` is ``None`` — absent/null, never a zeroed span with fake
  numbers — and run totals cover the stage spans alone;
* ``dispatch_prompts: true`` on a formation opts back into the dispatcher
  fill-in call (the pre-PERF-2 behavior), and ``auto`` keeps the dispatcher
  unchanged.

Engine-level contracts only — every assertion here is meaningful against the
pre-fix tree too (where it FAILS: a dispatcher call happens and
``trace.dispatch`` is a span).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from chimera.config import ChimeraConfig, FormationPreset
from tests.conftest import CONFIG_DICT, FakeGateway

DAG_STAGES: list[dict[str, Any]] = [
    {"id": "slow", "kind": "worker", "model": "deepseek/deepseek-chat", "depends_on": []},
    {"id": "fast", "kind": "worker", "model": "deepseek/deepseek-v4-flash", "depends_on": []},
    {
        "id": "verdict",
        "kind": "merge",
        "model": "zai-coding-plan/glm-5.2",
        "depends_on": ["slow", "fast"],
    },
]
DAG_EDGES: list[list[str]] = [["slow", "verdict"], ["fast", "verdict"]]


def _config_with_dag_formation(**preset_extra: Any) -> ChimeraConfig:
    """The shared fixture catalog plus a run-30-shaped ``budgettest`` DAG formation."""
    config = ChimeraConfig.model_validate(CONFIG_DICT)
    config.formations["budgettest"] = FormationPreset(
        dag={"stages": DAG_STAGES, "edges": DAG_EDGES}, **preset_extra
    )
    return config


def _assert_no_dispatcher_call(gw: FakeGateway) -> None:
    """The gateway must have seen ONLY stage calls — none with the dispatcher's
    ``response_format={"type": "json_object"}`` marker."""
    assert gw.calls, "expected the stage calls to have happened"
    for model, _messages, kwargs in gw.calls:
        assert kwargs.get("response_format") is None, (
            f"dispatcher call leaked to the gateway: model={model} kwargs={kwargs}"
        )


@pytest.mark.asyncio
async def test_config_dag_formation_skips_dispatcher() -> None:
    """A config-defined DAG formation runs with no dispatcher call at all."""
    from chimera.engine import Engine

    config = _config_with_dag_formation()
    gw = FakeGateway()
    result = await Engine(config, gw).deliberate("Is a per-stage timeout budget useful?", "budgettest")

    _assert_no_dispatcher_call(gw)
    # Exactly the three stage calls — no extra round-trip anywhere.
    assert [model for model, _, _ in gw.calls] == [
        "deepseek/deepseek-chat",
        "deepseek/deepseek-v4-flash",
        "zai-coding-plan/glm-5.2",
    ]

    trace = result.trace
    assert trace.dispatch is None, "a skipped dispatch must leave trace.dispatch null"
    assert trace.source == "preset"
    # The configured structure is honored verbatim.
    assert trace.answer_stage_id == "verdict"
    assert sorted(w.stage_id for w in trace.workers) == ["fast", "slow"]
    # Workers ran on the deterministic templated task prompt, not an authored one.
    prompts = {w.stage_id: w.prompt for w in trace.workers}
    assert "You are worker 'slow'." in prompts["slow"]
    assert "You are worker 'fast'." in prompts["fast"]


@pytest.mark.asyncio
async def test_named_structural_preset_skips_dispatcher() -> None:
    """A named workers/aggregator preset (no DAG) skips the dispatcher too."""
    from chimera.engine import Engine

    config = ChimeraConfig.model_validate(CONFIG_DICT)
    gw = FakeGateway()
    result = await Engine(config, gw).deliberate("Quick take?", "simple")

    _assert_no_dispatcher_call(gw)
    trace = result.trace
    assert trace.dispatch is None
    assert trace.source == "preset"
    assert sorted(w.stage_id for w in trace.workers) == ["worker_1", "worker_2"]
    assert all("You are worker" in w.prompt for w in trace.workers)


@pytest.mark.asyncio
async def test_request_custom_dag_skips_dispatcher() -> None:
    """A request-level custom DAG skips the dispatcher and keeps ``source=custom``."""
    from chimera.engine import Engine

    config = ChimeraConfig.model_validate(CONFIG_DICT)
    gw = FakeGateway()
    result = await Engine(config, gw).deliberate(
        "Is a per-stage timeout budget useful?",
        "auto",
        dag={"stages": DAG_STAGES, "edges": DAG_EDGES},
        allow_custom_dag=True,
    )

    _assert_no_dispatcher_call(gw)
    trace = result.trace
    assert trace.dispatch is None
    assert trace.source == "custom"
    assert sorted(w.stage_id for w in trace.workers) == ["fast", "slow"]


@pytest.mark.asyncio
async def test_dispatch_prompts_restores_fill_in_call() -> None:
    """``dispatch_prompts: true`` opts back into the dispatcher-authored fill-in."""
    from chimera.engine import Engine
    from tests.conftest import dispatch_json

    config = _config_with_dag_formation(dispatch_prompts=True)
    payload = dispatch_json(
        workers=[("slow", "deepseek/deepseek-chat"), ("fast", "deepseek/deepseek-v4-flash")],
        aggregator="zai-coding-plan/glm-5.2",
        aggregator_instructions="Merge the slow and fast reviews.",
        extra_stages=[{"id": "verdict", "kind": "merge", "model": "zai-coding-plan/glm-5.2"}],
    )

    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:  # the dispatcher fill-in call
            from tests.conftest import resp

            return resp(payload, model, tok_in=120, tok_out=180)
        from tests.conftest import resp

        return resp(f"[stage output from {model}]", model)

    gw = FakeGateway(responder)
    result = await Engine(config, gw).deliberate("Is a per-stage timeout budget useful?", "budgettest")

    dispatch_calls = [call for call in gw.calls if call[2].get("response_format") is not None]
    assert len(dispatch_calls) == 1, "the opt-in must restore exactly one dispatcher call"
    trace = result.trace
    assert trace.dispatch is not None, "the opt-in keeps a real dispatch span"
    assert trace.source == "preset"
    prompts = {w.stage_id: w.prompt for w in trace.workers}
    assert "Custom subtask for slow" in prompts["slow"]
    assert "Custom subtask for fast" in prompts["fast"]


@pytest.mark.asyncio
async def test_auto_formation_still_calls_dispatcher() -> None:
    """The auto path is unchanged: one dispatcher call, a real dispatch span."""
    from chimera.engine import Engine
    from tests.conftest import dispatch_json, resp

    config = ChimeraConfig.model_validate(CONFIG_DICT)
    payload = dispatch_json()

    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:  # the dispatcher call
            return resp(payload, model, tok_in=120, tok_out=180)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:  # aggregator/merge/audit
            return resp(f"[FINAL MERGED ANSWER from {model}]", model)
        return resp(f"[worker output {model}]", model)

    gw = FakeGateway(responder)
    result = await Engine(config, gw).deliberate("Design + build a service", "auto")

    dispatch_calls = [call for call in gw.calls if call[2].get("response_format") is not None]
    assert len(dispatch_calls) == 1, "auto must keep exactly one dispatcher call"
    assert result.trace.dispatch is not None
    assert result.trace.dispatch.kind == "dispatch"


@pytest.mark.asyncio
async def test_totals_cover_stage_spans_only_when_dispatch_skipped() -> None:
    """Cost/token totals add up over the stage spans alone — nothing invented."""
    from chimera.engine import Engine

    config = _config_with_dag_formation()
    gw = FakeGateway()
    result = await Engine(config, gw).deliberate("Is a per-stage timeout budget useful?", "budgettest")

    trace = result.trace
    assert trace.dispatch is None
    stage_tokens = sum(s.tokens_input + s.tokens_output for s in trace.stages)
    stage_cost = round(sum(s.cost for s in trace.stages), 6)
    assert trace.total_tokens == stage_tokens
    assert trace.total_cost == stage_cost
    # The JSON contract: the key stays present with a null value.
    assert trace.model_dump(mode="json")["dispatch"] is None


@pytest.mark.asyncio
async def test_aggregate_usage_handles_skipped_dispatch() -> None:
    """The OpenAI-compat usage aggregate tolerates a None dispatch span."""
    from chimera.api.server import aggregate_usage
    from chimera.engine import Engine

    config = _config_with_dag_formation()
    gw = FakeGateway()
    result = await Engine(config, gw).deliberate("Is a per-stage timeout budget useful?", "budgettest")

    prompt, completion, total = aggregate_usage(result.trace)
    assert total == prompt + completion
    assert total == result.trace.total_tokens
