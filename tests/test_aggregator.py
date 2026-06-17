"""Tests for the aggregator merge-prompt construction and execution."""

from __future__ import annotations

import pytest

from chimera.dispatcher import DispatchResult, FormationDAG, Stage, WorkerPrompt
from chimera.gateway import GatewayResponse
from chimera.aggregator import Aggregator, StageResult, build_merge_prompt
from tests.conftest import FakeGateway, resp


def _make_dispatch(aggregator_instructions: str = "Merge A and B.") -> DispatchResult:
    dag = FormationDAG(
        stages=[
            Stage(id="worker_1", kind="worker", model="deepseek/deepseek-chat"),
            Stage(id="worker_2", kind="worker", model="openrouter/google/gemini-2.5-flash"),
            Stage(id="aggregator", kind="aggregator", model="zai-coding-plan/glm-5.2",
                  depends_on=["worker_1", "worker_2"]),
        ],
        edges=[("worker_1", "aggregator"), ("worker_2", "aggregator")],
    )
    return DispatchResult(
        formation=dag,
        worker_prompts=[
            WorkerPrompt(stage_id="worker_1", model="deepseek/deepseek-chat",
                         prompt="Implement the service boundaries."),
            WorkerPrompt(stage_id="worker_2", model="openrouter/google/gemini-2.5-flash",
                         prompt="Design the system architecture."),
        ],
        aggregator_instructions=aggregator_instructions,
    )


def _make_deps() -> list[StageResult]:
    return [
        StageResult(stage_id="worker_1", model="deepseek/deepseek-chat",
                    prompt="Implement the service boundaries.",
                    response=resp("order-service, payment-service", "deepseek/deepseek-chat")),
        StageResult(stage_id="worker_2", model="openrouter/google/gemini-2.5-flash",
                    prompt="Design the system architecture.",
                    response=resp("API gateway + microservices", "openrouter/google/gemini-2.5-flash")),
    ]


def test_build_merge_prompt_includes_worker_outputs_and_instructions() -> None:
    dispatch = _make_dispatch()
    stage = dispatch.formation.stage("aggregator")
    msgs = build_merge_prompt(stage, dispatch, _make_deps(), "Design an e-commerce backend")
    user_msg = msgs[1]["content"]
    assert "Design an e-commerce backend" in user_msg
    assert "Merge A and B." in user_msg
    # each worker's output and what it was asked appear
    assert "order-service, payment-service" in user_msg
    assert "API gateway + microservices" in user_msg
    assert "Implement the service boundaries." in user_msg
    assert "Design the system architecture." in user_msg
    # model attribution
    assert "deepseek/deepseek-chat" in user_msg


def test_build_merge_prompt_audit_stage_uses_stage_instructions() -> None:
    dag = FormationDAG(
        stages=[
            Stage(id="aggregator", kind="aggregator", model="m", depends_on=[]),
            Stage(id="audit", kind="audit", model="m", depends_on=["aggregator"]),
        ],
        edges=[("aggregator", "audit")],
    )
    dispatch = DispatchResult(
        formation=dag,
        aggregator_instructions="aggregator-instr",
        stage_instructions={"audit": "Audit for correctness."},
    )
    audit = dispatch.formation.stage("audit")
    msgs = build_merge_prompt(audit, dispatch, [], "prompt")
    assert "Audit for correctness." in msgs[1]["content"]


@pytest.mark.asyncio
async def test_aggregator_execute_calls_correct_model(config) -> None:  # type: ignore[no-untyped-def]
    dispatch = _make_dispatch()
    stage = dispatch.formation.stage("aggregator")
    gw = FakeGateway(lambda m, msg, **k: resp(f"merged by {m}", m))
    aggregator = Aggregator(config, gw)
    response = await aggregator.execute(stage, dispatch, _make_deps(), "design a system")
    assert isinstance(response, GatewayResponse)
    assert response.model == "zai-coding-plan/glm-5.2"
    assert response.text == "merged by zai-coding-plan/glm-5.2"
    # exactly one call, to the aggregator model
    assert len(gw.calls) == 1
    assert gw.calls[0][0] == "zai-coding-plan/glm-5.2"
