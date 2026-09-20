"""DF-CHIMERA-V2-19 — aged sessions replay their SSE events and stop reconnecting.

The defect: ``sse_stream()`` replayed ``session.last_sse_events`` only when the
newest turn was **younger than 30 s**; every older session got an instant,
zero-byte close. A browser cannot tell that from a dropped connection, so the
SPA's ``onerror`` retried every 3 s forever behind a permanent
"⏳ SSE reconnecting…" banner (measured live: one ``GET /web/sse/<sid> 200``
every 3.0 s indefinitely, 84 of 138 such requests for a single session).

The fix has two halves, and these tests pin each:

* **server** — any session with turns replays its stored events and closes with a
  ``replay_done`` terminal marker; an unknown session is answered as a terminal
  *stream* (200) instead of a JSON 404 the browser can only read as a retryable
  drop; a session with no turns still keeps its stream open; a session with a
  deliberation in flight is never short-circuited by a replay.
* **client** — the marker lands in ``static/index.html`` and ends the stream
  explicitly (``EventSource.close()``), because the browser retries a dropped
  stream by itself and ``retry:`` alone cannot stop it.

Hermetic: FastAPI ``TestClient`` over a ``FakeGateway`` engine, no network, no
provider keys, no live server.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import chimera.web.routes as web_routes
import chimera.web.sse as sse_module
from chimera.api.server import create_app
from chimera.engine import Engine
from chimera.web.session import Session, SessionManager, Turn
from chimera.web.sse import SSEBroadcaster, SSEEvent

REPO_ROOT = Path(__file__).resolve().parents[1]
SPA_PATH = REPO_ROOT / "src" / "chimera" / "web" / "static" / "index.html"

from tests.conftest import FakeGateway, dispatch_json  # noqa: E402

#: How far into the past the aged session's last turn is stamped. Comfortably
#: beyond the 30 s gate that used to suppress the replay.
AGED_SECONDS = 3600.0

#: The stored replay a finished turn leaves behind (routes.py, chat handler).
STORED_EVENTS: list[tuple[str, dict]] = [
    ("deliberation_started", {"prompt": "aged question"}),
    ("dag_designed", {"mermaid": "flowchart TB\n  a-->b", "stage_count": 2}),
    ("deliberation_done", {"answer": "42", "turn_number": 1}),
]


def _resp(text: str, model: str, ti: int = 5, to: int = 7):  # type: ignore[no-untyped-def]
    from chimera.gateway import GatewayResponse

    return GatewayResponse(text=text, model=model, tokens_input=ti, tokens_output=to)


def _client(config):  # type: ignore[no-untyped-def]
    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:
            return _resp(dispatch_json(), model, 100, 200)
        joined = " ".join(str(m) for m in messages)
        if "Upstream outputs" in joined:
            return _resp("FINAL ANSWER", model, 60, 90)
        return _resp(f"worker {model}", model, 20, 40)

    engine = Engine(config, FakeGateway(responder))
    return TestClient(create_app(config=config, engine=engine))


@pytest.fixture(autouse=True)
def _reset_web_singletons():  # type: ignore[no-untyped-def]
    """Isolate module-level web state per test (same pattern as test_web.py)."""
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()
    yield
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()


def _turn(prompt: str, answer: str, *, age_seconds: float) -> Turn:
    return Turn(
        user_prompt=prompt,
        answer=answer,
        formation="simple",
        dispatch_model="zai-coding-plan/glm-5.2",
        worker_models=["deepseek/deepseek-chat"],
        aggregator_model="zai-coding-plan/glm-5.2",
        total_tokens=42,
        total_cost=0.012,
        timestamp=time.time() - age_seconds,
    )


def _aged_session(client, *, age_seconds: float = AGED_SECONDS) -> str:
    """Create a session whose only turn is far older than the 30 s gate."""
    session_id = client.post("/web/sessions").json()["session_id"]
    session = web_routes._session_manager.get(session_id)
    assert session is not None
    session.add_turn(_turn("aged question", "42", age_seconds=age_seconds))
    session.last_sse_events = list(STORED_EVENTS)
    return session_id


def _event_names(body: str) -> list[str]:
    return re.findall(r"^event: (.+)$", body, flags=re.MULTILINE)


# ═══════════════════════════════════════════════════════════════════════════
#  1. An aged session replays its stored events, marks the end, and closes
# ═══════════════════════════════════════════════════════════════════════════


def test_aged_session_replays_stored_events_and_closes_with_marker(config) -> None:  # type: ignore[no-untyped-def]
    """The whole point of the row: an hour-old turn still replays, then closes.

    Pre-fix this response was ``""`` (zero bytes) in ~1 ms — the exact shape that
    drove the SPA's 3-second reconnect loop.
    """
    client = _client(config)
    session_id = _aged_session(client)

    started = time.monotonic()
    response = client.get(f"/web/sse/{session_id}")
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    names = _event_names(response.text)
    assert names == [
        "deliberation_started",
        "dag_designed",
        "deliberation_done",
        sse_module.TERMINAL_EVENT,
    ], f"aged replay must end with the terminal marker, got {names}"

    # The stored payloads are on the wire, not just their names.
    assert 'data: {"prompt": "aged question"}' in response.text
    assert "flowchart TB" in response.text
    assert 'data: {"answer": "42", "turn_number": 1}' in response.text

    # The marker carries the reconnect backoff so a client that does not know
    # the event name still inherits a 60 s (not 3 s) retry from the SSE spec.
    assert f"retry: {sse_module.TERMINAL_RETRY_MS}" in response.text

    # Clean teardown, and well under a second — no idle timeout was waited out.
    assert session_id not in web_routes._sse_broadcaster._subscribers
    assert elapsed < 1.0, f"aged replay took {elapsed:.3f}s"


def test_terminal_marker_is_the_last_frame_before_close(config) -> None:  # type: ignore[no-untyped-def]
    """Ordering is the contract: marker strictly after the data, nothing after it."""
    client = _client(config)
    session_id = _aged_session(client)

    body = client.get(f"/web/sse/{session_id}").text

    marker_at = body.index(f"event: {sse_module.TERMINAL_EVENT}")
    done_at = body.index("event: deliberation_done")
    assert done_at < marker_at
    # The stream is not merely closed after the marker — the marker is terminal.
    assert body[marker_at:].strip().splitlines()[0] == f"event: {sse_module.TERMINAL_EVENT}"


# ═══════════════════════════════════════════════════════════════════════════
#  2. Reconnect pressure: the replay is idempotent and the client stops at the
#     marker instead of retrying
# ═══════════════════════════════════════════════════════════════════════════


def test_reconnect_after_replay_gets_the_same_events_idempotently(config) -> None:  # type: ignore[no-untyped-def]
    """A second (client-initiated) connect sees byte-identical frames.

    This is the reconnect a client performs *after* missing the marker: it must
    be served the same replay, and it must end the same way, so the exchange is
    convergent rather than a loop that changes nothing.
    """
    client = _client(config)
    session_id = _aged_session(client)

    first = client.get(f"/web/sse/{session_id}")
    second = client.get(f"/web/sse/{session_id}")

    assert first.text == second.text
    assert _event_names(second.text)[-1] == sse_module.TERMINAL_EVENT
    assert session_id not in web_routes._sse_broadcaster._subscribers


def test_broadcaster_queues_no_marker_on_a_non_deliberate_teardown() -> None:
    """A disconnected/idle client must NOT be handed a terminal marker.

    ``unsubscribe`` is the non-deliberate path (client gone, idle timeout): its
    only frame is the close sentinel. If a marker leaked here, a test that reads
    the queue afterwards would report a "clean terminal close" the client never
    saw — the replay marker must mean exactly one thing.
    """
    broadcaster = SSEBroadcaster()
    sub = broadcaster.subscribe("session")

    broadcaster.unsubscribe("session", sub)

    assert sub.queue.get_nowait() is None
    assert sub.queue.empty()


def test_deliberate_close_queues_marker_then_sentinel() -> None:
    """``close_subscriber`` is marker-then-sentinel, and removes the subscriber."""
    broadcaster = SSEBroadcaster()
    sub = broadcaster.subscribe("session")

    broadcaster.close_subscriber("session", sub)

    marker = sub.queue.get_nowait()
    assert isinstance(marker, SSEEvent)
    assert marker.event == sse_module.TERMINAL_EVENT
    assert marker.retry == sse_module.TERMINAL_RETRY_MS
    assert sub.queue.get_nowait() is None
    assert "session" not in broadcaster._subscribers


def test_close_subscriber_still_closes_when_the_queue_is_full() -> None:
    """The sentinel is unconditional: a full queue must not strand the generator.

    The marker is best-effort (a 256-deep queue can drop it), but a close path
    that skips the sentinel would hang the stream until the idle timeout — the
    degradation would be worse than the bug being fixed.
    """
    broadcaster = SSEBroadcaster()
    sub = broadcaster.subscribe("session")
    filler = SSEEvent(event="filler", data={})
    for _ in range(sub.queue.maxsize):
        sub.queue.put_nowait(filler)

    broadcaster.close_subscriber("session", sub)

    assert sub.queue.qsize() == sub.queue.maxsize  # nothing new fit
    assert "session" not in broadcaster._subscribers
    drained = [sub.queue.get_nowait() for _ in range(sub.queue.maxsize)]
    assert all(item is filler for item in drained)


def test_replay_speaks_only_to_the_requesting_subscriber(config) -> None:  # type: ignore[no-untyped-def]
    """The replay must not be broadcast into other open streams of the session.

    ``broadcast`` would hand a late-joining client's stored turn to every other
    subscriber — and it was also the mechanism that would have closed them all.
    """
    client = _client(config)
    session_id = _aged_session(client)
    other = web_routes._sse_broadcaster.subscribe(session_id)

    response = client.get(f"/web/sse/{session_id}")

    assert _event_names(response.text)[-1] == sse_module.TERMINAL_EVENT
    assert other.queue.empty(), "the replay leaked into another subscriber"


def test_spa_js_treats_the_marker_as_terminal(config) -> None:  # type: ignore[no-untyped-def]
    """The client half of the contract, asserted against the served SPA.

    Two things must be true in the shipped JavaScript: the marker event is
    listened for, and the handler *closes* the EventSource. ``retry:`` only
    changes the browser's own retry delay — without ``close()`` the loop keeps
    running no matter what the status line says.
    """
    served = _client(config).get("/web/").text
    assert sse_module.TERMINAL_EVENT in served, (
        "served index.html does not listen for the terminal marker — the "
        "reconnect loop would survive the server-side fix"
    )

    source = SPA_PATH.read_text(encoding="utf-8")
    pattern = (
        "addEventListener\\(\\s*'"
        + re.escape(sse_module.TERMINAL_EVENT)
        + "'\\s*,(?P<body>.*?)\\n\\s*\\}\\);"
    )
    marker_handler = re.search(pattern, source, flags=re.DOTALL)
    assert marker_handler, f"no '{sse_module.TERMINAL_EVENT}' listener in {SPA_PATH.name}"
    assert "endStream(" in marker_handler.group("body")

    end_stream = re.search(
        r"function endStream\((?P<args>[^)]*)\)\s*\{(?P<body>.*?)\n\}",
        source,
        flags=re.DOTALL,
    )
    assert end_stream, "endStream() is missing from the SPA"
    assert "eventSource.close()" in end_stream.group("body"), (
        "endStream() must close the EventSource — a bare status update leaves "
        "the browser's own retry running underneath"
    )
    # The reconnect guard consults the terminal flag, and the retry is owned by
    # onerror (3 s) only while no terminal marker has been seen.
    onerror = re.search(
        r"eventSource\.onerror\s*=\s*\(\)\s*=>\s*\{(?P<body>.*?)\n\s*\}\s*;",
        source,
        flags=re.DOTALL,
    )
    assert onerror, "no eventSource.onerror handler in the SPA"
    assert "sseTerminalSeen" in onerror.group("body")


def test_aged_replay_does_not_reconnect_in_a_loop(config) -> None:  # type: ignore[no-untyped-def]
    """Simulate the old 3-second client loop and count the server's answers.

    Pre-fix, each of these GETs returned an empty body and no marker, which is
    precisely why the client retried (there was no terminal signal to stop on).
    Post-fix every iteration is terminal, so the loop is observationally
    convergent: identical frames, last event always the marker, and no
    subscriber left registered behind it.
    """
    client = _client(config)
    session_id = _aged_session(client)

    bodies = [client.get(f"/web/sse/{session_id}").text for _ in range(5)]

    assert len(set(bodies)) == 1, "reconnect replay is not idempotent"
    assert all(body for body in bodies), "an aged session still closed with zero bytes"
    for body in bodies:
        assert _event_names(body)[-1] == sse_module.TERMINAL_EVENT, (
            "a reconnect attempt got no terminal marker — the client has nothing "
            "to stop on and will retry forever"
        )
    assert session_id not in web_routes._sse_broadcaster._subscribers


# ═══════════════════════════════════════════════════════════════════════════
#  3. Unknown session: terminal semantics instead of a retryable JSON body
# ═══════════════════════════════════════════════════════════════════════════


def test_unknown_session_stream_is_terminal_not_a_json_error(config) -> None:  # type: ignore[no-untyped-def]
    """A dead session id must not answer with a body a browser reads as a drop."""
    client = _client(config)

    started = time.monotonic()
    response = client.get("/web/sse/deadbeef1234")
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers.get("x-chimera-session-status") == "unknown"

    names = _event_names(response.text)
    assert names == ["error", sse_module.TERMINAL_EVENT], (
        f"unknown session must send error+marker, got {names}"
    )
    assert '"reason": "unknown_session"' in response.text
    assert f"retry: {sse_module.TERMINAL_RETRY_MS}" in response.text

    # Never a JSON error body, and never a registered subscriber.
    assert not response.text.lstrip().startswith("{")
    assert "not found" not in response.text
    assert elapsed < 1.0
    assert "deadbeef1234" not in web_routes._sse_broadcaster._subscribers


def test_unknown_session_does_not_leak_a_subscriber(config) -> None:  # type: ignore[no-untyped-def]
    """Repeated probes of a dead id must not accumulate broadcaster state."""
    client = _client(config)
    broadcaster = web_routes._sse_broadcaster

    for _ in range(3):
        assert client.get("/web/sse/gone").status_code == 200

    assert broadcaster._subscribers == {}
    assert broadcaster._ready == {}


def test_spa_drops_the_session_id_on_unknown_session(config) -> None:  # type: ignore[no-untyped-def]
    """The SPA must forget a dead session id rather than keep re-streaming it."""
    source = SPA_PATH.read_text(encoding="utf-8")

    assert "'unknown_session'" in source
    assert "localStorage.removeItem('chimera_session_id')" in source


# ═══════════════════════════════════════════════════════════════════════════
#  4. Behaviour that must NOT change
# ═══════════════════════════════════════════════════════════════════════════


def test_session_without_turns_still_keeps_its_stream_open(config) -> None:  # type: ignore[no-untyped-def]
    """No turns → nothing to replay → the stream stays open for the live run.

    Closing this one would break a first-ever prompt: the chat POST would have
    no subscriber to deliver ``deliberation_started`` to.
    """
    client = _client(config)
    session_id = client.post("/web/sessions").json()["session_id"]

    # Drive it through the dormant path deterministically: mark the broadcaster
    # so ``event_stream`` exits on the idle timeout instead of waiting 30 s out.
    async def immediate_timeout(awaitable, *, timeout):  # type: ignore[no-untyped-def]
        del timeout
        awaitable.close()
        raise TimeoutError

    import chimera.web.sse as sse_mod

    original = sse_mod.asyncio.wait_for
    sse_mod.asyncio.wait_for = immediate_timeout  # type: ignore[assignment]
    try:
        response = client.get(f"/web/sse/{session_id}")
    finally:
        sse_mod.asyncio.wait_for = original  # type: ignore[assignment]

    assert response.status_code == 200
    assert response.text == "", "a turn-less session must not be given a replay"
    assert sse_module.TERMINAL_EVENT not in response.text


def test_in_flight_deliberation_is_not_short_circuited_by_a_replay(config) -> None:  # type: ignore[no-untyped-def]
    """A client connecting during a run must wait for the run, not get a replay.

    The session already has a previous turn, so the replay branch is available —
    but the deliberation is executing *now*, which means its stream must stay
    open and carry the live events (brief step 3).
    """
    client = _client(config)
    session_id = _aged_session(client)
    session = web_routes._session_manager.get(session_id)
    assert session is not None
    session.deliberation_in_flight = True

    async def immediate_timeout(awaitable, *, timeout):  # type: ignore[no-untyped-def]
        del timeout
        awaitable.close()
        raise TimeoutError

    import chimera.web.sse as sse_mod

    original = sse_mod.asyncio.wait_for
    sse_mod.asyncio.wait_for = immediate_timeout  # type: ignore[assignment]
    try:
        response = client.get(f"/web/sse/{session_id}")
    finally:
        sse_mod.asyncio.wait_for = original  # type: ignore[assignment]

    assert response.status_code == 200
    assert response.text == "", "an in-flight run must not be answered with a replay"
    assert sse_module.TERMINAL_EVENT not in response.text


def test_in_flight_flag_clears_after_a_turn(config) -> None:  # type: ignore[no-untyped-def]
    """The flag is scoped to the request — a finished turn replays again."""
    client = _client(config)
    session_id = client.post("/web/sessions").json()["session_id"]
    web_routes._sse_broadcaster.ensure_ready(session_id).set()

    response = client.post(
        f"/web/sessions/{session_id}/chat",
        json={"prompt": "first", "formation": "simple"},
    )

    assert response.status_code == 200, response.text
    session = web_routes._session_manager.get(session_id)
    assert session is not None
    assert session.deliberation_in_flight is False

    stream = client.get(f"/web/sse/{session_id}")
    assert _event_names(stream.text)[-1] == sse_module.TERMINAL_EVENT


def test_chat_unaffected_by_replay_flag(config) -> None:  # type: ignore[no-untyped-def]
    """An error inside the engine must not leave the flag latched on."""
    client = _client(config)
    session_id = client.post("/web/sessions").json()["session_id"]
    session = web_routes._session_manager.get(session_id)
    assert session is not None

    async def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("engine exploded")

    engine = client.app.state.engine  # type: ignore[attr-defined]
    original = engine.deliberate
    engine.deliberate = boom  # type: ignore[method-assign]
    try:
        with pytest.raises(RuntimeError):
            client.post(
                f"/web/sessions/{session_id}/chat",
                json={"prompt": "boom", "formation": "simple"},
            )
    finally:
        engine.deliberate = original  # type: ignore[method-assign]

    assert session.deliberation_in_flight is False, (
        "the in-flight flag latched after an exception — every later SSE "
        "connection for this session would keep its stream open forever"
    )


def test_session_dataclass_defaults_are_unchanged() -> None:
    """``Session`` keeps working when constructed positionally, as tests do."""
    session = Session(session_id="s", created_at=1.0)

    assert session.turns == []
    assert session.last_sse_events == []
    assert session.deliberation_in_flight is False
    assert session.turn_count == 0
