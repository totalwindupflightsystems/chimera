"""Regression tests: the /web session chat surface validates the formation.

DF-CHIMERA-0917-2 (surface-parity class).  REST answers HTTP 422
``Unknown formation: <name>`` (``src/chimera/api/server.py``) and the CLI exits
2 before any provider call; the web session surface used to hand the name
straight to ``engine.deliberate(...)``, where the dispatcher's internal
``auto`` fallback silently deliberated with the WRONG formation — a typo billed
real providers and this surface still answered 200.

These tests pin the edge behaviour:

* an unknown formation -> 422 whose detail names the offending value and the
  available names, with ZERO gateway calls recorded (no provider call, no
  billing) and no turn recorded on the session;
* a valid formation still returns 200 with an answer;
* the default (``formation`` omitted) still deliberates with ``auto``.

The dispatcher's internal unknown-formation fallback is intentionally left
alone (``tests/test_dispatcher.py::test_dispatcher_unknown_formation_uses_auto``)
— validation belongs at the HTTP edge only.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import chimera.web.routes as web_routes  # noqa: E402
from chimera.api.server import create_app  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402
from chimera.web.session import SessionManager  # noqa: E402
from chimera.web.sse import SSEBroadcaster  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402


def _resp(text: str, model: str, tok_in: int, tok_out: int) -> GatewayResponse:
    return GatewayResponse(text=text, model=model, tokens_input=tok_in, tokens_output=tok_out)


def _build(config):  # type: ignore[no-untyped-def]
    """Return ``(client, gateway)`` — responder mirrors tests/test_web.py::_client."""

    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:
            return _resp(dispatch_json(), model, 100, 200)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:
            return _resp("FINAL ANSWER", model, 60, 90)
        return _resp(f"worker {model}", model, 20, 40)

    gateway = FakeGateway(responder)
    engine = Engine(config, gateway)
    app = create_app(config=config, engine=engine)
    return TestClient(app), gateway


@pytest.fixture(autouse=True)
def _reset_web_singletons():  # type: ignore[no-untyped-def]
    """Keep module-level web state isolated (same fixture as tests/test_web.py)."""
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()
    yield
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()


def _new_session(client: TestClient, *, sse_ready: bool = True) -> str:
    response = client.post("/web/sessions")
    assert response.status_code == 200, response.text
    session_id = response.json()["session_id"]
    # unsubscribe_all() clears the readiness signal after a chat call, so mark
    # it ready up-front to avoid the 2s wait in session_chat().  Pass
    # sse_ready=False to observe whether a request ever reaches that block.
    if sse_ready:
        web_routes._sse_broadcaster.ensure_ready(session_id).set()
    return session_id


# ---------------------------------------------------------------------------
# Unknown formation -> 422, and nothing reaches the engine
# ---------------------------------------------------------------------------


def test_unknown_formation_is_rejected_before_any_provider_call(config) -> None:  # type: ignore[no-untyped-def]
    client, gateway = _build(config)
    # Deliberately NOT pre-registered with the broadcaster: if the guard ever
    # ran after the SSE block, this session id would appear in _ready.
    session_id = _new_session(client, sse_ready=False)

    response = client.post(
        f"/web/sessions/{session_id}/chat",
        json={"prompt": "hi", "formation": "nope"},
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert "Unknown formation" in detail
    assert "nope" in detail
    assert "Available formations: " in detail
    # Every configured formation is offered, sorted and comma-separated, so the
    # error is actionable (parity with the CLI's available-names list).
    assert ", ".join(sorted(config.formations)) in detail
    assert "simple" in detail

    # Zero provider calls: an unknown name must not bill anybody.
    assert gateway.calls == []

    # The rejection happens BEFORE the SSE readiness/broadcast block and
    # BEFORE any turn is recorded on the session.
    assert session_id not in web_routes._sse_broadcaster._ready
    history = client.get(f"/web/sessions/{session_id}").json()
    assert history["turn_count"] == 0
    assert history["turns"] == []


def test_unknown_formation_does_not_record_a_turn(config) -> None:  # type: ignore[no-untyped-def]
    """A rejected chat leaves the session usable — a later valid turn works."""
    client, gateway = _build(config)
    session_id = _new_session(client, sse_ready=False)

    rejected = client.post(
        f"/web/sessions/{session_id}/chat",
        json={"prompt": "typo", "formation": "dabate"},
    )
    assert rejected.status_code == 422, rejected.text
    assert "dabate" in rejected.json()["detail"]
    assert gateway.calls == []
    assert session_id not in web_routes._sse_broadcaster._ready

    web_routes._sse_broadcaster.ensure_ready(session_id).set()
    accepted = client.post(
        f"/web/sessions/{session_id}/chat",
        json={"prompt": "hi", "formation": "simple"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["answer"]
    assert accepted.json()["turn_number"] == 1


# ---------------------------------------------------------------------------
# Valid formations keep working
# ---------------------------------------------------------------------------


def test_valid_formation_still_deliberates(config) -> None:  # type: ignore[no-untyped-def]
    client, gateway = _build(config)
    session_id = _new_session(client)

    response = client.post(
        f"/web/sessions/{session_id}/chat",
        json={"prompt": "hi", "formation": "simple"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["answer"]
    assert data["turn_number"] == 1
    assert gateway.calls


def test_default_formation_uses_auto_and_still_works(config) -> None:  # type: ignore[no-untyped-def]
    client, gateway = _build(config)
    session_id = _new_session(client)

    response = client.post(
        f"/web/sessions/{session_id}/chat",
        json={"prompt": "hi"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["answer"]
    assert data["turn_number"] == 1
    assert gateway.calls
    history = client.get(f"/web/sessions/{session_id}").json()
    assert history["turns"][0]["formation"] == "auto"
