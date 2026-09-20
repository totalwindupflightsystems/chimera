"""Server-Sent Events broadcaster for live deliberation streaming.

The web UI opens an SSE connection to ``/web/sse/{session_id}`` and receives
real-time events as the deliberation progresses:

* ``deliberation_started`` — session_chat accepted the prompt
* ``stage_started`` — a worker/aggregator stage began executing
* ``stage_completed`` — a stage finished (model, tokens, latency, cost)
* ``dag_designed`` — dispatcher finished, DAG is ready (includes mermaid string)
* ``deliberation_done`` — final answer + full trace summary
* ``replay_done`` — terminal marker: the server closed this stream on purpose

The two stage events are emitted mid-run (DF-CHIMERA-V2-18): session_chat
attaches a ``stage_observer`` to ``engine.deliberate`` and fans each stage
payload out through the broadcaster while the deliberation is still executing.

Each event carries a ``stage_id``, ``kind``, and relevant data so the
frontend can update the DAG visualization and token dashboard in real time.

``replay_done`` (DF-CHIMERA-V2-19) is the one event a browser can use to tell
an *intentional* close from a dropped connection. A client that opened the
stream late receives the stored events of the last turn, then this marker, then
the close — so it can go idle instead of reconnecting every 3 s forever. It is
emitted exactly once, and only on the deliberate close path (the ``None``
sentinel); an idle-timeout close emits nothing, because a client that is
waiting out a long deliberation must keep its reconnect ability.

Note: as of DF-CHIMERA-V2-18 the shipped SPA (static/index.html) implements
listeners for ``deliberation_started`` / ``dag_designed`` /
``deliberation_done`` only; ``stage_started`` / ``stage_completed`` are
emitted and documented here so any client (including a future SPA update)
can consume them without another protocol change. The DAG panel therefore
does not yet render those mid-run events — see DF-CHIMERA-V2-25.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass, field
from typing import Any

#: Terminal marker event name — sent right before a deliberate stream close.
#: The SPA (``static/index.html``) listens for exactly this name to stop its
#: reconnect loop; keep the two in sync.
TERMINAL_EVENT = "replay_done"

#: Reconnect delay advertised to clients that do NOT understand the terminal
#: marker (a stale, proxy-cached copy of the SPA). ``retry:`` is part of the
#: SSE wire format, so even an old client backs off from 3 s to 60 s.
TERMINAL_RETRY_MS = 60_000


@dataclass(slots=True)
class SSEEvent:
    """A single SSE event to send to one client."""

    event: str
    data: dict[str, Any]
    id: str | None = None
    retry: int | None = None

    def format(self) -> str:
        """Format as one SSE frame: field lines, then the blank-line terminator.

        Per the SSE spec an event is dispatched only when a BLANK LINE ends it
        (https://html.spec.whatwg.org/multipage/server-sent-events.html#dispatchMessage),
        so the frame must end with ``\\n\\n``. A single trailing newline glues
        every frame to the next and a compliant ``EventSource`` buffers forever,
        dispatching nothing — the deployed defect of DF-CHIMERA-V2-29.
        """
        lines: list[str] = []
        if self.id is not None:
            lines.append(f"id: {self.id}")
        if self.event:
            lines.append(f"event: {self.event}")
        for line in json.dumps(self.data).split("\n"):
            lines.append(f"data: {line}")
        if self.retry is not None:
            lines.append(f"retry: {self.retry}")
        return "\n".join(lines) + "\n\n"


@dataclass(slots=True)
class SSESubscriber:
    """One connected SSE client."""

    queue: asyncio.Queue[SSEEvent | None] = field(
        default_factory=lambda: asyncio.Queue(maxsize=256),
    )


class SSEBroadcaster:
    """Manages SSE subscribers and fans out events to all of them."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[SSESubscriber]] = {}
        # Per-session signal: set when the first subscriber's event_stream starts
        self._ready: dict[str, asyncio.Event] = {}

    def subscribe(self, session_id: str) -> SSESubscriber:
        """Register a new SSE subscriber for *session_id*."""
        sub = SSESubscriber()
        if session_id not in self._subscribers:
            self._subscribers[session_id] = []
        self._subscribers[session_id].append(sub)
        # Ensure a ready-event exists for this session
        self._ready.setdefault(session_id, asyncio.Event())
        return sub

    def ensure_ready(self, session_id: str) -> asyncio.Event:
        """Return (or create) the ready-event that chat waits on before broadcasting."""
        return self._ready.setdefault(session_id, asyncio.Event())

    def unsubscribe(self, session_id: str, sub: SSESubscriber) -> None:
        """Remove a subscriber; signal completion by pushing None.

        Non-terminal teardown: a client that disconnected, or a stream that hit
        its idle timeout. No marker is queued here — see
        :meth:`close_subscriber` for the deliberate-close path.
        """
        if session_id in self._subscribers:
            with contextlib.suppress(ValueError):
                self._subscribers[session_id].remove(sub)
            if not self._subscribers[session_id]:
                del self._subscribers[session_id]
        # Push sentinel so the generator exits cleanly
        with contextlib.suppress(asyncio.QueueFull):
            sub.queue.put_nowait(None)

    def unsubscribe_all(self, session_id: str) -> None:
        """Push sentinel to all subscribers of *session_id* and remove them.

        Called after ``deliberation_done`` so all connected SSE clients
        close their streams cleanly instead of timing out.

        Deliberately NOT routed through :meth:`close_subscriber`: on this path
        ``deliberation_done`` is the terminal frame and must stay the LAST event
        on the wire (a documented contract, guarded by
        ``tests/integration/test_web_sse.py::test_sse_event_ordering_guaranteed``).
        The frontend's ``deliberationComplete`` guard already covers it.
        """
        subs = self._subscribers.pop(session_id, [])
        for sub in subs:
            with contextlib.suppress(asyncio.QueueFull):
                sub.queue.put_nowait(None)
        # Clean up ready-event so it doesn't leak across tests
        self._ready.pop(session_id, None)

    def deliver(self, sub: SSESubscriber, event: SSEEvent | None) -> None:
        """Queue *event* (or the ``None`` close sentinel) for ONE subscriber.

        Best effort: a full queue drops the frame. Unlike :meth:`broadcast` this
        does not fan out to every subscriber of the session — the replay in
        :func:`chimera.web.routes.sse_stream` speaks only to the client that
        asked for it.
        """
        with contextlib.suppress(asyncio.QueueFull):
            sub.queue.put_nowait(event)

    def close_subscriber(self, session_id: str, sub: SSESubscriber) -> None:
        """Deliberate end-of-stream for one subscriber: marker, then sentinel.

        The client's ``EventSource`` reports *any* close as an ``error`` and
        cannot tell "the server is done with this stream" from "the connection
        dropped", so it retries every 3 s forever (DF-CHIMERA-V2-19). The
        :data:`TERMINAL_EVENT` marker is the one frame that carries that
        distinction, and it must precede the sentinel — which is queued
        unconditionally, even when the marker was dropped on a full queue, or
        the generator would never exit.

        ``retry`` rides along for clients that do NOT understand the marker (say,
        a stale SPA served from a proxy cache): the SSE spec applies ``retry:``
        to the connection itself, so even those back off from 3 s to a minute.
        """
        self.deliver(
            sub,
            SSEEvent(event=TERMINAL_EVENT, data={}, retry=TERMINAL_RETRY_MS),
        )
        self.deliver(sub, None)  # sentinel: the generator exits cleanly
        if session_id in self._subscribers:
            with contextlib.suppress(ValueError):
                self._subscribers[session_id].remove(sub)
            if not self._subscribers[session_id]:
                del self._subscribers[session_id]

    def broadcast(self, session_id: str, event: SSEEvent) -> None:
        """Send an event to every subscriber of *session_id*.

        Iterates over a snapshot so concurrent unsubscribe during broadcast
        is safe.  Silently drops events when a subscriber's queue is full.
        """
        subs = self._subscribers.get(session_id, ())
        for sub in tuple(subs):
            with contextlib.suppress(asyncio.QueueFull):
                sub.queue.put_nowait(event)

    async def event_stream(self, session_id: str, sub: SSESubscriber):
        """Async generator yielding SSE-formatted strings.

        Yields events until the subscriber is unsubscribed (sentinel None),
        the client disconnects, or the idle timeout expires with no events.
        """
        # Signal that at least one subscriber is live and ready to receive.
        ready = self._ready.get(session_id)
        if ready is not None:
            ready.set()
        idle_timeout = 30.0  # Generous initial timeout for slow dispatchers
        try:
            while True:
                try:
                    event = await asyncio.wait_for(sub.queue.get(), timeout=idle_timeout)
                except TimeoutError:
                    break  # No events within timeout — close cleanly
                if event is None:
                    break
                try:
                    yield event.format()
                except Exception:
                    # Malformed event — skip it rather than crash the stream
                    continue
                idle_timeout = 120.0  # Reset to long timeout after first event
        except asyncio.CancelledError:
            pass
        finally:
            self.unsubscribe(session_id, sub)
