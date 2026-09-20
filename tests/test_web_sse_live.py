"""DF-CHIMERA-V2-29 — live-mode SSE: a turn's stream opens and carries its events.

The defect, measured on the deployed :8765: the SPA's ``EventSource`` never left
``CONNECTING`` during a real deliberation — ``readyState`` stuck at 0, an
open→error cycle every ~3 s, and ZERO ``stage_started`` / ``stage_completed``
events in the UI for a whole run (the DAG panel stayed a placeholder until the
chat POST returned and the fetch fallback painted the final graph).  The server
half was real (``curl -N`` sees every frame, mid-run, before the POST returns)
and the 393322b listeners were wired — the bug was the stream LIFECYCLE, in two
halves:

* **server** — ``sse_stream`` answers any session with recorded turns by
  replaying the stored events and then closing (DF-CHIMERA-V2-19).  A browser
  cannot tell that deliberate close from a dropped connection, so it re-dials →
  replay → close → forever.  Such a stream can never carry the turn that is
  about to run, which is exactly the turn the user is waiting on.
* **client** — ``sendMessage()`` cleared the reconnect guards but never re-dialed
  the stream, so at send time the only ``EventSource`` was the page-load one,
  stuck in that cycle.

The fix is a LIVE mode: ``?live=1`` skips the replay and leaves the stream open
for the next turn — the chat handler closes every subscriber of the session
right after ``deliberation_done``, which ends it cleanly — and ``sendMessage()``
re-dials with that flag right when the turn starts.  The default (no flag):
replay, terminal marker, close, unchanged for page loads and other consumers.

Hermetic: a hand-driven ASGI call for the structural half, one real uvicorn
socket for the end-to-end half (the same split ``tests/test_stage_observer.py``
uses), ``FakeGateway`` throughout — no network, no provider keys.
"""

from __future__ import annotations

import asyncio
import json
import re
import socket
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
from fastapi.testclient import TestClient  # noqa: E402

import chimera.web.routes as web_routes  # noqa: E402
from chimera.api.server import create_app  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402
from chimera.web.session import SessionManager, Turn  # noqa: E402
from chimera.web.sse import TERMINAL_RETRY_MS, SSEBroadcaster, SSEEvent  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
SPA_PATH = REPO_ROOT / "src" / "chimera" / "web" / "static" / "index.html"
SPA_SOURCE = SPA_PATH.read_text(encoding="utf-8")

#: The exact query the shipped SPA appends when it dials for a turn in flight.
#: Derived from the SPA itself so the two halves cannot drift apart: a rename on
#: either side (the flag name the server declares, the string the client sends)
#: makes the ASGI test below fail instead of silently leaving live mode OFF.
_LIVE_DIAL = re.search(r"live \? '(\?[^']*)'", SPA_SOURCE)
assert _LIVE_DIAL, "the SPA no longer builds a live-mode dial URL"
LIVE_QUERY = _LIVE_DIAL.group(1)              # e.g. "?live=1"
LIVE_QUERY_STRING = LIVE_QUERY.lstrip("?")    # e.g. "live=1"

#: The replay a finished turn leaves behind — the frame that must NOT appear on
#: a live-mode stream (its prompt is deliberately distinguishable from the live
#: turn's, so "no replay" is an assertion about a payload, not about timing).
REPLAY_PROMPT = "replayed question"
LIVE_PROMPT = "live question"
STORED_EVENTS: list[tuple[str, dict]] = [
    ("deliberation_started", {"prompt": REPLAY_PROMPT}),
    ("dag_designed", {"mermaid": "flowchart TB\n  a-->b", "stage_count": 2}),
    ("deliberation_done", {"answer": "previous answer", "turn_number": 1}),
]


def _resp(text: str, model: str, ti: int = 5, to: int = 7) -> GatewayResponse:
    return GatewayResponse(text=text, model=model, tokens_input=ti, tokens_output=to)


async def _delayed(response: GatewayResponse, delay: float) -> GatewayResponse:
    await asyncio.sleep(delay)
    return response


