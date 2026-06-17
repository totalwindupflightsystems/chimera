"""Tests for the dispatcher — the core of Chimera.

Covers: preset DAG construction, dispatcher prompt building, structured-output
parsing (including malformed output → fallback), and the live Dispatcher flow
with a scripted gateway.
"""

from __future__ import annotations

from typing import Any

import pytest

from chimera.config import FormationPreset
from chimera.dispatcher import (
    DispatchOutcome,
    Dispatcher,
    FormationDAG,
    Stage,
    build_dag_from_dict,
    build_dispatcher_prompt,
    build_preset_dag,
    parse_dispatch_result,
)
from chimera.gateway import GatewayError
from tests.conftest import FakeGateway, dispatch_json, resp


def _client_dag(
    *,
    workers: list[tuple[str, str]] | None = None,
    aggregator: str = "zai-coding-plan/glm-5.2",
    extra_stages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a valid client/config DAG mapping (the runtime DAG shape)."""
    workers = workers or [("worker_1", "deepseek/deepseek-chat")]
    stages: list[dict[str, Any]] = []
    edges: list[list[str]] = []
    worker_ids = [wid for wid, _ in workers]
    for wid, wmodel in workers:
        stages.append({"id": wid, "kind": "worker", "model": wmodel, "depends_on": []})
        edges.append([wid, "aggregator"])
    stages.append(
        {"id": "aggregator", "kind": "aggregator", "model": aggregator, "depends_on": worker_ids}
    )
    for s in extra_stages or []:
        stages.append(s)
        for dep in s.get("depends_on", []):
            edges.append([dep, s["id"]])
    return {"stages": stages, "edges": edges}


# --------------------------------------------------------------------------- #
# Preset → DAG construction
# --------------------------------------------------------------------------- #


def test_preset_simple_dag(config) -> None:  # type: ignore[no-untyped-def]
    dag = build_preset_dag(config.formations["simple"], config)
    kinds = {s.kind for s in dag.stages}
    assert kinds == {"worker", "aggregator"}
    workers = [s for s in dag.stages if s.kind == "worker"]
    assert len(workers) == 2
    assert all(s.model == config.defaults.default_worker for s in workers)
    aggregator = dag.stage("aggregator")
    assert aggregator.model == config.defaults.default_aggregator
    assert set(aggregator.depends_on) == {w.id for w in workers}
    assert ("worker_1", "aggregator") in dag.edges
    assert ("worker_2", "aggregator") in dag.edges


def test_preset_debate_dag_has_two_judges_and_merge(config) -> None:  # type: ignore[no-untyped-def]
    dag = build_preset_dag(config.formations["debate"], config)
    judges = [s for s in dag.stages if s.kind == "aggregator"]
    assert len(judges) == 2
    aggregator_models = {j.model for j in judges}
    assert aggregator_models == {"zai-coding-plan/glm-5.2",
                            "openrouter/anthropic/claude-sonnet-4"}
    merge = dag.stage("merge")
    assert merge.kind == "merge"
    assert set(merge.depends_on) == {j.id for j in judges}
    # three workers
    workers = [s for s in dag.stages if s.kind == "worker"]
    assert len(workers) == 3


def test_preset_audit_dag_has_audit_stage(config) -> None:  # type: ignore[no-untyped-def]
    dag = build_preset_dag(config.formations["audit"], config)
    audit = dag.stage("audit")
    assert audit.kind == "audit"
    assert audit.model == "openrouter/anthropic/claude-sonnet-4"
    assert audit.depends_on == ["aggregator"]
    # the answer stage is the audit (nothing depends on it)
    terminals = dag.terminals()
    assert [t.id for t in terminals] == ["audit"]


def test_preset_worker_models_override(config) -> None:  # type: ignore[no-untyped-def]
    preset = FormationPreset(workers=2,
                             worker_models=["deepseek/deepseek-chat",
                                            "openrouter/google/gemini-2.5-flash"],
                             aggregator="default")
    dag = build_preset_dag(preset, config)
    workers = sorted(s.model for s in dag.stages if s.kind == "worker")
    assert workers == ["deepseek/deepseek-chat", "openrouter/google/gemini-2.5-flash"]


def test_build_preset_dag_rejects_auto(config) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        build_preset_dag(config.formations["auto"], config)


def test_build_preset_dag_rejects_unknown_model(config) -> None:  # type: ignore[no-untyped-def]
    preset = FormationPreset(workers=1, aggregator="no/such/model")
    with pytest.raises(ValueError):
        build_preset_dag(preset, config)


# --------------------------------------------------------------------------- #
# DAG helpers
# --------------------------------------------------------------------------- #


def test_topo_order_respects_dependencies() -> None:
    dag = FormationDAG(
        stages=[
            Stage(id="aggregator", kind="aggregator", model="m", depends_on=["w2"]),
            Stage(id="w1", kind="worker", model="m"),
            Stage(id="w2", kind="worker", model="m", depends_on=["w1"]),
        ],
        edges=[("w1", "w2"), ("w2", "aggregator")],
    )
    order = [s.id for s in dag.topo_order()]
    assert order.index("w1") < order.index("w2") < order.index("aggregator")


def test_terminals_are_nodes_with_no_dependents() -> None:
    dag = FormationDAG(
        stages=[
            Stage(id="w1", kind="worker", model="m"),
            Stage(id="j", kind="aggregator", model="m", depends_on=["w1"]),
        ],
        edges=[("w1", "j")],
    )
    assert [t.id for t in dag.terminals()] == ["j"]


# --------------------------------------------------------------------------- #
# Dispatcher prompt construction
# --------------------------------------------------------------------------- #


def test_dispatcher_prompt_auto_includes_catalog_and_request(config) -> None:  # type: ignore[no-untyped-def]
    msgs = build_dispatcher_prompt("Design an e-commerce backend", config)
    assert msgs[0]["role"] == "system"
    sys_text = msgs[0]["content"]
    assert "zai-coding-plan/glm-5.2" in sys_text
    assert "code=0.95" in sys_text  # deepseek's strongest category
    assert "AUTO mode" in sys_text
    assert "Design an e-commerce backend" in msgs[1]["content"]


def test_dispatcher_prompt_preset_embeds_fixed_dag(config) -> None:  # type: ignore[no-untyped-def]
    dag = build_preset_dag(config.formations["simple"], config)
    msgs = build_dispatcher_prompt("some task", config, fixed_dag=dag)
    sys_text = msgs[0]["content"]
    assert "Do NOT change the structure" in sys_text
    assert '"worker_1"' in sys_text
    assert "AUTO mode" not in sys_text


# --------------------------------------------------------------------------- #
# Output parsing
# --------------------------------------------------------------------------- #


def test_parse_dispatch_result_valid_json(config) -> None:  # type: ignore[no-untyped-def]
    raw = dispatch_json(workers=[("worker_1", "deepseek/deepseek-chat"),
                                 ("worker_2", "openrouter/google/gemini-2.5-flash")],
                        aggregator_instructions="Combine code + design parts.")
    result = parse_dispatch_result(raw, config)
    assert result.source == "auto"
    assert len(result.formation.stages) == 3
    assert {s.kind for s in result.formation.stages} == {"worker", "aggregator"}
    # custom prompts preserved
    prompts = {wp.stage_id: wp.prompt for wp in result.worker_prompts}
    assert prompts["worker_1"] == "Custom subtask for worker_1"
    assert result.aggregator_instructions == "Combine code + design parts."


def test_parse_dispatch_result_unknown_model_falls_back(config) -> None:  # type: ignore[no-untyped-def]
    raw = dispatch_json(workers=[("worker_1", "no/such/model")])
    result = parse_dispatch_result(raw, config)
    # unknown worker model replaced with default worker
    worker = result.formation.stage("worker_1")
    assert worker.model == config.defaults.default_worker


def test_parse_dispatch_result_malformed_json_falls_back(config) -> None:  # type: ignore[no-untyped-def]
    result = parse_dispatch_result("this is not json at all {{{", config)
    assert result.source == "fallback"
    assert len(result.formation.stages) == 2  # 1 worker + 1 aggregator
    assert result.formation.stage("aggregator").kind == "aggregator"
    # worker prompt gets a non-empty template
    assert result.worker_prompts[0].prompt


def test_parse_dispatch_result_uses_fallback_dag_when_provided(config) -> None:  # type: ignore[no-untyped-def]
    dag = build_preset_dag(config.formations["debate"], config)
    result = parse_dispatch_result("garbage", config, fallback_dag=dag)
    assert result.source == "fallback"
    # keeps the debate structure (3 workers + 2 judges + merge)
    assert len([s for s in result.formation.stages if s.kind == "worker"]) == 3
    assert any(s.kind == "merge" for s in result.formation.stages)


def test_parse_dispatch_result_strips_code_fences(config) -> None:  # type: ignore[no-untyped-def]
    raw = "```json\n" + dispatch_json() + "\n```"
    result = parse_dispatch_result(raw, config)
    assert result.source == "auto"
    assert len(result.formation.stages) == 3


# --------------------------------------------------------------------------- #
# Dispatcher live flow (scripted gateway)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dispatcher_auto_flow(config) -> None:  # type: ignore[no-untyped-def]
    payload = dispatch_json(
        workers=[("worker_1", "deepseek/deepseek-chat"),
                 ("worker_2", "openrouter/google/gemini-2.5-flash")],
        aggregator_instructions="Merge the architecture + service boundaries.",
    )

    def responder(model, messages, **kw):
        if model == config.defaults.dispatcher:
            return resp(payload, model, tok_in=100, tok_out=200)
        return resp("x", model)

    gw = FakeGateway(responder)
    outcome = await Dispatcher(config, gw).dispatch("design a system", "auto")
    assert isinstance(outcome, DispatchOutcome)
    assert outcome.result.source == "auto"
    assert len(outcome.result.worker_prompts) == 2
    # the dispatcher was called exactly once
    dispatcher_calls = [c for c in gw.calls if c[0] == config.defaults.dispatcher]
    assert len(dispatcher_calls) == 1
    # JSON object response format was requested
    assert dispatcher_calls[0][2]["response_format"] == {"type": "json_object"}
    # dispatch latency was measured
    assert outcome.latency_ms >= 0


@pytest.mark.asyncio
async def test_dispatcher_preset_flow_honors_structure(config) -> None:  # type: ignore[no-untyped-def]
    payload = dispatch_json(workers=[("ignored", "ignored")])  # should be overridden
    gw = FakeGateway(lambda m, msg, **k: resp(payload, m))
    outcome = await Dispatcher(config, gw).dispatch("task", "debate")
    dag = outcome.result.formation
    assert outcome.result.source == "preset"
    # debate structure enforced regardless of LLM output
    assert len([s for s in dag.stages if s.kind == "worker"]) == 3
    judges = [s for s in dag.stages if s.kind == "aggregator"]
    assert len(judges) == 2
    assert any(s.kind == "merge" for s in dag.stages)


@pytest.mark.asyncio
async def test_dispatcher_gateway_failure_falls_back(config) -> None:  # type: ignore[no-untyped-def]
    class BoomGateway(FakeGateway):
        async def complete(self, *a, **k):
            raise GatewayError("provider down")
    gw = BoomGateway()
    outcome = await Dispatcher(config, gw).dispatch("task", "auto")
    assert outcome.result.source == "fallback"
    assert outcome.response.text == "{}"  # graceful empty payload


@pytest.mark.asyncio
async def test_dispatcher_unknown_formation_uses_auto(config) -> None:  # type: ignore[no-untyped-def]
    gw = FakeGateway(lambda m, msg, **k: resp(dispatch_json(), m))
    outcome = await Dispatcher(config, gw).dispatch("task", "nonexistent")
    # auto mode applied
    assert outcome.result.source == "auto"


# --------------------------------------------------------------------------- #
# Config-defined custom DAG formation (Feature 3) + build_dag_from_dict
# --------------------------------------------------------------------------- #


def test_config_defined_custom_formation_loaded_correctly(config) -> None:  # type: ignore[no-untyped-def]
    """A FormationPreset with `dag` builds that DAG directly via build_preset_dag."""
    dag_dict = _client_dag(
        workers=[("analyzer", "deepseek/deepseek-chat"),
                 ("designer", "openrouter/google/gemini-2.5-flash")],
        aggregator="zai-coding-plan/glm-5.2",
    )
    preset = FormationPreset(dag=dag_dict)
    assert preset.has_dag is True
    dag = build_preset_dag(preset, config)
    stage_ids = dag.stage_ids()
    assert stage_ids == ["analyzer", "designer", "aggregator"]
    # models preserved
    assert dag.stage("analyzer").model == "deepseek/deepseek-chat"
    assert dag.stage("designer").model == "openrouter/google/gemini-2.5-flash"
    assert dag.stage("aggregator").model == "zai-coding-plan/glm-5.2"
    # edges preserved
    assert ("analyzer", "aggregator") in dag.edges
    assert ("designer", "aggregator") in dag.edges


def test_config_defined_dag_wins_over_legacy_fields(config) -> None:  # type: ignore[no-untyped-def]
    """When both `dag` and legacy `workers` are set, `dag` wins."""
    dag_dict = _client_dag(workers=[("solo", "deepseek/deepseek-chat")])
    preset = FormationPreset(workers=99, aggregator="default", dag=dag_dict)
    dag = build_preset_dag(preset, config)
    # Only the single worker from the dag, not 99
    assert len([s for s in dag.stages if s.kind == "worker"]) == 1
    assert dag.stage("solo") is not None


def test_config_defined_custom_chain_dag(config) -> None:  # type: ignore[no-untyped-def]
    """An arbitrary multi-stage chain DAG from config is honored exactly."""
    chain = {
        "stages": [
            {"id": "analyzer", "kind": "worker", "model": "deepseek/deepseek-chat"},
            {"id": "reviewer", "kind": "aggregator",
             "model": "zai-coding-plan/glm-5.2", "depends_on": ["analyzer"]},
            {"id": "implementer", "kind": "worker",
             "model": "openrouter/anthropic/claude-sonnet-4", "depends_on": ["reviewer"]},
            {"id": "verifier", "kind": "aggregator",
             "model": "zai-coding-plan/glm-5.2", "depends_on": ["implementer"]},
            {"id": "finalizer", "kind": "merge",
             "model": "deepseek/deepseek-chat", "depends_on": ["verifier"]},
        ],
        "edges": [["analyzer", "reviewer"], ["reviewer", "implementer"],
                  ["implementer", "verifier"], ["verifier", "finalizer"]],
    }
    dag = build_preset_dag(FormationPreset(dag=chain), config)
    order = dag.topo_order()
    ids = [s.id for s in order]
    assert ids == ["analyzer", "reviewer", "implementer", "verifier", "finalizer"]
    assert dag.terminals()[-1].id == "finalizer"


# --------------------------------------------------------------------------- #
# Client DAG validation (Feature 1) — build_dag_from_dict rejections
# --------------------------------------------------------------------------- #


def test_client_dag_invalid_model_rejected(config) -> None:  # type: ignore[no-untyped-def]
    bad = _client_dag(workers=[("worker_1", "no/such/model")])
    with pytest.raises(ValueError, match="unknown model"):
        build_dag_from_dict(bad, config)


def test_client_dag_cycle_rejected(config) -> None:  # type: ignore[no-untyped-def]
    cyclic = {
        "stages": [
            {"id": "a", "kind": "worker", "model": "deepseek/deepseek-chat",
             "depends_on": ["b"]},
            {"id": "b", "kind": "aggregator", "model": "zai-coding-plan/glm-5.2",
             "depends_on": ["a"]},
        ],
        "edges": [["a", "b"], ["b", "a"]],
    }
    with pytest.raises(ValueError, match="cycle"):
        build_dag_from_dict(cyclic, config)


def test_client_dag_no_worker_stages_rejected(config) -> None:  # type: ignore[no-untyped-def]
    no_worker = {
        "stages": [
            {"id": "aggregator", "kind": "aggregator", "model": "zai-coding-plan/glm-5.2"},
        ],
        "edges": [],
    }
    with pytest.raises(ValueError, match="no worker"):
        build_dag_from_dict(no_worker, config)


def test_client_dag_no_aggregator_stages_rejected(config) -> None:  # type: ignore[no-untyped-def]
    no_agg = {
        "stages": [
            {"id": "worker_1", "kind": "worker", "model": "deepseek/deepseek-chat"},
        ],
        "edges": [],
    }
    with pytest.raises(ValueError, match="no aggregator"):
        build_dag_from_dict(no_agg, config)


def test_client_dag_dangling_dependency_rejected(config) -> None:  # type: ignore[no-untyped-def]
    bad = {
        "stages": [
            {"id": "worker_1", "kind": "worker", "model": "deepseek/deepseek-chat",
             "depends_on": ["ghost"]},
            {"id": "aggregator", "kind": "aggregator",
             "model": "zai-coding-plan/glm-5.2", "depends_on": ["worker_1"]},
        ],
        "edges": [["worker_1", "aggregator"]],
    }
    with pytest.raises(ValueError, match="unknown"):
        build_dag_from_dict(bad, config)


def test_client_dag_resolves_default_alias(config) -> None:  # type: ignore[no-untyped-def]
    dag_dict = {
        "stages": [
            {"id": "worker_1", "kind": "worker", "model": "default_worker"},
            {"id": "aggregator", "kind": "aggregator", "model": "default",
             "depends_on": ["worker_1"]},
        ],
        "edges": [["worker_1", "aggregator"]],
    }
    dag = build_dag_from_dict(dag_dict, config)
    assert dag.stage("worker_1").model == config.defaults.default_worker
    assert dag.stage("aggregator").model == config.defaults.default_aggregator


# --------------------------------------------------------------------------- #
# Custom DAG dispatcher flow (Feature 1) — FILL-IN pass only
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_custom_dag_dispatch_fills_prompts_and_honors_structure(config) -> None:  # type: ignore[no-untyped-def]
    """allow_custom_dag: dispatcher is called once to FILL-IN, structure honored."""
    dag_dict = _client_dag(
        workers=[("researcher", "deepseek/deepseek-chat")],
        aggregator="zai-coding-plan/glm-5.2",
    )
    # Dispatcher payload references different/ignored stage ids — must be ignored
    # in favor of the fixed DAG, but its prompts should still parse.
    payload = dispatch_json(
        workers=[("researcher", "deepseek/deepseek-chat")],
        aggregator_instructions="Merge research into a final answer.",
    )

    def responder(model, messages, **kw):
        if model == config.defaults.dispatcher:
            return resp(payload, model, tok_in=100, tok_out=200)
        return resp(f"[output from {model}]", model)

    gw = FakeGateway(responder)
    custom_dag = build_dag_from_dict(dag_dict, config)
    outcome = await Dispatcher(config, gw).dispatch("task", "auto", custom_dag=custom_dag)
    assert outcome.result.source == "custom"
    # Structure honored exactly
    assert outcome.result.formation.stage_ids() == ["researcher", "aggregator"]
    # Dispatcher called exactly once (FILL-IN pass)
    dispatcher_calls = [c for c in gw.calls if c[0] == config.defaults.dispatcher]
    assert len(dispatcher_calls) == 1
    # The fixed DAG was embedded in the dispatcher prompt
    assert "researcher" in dispatcher_calls[0][1][0]["content"]
