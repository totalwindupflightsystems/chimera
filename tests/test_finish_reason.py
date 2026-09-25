"""Stage truncation surfaced as ``finish_reason="length"`` on the OpenAI response.

DF-CHIMERA-V2-54.  ``max_tokens`` already caps every answer-producing call
(CH-GAP-031) and the gateway already extracts the per-call finish reason onto
``GatewayResponse.finish_reason`` — but the OpenAI-compatible choice always
reported ``finish_reason: "stop"``, so a drop-in SDK client that retries or
continues on ``"length"`` silently misfired on truncated deliberations.  These
tests pin the flow: gateway response → closed ``StageSpan`` → the aggregated
choice's ``finish_reason``.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api import server as api_server  # noqa: E402
from chimera.engine import DeliberationTrace, Engine, StageSpan  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402


def _trace_with_stage_finish_reasons(
    reasons: list[str],
    dispatch_reason: str = "",
) -> DeliberationTrace:
    """A minimal trace whose stage spans carry the given finish reasons."""
    return DeliberationTrace(
        request_id="req-fr",
        formation="simple",
        source="preset",
        dispatch=StageSpan(
            stage_id="dispatch",
            kind="dispatch",
            model="zai-coding-plan/glm-5.2",
            prompt="design the deliberation",
            response="{}",
            finish_reason=dispatch_reason,
        ),
        stages=[
            StageSpan(
                stage_id=f"stage_{i}",
                kind="worker",
                model="deepseek/deepseek-chat",
                prompt="p",
                response="r",
                finish_reason=reason,
            )
            for i, reason in enumerate(reasons)
        ],
    )


def test_aggregated_finish_reason_length_when_any_stage_truncated() -> None:
    """One truncated stage span ⇒ the choice reports ``"length"``."""
    trace = _trace_with_stage_finish_reasons(["stop", "length", "stop"])
    assert api_server.aggregated_finish_reason(trace) == "length"


def test_aggregated_finish_reason_stop_when_no_stage_truncated() -> None:
    """No truncated span (``"stop"`` or unset ``""``) ⇒ ``"stop"``."""
    trace = _trace_with_stage_finish_reasons(["stop", "", "stop"])
    assert api_server.aggregated_finish_reason(trace) == "stop"


def test_aggregated_finish_reason_ignores_dispatch_span() -> None:
    """Only answer-contributing stages count — the dispatch span never does.

    ``trace.stages`` never contains the dispatch span: the dispatcher's design
    call is small, structured, and uncapped, and it contributes no answer
    text, so its outcome must not surface as the deliberation's finish reason.
    """
    trace = _trace_with_stage_finish_reasons([], dispatch_reason="length")
    assert api_server.aggregated_finish_reason(trace) == "stop"


def _client_with_gateway(config, responder):  # type: ignore[no-untyped-def]
    """TestClient + FakeGateway pair so tests can script every call."""
    gateway = FakeGateway(responder)
    engine = Engine(config, gateway)
    app = api_server.create_app(config=config, engine=engine)
    return TestClient(app), gateway


def _truncating_responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    """Workers report ``length``; dispatcher and aggregator stay normal."""
    if response_format is not None:  # dispatcher design call — uncapped
        return GatewayResponse(
            text=dispatch_json(),
            model=model,
            tokens_input=100,
            tokens_output=200,
        )
    joined = json.dumps(messages)
    if "Upstream outputs" in joined:  # aggregator merges the truncated outputs
        return GatewayResponse(
            text="FINAL ANSWER",
            model=model,
            tokens_input=60,
            tokens_output=90,
            finish_reason="stop",
        )
    return GatewayResponse(  # workers truncated at their max_tokens cap
        text=f"worker {model} cut off mid-sent",
        model=model,
        tokens_input=20,
        tokens_output=40,
        finish_reason="length",
    )


def _standard_responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    """Every call finishes normally — no truncation anywhere."""
    if response_format is not None:
        return GatewayResponse(
            text=dispatch_json(),
            model=model,
            tokens_input=100,
            tokens_output=200,
        )
    joined = json.dumps(messages)
    if "Upstream outputs" in joined:
        return GatewayResponse(
            text="FINAL ANSWER",
            model=model,
            tokens_input=60,
            tokens_output=90,
        )
    return GatewayResponse(
        text=f"worker {model}",
        model=model,
        tokens_input=20,
        tokens_output=40,
    )


def test_chat_completions_finish_reason_length_when_worker_truncated(config) -> None:  # type: ignore[no-untyped-def]
    """Route-level: a truncated worker span surfaces as ``finish_reason="length"``."""
    client, _gateway = _client_with_gateway(config, _truncating_responder)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["choices"][0]["finish_reason"] == "length"


def test_chat_completions_finish_reason_stop_when_no_truncation(config) -> None:  # type: ignore[no-untyped-def]
    """Route-level: an untruncated deliberation keeps the ``"stop"`` default."""
    client, _gateway = _client_with_gateway(config, _standard_responder)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["choices"][0]["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_stage_span_carries_gateway_finish_reason(config) -> None:  # type: ignore[no-untyped-def]
    """Span plumbing: each closed StageSpan carries ITS call's finish reason.

    Workers report ``length`` (truncated at the cap), the aggregator reports
    ``stop``, and the dispatcher's design call reports none — so every span
    close site (workers, aggregator, dispatch) must read the finish reason off
    its own ``GatewayResponse``, never a shared or defaulted one.
    """

    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:  # dispatcher — carries no finish reason
            return GatewayResponse(
                text=dispatch_json(),
                model=model,
                tokens_input=120,
                tokens_output=180,
            )
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:  # aggregator
            return GatewayResponse(
                text=f"[MERGED {model}]",
                model=model,
                tokens_input=60,
                tokens_output=90,
                finish_reason="stop",
            )
        return GatewayResponse(  # workers
            text=f"[worker {model}]",
            model=model,
            tokens_input=25,
            tokens_output=35,
            finish_reason="length",
        )

    gw = FakeGateway(responder)
    result = await Engine(config, gw).deliberate("task", "auto")
    trace = result.trace

    assert trace.dispatch.finish_reason == ""
    worker_spans = [s for s in trace.stages if s.kind == "worker"]
    assert worker_spans
    assert all(s.finish_reason == "length" for s in worker_spans)
    agg_spans = [s for s in trace.stages if s.kind in {"aggregator", "merge", "audit"}]
    assert agg_spans
    assert all(s.finish_reason == "stop" for s in agg_spans)
