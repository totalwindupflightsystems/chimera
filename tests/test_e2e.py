"""End-to-end test of the full deliberation pipeline.

Uses a scripted gateway that mimics a real category-weighted dispatch: a
"design + code" task gets a code worker (DeepSeek) and a design worker
(Gemini), then the aggregator merges. Verifies the entire trace.
"""

from __future__ import annotations

import json

import pytest

from chimera.engine import Engine
from tests.conftest import FakeGateway, dispatch_json, resp


# A dispatcher payload that demonstrates category-weighted routing:
# code-heavy task → DeepSeek (code=0.95), design-heavy task → Gemini (design=0.90).
REAL_DISPATCH = dispatch_json(
    workers=[
        ("worker_code", "deepseek/deepseek-chat"),
        ("worker_design", "openrouter/google/gemini-2.5-flash"),
    ],
    aggregator="zai-coding-plan/glm-5.2",
    aggregator_instructions=(
        "worker_code was asked to implement the service code; "
        "worker_design was asked to design the architecture. "
        "Merge them into a single design + implementation answer."
    ),
)


def _real_responder(model, messages, response_format=None, **kw):
    if response_format is not None:  # dispatcher
        return resp(REAL_DISPATCH, model, tok_in=140, tok_out=210)
    joined = json.dumps(messages)
    if "Upstream outputs" in joined:  # aggregator
        # The aggregator prompt must mention what each worker was asked + their outputs
        assert "implement the service code" in joined
        assert "design the architecture" in joined
        return resp(
            "## E-commerce Platform\n\n"
            "### Architecture (Gemini)\nAPI gateway + microservices.\n\n"
            "### Implementation (DeepSeek)\nOrderService, PaymentService.\n",
            model,
            tok_in=70,
            tok_out=120,
        )
    # worker
    if "worker_code" in joined or "service code" in joined:
        return resp("OrderService, PaymentService", "deepseek/deepseek-chat", 30, 45)
    return resp("API gateway + microservices", "openrouter/google/gemini-2.5-flash", 30, 40)


@pytest.mark.asyncio
async def test_e2e_full_pipeline(config) -> None:  # type: ignore[no-untyped-def]
    gw = FakeGateway(_real_responder)
    result = await Engine(config, gw).deliberate(
        "Design and implement a scalable e-commerce platform", "auto"
    )

    # ---- Final answer is the aggregator's merge ----
    assert "E-commerce Platform" in result.answer
    assert "OrderService" in result.answer

    trace = result.trace

    # ---- Trace structure: dispatch → workers → aggregator ----
    assert trace.dispatch.kind == "dispatch"
    worker_ids = [w.stage_id for w in trace.workers]
    assert worker_ids == ["worker_code", "worker_design"]
    assert trace.aggregator is not None
    assert trace.aggregator.kind == "aggregator"

    # ---- Correct model assignments (category-weighted routing) ----
    code_worker = next(w for w in trace.workers if w.stage_id == "worker_code")
    design_worker = next(w for w in trace.workers if w.stage_id == "worker_design")
    assert code_worker.model == "deepseek/deepseek-chat"      # code=0.95
    assert design_worker.model == "openrouter/google/gemini-2.5-flash"  # design=0.90
    assert trace.aggregator.model == "zai-coding-plan/glm-5.2"     # premium reasoning

    # ---- Custom (non-identical) worker prompts ----
    assert code_worker.prompt != design_worker.prompt

    # ---- Execution order: aggregator ran after both workers ----
    assert trace.aggregator.tokens_input > 0  # received worker outputs

    # ---- Totals aggregate every span ----
    every = [trace.dispatch, *trace.workers, trace.aggregator]
    assert trace.total_tokens == sum(s.tokens_input + s.tokens_output for s in every)
    assert trace.total_cost > 0

    # ---- Exactly one dispatcher call ----
    dispatcher_calls = [c for c in gw.calls if c[2].get("response_format")]
    assert len(dispatcher_calls) == 1

    # ---- The dispatcher saw the model catalog with category weights ----
    dispatch_prompt = dispatcher_calls[0][1][0]["content"]
    assert "code=0.95" in dispatch_prompt       # DeepSeek strength
    assert "design=0.90" in dispatch_prompt     # Gemini strength
    assert "reasoning=0.95" in dispatch_prompt  # GLM strength


@pytest.mark.asyncio
async def test_e2e_trace_is_json_serializable(config) -> None:  # type: ignore[no-untyped-def]
    gw = FakeGateway(_real_responder)
    result = await Engine(config, gw).deliberate("task", "auto")
    blob = json.dumps(result.trace.model_dump(mode="json"))
    parsed = json.loads(blob)
    assert parsed["dispatch"]["kind"] == "dispatch"
    assert len(parsed["workers"]) == 2
    assert parsed["answer_stage_id"] == "aggregator"
