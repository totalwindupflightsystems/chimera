"""Regression tests: the ``/web/*`` surface honours ``auth.enabled`` (INT-API-001).

``require_api_key`` used to be attached only to ``POST /v1/deliberate`` and
``POST /v1/chat/completions`` (``src/chimera/api/server.py``), so the whole web
router — session creation, session chat, session history, the SSE stream, the
SPA shell — stayed reachable with no credentials even with auth turned on.  A
keyless ``POST /web/sessions`` answered 200 on a server started with
``CHIMERA_AUTH_ENABLED=true`` while ``POST /v1/deliberate`` answered 401.

The fix attaches the existing dependency at the ROUTER (``create_app``'s
``app.include_router(web_router, dependencies=[Depends(require_api_key)])``),
so every current and future ``/web`` route is gated by one line and nothing
below the auth layer runs for an unauthenticated request.

DF-CHIMERA-V2-41 refined that: the SPA shell and the vendored assets it loads
are served by a second, public router (``ui_router``) — a browser has no key to
send before it has loaded the page that asks for one, so gating the shell made
the UI unreachable.  The dependency on ``router`` is unchanged, and the census
test below pins the carve-out to exactly those two read-only paths.

These tests pin the edge behaviour, with a stubbed gateway throughout — an
unauthenticated request must be refused BEFORE the engine is reached, so a 401
case must record zero gateway calls (no provider billing):

* auth ON  : every ``/web`` path answers 401 without credentials, 200 with a
  valid ``X-API-Key`` or ``Authorization: Bearer`` key, and the keyed chat path
  still deliberates;
* auth OFF : the default deployment is byte-for-byte unchanged — keyless web
  requests keep working.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import chimera.web.routes as web_routes  # noqa: E402
from chimera.api.server import create_app  # noqa: E402
from chimera.config import ChimeraConfig  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402
from chimera.web.session import SessionManager  # noqa: E402
from chimera.web.sse import SSEBroadcaster  # noqa: E402
from tests.conftest import CONFIG_DICT, FakeGateway, dispatch_json  # noqa: E402

#: Deliberately bogus keys — not a secret, never a real credential.
WEB_KEY = "web-test-key-not-a-secret"
ENV_KEY = "env-test-key-not-a-secret"

#: A syntactically valid but nonexistent session id (path-parameter filler).
MISSING_SESSION = "deadbeef0000"


def _resp(text: str, model: str, tok_in: int, tok_out: int) -> GatewayResponse:
    return GatewayResponse(text=text, model=model, tokens_input=tok_in, tokens_output=tok_out)


def _responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
    """Canned responder mirroring tests/test_web.py — zero network calls."""
    if response_format is not None:
        return _resp(dispatch_json(), model, 100, 200)
    joined = json.dumps(messages)
    if "Upstream outputs" in joined:
        return _resp("FINAL ANSWER", model, 60, 90)
    return _resp(f"worker {model}", model, 20, 40)


def _config(auth: dict | None = None) -> ChimeraConfig:
    cfg_dict = dict(CONFIG_DICT)
    if auth is not None:
        cfg_dict["auth"] = auth
    return ChimeraConfig.model_validate(cfg_dict)


def _auth_on_list() -> dict:
    """Auth enabled, ``list`` mode, one named key."""
    return {
        "enabled": True,
        "mode": "list",
        "keys": [{"key": WEB_KEY, "name": "web-test"}],
    }


def _auth_on_env() -> dict:
    """Auth enabled, ``env`` mode (key read from CHIMERA_API_KEY)."""
    return {"enabled": True, "mode": "env"}


def _auth_off() -> dict:
    """Explicitly disabled — the default deployment."""
    return {"enabled": False}


def _build(auth: dict | None = None):  # type: ignore[no-untyped-def]
    """Return ``(client, app, gateway)`` built on a stubbed gateway."""
    config = _config(auth)
    gateway = FakeGateway(_responder)
    app = create_app(config=config, engine=Engine(config, gateway))
    return TestClient(app), app, gateway


@pytest.fixture(autouse=True)
def _reset_web_singletons():  # type: ignore[no-untyped-def]
    """Keep module-level web state isolated (same fixture as tests/test_web.py)."""
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()
    yield
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()


def _keyed_session(client: TestClient) -> str:
    """Create a session with a valid key and mark its SSE stream ready."""
    client.headers["X-API-Key"] = WEB_KEY
    response = client.post("/web/sessions")
    assert response.status_code == 200, response.text
    session_id = response.json()["session_id"]
    web_routes._sse_broadcaster.ensure_ready(session_id).set()
    return session_id


def _assert_unauthorized(response, *, expect_code: int = 401) -> None:  # type: ignore[no-untyped-def]
    assert response.status_code == expect_code, response.text
    detail = response.json().get("detail", response.json())
    assert detail["error"] == "unauthorized"
    assert "API key" in detail["message"]


# ---------------------------------------------------------------------------
# auth enabled — the whole /web surface requires the key
# ---------------------------------------------------------------------------


def test_web_session_create_requires_key() -> None:
    client, _, gateway = _build(_auth_on_list())

    response = client.post("/web/sessions")

    _assert_unauthorized(response)
    assert "Missing API key" in response.json()["detail"]["message"]
    # The refusal happens at the auth layer: no engine call, no billing.
    assert gateway.calls == []
    assert web_routes._session_manager.session_count == 0


def test_web_session_create_accepts_x_api_key() -> None:
    client, _, _ = _build(_auth_on_list())
    client.headers["X-API-Key"] = WEB_KEY

    response = client.post("/web/sessions")

    assert response.status_code == 200, response.text
    assert len(response.json()["session_id"]) == 12


def test_web_session_create_accepts_bearer_token() -> None:
    client, _, _ = _build(_auth_on_list())
    client.headers["Authorization"] = f"Bearer {WEB_KEY}"

    response = client.post("/web/sessions")

    assert response.status_code == 200, response.text


def test_web_session_create_rejects_wrong_key() -> None:
    client, _, gateway = _build(_auth_on_list())
    client.headers["X-API-Key"] = "wrong-key-not-a-secret"

    response = client.post("/web/sessions")

    _assert_unauthorized(response)
    assert "Invalid API key" in response.json()["detail"]["message"]
    assert gateway.calls == []


def test_web_chat_requires_key_and_never_reaches_the_engine() -> None:
    client, _, gateway = _build(_auth_on_list())
    session_id = _keyed_session(client)

    # Drop the credential: the session exists, the caller is anonymous.
    del client.headers["X-API-Key"]
    gateway.calls.clear()

    response = client.post(
        f"/web/sessions/{session_id}/chat",
        json={"prompt": "hello", "formation": "simple"},
    )

    _assert_unauthorized(response)
    assert gateway.calls == []
    # Rejected before the SSE readiness/broadcast block and before any turn.
    session = web_routes._session_manager.get(session_id)
    assert session is not None
    assert session.turn_count == 0


def test_web_session_history_requires_key() -> None:
    client, _, _ = _build(_auth_on_list())
    session_id = _keyed_session(client)
    del client.headers["X-API-Key"]

    response = client.get(f"/web/sessions/{session_id}")

    _assert_unauthorized(response)


def test_web_sse_stream_requires_key() -> None:
    client, _, _ = _build(_auth_on_list())
    session_id = _keyed_session(client)
    del client.headers["X-API-Key"]

    response = client.get(f"/web/sse/{session_id}")

    _assert_unauthorized(response)
    assert session_id not in web_routes._sse_broadcaster._subscribers


def test_web_spa_shell_is_served_without_a_key() -> None:
    """DF-CHIMERA-V2-41: the shell is public — the data surface is not.

    The SPA is the only place a browser can enter a key, so gating it locked
    every browser out of the UI with no way back in: ``GET /web/`` answered 401
    JSON, which the browser rendered as the page.  The shell (and the vendored
    assets it loads) therefore serve anonymously; the box they ship is what
    asks for the key, and every route it calls back into stays gated (see
    ``test_every_registered_web_path_is_gated_except_the_public_shell``).
    """
    client, _, _ = _build(_auth_on_list())

    response = client.get("/web/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="auth-overlay"' in response.text, "the public shell must carry the key prompt"


def test_web_debug_reset_requires_key() -> None:
    client, _, _ = _build(_auth_on_list())
    before = web_routes._session_manager

    response = client.post("/web/debug/reset")

    _assert_unauthorized(response)
    # The singletons were NOT replaced by an anonymous caller.
    assert web_routes._session_manager is before


def test_every_registered_web_path_is_gated_except_the_public_shell() -> None:
    """Derive the surface from the app's own OpenAPI spec, not a hardcoded list.

    A route added to the web router later inherits the router-level dependency,
    so this test fails (rather than silently missing coverage) if any ``/web``
    path ever escapes the key requirement.

    DF-CHIMERA-V2-41 carves exactly TWO read-only paths out of that gate — the
    SPA shell and the vendored static assets it loads — because a browser has
    no key to send before it has loaded the page that asks for one.  Everything
    else (including the SSE stream, which validates the key the same way) stays
    a 401 for an anonymous caller.
    """
    client, app, gateway = _build(_auth_on_list())

    #: The carve-out, in the app's own OpenAPI spelling.
    public_paths = {"/web/", "/web/{asset_path}"}

    web_paths = sorted(p for p in app.openapi()["paths"] if p.startswith("/web"))
    assert web_paths, "the web router must be mounted for this test to mean anything"
    assert "/web/sessions" in web_paths
    assert "/web/sessions/{session_id}/chat" in web_paths

    gated: list[str] = []
    public: list[str] = []
    for path in web_paths:
        item = app.openapi()["paths"][path]
        url = path.replace("{session_id}", MISSING_SESSION)
        for method in ("get", "post"):
            if method not in item:
                continue
            if path in public_paths:
                public.append(f"{method.upper()} {path}")
                continue
            response = client.request(method.upper(), url)
            # 401 wins over 404: the auth layer runs before the handler, so an
            # anonymous caller learns nothing about which sessions exist.
            assert response.status_code == 401, f"{method.upper()} {path} -> {response.status_code}"
            gated.append(f"{method.upper()} {path}")

    # DF-CHIMERA-V2-21: the vendored-asset catch-all (GET /web/vendor/…) is now
    # public alongside the shell; the other five paths — session create, chat,
    # history, debug/reset and the SSE stream — stay gated.
    assert public == ["GET /web/", "GET /web/{asset_path}"], public
    assert len(gated) == 5, gated
    assert gateway.calls == []

    # The carve-out is real, not merely "not a 401": the shell and a vendored
    # asset both serve anonymously.
    assert client.get("/web/").status_code == 200
    assert client.get("/web/vendor/mermaid.min.js").status_code == 200


def test_keyed_chat_still_deliberates() -> None:
    """No regression: a correctly keyed web chat behaves exactly as before."""
    client, _, gateway = _build(_auth_on_list())
    session_id = _keyed_session(client)

    response = client.post(
        f"/web/sessions/{session_id}/chat",
        json={"prompt": "hi", "formation": "simple"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["answer"] == "FINAL ANSWER"
    assert data["turn_number"] == 1
    assert gateway.calls
    history = client.get(f"/web/sessions/{session_id}").json()
    assert history["turn_count"] == 1


def test_keyed_spa_and_openapi_are_reachable_with_the_key() -> None:
    client, _, _ = _build(_auth_on_list())
    client.headers["X-API-Key"] = WEB_KEY

    assert client.get("/web/").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_v1_deliberate_control_is_unchanged() -> None:
    """The pre-existing protected surface keeps answering 401 without a key."""
    client, _, gateway = _build(_auth_on_list())

    response = client.post("/v1/deliberate", json={"prompt": "hello"})

    _assert_unauthorized(response)
    assert gateway.calls == []


def test_env_mode_gates_the_web_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    """``mode: env`` reads CHIMERA_API_KEY — same gate on /web/*."""
    monkeypatch.setenv("CHIMERA_API_KEY", ENV_KEY)
    client, _, gateway = _build(_auth_on_env())

    _assert_unauthorized(client.post("/web/sessions"))

    client.headers["X-API-Key"] = ENV_KEY
    assert client.post("/web/sessions").status_code == 200
    assert gateway.calls == []


# ---------------------------------------------------------------------------
# auth disabled — the default deployment keeps working keyless
# ---------------------------------------------------------------------------


def test_auth_disabled_web_session_is_keyless() -> None:
    client, _, _ = _build(_auth_off())

    response = client.post("/web/sessions")

    assert response.status_code == 200, response.text
    assert len(response.json()["session_id"]) == 12


def test_auth_disabled_web_spa_is_keyless() -> None:
    client, _, _ = _build(_auth_off())

    assert client.get("/web/").status_code == 200


def test_auth_disabled_web_chat_still_deliberates_keyless() -> None:
    client, _, gateway = _build(_auth_off())
    session_id = client.post("/web/sessions").json()["session_id"]
    web_routes._sse_broadcaster.ensure_ready(session_id).set()

    response = client.post(
        f"/web/sessions/{session_id}/chat",
        json={"prompt": "hi", "formation": "simple"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["answer"] == "FINAL ANSWER"
    assert gateway.calls


def test_auth_disabled_history_and_sse_are_keyless() -> None:
    import time

    client, _, _ = _build(_auth_off())
    session_id = client.post("/web/sessions").json()["session_id"]

    assert client.get(f"/web/sessions/{session_id}").status_code == 200

    # Give the session a recent turn + stored events so the SSE stream closes
    # immediately instead of waiting out its 30s idle timeout.
    session = web_routes._session_manager.get(session_id)
    assert session is not None
    session.add_turn(
        web_routes.Turn(
            user_prompt="p",
            answer="a",
            formation="simple",
            dispatch_model="m",
            worker_models=[],
            aggregator_model="m",
            total_tokens=1,
            total_cost=0.0,
            timestamp=time.time(),
        )
    )
    session.last_sse_events = [("deliberation_done", {"answer": "a", "turn_number": 1})]

    stream = client.get(f"/web/sse/{session_id}")

    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "event: deliberation_done" in stream.text


def test_no_auth_section_at_all_defaults_to_open() -> None:
    """A config with no ``auth`` block leaves the web surface open (default)."""
    client, _, _ = _build()

    assert client.post("/web/sessions").status_code == 200
