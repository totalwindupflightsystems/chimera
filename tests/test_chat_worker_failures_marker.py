"""Hard worker-failure marker on the OpenAI-compatible chat response.

DF-CHIMERA-V2-75.  When a worker stage dies hard upstream (gateway failure,
timeout, budget exhaustion) the deliberation still answers — HTTP 200 with
``finish_reason="stop"`` — but the merged output is silently missing that
worker's contribution.  ``/v1/deliberate`` exposes the truth as
``trace.worker_failures`` and the CLI prints a dropped-worker warning; the
chat surface showed nothing.  This adds ``chimera_worker_failures`` (one
``{stage_id, model, error}`` entry per dropped stage) to
``ChatCompletionResponse``, ABSENT on clean runs
(``response_model_exclude_none``, byte-identical shape).

The new marker is deliberately DISJOINT from ``chimera_degraded_reasons``
(DF-CHIMERA-V2-55), which stays token-limit truncation only: a hard worker
failure sets the former and never the latter, and vice versa.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api import server as api_server  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayError, GatewayResponse  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402

#: worker_1's model in the default dispatcher payload (tests/conftest.py).
WORKER_1 = "deepseek/deepseek-chat"
WORKER_2 = "openrouter/google/gemini-2.5-flash"


def _failing_responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    """worker_1 dies with a hard upstream error; everyone else answers."""
    if response_format is not None:  # dispatcher design call
        return GatewayResponse(
            text=dispatch_json(),
            model=model,
            tokens_input=100,
            tokens_output=200,
        )
    joined = json.dumps(messages)
    if "Upstream outputs" in joined:  # aggregator merges over the drop
        return GatewayResponse(
            text="FINAL ANSWER",
            model=model,
            tokens_input=60,
            tokens_output=90,
        )
    if model == WORKER_1:  # hard upstream failure — the dropped worker
        raise GatewayError("upstream connect error")
    return GatewayResponse(  # worker_2 fine
        text=f"worker {model}",
        model=model,
        tokens_input=20,
        tokens_output=40,
    )


def _standard_responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    """Every call finishes normally — no failure anywhere."""
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


# --------------------------------------------------------------------------- #
# Engine level — the trace source the chat surface mirrors
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_trace_worker_failures_record_the_dropped_stage(config) -> None:  # type: ignore[no-untyped-def]
    """Engine-level: one entry per dropped stage, with stage/model/error."""
    gw = FakeGateway(_failing_responder)
    result = await Engine(config, gw).deliberate("task", "auto")
    assert len(result.trace.worker_failures) == 1, result.trace.worker_failures
    failure = result.trace.worker_failures[0]
    assert failure.stage_id == "worker_1"
    assert failure.model == WORKER_1
    assert failure.error  # upstream reason present, never blank


@pytest.mark.asyncio
async def test_trace_worker_failures_empty_when_clean(config) -> None:  # type: ignore[no-untyped-def]
    """Engine-level: a clean run carries no dropped stages."""
    gw = FakeGateway(_standard_responder)
    result = await Engine(config, gw).deliberate("task", "auto")
    assert result.trace.worker_failures == []


# --------------------------------------------------------------------------- #
# Chat surface — the new marker
# --------------------------------------------------------------------------- #


def test_chat_completions_carries_worker_failure_marker(config) -> None:  # type: ignore[no-untyped-def]
    """Route-level: a dropped worker rides the 200 response as the marker."""
    client, _gateway = _client_with_gateway(config, _failing_responder)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["choices"][0]["finish_reason"] == "stop"  # the silent-200 problem
    failures = body["chimera_worker_failures"]
    assert len(failures) == 1, failures
    assert failures[0]["stage_id"] == "worker_1"
    assert failures[0]["model"] == WORKER_1
    assert failures[0]["error"]  # mirrors trace.worker_failures' shape


def test_chat_completions_omits_worker_failure_marker_when_clean(config) -> None:  # type: ignore[no-untyped-def]
    """Route-level: a clean run keeps the field ABSENT (byte-identical shape)."""
    client, _gateway = _client_with_gateway(config, _standard_responder)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    assert "chimera_worker_failures" not in r.json()


def test_chat_completions_worker_failures_disjoint_from_truncation_marker(config) -> None:  # type: ignore[no-untyped-def]
    """Disjointness: a hard failure sets ONLY chimera_worker_failures.

    ``chimera_degraded_reasons`` stays token-limit truncation only
    (DF-CHIMERA-V2-55 semantics unchanged) — a dropped worker must not leak
    into it.
    """
    client, _gateway = _client_with_gateway(config, _failing_responder)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chimera_worker_failures"]
    assert "chimera_degraded_reasons" not in body


def test_chat_completions_truncation_marker_disjoint_from_worker_failures(config) -> None:  # type: ignore[no-untyped-def]
    """Disjointness, other direction: truncation sets ONLY degraded_reasons.

    Non-vacuity: the truncating run REALLY has both lists available (the
    truncation marker is present), so the absence of the worker-failure
    marker is a real negative, not an empty-world accident.
    """
    from tests.test_truncation_degraded_marker import _truncating_responder

    client, _gateway = _client_with_gateway(config, _truncating_responder)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chimera_degraded_reasons"]  # truncation really happened
    assert "chimera_worker_failures" not in body


# --------------------------------------------------------------------------- #
# /v1/deliberate — the mirror the chat surface copies
# --------------------------------------------------------------------------- #


def test_deliberate_trace_carries_worker_failures(config) -> None:  # type: ignore[no-untyped-def]
    """``POST /v1/deliberate``: the dropped stage rides the trace summary."""
    client, _gateway = _client_with_gateway(config, _failing_responder)
    r = client.post(
        "/v1/deliberate",
        json={"prompt": "hi", "formation": "auto"},
    )
    assert r.status_code == 200, r.text
    failures = r.json()["trace"]["worker_failures"]
    assert [f["stage_id"] for f in failures] == ["worker_1"], failures
    assert failures[0]["model"] == WORKER_1, failures
    assert failures[0]["error"], failures