def _slow_stage_responder(payload: str, delay: float):  # type: ignore[no-untyped-def]
    """FakeGateway responder whose stage calls sleep *delay* (dispatcher: none)."""

    def _responder(model: str, messages: list[dict[str, str]], response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:  # dispatcher pass — no delay
            return _resp(payload, model, 100, 200)
        joined = " ".join(str(m) for m in messages)
        if "Upstream outputs" in joined:
            return _delayed(_resp("FINAL ANSWER", model, 60, 90), delay)
        return _delayed(_resp(f"worker {model}", model, 20, 40), delay)

    return _responder


def _engine_with_slow_stages(config: Any, delay: float) -> Engine:
    payload = dispatch_json(
        workers=[("worker_1", "deepseek/deepseek-chat"),
                 ("worker_2", "openrouter/google/gemini-2.5-flash")],
    )
    return Engine(config, FakeGateway(_slow_stage_responder(payload, delay)))


def _client(config: Any) -> TestClient:  # type: ignore[no-untyped-def]
    return TestClient(create_app(config=config, engine=_engine_with_slow_stages(config, 0.05)))


@pytest.fixture(autouse=True)
def _reset_web_singletons():  # type: ignore[no-untyped-def]
    """Isolate module-level web state per test (same fixture as the siblings)."""
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()
    yield
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()


def _aged_session(client: TestClient) -> str:
    """A session with one finished turn — i.e. one the replay branch answers."""
    session_id = client.post("/web/sessions").json()["session_id"]
    session = web_routes._session_manager.get(session_id)
    assert session is not None
    session.add_turn(
        Turn(
            user_prompt=REPLAY_PROMPT,
            answer="previous answer",
            formation="simple",
            dispatch_model="zai-coding-plan/glm-5.2",
            worker_models=["deepseek/deepseek-chat"],
            aggregator_model="zai-coding-plan/glm-5.2",
            total_tokens=42,
            total_cost=0.012,
            timestamp=time.time() - 3600.0,
        )
    )
    session.last_sse_events = list(STORED_EVENTS)
    return session_id


def _event_names(body: str) -> list[str]:
    return re.findall(r"^event: (.+)$", body, flags=re.MULTILINE)


# ═══════════════════════════════════════════════════════════════════════════
#  ASGI driver: read a live SSE response incrementally, on a teardown WE own
# ═══════════════════════════════════════════════════════════════════════════


class _LiveStream:
    """A ``GET /web/sse/…`` driven as an ASGI call, frame by frame.

    ``receive`` parks until the test asks for a disconnect, so the request
    returns when the TEST says so — no idle timeout is waited out, and the
    response is observed while it is still open. That is the ASGI-level
    equivalent of a browser holding (and later closing) an ``EventSource``.
    """

    def __init__(self, app: Any, session_id: str, query: str = "") -> None:  # type: ignore[no-untyped-def]
        self.chunks: list[str] = []
        self.status: int | None = None
        self.headers: dict[str, str] = {}
        self._disconnect = asyncio.Event()
        self._opened = asyncio.Event()
        path = f"/web/sse/{session_id}"

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "root_path": "",
            "headers": [(b"host", b"chimera.test")],
            "client": ("testclient", 50000),
            "server": ("chimera.test", 80),
        }

        async def receive() -> dict[str, Any]:
            await self._disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                self.status = message["status"]
                self.headers = {
                    k.decode(): v.decode() for k, v in message.get("headers", ())
                }
                self._opened.set()
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body:
                    self.chunks.append(body.decode())

        self.task = asyncio.create_task(app(scope, receive, send))

    async def opened(self) -> _LiveStream:
        await asyncio.wait_for(self._opened.wait(), timeout=5.0)
        return self

    @property
    def text(self) -> str:
        return "".join(self.chunks)

    @property
    def names(self) -> list[str]:
        return _event_names(self.text)

    async def close(self) -> None:
        """Client goes away; the app tears the stream down and the call returns."""
        self._disconnect.set()
        await asyncio.wait_for(self.task, timeout=10.0)


# ═══════════════════════════════════════════════════════════════════════════
#  1. Live mode: no replay, stays open, DELIVERS events emitted after connect
# ═══════════════════════════════════════════════════════════════════════════


async def test_live_mode_on_a_session_with_history_does_not_replay_or_close(config) -> None:  # type: ignore[no-untyped-def]
    """The whole point of the row, and the stream the SPA now dials.

    A session with an aged turn is exactly what the replay branch answers — so
    pre-fix this request returned the stored frames and closed the stream
    immediately, which is the cycle the SPA never escaped. In live mode the
    response must open, stay open with ZERO stored frames, and carry the events
    broadcast after it connected.
    """
    app = create_app(config=config, engine=_engine_with_slow_stages(config, 0.05))
    session_id = _aged_session(TestClient(app))

    stream = await _LiveStream(app, session_id, LIVE_QUERY_STRING).opened()

    assert stream.status == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    # Nothing replayed: the stored turn's frames are NOT on a live stream.
    assert stream.text == "", (
        "a live-mode stream replayed the previous turn — that is the frame set "
        f"the SPA's EventSource loops on: {stream.names}"
    )
    assert "replay_done" not in stream.names

    # The stream is a LIVE pipe: events emitted AFTER connect reach it.
    web_routes._sse_broadcaster.broadcast(
        session_id,
        SSEEvent(event="stage_started", data={"stage": "worker_1", "kind": "worker",
                                              "model": "deepseek/deepseek-chat"}),
    )
    web_routes._sse_broadcaster.broadcast(
        session_id,
        SSEEvent(event="stage_completed", data={"stage": "worker_1", "kind": "worker",
                                                "model": "deepseek/deepseek-chat",
                                                "tokens": 30, "latency_ms": 12.0,
                                                "cost": 0.0001}),
    )
    # Poll rather than sleep a fixed amount: the two sends are two awaits, and a
    # loaded box can take several scheduler ticks to drain both queue entries.
    for _ in range(200):
        if len(stream.names) >= 2:
            break
        await asyncio.sleep(0.01)

    assert stream.names == ["stage_started", "stage_completed"], stream.names
    assert '"stage": "worker_1"' in stream.text

    await stream.close()
    assert session_id not in web_routes._sse_broadcaster._subscribers, (
        "the live subscriber outlived its stream"
    )


