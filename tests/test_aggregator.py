"""Tests for the aggregator merge-prompt construction and execution."""

from __future__ import annotations

import pytest
import structlog.testing

from chimera.aggregator import Aggregator, StageResult, build_merge_prompt
from chimera.dispatcher import DispatchResult, FormationDAG, Stage, WorkerPrompt
from chimera.gateway import GatewayResponse
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


# ── Truncation behavior (large panel / saturating context) ──────────────


def _make_big_dispatch(worker_count: int = 3) -> DispatchResult:
    """A 3-worker dispatch with customisable per-worker output sizes."""
    dag = FormationDAG(
        stages=[
            Stage(id=f"worker_{i}", kind="worker", model="m")
            for i in range(1, worker_count + 1)
        ]
        + [
            Stage(
                id="aggregator",
                kind="aggregator",
                model="agg",
                depends_on=[f"worker_{i}" for i in range(1, worker_count + 1)],
            )
        ],
        edges=[
            (f"worker_{i}", "aggregator") for i in range(1, worker_count + 1)
        ],
    )
    return DispatchResult(
        formation=dag,
        worker_prompts=[
            WorkerPrompt(stage_id=f"worker_{i}", model="m", prompt=f"subtask {i}")
            for i in range(1, worker_count + 1)
        ],
        aggregator_instructions="merge them",
    )


def _make_big_deps(outputs: list[str], degraded: list[bool] | None = None) -> list[StageResult]:
    if degraded is None:
        degraded = [False] * len(outputs)
    return [
        StageResult(
            stage_id=f"worker_{i + 1}",
            model="m",
            prompt=f"subtask {i + 1}",
            response=resp(out, "m"),
            degraded=deg,
        )
        for i, (out, deg) in enumerate(zip(outputs, degraded))
    ]


def test_no_truncation_when_outputs_fit_budget() -> None:
    """All outputs fit; no truncation marker appears; no warning logged."""
    dispatch = _make_big_dispatch(3)
    stage = dispatch.formation.stage("aggregator")
    deps = _make_big_deps(["short output A", "short output B", "short output C"])

    with structlog.testing.capture_logs() as logs:
        msgs = build_merge_prompt(
            stage, dispatch, deps, "user prompt", max_prompt_tokens=10_000,
        )
    user_msg = msgs[1]["content"]

    # Every output survives intact.
    assert "short output A" in user_msg
    assert "short output B" in user_msg
    assert "short output C" in user_msg
    # No [TRUNCATED] tag is emitted and no warning is logged.
    assert "[TRUNCATED]" not in user_msg
    assert all(
        ev.get("event") != "aggregator_prompt_truncated" for ev in logs
    )


def test_truncation_when_outputs_exceed_budget() -> None:
    """Outputs are shrunk; longest ones go first; budget is respected."""
    dispatch = _make_big_dispatch(3)
    stage = dispatch.formation.stage("aggregator")
    # 1 × 10K (longest), 1 × 5K, 1 × 1K (shortest)
    deps = _make_big_deps(["A" * 10_000, "B" * 5_000, "C" * 1_000])

    with structlog.testing.capture_logs() as logs:
        msgs = build_merge_prompt(
            stage, dispatch, deps, "user prompt", max_prompt_tokens=500,
        )
    user_msg = msgs[1]["content"]

    # Truncation marker is present and the budget is respected.
    assert "[TRUNCATED]" in user_msg
    # Estimate the final prompt size — it should be ≤ max_prompt_tokens
    # (heuristic; 1 token ≈ 4 chars).
    total_chars = sum(len(m["content"]) for m in msgs)
    assert total_chars <= 500 * 4 + 500  # generous slack for marker / rounding

    # The shortest output (worker_3) is preserved in full because we
    # truncate the longest ones first.
    assert "C" * 1_000 in user_msg
    # The longest output (worker_1) is the first victim — its 10K of A's
    # is not present verbatim.
    assert "A" * 10_000 not in user_msg

    # A warning log was emitted with the right shape.
    trunc_events = [
        ev for ev in logs if ev.get("event") == "aggregator_prompt_truncated"
    ]
    assert len(trunc_events) == 1
    ev = trunc_events[0]
    assert ev["stage"] == "aggregator"
    assert ev["max_prompt_tokens"] == 500
    assert ev["n_total"] == 3
    assert ev["n_truncated"] >= 1
    assert "worker_1" in ev["truncated"]  # longest was definitely trimmed
    # log level is warning
    assert ev["log_level"] == "warning"


