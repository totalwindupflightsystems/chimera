"""Server-Sent Events broadcaster for live deliberation streaming.

The web UI opens an SSE connection to ``/web/sse/{session_id}`` and receives
real-time events as the deliberation progresses:

* ``dag_designed`` — dispatcher finished, DAG is ready (includes mermaid string)
* ``stage_started`` — a worker/aggregator stage began executing
* ``stage_completed`` — a stage finished (model, tokens, latency, cost)
* ``deliberation_done`` — final answer + full trace summary

Each event carries a ``stage_id``, ``kind``, and relevant data so the
frontend can update the DAG visualization and token dashboard in real time.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SSEEvent:
    """A single SSE event to send to one client."""

    event: str
    data: dict[str, Any]
    id: str | None = None
    retry: int | None = None

    def format(self) -> str:
        """Format as an SSE message (lines + blank line terminator)."""
        lines: list[str] = []
        if self.id is not None:
            lines.append(f"id: {self.id}")
        if self.event:
            lines.append(f"event: {self.event}")
        for line in json.dumps(self.data).split("\n"):
            lines.append(f"data: {line}")
        if self.retry is not None:
            lines.append(f"retry: {self.retry}")
        lines.append("")  # blank line terminates the event
        return "\n".join(lines)


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

    def subscribe(self, session_id: str) -> SSESubscriber:
        """Register a new SSE subscriber for *session_id*."""
        sub = SSESubscriber()
        if session_id not in self._subscribers:
            self._subscribers[session_id] = []
        self._subscribers[session_id].append(sub)
        return sub

    def unsubscribe(self, session_id: str, sub: SSESubscriber) -> None:
        """Remove a subscriber; signal completion by pushing None."""
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
        """
        subs = self._subscribers.pop(session_id, [])
        for sub in subs:
            with contextlib.suppress(asyncio.QueueFull):
                sub.queue.put_nowait(None)

    def broadcast(self, session_id: str, event: SSEEvent) -> None:
        """Send an event to every subscriber of *session_id*."""
        subs = self._subscribers.get(session_id, [])
        for sub in subs[:]:
            # Client can't keep up — drop the event rather than block.
            with contextlib.suppress(asyncio.QueueFull):
                sub.queue.put_nowait(event)

    async def event_stream(self, session_id: str, sub: SSESubscriber):
        """Async generator yielding SSE-formatted strings.

        Yields events until the subscriber is unsubscribed (sentinel None)
        or the client disconnects.
        """
        try:
            while True:
                event = await sub.queue.get()
                if event is None:
                    break
                yield event.format()
        except asyncio.CancelledError:
            pass
        finally:
            self.unsubscribe(session_id, sub)
