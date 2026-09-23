"""DF-CHIMERA-V2-41 — with auth enabled the browser can still reach the web UI.

The defect: ``create_app`` mounted the WHOLE web router behind
``Depends(require_api_key)``, so ``GET /web/`` — the SPA shell — answered 401
JSON as the page whenever ``auth.enabled=true``.  A browser has nowhere to
type a key before the page that asks for one has loaded, so turning auth on
locked every browser out of the UI entirely: the shell was gated, and the SPA
sent no credential on any of its ``fetch`` calls (``EventSource``, which drives
the SSE stream, cannot set request headers at all).

The fix has three halves, pinned here:

* **public read surface** — ``GET /web/`` (the shell) and
  ``GET /web/{asset_path}`` (the vendored ``.js``/``.css`` it loads) are served
  WITHOUT a key, because they are the page and the code that must run before a
  key can be entered.  Every other ``/web`` route — session create, chat,
  history, the SSE stream, the debug reset — keeps the header-only
  ``require_api_key`` semantics: 401 without a valid key.
* **key-entry surface** — the SPA ships an auth box, stores the entered key
  (``localStorage``), attaches ``Authorization: Bearer <key>`` to every API
  fetch (the header shape ``_extract_api_key`` reads), and retries once after a
  401.  With auth disabled nothing is stored, no header is attached and the box
  never appears.
* **SSE seam** — ``EventSource`` cannot set headers, so ``GET /web/sse/{id}``
  ADDITIONALLY accepts ``?api_key=``, verified by the same comparison function
  the header path uses (no forked check).  It is the only route that takes it.

Hermetic: FastAPI ``TestClient`` over a ``FakeGateway`` — no network, no keys.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import chimera.api.dependencies as dependencies  # noqa: E402
import chimera.web.routes as web_routes  # noqa: E402
from chimera.api.server import create_app  # noqa: E402
from chimera.config import ChimeraConfig  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.web.session import SessionManager  # noqa: E402
from chimera.web.sse import SSEBroadcaster  # noqa: E402
from tests.conftest import CONFIG_DICT, FakeGateway  # noqa: E402

#: Deliberately bogus keys — not secrets, never real credentials.
WEB_KEY = "web-test-key-not-a-secret"
ENV_KEY = "env-test-key-not-a-secret"
WRONG_KEY = "wrong-key-not-a-secret"

REPO_ROOT = Path(__file__).resolve().parents[1]
SPA_PATH = REPO_ROOT / "src" / "chimera" / "web" / "static" / "index.html"
SPA_SOURCE = SPA_PATH.read_text(encoding="utf-8")


def _js_function(declaration: str) -> str:
    """The text of a shipped JS function, from its declaration to its last brace.

    Brace-matched rather than section-sliced so the assertion window is exactly
    the function's own body — a statement that merely sits NEAR it in the file
    cannot satisfy a check (same helper shape as tests/test_web_sse_live.py).
    """
    start = SPA_SOURCE.index(declaration)
    brace = SPA_SOURCE.index("{", start + len(declaration))
    depth = 0
    for i in range(brace, len(SPA_SOURCE)):
        char = SPA_SOURCE[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return SPA_SOURCE[start : i + 1]
    raise AssertionError(f"unbalanced braces after {declaration!r}")


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
    gateway = FakeGateway()
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


def _keyed_session(client: TestClient, key: str = WEB_KEY) -> str:
    """Create a session with a valid key and mark its SSE stream ready."""
    client.headers["X-API-Key"] = key
    response = client.post("/web/sessions")
    assert response.status_code == 200, response.text
    session_id = response.json()["session_id"]
    web_routes._sse_broadcaster.ensure_ready(session_id).set()
    return session_id


def _finish_last_turn(session_id: str) -> None:
    """Give *session_id* one recorded turn plus its stored SSE events.

    Such a session is replayed-then-closed by the SSE route, so a test reads a
    bounded body instead of waiting out the idle timeout (the same setup
    tests/test_web_auth.py uses for its auth-disabled SSE case).
    """
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


def _assert_unauthorized(response) -> None:  # type: ignore[no-untyped-def]
    assert response.status_code == 401, response.text
    detail = response.json().get("detail", response.json())
    assert detail["error"] == "unauthorized"


# ---------------------------------------------------------------------------
# A1 — the public read surface: shell + vendored assets, no key
# ---------------------------------------------------------------------------


def test_auth_enabled_serves_the_spa_shell_without_a_key() -> None:
    """THE defect: GET /web/ answered 401 JSON and the browser rendered it.

    The shell is the only place a browser can enter a key, so it must be
    readable before one is known.
    """
    client, _, _ = _build(_auth_on_list())

    response = client.get("/web/")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    assert "<html" in response.text.lower(), "the 401 JSON body was served as the page"


def test_served_shell_ships_the_key_entry_surface() -> None:
    """The public shell is only useful if it carries the box that asks for a key."""
    client, _, _ = _build(_auth_on_list())

    page = client.get("/web/").text

    assert 'id="auth-overlay"' in page
    assert 'id="auth-input"' in page
    assert 'id="auth-save"' in page


def test_auth_enabled_serves_vendored_static_assets_without_a_key() -> None:
    """A gated asset 404s-to-401 and leaves the UI unrendered: it is public too."""
    client, _, _ = _build(_auth_on_list())

    response = client.get("/web/vendor/mermaid.min.js")

    assert response.status_code == 200, response.text
    assert "javascript" in response.headers.get("content-type", "")
    assert len(response.content) > 1000


def test_auth_enabled_still_gates_the_data_routes() -> None:
    """The carve-out is exactly the shell + assets — the data surface is unchanged."""
    client, _, gateway = _build(_auth_on_list())
    session_id = _keyed_session(client)
    del client.headers["X-API-Key"]
    gateway.calls.clear()

    assert client.post("/web/sessions").status_code == 401
    assert client.get(f"/web/sessions/{session_id}").status_code == 401
    assert (
        client.post(
            f"/web/sessions/{session_id}/chat", json={"prompt": "hi", "formation": "simple"}
        ).status_code
        == 401
    )
    assert client.post("/web/debug/reset").status_code == 401
    assert client.get(f"/web/sse/{session_id}").status_code == 401
    # Nothing reached the engine: every refusal happened at the auth layer.
    assert gateway.calls == []

    # …and the keyed calls still work exactly as before.
    client.headers["X-API-Key"] = WEB_KEY
    assert client.post("/web/sessions").status_code == 200
    assert client.get(f"/web/sessions/{session_id}").status_code == 200


def test_query_param_key_does_not_open_the_data_surface() -> None:
    """The ``?api_key=`` seam is SSE-only (the one surface a browser cannot key).

    Accepting it on state-changing routes would put keys in access logs for
    every call, so the header-only dependency stays in force everywhere else.
    """
    client, _, _ = _build(_auth_on_list())

    response = client.post(f"/web/sessions?api_key={WEB_KEY}")

    _assert_unauthorized(response)
    assert web_routes._session_manager.session_count == 0


# ---------------------------------------------------------------------------
# A2 — the SSE seam: header OR ?api_key=, verified by the same checker
# ---------------------------------------------------------------------------


def test_sse_accepts_the_key_as_a_query_parameter() -> None:
    """An EventSource cannot set headers — the key rides the URL instead."""
    client, _, _ = _build(_auth_on_list())
    session_id = _keyed_session(client)
    _finish_last_turn(session_id)
    del client.headers["X-API-Key"]

    stream = client.get(f"/web/sse/{session_id}?api_key={WEB_KEY}")

    assert stream.status_code == 200, stream.text
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "event: deliberation_done" in stream.text


def test_sse_query_param_is_validated_like_the_header() -> None:
    """A missing or wrong parameter is a 401 with no subscriber registered."""
    client, _, _ = _build(_auth_on_list())
    session_id = _keyed_session(client)
    del client.headers["X-API-Key"]

    for query in ("", f"?api_key={WRONG_KEY}", "?api_key="):
        response = client.get(f"/web/sse/{session_id}{query}")

        _assert_unauthorized(response)
        assert session_id not in web_routes._sse_broadcaster._subscribers, query


def test_sse_header_key_still_works() -> None:
    """curl/CLI callers keep the header path — the parameter is additive."""
    client, _, _ = _build(_auth_on_list())
    session_id = _keyed_session(client)
    _finish_last_turn(session_id)

    stream = client.get(f"/web/sse/{session_id}")

    assert stream.status_code == 200, stream.text
    assert "event: deliberation_done" in stream.text


def test_sse_query_param_works_in_env_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """``mode: env`` resolves the same parameter through the same comparison."""
    monkeypatch.setenv("CHIMERA_API_KEY", ENV_KEY)
    client, _, _ = _build(_auth_on_env())
    session_id = _keyed_session(client, ENV_KEY)
    _finish_last_turn(session_id)
    del client.headers["X-API-Key"]

    assert client.get(f"/web/sse/{session_id}?api_key={ENV_KEY}").status_code == 200
    _assert_unauthorized(client.get(f"/web/sse/{session_id}?api_key={WEB_KEY}"))


# ---------------------------------------------------------------------------
# A4 — auth disabled: byte-for-byte the old behaviour
# ---------------------------------------------------------------------------


def test_auth_disabled_shell_data_and_sse_are_keyless() -> None:
    client, _, gateway = _build(_auth_off())

    assert client.get("/web/").status_code == 200
    assert client.get("/web/vendor/mermaid.min.js").status_code == 200

    create = client.post("/web/sessions")
    assert create.status_code == 200, create.text
    session_id = create.json()["session_id"]
    assert client.get(f"/web/sessions/{session_id}").status_code == 200
    assert gateway.calls == []

    _finish_last_turn(session_id)
    stream = client.get(f"/web/sse/{session_id}")
    assert stream.status_code == 200
    assert "event: deliberation_done" in stream.text


def test_auth_disabled_sse_ignores_a_stray_api_key_param() -> None:
    """No key is required — a leftover parameter neither helps nor breaks."""
    client, _, _ = _build(_auth_off())
    session_id = client.post("/web/sessions").json()["session_id"]
    _finish_last_turn(session_id)

    stream = client.get(f"/web/sse/{session_id}?api_key=anything")

    assert stream.status_code == 200, stream.text


# ---------------------------------------------------------------------------
# A3 — the SPA half: key entry, header on every fetch, param on the SSE dial
# ---------------------------------------------------------------------------


def test_spa_ships_a_key_entry_surface() -> None:
    """The box (not a bare alert) plus its storage slot and prompt entry point."""
    assert 'id="auth-overlay"' in SPA_SOURCE
    assert 'id="auth-box"' in SPA_SOURCE
    assert 'id="auth-input"' in SPA_SOURCE
    assert 'id="auth-save"' in SPA_SOURCE
    assert 'id="api-key-btn"' in SPA_SOURCE
    assert "function promptForApiKey(" in SPA_SOURCE
    # The key is remembered per browser, so a reload does not re-prompt.
    assert "localStorage.setItem(API_KEY_STORAGE" in SPA_SOURCE
    assert "localStorage.getItem(API_KEY_STORAGE" in SPA_SOURCE


def test_spa_sends_the_header_shape_the_server_reads() -> None:
    """``Authorization: Bearer <key>`` — the shape ``_extract_api_key`` parses.

    tests/test_web_auth.py pins the server side
    (``test_web_session_create_accepts_bearer_token``); this pins the client
    half of the same contract.
    """
    body = _js_function("function authHeaders(")

    assert re.search(r"headers\['Authorization'\]\s*=\s*`Bearer \$\{apiKey\}`", body), (
        "the SPA must send Authorization: Bearer <key> on API requests"
    )
    # No key stored (auth disabled) -> no header at all.
    assert re.search(r"if \(apiKey\)", body)


def test_every_api_fetch_carries_the_stored_key() -> None:
    """No raw ``fetch()`` call site may escape the key-aware wrapper.

    One missed call site is the whole defect: that request answers 401 while
    the rest of the UI keeps working.
    """
    wrapper = _js_function("async function apiFetch(")

    assert "await fetch(" in wrapper, "the wrapper must perform the request"
    assert "authHeaders(" in wrapper, "the wrapper must attach the key"
    assert "401" in wrapper
    assert "promptForApiKey(" in wrapper

    outside = SPA_SOURCE.replace(wrapper, "")
    assert "await fetch(" not in outside, "a raw fetch() bypasses the key"
    assert outside.count("await apiFetch(") >= 4, (
        "session create / restore / chat / history must all go through apiFetch"
    )


def test_spa_prompts_for_a_key_on_401_and_retries_with_it() -> None:
    """The 401 is what surfaces the box — and the retry carries the new key."""
    body = _js_function("async function apiFetch(")

    assert re.search(r"r\.status\s*===\s*401", body)
    retry = body.split("401")[1]
    assert "promptForApiKey(" in retry, "the 401 must be what asks for the key"
    assert "await fetch(" in retry, "the request must be retried with the entered key"


def test_spa_appends_the_api_key_to_the_event_source_url() -> None:
    """EventSource cannot set headers — the SSE dial carries ?api_key=.

    The parameter name is taken from the server module so the two halves
    cannot drift: a rename on either side fails here.
    """
    body = _js_function("function connectSSE(")

    assert "new EventSource(" in body
    assert f"{dependencies.SSE_API_KEY_PARAM}=" in body, (
        "the SSE dial must carry the api_key parameter the server reads"
    )
    assert re.search(r"apiKey\s*\?", body), (
        "the parameter must be conditional on a stored key — an unkeyed dial "
        "keeps the exact URL it had before"
    )


def test_spa_encodes_the_key_in_the_dial() -> None:
    """A key copied with punctuation must not corrupt the query string."""
    body = _js_function("function connectSSE(")

    assert "encodeURIComponent(apiKey)" in body


def test_the_sse_query_separator_follows_the_live_flag() -> None:
    """``?live=1`` already opens the query — the key must join with ``&``.

    Without this the keyed live dial would be ``?live=1api_key=…``, which the
    server reads as a single bogus ``live`` value: the seam would look wired and
    every keyed live stream would silently lose the key.
    """
    body = _js_function("function connectSSE(")

    assert re.search(r"live \?\s*'\?live=1'\s*:\s*''", body), (
        "the live flag must stay the first query component"
    )
    assert re.search(r"\?\s*'&'\s*:\s*'\?'", body), (
        "the api_key parameter must be joined with & when the URL already has a query"
    )