def test_degraded_outputs_preserved_through_truncation() -> None:
    """A degraded worker's output stays in the prompt (with [DEGRADED] tag)
    even when the budget is tight — the aggregator must still see *that*
    the worker failed."""
    dispatch = _make_big_dispatch(2)
    stage = dispatch.formation.stage("aggregator")
    # worker_1 huge + healthy, worker_2 tiny but degraded
    deps = _make_big_deps(
        ["X" * 8_000, "could not parse"],
        degraded=[False, True],
    )

    with structlog.testing.capture_logs():
        msgs = build_merge_prompt(
            stage, dispatch, deps, "user prompt", max_prompt_tokens=300,
        )
    user_msg = msgs[1]["content"]

    # Degraded marker is present and the failure note survives.
    assert "[DEGRADED]" in user_msg
    assert "could not parse" in user_msg
    assert "This stage failed to produce valid output." in user_msg
    # The huge healthy output is what got cut.
    assert "X" * 8_000 not in user_msg


def test_truncation_warning_log_contains_diagnostics() -> None:
    """The warning log carries enough info to debug saturation post-hoc."""
    dispatch = _make_big_dispatch(2)
    stage = dispatch.formation.stage("aggregator")
    deps = _make_big_deps(["alpha " * 5_000, "beta " * 5_000])

    with structlog.testing.capture_logs() as logs:
        build_merge_prompt(
            stage, dispatch, deps, "user prompt", max_prompt_tokens=200,
        )

    events = [ev for ev in logs if ev.get("event") == "aggregator_prompt_truncated"]
    assert len(events) == 1
    ev = events[0]
    # All diagnostic fields are present.
    assert ev["stage"] == "aggregator"
    assert ev["n_truncated"] == 2
    assert ev["n_total"] == 2
    assert ev["max_prompt_tokens"] == 200
    # estimated_total_tokens is above the cap
    assert ev["estimated_total_tokens"] > ev["max_prompt_tokens"]
    # truncated list contains both stage ids
    assert set(ev["truncated"]) == {"worker_1", "worker_2"}


def test_max_prompt_tokens_default_is_unlimited() -> None:
    """Backward compat: omitting max_prompt_tokens preserves old behavior."""
    dispatch = _make_big_dispatch(2)
    stage = dispatch.formation.stage("aggregator")
    deps = _make_big_deps(["alpha " * 2_000, "beta " * 2_000])

    with structlog.testing.capture_logs() as logs:
        msgs = build_merge_prompt(stage, dispatch, deps, "user prompt")
    user_msg = msgs[1]["content"]

    # Both outputs are present verbatim, no [TRUNCATED] anywhere.
    assert "alpha " * 2_000 in user_msg
    assert "beta " * 2_000 in user_msg
    assert "[TRUNCATED]" not in user_msg
    # No warning was logged.
    assert not any(ev.get("event") == "aggregator_prompt_truncated" for ev in logs)


def test_chimera_config_has_max_aggregator_context_tokens() -> None:
    """The config field exists and defaults to None (no cap)."""
    from chimera.config import ChimeraConfig
    cfg = ChimeraConfig.model_validate({
        "defaults": {
            "dispatcher": "m",
            "default_worker": "m",
            "default_aggregator": "m",
        }
    })
    assert hasattr(cfg, "max_aggregator_context_tokens")
    assert cfg.max_aggregator_context_tokens is None
    # And can be set to an int.
    cfg2 = ChimeraConfig.model_validate({
        "defaults": {
            "dispatcher": "m",
            "default_worker": "m",
            "default_aggregator": "m",
        },
        "max_aggregator_context_tokens": 8000,
    })
    assert cfg2.max_aggregator_context_tokens == 8000


@pytest.mark.asyncio
async def test_aggregator_uses_config_max_aggregator_context_tokens(config) -> None:  # type: ignore[no-untyped-def]
    """When the config sets a cap, Aggregator.execute applies it."""
    # Set the cap on the existing fixture config.
    object.__setattr__(config, "max_aggregator_context_tokens", 300)
    dispatch = _make_dispatch()
    stage = dispatch.formation.stage("aggregator")
    deps = _make_deps()
    # Blow up the deps' outputs.
    deps[0] = StageResult(
        stage_id="worker_1", model=deps[0].model, prompt=deps[0].prompt,
        response=resp("X" * 8_000, deps[0].model),
    )
    deps[1] = StageResult(
        stage_id="worker_2", model=deps[1].model, prompt=deps[1].prompt,
        response=resp("Y" * 8_000, deps[1].model),
    )

    captured: dict[str, object] = {}

    def _responder(model, messages, **kw):
        captured["model"] = model
        captured["messages"] = messages
        return resp("merged", model)

    gw = FakeGateway(_responder)
    aggregator = Aggregator(config, gw)
    await aggregator.execute(stage, dispatch, deps, "the user prompt")

    msgs = captured["messages"]
    assert isinstance(msgs, list) and len(msgs) >= 1
    user_msg = msgs[1]["content"]
    # Truncation kicked in because the config cap was set.
    assert "[TRUNCATED]" in user_msg
    # Neither huge output survived in full.
    assert "X" * 8_000 not in user_msg
    assert "Y" * 8_000 not in user_msg