async def test_live_mode_stream_ends_when_the_turn_completes(config) -> None:  # type: ignore[no-untyped-def]
    """Live mode is bounded by the turn, not by the idle timeout.

    The chat handler closes every subscriber of the session right after
    ``deliberation_done`` (routes.py, ``unsubscribe_all``) — so a live client of
    a finished turn sees the final event and then a clean end of stream, instead
    of a 30 s wait cancelled by a clock.
    """
    app = create_app(config=config, engine=_engine_with_slow_stages(config, 0.05))
    session_id = _aged_session(TestClient(app))

    stream = await _LiveStream(app, session_id, LIVE_QUERY_STRING).opened()
    assert stream.names == []

    web_routes._sse_broadcaster.broadcast(
        session_id, SSEEvent(event="deliberation_done", data={"answer": "x", "turn_number": 2})
    )
    web_routes._sse_broadcaster.unsubscribe_all(session_id)

    await asyncio.wait_for(stream.task, timeout=5.0)  # NOT the idle timeout
    assert stream.names == ["deliberation_done"]
    assert stream.text.rstrip().endswith('data: {"answer": "x", "turn_number": 2}')


async def test_turn_less_session_is_unaffected_by_the_live_flag(config) -> None:  # type: ignore[no-untyped-def]
    """A first-ever prompt: nothing to replay, so live mode changes nothing."""
    app = create_app(config=config, engine=_engine_with_slow_stages(config, 0.05))
    session_id = TestClient(app).post("/web/sessions").json()["session_id"]

    stream = await _LiveStream(app, session_id, LIVE_QUERY_STRING).opened()

    assert stream.status == 200
    assert stream.text == ""
    assert session_id in web_routes._sse_broadcaster._subscribers, (
        "the stream of a session with no turns must stay open for the run to come"
    )
    await stream.close()


# ═══════════════════════════════════════════════════════════════════════════
#  2. DF-CHIMERA-V2-19 must not regress: the default still replays, then closes
# ═══════════════════════════════════════════════════════════════════════════


def test_default_mode_still_replays_then_closes_with_the_marker(config) -> None:  # type: ignore[no-untyped-def]
    """Page loads keep the replay contract — live mode is strictly opt-in."""
    client = _client(config)
    session_id = _aged_session(client)

    started = time.monotonic()
    response = client.get(f"/web/sse/{session_id}")
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert _event_names(response.text) == [
        "deliberation_started",
        "dag_designed",
        "deliberation_done",
        "replay_done",
    ]
    assert f'data: {{"prompt": "{REPLAY_PROMPT}"}}' in response.text
    assert elapsed < 1.0, f"the default replay waited on the idle timeout ({elapsed:.3f}s)"
    assert session_id not in web_routes._sse_broadcaster._subscribers


@pytest.mark.parametrize(
    "query",
    ["?live=0", "?live=false", "?live=", "?", "?live=no", "?live=off", "?live=maybe"],
)
def test_a_non_live_flag_value_replays_like_the_default(config, query: str) -> None:  # type: ignore[no-untyped-def]
    """Only a truthy flag is live: ``live=0`` must not silence the replay.

    The boundary matters because the flag is a contract between two files — if
    "false" were read as "present", a caller that explicitly asked for the
    page-load behavior would silently get a stream that waits for a turn. The
    unparseable value (``maybe``) also must not 422: an ``EventSource`` reads a
    non-200 as a retryable drop, which is the failure class DF-19 fixed for the
    unknown-session case.
    """
    client = _client(config)
    session_id = _aged_session(client)

    response = client.get(f"/web/sse/{session_id}{query}")

    assert response.status_code == 200, f"query {query!r} answered {response.status_code}"
    assert _event_names(response.text) == [
        "deliberation_started",
        "dag_designed",
        "deliberation_done",
        "replay_done",
    ], f"query {query!r} did not replay"


