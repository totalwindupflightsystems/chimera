"""Degraded-answer marker for token-capped worker stages.

DF-CHIMERA-V2-55.  With a small ``max_tokens`` cap a worker stage is cut off
mid-protocol (its output is a fragment like ``"We need answer user. Output:"``),
the aggregator merges its own reasoning about those fragments, and the final
answer READS as clean, well-formed prose — a cost-bounding client cannot tell
that garbage merge from a good one.  DF-CHIMERA-V2-54 surfaced the truncation
as the choice's ``finish_reason="length"``; this task adds the visible
degraded marker that names the truncated stages: ``trace.degraded_reasons``
(one ``"<stage_id>: token_limit"`` entry per truncated stage span) and the
``chimera_degraded_reasons`` field on the OpenAI-compatible response (absent
when nothing was truncated).
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api import server as api_server  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402


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


def _client_with_gateway(config, responder):  # type: ignore[no-untyped-def]
    """TestClient + FakeGateway pair so tests can script every call."""
    gateway = FakeGateway(responder)
    engine = Engine(config, gateway)
    app = api_server.create_app(config=config, engine=engine)
    return TestClient(app), gateway


@pytest.mark.asyncio
async def test_trace_degraded_reasons_name_truncated_workers(config) -> None:  # type: ignore[no-untyped-def]
    """Engine-level: one ``"<stage_id>: token_limit"`` entry per truncated stage."""
    gw = FakeGateway(_truncating_responder)
    result = await Engine(config, gw).deliberate("task", "auto")
    assert sorted(result.trace.degraded_reasons) == [
        "worker_1: token_limit",
        "worker_2: token_limit",
    ]


@pytest.mark.asyncio
async def test_trace_degraded_reasons_empty_when_no_truncation(config) -> None:  # type: ignore[no-untyped-def]
    """Engine-level: a clean run carries no degraded marker."""
    gw = FakeGateway(_standard_responder)
    result = await Engine(config, gw).deliberate("task", "auto")
    assert result.trace.degraded_reasons == []


@pytest.mark.asyncio
async def test_trace_degraded_reasons_exclude_dispatch_span(config) -> None:  # type: ignore[no-untyped-def]
    """The dispatch span never contributes — its design call produces no answer text.

    Non-vacuity: even when the dispatcher's own call reports ``length``, no
    ``"dispatch: token_limit"`` entry may appear; only the truncated aggregator
    (an answer-contributing stage) is named.
    """

    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:  # dispatcher — truncated design call
            return GatewayResponse(
                text=dispatch_json(),
                model=model,
                tokens_input=100,
                tokens_output=200,
                finish_reason="length",
            )
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:  # aggregator truncated too
            return GatewayResponse(
                text="FINAL",
                model=model,
                tokens_input=60,
                tokens_output=90,
                finish_reason="length",
            )
        return GatewayResponse(  # workers clean
            text=f"worker {model}",
            model=model,
            tokens_input=20,
            tokens_output=40,
            finish_reason="stop",
        )

    gw = FakeGateway(responder)
    result = await Engine(config, gw).deliberate("task", "auto")
    assert result.trace.degraded_reasons == ["aggregator: token_limit"]


def test_chat_completions_carries_degraded_marker_when_worker_truncated(config) -> None:  # type: ignore[no-untyped-def]
    """Route-level: the compat response names the truncated stages."""
    client, _gateway = _client_with_gateway(config, _truncating_responder)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert sorted(body["chimera_degraded_reasons"]) == [
        "worker_1: token_limit",
        "worker_2: token_limit",
    ]


def test_chat_completions_omits_degraded_marker_when_clean(config) -> None:  # type: ignore[no-untyped-def]
    """Route-level: a clean run keeps the field ABSENT (byte-identical shape)."""
    client, _gateway = _client_with_gateway(config, _standard_responder)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    assert "chimera_degraded_reasons" not in r.json()


def test_deliberate_trace_carries_degraded_reasons(config) -> None:  # type: ignore[no-untyped-def]
    """``POST /v1/deliberate``: the marker rides the trace summary."""
    client, _gateway = _client_with_gateway(config, _truncating_responder)
    r = client.post(
        "/v1/deliberate",
        json={"prompt": "hi", "formation": "auto"},
    )
    assert r.status_code == 200, r.text
    assert sorted(r.json()["trace"]["degraded_reasons"]) == [
        "worker_1: token_limit",
        "worker_2: token_limit",
    ]


def test_deliberate_trace_degraded_reasons_empty_when_clean(config) -> None:  # type: ignore[no-untyped-def]
    """``POST /v1/deliberate``: a clean run's trace carries an empty list."""
    client, _gateway = _client_with_gateway(config, _standard_responder)
    r = client.post(
        "/v1/deliberate",
        json={"prompt": "hi", "formation": "auto"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["trace"]["degraded_reasons"] == []