@pytest.mark.parametrize("query", ["?live=1", "?live=true", "?live=TRUE", "?live=yes", "?live=on"])
async def test_a_truthy_live_flag_skips_the_replay(config, query: str) -> None:  # type: ignore[no-untyped-def]
    """Every truthy spelling the route documents actually engages live mode."""
    app = create_app(config=config, engine=_engine_with_slow_stages(config, 0.05))
    session_id = _aged_session(TestClient(app))

    stream = await _LiveStream(app, session_id, query.lstrip("?")).opened()

    assert stream.status == 200
    assert stream.text == "", (
        f"query {query!r} was answered as a replay: {stream.names}"
    )
    assert session_id in web_routes._sse_broadcaster._subscribers, (
        f"query {query!r} did not leave a live subscriber open"
    )
    await stream.close()


def test_live_dial_is_never_answered_with_a_non_200(config) -> None:  # type: ignore[no-untyped-def]
    """A live dial must never earn a status an EventSource reads as a drop.

    Same failure class DF-19 fixed for the unknown-session case: the browser
    surfaces ANY non-200 as a retryable ``error``, indistinguishable from a
    dropped connection. So no query spelling — a plain unparseable one, an
    unknown session with the flag on, or the flag repeated — may answer 422/404.
    """
    client = _client(config)
    session_id = _aged_session(client)

    # Stand in for the idle timeout so the open live streams below close at
    # once; the assertion is about the RESPONSE, and waiting 4 × 30 s for a
    # stream that is meant to stay open would only slow the suite. The
    # generator's timeout is neutralised while both the status and the headers
    # are still produced by the real handler.
    async def _idle_out(awaitable, *, timeout):  # type: ignore[no-untyped-def]
        del timeout
        awaitable.close()
        raise TimeoutError

    import chimera.web.sse as sse_mod

    original = sse_mod.asyncio.wait_for
    sse_mod.asyncio.wait_for = _idle_out  # type: ignore[assignment]
    try:
        for query in ("?live=1", "?live=maybe", "?live=1&live=0", "?live=NULL"):
            response = client.get(f"/web/sse/{session_id}{query}")
            assert response.status_code == 200, f"{query} answered {response.status_code}"
            assert response.headers["content-type"].startswith("text/event-stream")

        # A dead session id with the flag on still gets the terminal stream.
        dead = client.get("/web/sse/gone-with-live?live=1")
        assert dead.status_code == 200
        assert dead.headers.get("x-chimera-session-status") == "unknown"
    finally:
        sse_mod.asyncio.wait_for = original  # type: ignore[assignment]


def test_in_flight_deliberation_still_skips_the_replay_without_the_flag(config) -> None:  # type: ignore[no-untyped-def]
    """The other existing exception (a run executing now) is untouched."""
    client = _client(config)
    session_id = _aged_session(client)
    session = web_routes._session_manager.get(session_id)
    assert session is not None
    session.deliberation_in_flight = True

    async def _never(awaitable, *, timeout):  # type: ignore[no-untyped-def]
        del timeout
        awaitable.close()
        raise TimeoutError

    import chimera.web.sse as sse_mod

    original = sse_mod.asyncio.wait_for
    sse_mod.asyncio.wait_for = _never  # type: ignore[assignment]
    try:
        response = client.get(f"/web/sse/{session_id}")
    finally:
        sse_mod.asyncio.wait_for = original  # type: ignore[assignment]

    assert response.text == "", "an in-flight run was answered with a replay"
    assert "replay_done" not in response.text


# ═══════════════════════════════════════════════════════════════════════════
#  3. The SPA half: sendMessage() re-dials live, and the mode survives a blip
# ═══════════════════════════════════════════════════════════════════════════


def _js_function(declaration: str) -> str:
    """The text of a shipped JS function, from its declaration to its last brace.

    Brace-matched rather than section-sliced so the assertion window is exactly
    the function's own body — a statement that merely sits NEAR it in the file
    cannot satisfy a check (and a sibling's function cannot break one).
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


def test_send_message_redials_the_stream_for_the_new_turn() -> None:
    """THE client half of the bug: sendMessage() never re-dialed the stream.

    Pre-fix the function cleared ``deliberationComplete`` and the retry timer and
    then went straight to the fetch, so the only ``EventSource`` on a session
    with history was the page-load one — the replay/close/redial cycle that can
    never carry this turn's stage events.
    """
    body = _js_function("async function sendMessage()")

    assert re.search(r"connectSSE\(\s*true\s*\)", body), (
        "sendMessage() must (re)connect the stream in live mode for the turn it "
        "is about to start — otherwise the stage listeners run on the stale "
        "replay stream"
    )
    # The re-dial has to happen BEFORE the chat POST: the server's readiness
    # gate and the first events are both on the far side of that request.
    assert body.index("connectSSE(true)") < body.index("await fetch("), (
        "the live stream must be open before the chat request is sent"
    )


def test_connect_sse_dials_the_live_url_when_asked() -> None:
    """Live mode is a request the server understands, not just client state."""
    body = _js_function("function connectSSE(")

    assert re.search(r"function connectSSE\(\s*live\s*=\s*false\s*\)", body), (
        "connectSSE must take a live flag defaulting to false (page loads)"
    )
    assert "?live=1" in body, "the live dial URL is missing"
    assert re.search(r"live \? '\?live=1' : ''", body), (
        "the live query must be appended only when live — the default dial has "
        "to keep the page-load replay contract"
    )


def test_page_load_dials_are_not_live() -> None:
    """createSession/restoreSession keep the replay dial — DF-19 not regressed."""
    for declaration in ("async function createSession()", "async function restoreSession("):
        body = _js_function(declaration)
        assert re.search(r"connectSSE\(\s*\)", body), (
            f"{declaration} must dial without the live flag"
        )
        assert "connectSSE(true)" not in body


def test_deliberation_done_closes_a_live_stream() -> None:
    """The live stream is ended by the client when the turn is done.

    The server closes its side right after ``deliberation_done``; a browser
    retries a closed ``EventSource`` by itself, so without ``close()`` the
    ``?live=1`` URL would be re-dialed all day with no turn to deliver.
    """
    body = _js_function("eventSource.addEventListener('deliberation_done'")

    assert "sseLiveMode" in body, "the live stream must be recognized as live here"
    assert "eventSource.close()" in body, (
        "a finished turn must close the live stream, or the browser re-dials it forever"
    )


def test_error_redial_preserves_the_stream_mode() -> None:
    """A transport blip during a live turn must redial LIVE, not replay."""
    onerror = SPA_SOURCE.split("eventSource.onerror = () => {")[1].split("\n};")[0]

    assert "connectSSE(sseLiveMode)" in onerror, (
        "onerror's reconnect must carry the current mode — redialing the plain "
        "URL mid-turn puts the client back on the replay-then-close cycle"
    )


def test_end_stream_clears_the_live_mode_flag() -> None:
    """A terminal stream resets the mode so the next dial chooses deliberately."""
    body = _js_function("function endStream(")

    assert re.search(r"sseLiveMode\s*=\s*false", body)


def test_the_live_query_the_spa_sends_is_the_one_the_server_parses() -> None:
    """Cross-surface contract: the dial string and the route parameter agree.

    The ASGI driver above dials with ``LIVE_QUERY_STRING``, which is extracted
    from the shipped SPA — so an unknown query parameter (a rename on either
    side) makes "no replay + stays open" fail there rather than silently
    leaving live mode OFF in production. This test names the two sides.
    """
    assert LIVE_QUERY == "?live=1", LIVE_QUERY
    import inspect

    route = web_routes.sse_stream
    params = inspect.signature(route).parameters
    assert "live" in params, (
        "the SSE route no longer declares the live parameter the SPA sends"
    )
    # Off by default: the replay contract is what a page load gets. (``None``
    # and not ``False`` because the flag is truthy-parsed — see the route.)
    assert params["live"].default is None, (
        "live mode must default to off — the replay contract is the default"
    )
    assert web_routes._SSE_LIVE_VALUES, "the truthy value table is missing"
    assert {"1", "true"} <= set(web_routes._SSE_LIVE_VALUES)


# ═══════════════════════════════════════════════════════════════════════════
#  4. End-to-end over a real socket: a live stream carries a real turn's stage
#     events while the chat POST is still in flight
# ═══════════════════════════════════════════════════════════════════════════


def test_live_stream_carries_a_real_turn_mid_post(config) -> None:  # type: ignore[no-untyped-def]
    """The deployed bug, reproduced and fixed end to end.

    A real uvicorn socket, a session with an aged turn (so the replay branch is
    available), a live dial exactly as the SPA builds it, and a real chat POST.
    Pre-fix this stream delivered the stored frames and closed before the turn
    began — the reader thread would see the replay prompt and nothing else. The
    assertions are: no replay frame on the wire, the turn's own
    ``deliberation_started`` first, stage events arriving BEFORE the POST
    returns, and a clean end at ``deliberation_done``.
    """
    import uvicorn

    app = create_app(config=config, engine=_engine_with_slow_stages(config, 0.3))
    uv_config = uvicorn.Config(app, log_level="warning", access_log=False)
    server = uvicorn.Server(uv_config)
    # Bind our own socket (port 0 → kernel-assigned) and hand it to uvicorn, so
    # the test reads the port without depending on uvicorn's private attributes.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.set_inheritable(True)
    host, port = sock.getsockname()[:2]
    base = f"http://{host}:{port}"
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10.0
        while not getattr(server, "started", False):
            assert thread.is_alive(), "uvicorn server died before startup finished"
            assert time.monotonic() < deadline, "uvicorn never finished startup"
            time.sleep(0.02)

        created = urllib.request.urlopen(
            urllib.request.Request(f"{base}/web/sessions", data=b"", method="POST"), timeout=30
        )
        session_id = json.loads(created.read())["session_id"]
        created.close()

        session = web_routes._session_manager.get(session_id)
        assert session is not None
        session.add_turn(
            Turn(
                user_prompt=REPLAY_PROMPT,
                answer="previous answer",
                formation="simple",
                dispatch_model="zai-coding-plan/glm-5.2",
                worker_models=["deepseek/deepseek-chat"],
                aggregator_model="zai-coding-plan/glm-5.2",
                total_tokens=42,
                total_cost=0.012,
                timestamp=time.time() - 3600.0,
            )
        )
        session.last_sse_events = list(STORED_EVENTS)

        frames: list[tuple[float, str]] = []
        body_chunks: list[str] = []

        def read_sse() -> None:
            try:
                with urllib.request.urlopen(
                    f"{base}/web/sse/{session_id}{LIVE_QUERY}", timeout=30
                ) as resp:
                    for raw in resp:
                        line = raw.decode("utf-8")
                        body_chunks.append(line)
                        if line.startswith("event: "):
                            frames.append((time.monotonic(), line[len("event: "):].strip()))
            except Exception:
                pass  # stream closed by the sentinel — expected

        reader = threading.Thread(target=read_sse, daemon=True)
        reader.start()

        # Wait until the live subscriber is ready, exactly like the SPA does, so
        # the chat's 2 s readiness window cannot mask a wiring bug.
        ready = None
        ready_deadline = time.monotonic() + 5.0
        while time.monotonic() < ready_deadline:
            ready = web_routes._sse_broadcaster._ready.get(session_id)
            if ready is not None and ready.is_set():
                break
            time.sleep(0.02)
        assert ready is not None and ready.is_set(), "the live SSE subscriber never became ready"

        chat_req = urllib.request.Request(
            f"{base}/web/sessions/{session_id}/chat",
            data=json.dumps({"prompt": LIVE_PROMPT, "formation": "simple"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        chat_started = time.monotonic()
        with urllib.request.urlopen(chat_req, timeout=60) as resp:
            assert resp.status == 200
            payload = json.loads(resp.read())
        chat_done = time.monotonic()
        assert payload["answer"], payload

        reader.join(timeout=15.0)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if [name for _, name in frames][-1:] == ["deliberation_done"]:
                break
            time.sleep(0.02)

        names = [name for _, name in frames]
        body = "".join(body_chunks)

        # No replay: the stored turn's prompt is not on this stream at all.
        assert REPLAY_PROMPT not in body, (
            "the live stream replayed the previous turn — the EventSource loop "
            "the SPA was stuck in"
        )
        assert names and names[0] == "deliberation_started", names
        assert '"prompt": "live question"' in body, "the new turn's events never arrived"
        assert names[-1] == "deliberation_done", names
        assert "dag_designed" in names, names

        # THE acceptance criterion: stage events reached the stream while the
        # chat POST was still in flight.
        assert names.count("stage_started") >= 3, names
        assert names.count("stage_completed") >= 3, names
        stage_ts = [ts for ts, name in frames if name == "stage_started"]
        assert stage_ts, names
        assert chat_started < min(stage_ts) < chat_done, (
            f"no stage event arrived mid-POST (first at {min(stage_ts) - chat_started:.2f}s "
            f"of a {chat_done - chat_started:.2f}s run)"
        )

        # DF-CHIMERA-V2-29 rework: a browser DISPATCHES events, it does not grep
        # lines. The same bytes this reader saw must yield the same event
        # sequence through a spec parser — pre-rework this assertion failed with
        # zero dispatched frames while `names` above showed every event.
        dispatched = _dispatch_sse(body)
        assert [e["event"] for e in dispatched] == names, (
            f"line-grep saw {names} but a spec parser dispatches "
            f"{[e['event'] for e in dispatched]} — the wire framing is broken"
        )
    finally:
        server.should_exit = True
        thread.join(timeout=10.0)


# ═══════════════════════════════════════════════════════════
#  5. DF-CHIMERA-V2-29 rework — the WIRE FORMAT, judged by a real parser
#
#  The first pass fixed the stream lifecycle; the browser check that exposed the
#  residual defect drove an instrumented EventSource: readyState went 0 → 1 (the
#  stream held) and the POST returned 200 — yet the EventSource received ZERO
#  events. A raw fetch().body.getReader() loop on the SAME url at the SAME moment
#  received every frame. Root cause (proven on the wire, 2415 captured bytes,
#  b"\n\n" occurrences: 0): ``SSEEvent.format()`` built its "blank line
#  terminator" with ``lines.append(""); return "\n".join(lines)``, which yields
#  ONE trailing newline — an unterminated frame. Per the SSE spec an event is
#  dispatched only when a blank line ends it, so a spec-compliant EventSource
#  buffers forever. Every prior test grepped ``event:``/``data:`` lines, so the
#  bug shipped through the suite: line-greps dispatch nothing.
# ═══════════════════════════════════════════════════════════


def _dispatch_sse(raw: str) -> list[dict]:
    """The WHATWG dispatch rule, literally: buffer fields, dispatch on a blank line.

    (https://html.spec.whatwg.org/multipage/server-sent-events.html#event-stream-interpretation)
    Field lines feed the dispatch buffer; the buffer is fired and EMPTIED only
    on an empty line; a buffer still pending when the stream ends dispatches
    nothing. Deliberately independent of ``_parse_sse_events`` (the integration
    helper splits on ``event:`` occurrences and would accept broken framing).
    """
    events: list[dict] = []
    buffer: dict[str, list[str]] = {}

    def _dispatch() -> None:
        if not buffer:
            return
        data = "\n".join(buffer.get("data", []))
        if data == "" and "data" not in buffer:
            buffer.clear()  # spec: no data field → fire no event
            return
        events.append(
            {
                "event": "\n".join(buffer.get("event", [])),
                "data": data,
                "id": buffer.get("id"),
            }
        )
        buffer.clear()

    for line in raw.split("\n"):
        if line.endswith("\r"):
            line = line[:-1]
        if line == "":
            _dispatch()  # the blank line dispatches the buffered event
        elif line.startswith("data:"):
            buffer.setdefault("data", []).append(line[5:].lstrip(" "))
        elif line.startswith("event:"):
            buffer.setdefault("event", []).append(line[6:].lstrip(" "))
        elif line.startswith("id:"):
            buffer.setdefault("id", []).append(line[3:].lstrip(" "))
        # retry:, comments, and unknown fields: ignored by dispatch
    return events


async def test_every_frame_carries_the_blank_line_the_spec_dispatches_on() -> None:
    """The unit half: EVERY SSEEvent.format() output is a terminated frame.

    Pre-rework: repr == ``'event: stage_started\\ndata: {"stage": "worker_1"}\\n'``
    — one trailing newline, ``endswith("\\n\\n")`` False. The whole 9-frame live
    wire contained ZERO ``b"\\n\\n"``: all frames glued into one unterminated
    buffer that a real EventSource never dispatches.
    """
    plain = SSEEvent(event="stage_started", data={"stage": "worker_1"}).format()
    assert plain.endswith("\n\n")
    assert plain == 'event: stage_started\ndata: {"stage": "worker_1"}\n\n'

    # Every field permutation terminates: id/event/data/retry in any combination.
    full = SSEEvent(
        id="event-7",
        event="stage_completed",
        data={"stage": "worker_1", "tokens": 17},
        retry=5000,
    ).format()
    assert full.endswith("\n\n")

    empty = SSEEvent(event="", data={"ok": True}).format()
    assert empty.endswith("\n\n")

    terminal = SSEEvent(event="replay_done", data={}, retry=TERMINAL_RETRY_MS).format()
    assert terminal.endswith("\n\n")

    # Consecutive frames are SEPARABLE — the delimiter a browser splits on.
    wire = "".join(SSEEvent(event=f"e{i}", data={"n": i}).format() for i in range(9))
    assert wire.count("\n\n") == 9

    # And the frames are dispatch-shaped: one buffered event per terminator.
    dispatched = _dispatch_sse(wire)
    assert [e["event"] for e in dispatched] == [f"e{i}" for i in range(9)]
    assert json.loads(dispatched[3]["data"]) == {"n": 3}


async def test_live_stream_dispatches_every_event_a_turn_broadcasts(config) -> None:  # type: ignore[no-untyped-def]
    """Criterion 5, hermetic: open the live stream, fire the run's broadcast
    sequence exactly as the chat handler does, and count what a REAL SSE parser
    DISPATCHES — not what the bytes contain.

    Pre-rework this count is 0: every frame sat unterminated in one buffer the
    spec never dispatches. The browser saw nothing while line-greps saw all 9
    events — that gap is the bug.
    """
    app = create_app(config=config, engine=_engine_with_slow_stages(config, 0.05))
    session_id = _aged_session(TestClient(app))

    stream = await _LiveStream(app, session_id, LIVE_QUERY_STRING).opened()
    assert stream.text == ""  # live mode: no replay frames

    # The exact sequence a simple-formation turn broadcasts (routes.py):
    # deliberation_started → 3x (stage_started, stage_completed) → dag_designed
    # → deliberation_done.
    web_routes._sse_broadcaster.broadcast(
        session_id, SSEEvent(event="deliberation_started", data={"prompt": LIVE_PROMPT})
    )
    for i in range(1, 4):
        web_routes._sse_broadcaster.broadcast(
            session_id,
            SSEEvent(
                event="stage_started",
                data={"stage": f"worker_{i}", "kind": "worker", "model": "m"},
            ),
        )
        web_routes._sse_broadcaster.broadcast(
            session_id,
            SSEEvent(
                event="stage_completed",
                data={"stage": f"worker_{i}", "kind": "worker", "model": "m",
                      "tokens": 30, "latency_ms": 12.0, "cost": 0.0001},
            ),
        )
    web_routes._sse_broadcaster.broadcast(
        session_id,
        SSEEvent(event="dag_designed",
                 data={"mermaid": "flowchart TB\n  a-->b", "stage_count": 3}),
    )
    web_routes._sse_broadcaster.broadcast(
        session_id,
        SSEEvent(event="deliberation_done",
                 data={"answer": "x", "turn_number": 2}),
    )
    web_routes._sse_broadcaster.unsubscribe_all(session_id)
    await asyncio.wait_for(stream.task, timeout=5.0)  # NOT the idle timeout

    # The old assertion — line-grep — would pass here EVEN WITH broken framing.
    # The assertion that matters: what a spec-compliant parser DISPATCHES.
    dispatched = _dispatch_sse(stream.text)
    assert len(dispatched) == 9, (
        f"9 events were broadcast, a real SSE parser dispatched {len(dispatched)}: "
        f"{[e['event'] for e in dispatched]} — unterminated frames on the wire"
    )
    assert [e["event"] for e in dispatched] == [
        "deliberation_started",
        "stage_started", "stage_completed",
        "stage_started", "stage_completed",
        "stage_started", "stage_completed",
        "dag_designed",
        "deliberation_done",
    ]
    # Data survives the framing: parsed payloads, not glued fragments.
    assert json.loads(dispatched[0]["data"])["prompt"] == LIVE_PROMPT
    assert json.loads(dispatched[7]["data"])["stage_count"] == 3
    assert json.loads(dispatched[8]["data"])["turn_number"] == 2


async def test_unknown_session_stream_dispatches_both_frames(config) -> None:  # type: ignore[no-untyped-def]
    """The retry/terminal path frames are terminated too (criterion 3).

    ``_unknown_session_stream`` hand-yields two ``format()`` strings — with a
    broken ``format()`` a browser dispatches neither the ``error`` frame nor
    the terminal marker that tells it to stop retrying.
    """
    client = _client(config)
    response = client.get("/web/sse/never-existed?live=1")
    assert response.status_code == 200

    dispatched = _dispatch_sse(response.text)
    assert [e["event"] for e in dispatched] == ["error", "replay_done"], dispatched
    error_data = json.loads(dispatched[0]["data"])
    assert error_data["reason"] == "unknown_session"
    # The terminal marker still advertises its retry to legacy clients.
    full_frame = response.text
    assert f"retry: {TERMINAL_RETRY_MS}\n\n" in full_frame


async def test_httpx_sse_client_stack_dispatches_the_live_stream(config) -> None:  # type: ignore[no-untyped-def]
    """Same gate through the real client stack, when httpx-sse is importable.

    A third-party spec parser — the one httpx users run in production — reads
    the live stream while the turn's frames are broadcast. Skipped honestly
    where the extra is not a declared dependency: the hand-rolled dispatch
    parser above is the authoritative gate, so the suite never depends on an
    undeclared package.
    """
    httpx_sse = pytest.importorskip("httpx_sse")
    import httpx

    app = create_app(config=config, engine=_engine_with_slow_stages(config, 0.05))
    session_id = _aged_session(TestClient(app))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=10.0
    ) as client:
        async def fire_broadcasts() -> None:
            # Give the request a beat to reach the handler and subscribe.
            for _ in range(200):
                if web_routes._sse_broadcaster._ready.get(session_id) is not None:
                    break
                await asyncio.sleep(0.01)
            for i in range(1, 4):
                web_routes._sse_broadcaster.broadcast(
                    session_id,
                    SSEEvent(event="stage_started",
                             data={"stage": f"worker_{i}", "kind": "worker"}),
                )
                web_routes._sse_broadcaster.broadcast(
                    session_id,
                    SSEEvent(event="stage_completed",
                             data={"stage": f"worker_{i}", "kind": "worker", "tokens": i}),
                )
            web_routes._sse_broadcaster.unsubscribe_all(session_id)

        asyncio.get_running_loop().create_task(fire_broadcasts())
        received: list[str] = []
        async with httpx_sse.aconnect_sse(
            client, "GET", f"/web/sse/{session_id}{LIVE_QUERY}"
        ) as event_source:
            async for sse in event_source.aiter_sse():
                received.append(sse.event)
                if sse.event == "deliberation_done":
                    break

    assert len(received) == 6, (
        f"6 events were broadcast, the httpx-sse parser dispatched {len(received)}: "
        f"{received} — unterminated frames on the wire"
    )
    assert received == ["stage_started", "stage_completed"] * 3, received
