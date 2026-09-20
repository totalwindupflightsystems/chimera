"""Web UI routes — session-backed multi-turn deliberation with SSE streaming.

Registered on the FastAPI app at ``/web/*``.  The core Engine is accessed
via ``request.app.state.engine`` (set during ``create_app()``).

Endpoints:

* ``POST /web/sessions`` — create a new session
* ``POST /web/sessions/{id}/chat`` — deliberate with session context
* ``GET  /web/sessions/{id}`` — get session history
* ``GET  /web/sse/{session_id}`` — SSE event stream
* ``GET  /web/`` — serve the SPA

``POST /web/sessions/{id}/chat`` runs the same billed deliberation as
``POST /v1/deliberate`` and ``POST /v1/chat/completions``, so it takes the same
two guards through the same implementations (DF-CHIMERA-V2-22): the shared
``RateLimiter`` and the shared ``RequestQueue``.  Neither helper is copied —
both are imported from the API module, which is the reference implementation.
"""

from __future__ import annotations

import os
import time
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from chimera.api.dependencies import require_api_key
from chimera.api.server import RequestQueue, _check_rate_limit
from chimera.web.session import SessionManager, Turn
from chimera.web.sse import TERMINAL_EVENT, TERMINAL_RETRY_MS, SSEBroadcaster, SSEEvent
from chimera.web.trace_viz import trace_to_mermaid

router = APIRouter(prefix="/web", tags=["web"])

#: Spellings of ``?live=`` that mean "this client is dialing for the turn that is
#: about to run" (DF-CHIMERA-V2-29).  Lower-cased before lookup.  Anything else —
#: including an empty or unparseable value — leaves the caller on the default
#: replay-then-close path, and never earns a 422 (an ``EventSource`` reports any
#: non-200 as a retryable drop; see the unknown-session branch).
_SSE_LIVE_VALUES = frozenset({"1", "true", "yes", "on"})

log = structlog.get_logger("chimera.web")

#: Dev/test switch for ``POST /web/debug/reset`` (DF-CHIMERA-V2-20).  The
#: handler rebinds the module-global session manager and SSE broadcaster,
#: destroying EVERY live session, so it must not answer on a server anyone
#: shares.  Set ``CHIMERA_WEB_DEBUG_RESET`` to ``1`` or ``true`` in the
#: SERVER's environment to enable it; anything else (the default) keeps the
#: route answering 404 without touching any state.
_DEBUG_RESET_ENV = "CHIMERA_WEB_DEBUG_RESET"

# Single shared instances, initialized when routes are registered.
_session_manager = SessionManager()
_sse_broadcaster = SSEBroadcaster()


def _debug_reset_enabled() -> bool:
    """Whether the destructive ``/web/debug/reset`` route may fire."""
    return os.environ.get(_DEBUG_RESET_ENV, "").lower() in ("1", "true")


# ── Request / response models ──────────────────────────────────────────────


class CreateSessionResponse(BaseModel):
    session_id: str


class ChatRequest(BaseModel):
    prompt: str
    formation: str = "auto"
    # Request-level overrides (same as REST API)
    allowed_models: list[str] | None = None
    dispatcher_model: str | None = None
    aggregator_model: str | None = None


class ChatResponse(BaseModel):
    answer: str
    trace: dict[str, Any]
    turn_number: int
    mermaid: str


class SessionInfo(BaseModel):
    session_id: str
    turn_count: int
    turns: list[dict[str, Any]]


# ── Routes ─────────────────────────────────────────────────────────────────


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session() -> CreateSessionResponse:
    """Create a new deliberation session."""
    session = _session_manager.create()
    return CreateSessionResponse(session_id=session.session_id)


@router.post("/sessions/{session_id}/chat", response_model=ChatResponse)
async def session_chat(
    session_id: str,
    body: ChatRequest,
    request: Request,
    api_key: Annotated[str, Depends(require_api_key)],
) -> ChatResponse:
    """Run a deliberation in the context of *session_id*.

    Past turns are injected into the dispatcher's prompt as conversation
    history.  SSE events are broadcast as the deliberation progresses.

    DF-CHIMERA-V2-22: this path bills the same providers as
    ``POST /v1/chat/completions`` and ``POST /v1/deliberate``, so it takes the
    same two guards — the shared rate limiter and the shared request queue —
    through the very same implementations (imported, never copied).  Without
    them N concurrent web-UI deliberations launched N unrestrained provider
    fan-outs and neither ``max_concurrent``/``max_queue_depth`` nor a
    configured rate limit applied.

    Both guards run BEFORE the SSE readiness/broadcast block and before any
    turn is recorded, and the slot is released in ``finally`` — so a
    saturation refusal never leaves a half-started turn that would suppress
    the events of an already in-flight deliberation on this session.
    """
    session = _session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    # DF-CHIMERA-0917-2: reject an unknown formation at the HTTP edge, like the
    # REST surface (422) and the CLI (exit 2) already do.  Without this check
    # the name travelled straight into ``engine.deliberate``, where the
    # dispatcher logs a structlog ``unknown_formation`` warning and silently
    # falls back to ``auto`` — a typo therefore bought a full deliberation on
    # the WRONG formation, billed the providers, and this surface answered 200.
    # The check runs before the SSE readiness/broadcast block and before any
    # turn is recorded, so a rejected request costs zero provider calls.  The
    # dispatcher's internal fallback itself is intentional for programmatic
    # callers and stays untouched.
    cfg = request.app.state.config
    if body.formation not in cfg.formations:
        available = ", ".join(sorted(cfg.formations))
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown formation: {body.formation}. "
                f"Available formations: {available}."
            ),
        )

    # F2: rate limiting — same helper object and same status/body/header shape
    # as the /v1 endpoints (SDK callers can reuse their 429 handling verbatim).
    # The refusal is text/plain: BaseHTTPMiddleware drops custom headers from a
    # JSONResponse's ``detail``, so the Retry-After would be lost otherwise.
    _check_rate_limit(request, api_key)

    # F5: queue/backpressure check — the SAME RequestQueue instance the /v1
    # endpoints acquire, so the web surface competes for the same slots.
    queue: RequestQueue = request.app.state.request_queue
    acquired = await queue.acquire()
    if not acquired:
        from starlette.responses import PlainTextResponse

        return PlainTextResponse(  # type: ignore[return-value]
            content="Server busy — queue full. Retry later.",
            status_code=503,
            headers={"Retry-After": "5"},
            media_type="text/plain",
        )

    # ``deliberation_in_flight`` is what tells a client connecting *now* apart
    # from one connecting after the turn is over: a live subscriber must keep its
    # stream open, a late one gets the replay of the finished turn plus the
    # terminal marker (DF-CHIMERA-V2-19). Set before the first broadcast and
    # cleared only once the session is quiescent again (after ``unsubscribe_all``)
    # so the whole window — readiness wait, engine call, trailing events — reads
    # as live to any client that arrives inside it.
    session.deliberation_in_flight = True

    try:
        engine = request.app.state.engine

        # Build context-augmented prompt
        augmented = session.augmented_prompt(body.prompt)

        # Build overrides for the engine
        from chimera.config import DeliberationOverrides

        # ── SSE: live stage progress (DF-CHIMERA-V2-18) ──
        # The engine invokes this observer while deliberate() is still executing,
        # so the DAG panel can show per-stage progress DURING the run instead of
        # only before/after it. The observer is sync and the engine calls it from
        # coroutines already running on this loop, so the put_nowait inside
        # broadcast() is loop-safe and the event reaches the SSE stream mid-run.
        # The closure is per-request (bound to this session_id), so concurrent
        # chats on the shared Engine cannot cross-deliver their stage events.
        def stage_observer(payload: dict[str, Any]) -> None:
            phase = payload.get("phase")
            if phase == "started":
                _sse_broadcaster.broadcast(
                    session_id,
                    SSEEvent(
                        event="stage_started",
                        data={
                            "stage": payload.get("stage", ""),
                            "kind": payload.get("kind", ""),
                            "model": payload.get("model", ""),
                        },
                    ),
                )
            elif phase == "completed":
                _sse_broadcaster.broadcast(
                    session_id,
                    SSEEvent(
                        event="stage_completed",
                        data={
                            "stage": payload.get("stage", ""),
                            "kind": payload.get("kind", ""),
                            "model": payload.get("model", ""),
                            "tokens": (
                                (payload.get("tokens_input") or 0)
                                + (payload.get("tokens_output") or 0)
                            ),
                            "latency_ms": payload.get("latency_ms", 0),
                            "cost": payload.get("cost", 0.0),
                            "degraded": payload.get("degraded", False),
                            "iteration": payload.get("iteration", 1),
                        },
                    ),
                )

        overrides = DeliberationOverrides(
            allowed_models=body.allowed_models,
            dispatcher_model=body.dispatcher_model,
            aggregator_model=body.aggregator_model,
        )

        started = time.monotonic()

        # ── Wait for SSE subscriber readiness (if any) ──
        # Prevents race where chat broadcasts before SSE subscriber is listening.
        import asyncio as _asyncio

        try:
            ready = _sse_broadcaster.ensure_ready(session_id)
            await _asyncio.wait_for(ready.wait(), timeout=2.0)
        except TimeoutError:
            pass  # No SSE subscriber within 2s — proceed anyway

        # ── SSE: deliberation started ──
        _sse_broadcaster.broadcast(
            session_id,
            SSEEvent(event="deliberation_started", data={"prompt": body.prompt}),
        )

        # Run the deliberation
        result = await engine.deliberate(
            augmented,
            formation=body.formation,
            overrides=overrides,
            stage_observer=stage_observer,
        )
        trace = result.trace.model_dump(mode="json")
        answer = result.answer

        elapsed_ms = int((time.monotonic() - started) * 1000)

        # ── SSE: DAG designed ──
        mermaid_str = trace_to_mermaid(trace)
        _sse_broadcaster.broadcast(
            session_id,
            SSEEvent(event="dag_designed", data={
                "mermaid": mermaid_str,
                "formation": body.formation,
                "source": trace.get("source", ""),
                "stage_count": len(trace.get("stages", [])),
            }),
        )

        # ── Record the turn ──
        workers = [
            s.get("model", "") for s in trace.get("stages", [])
            if s.get("kind") == "worker"
        ]
        aggregator_model = ""
        for s in trace.get("stages", []):
            if s.get("kind") in ("aggregator", "judge", "merge", "audit"):
                aggregator_model = s.get("model", "")
                break

        turn = Turn(
            user_prompt=body.prompt,
            answer=answer,
            formation=body.formation,
            dispatch_model=trace.get("dispatch", {}).get("model", ""),
            worker_models=workers,
            aggregator_model=aggregator_model,
            total_tokens=trace.get("total_tokens", 0),
            total_cost=trace.get("total_cost", 0.0),
            timestamp=time.time(),
        )
        session.add_turn(turn)

        # ── SSE: deliberation done ──
        done_event_data = {
            "answer": answer,
            "total_tokens": trace.get("total_tokens", 0),
            "total_cost": trace.get("total_cost", 0.0),
            "elapsed_ms": elapsed_ms,
            "turn_number": session.turn_count,
        }
        _sse_broadcaster.broadcast(
            session_id,
            SSEEvent(event="deliberation_done", data=done_event_data),
        )

        # ── Store events in session for late-connecting SSE subscribers ──
        session.last_sse_events = [
            ("deliberation_started", {"prompt": body.prompt}),
            ("dag_designed", {
                "mermaid": mermaid_str,
                "formation": body.formation,
                "source": trace.get("source", ""),
                "stage_count": len(trace.get("stages", [])),
            }),
            ("deliberation_done", done_event_data),
        ]

        # ── Close all SSE streams for this session ──
        _sse_broadcaster.unsubscribe_all(session_id)
    finally:
        # Both release paths run on every exit (success, exception, or an
        # early return below): the queue slot is returned and the in-flight
        # window closes so a later SSE client sees the turn as finished
        # rather than as live.
        session.deliberation_in_flight = False
        queue.release()

    return ChatResponse(
        answer=answer,
        trace={**trace, "elapsed_ms": elapsed_ms},
        turn_number=session.turn_count,
        mermaid=mermaid_str,
    )


@router.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str) -> SessionInfo:
    """Get session history."""
    session = _session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    return SessionInfo(
        session_id=session.session_id,
        turn_count=session.turn_count,
        turns=[
            {
                "user_prompt": t.user_prompt,
                "answer": t.answer,
                "formation": t.formation,
                "dispatch_model": t.dispatch_model,
                "worker_models": t.worker_models,
                "aggregator_model": t.aggregator_model,
                "total_tokens": t.total_tokens,
                "total_cost": t.total_cost,
                "timestamp": t.timestamp,
            }
            for t in session.turns
        ],
    )
# ═══════════════════════════════════════════════════════════════════════════
#  SSE endpoint
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/debug/reset")
async def debug_reset():
    """Reset singleton state between integration tests.

    Destructive: rebinds the shared session manager and SSE broadcaster so
    every live session and subscriber is dropped.  Disabled unless the server
    was started with ``CHIMERA_WEB_DEBUG_RESET=1`` (or ``true``) — any other
    deployment gets a 404 and keeps its sessions.
    """
    global _session_manager, _sse_broadcaster
    if not _debug_reset_enabled():
        raise HTTPException(status_code=404, detail="Not found")
    log.warning(
        "web_debug_reset_fired",
        session_count=_session_manager.session_count,
        switch=_DEBUG_RESET_ENV,
    )
    _session_manager = SessionManager()
    _sse_broadcaster = SSEBroadcaster()
    return {"status": "ok", "message": "singletons reset"}


@router.get("/sse/{session_id}")
async def sse_stream(
    session_id: str,
    request: Request,
    live: Annotated[
        str | None,
        Query(
            description=(
                "Truthy (1/true/yes/on) means: skip the replay of the previous "
                "turn and keep the stream open for the next one"
            )
        ),
    ] = None,
):
    """SSE event stream for a session.

    The client opens this as an EventSource and receives real-time updates
    as the deliberation progresses.

    Closing policy (DF-CHIMERA-V2-19). A browser cannot distinguish "the server
    closed this stream on purpose" from "the connection dropped", so every
    deliberate close here is announced with the :data:`~chimera.web.sse.
    TERMINAL_EVENT` marker:

    * **session with recorded turns** — its stored events (``deliberation_started``
      → ``dag_designed`` → ``deliberation_done``) are replayed, then the marker,
      then the close. The replay is idempotent: a reload, or a retry by a client
      that missed the marker, sees the same frames in milliseconds. This used to
      be gated on the newest turn being younger than 30 s, which meant a session
      a *returning* user reloads — i.e. every session with history — closed with
      zero bytes and no marker, and the SPA (whose only reconnection guard is the
      ``deliberation_done`` event) retried every 3 s forever behind a permanent
      "SSE reconnecting…" banner.
    * **session with no turns yet** — unchanged: the stream stays open and is
      closed either by the live events of the deliberation that follows or by the
      idle timeout, because there is nothing to replay and the client must keep
      its reconnect ability while it waits.
    * **unknown session** — also answered as an event stream (200) that closes
      after the marker, instead of a JSON 404 body: the browser's EventSource
      surfaces any non-200 as an ``error`` indistinguishable from a drop, so the
      404 body was itself a reconnect trigger. The marker is preceded by
      ``event: error``, which IS in the retryable set, so the frontend knows to
      drop the dead session id rather than treat it as a finished replay.
      ``X-Chimera-Session-Status: unknown`` lets non-browser callers (and curl)
      see the same distinction the marker carries.

    **Live mode** (``?live=1`` — the flag is truthy-parsed: any of
    ``1``/``true``/``yes``/``on``, DF-CHIMERA-V2-29). The replay-then-close
    policy above is the right answer for a page (re)load, but it is poison for
    the turn a user is about to start: the SPA's ``EventSource`` on a session
    with history sits in a replay/close/auto-redial cycle and NEVER carries a
    live turn, so mid-run ``stage_started`` / ``stage_completed`` events never
    reach the UI (measured live: readyState stuck at 0, zero stage events per
    run). Live mode means "this client is waiting on an in-flight or imminent
    turn": skip the replay entirely and keep the stream open until the turn's
    events have been delivered — the chat handler closes every subscriber of
    the session right after ``deliberation_done``
    (:meth:`~chimera.web.sse.SSEBroadcaster.unsubscribe_all`), which ends this
    stream cleanly; the idle timeout remains the backstop if no turn ever
    arrives. The default (no flag) behavior — replay, marker, close — is
    unchanged for page loads and other consumers.

    The replay and its marker are queued onto THIS request's subscriber only.
    Fanning the replay out through ``broadcast`` would dump a stranger's stored
    turn into every other open stream of the session — which is what the
    per-session isolation guard
    (``test_sse_subscriber_session_isolation``) exists to catch.
    """
    from starlette.responses import StreamingResponse

    # Tolerant truthiness, deliberately NOT a ``bool`` query parameter: a
    # declared bool 422s every value it cannot parse, and a 422 is exactly the
    # kind of answer an ``EventSource`` reports as a retryable drop (the reason
    # the unknown-session case is a stream and not a 404 body). A live dial must
    # never be answered with one, whatever form the flag takes.
    live_mode = bool(live and live.strip().lower() in _SSE_LIVE_VALUES)

    session = _session_manager.get(session_id)
    if session is None:
        return _unknown_session_stream(session_id)

    sub = _sse_broadcaster.subscribe(session_id)

    # A session that has finished at least one turn is not "live": nothing more
    # will be broadcast for it until a new chat request arrives. Replay the
    # stored events of the last turn and close deliberately — with the terminal
    # marker, which is the frame that tells the SPA not to retry.
    #
    # The one exception is a deliberation that is executing RIGHT NOW: a client
    # that connects inside that window is waiting for the run in flight, so its
    # stream must stay open and carry the live events (step 3 of the brief).
    #
    # A client that asked for live mode (?live=1) is never given the replay:
    # it is dialing for the turn that is about to run (the SPA re-dials with
    # the flag at send time), so replaying the PREVIOUS turn and closing would
    # strand it exactly the way the bug this branch fixes did.
    if (
        not live_mode
        and session.turns
        and session.last_sse_events
        and not session.deliberation_in_flight
    ):
        for event_name, event_data in session.last_sse_events:
            _sse_broadcaster.deliver(
                sub, SSEEvent(event=event_name, data=event_data)
            )
        _sse_broadcaster.close_subscriber(session_id, sub)

    async def generate():
        async for event_str in _sse_broadcaster.event_stream(session_id, sub):
            yield event_str

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _unknown_session_stream(session_id: str):
    """A terminal SSE stream for a session id that no longer exists.

    Sends the ``error`` frame (reason ``unknown_session``) followed by the
    terminal marker, then closes — so a browser gets a 200 stream it can read
    instead of a JSON 404 body it can only report as a retryable drop. No
    subscriber is ever registered, so nothing leaks into the broadcaster.
    """
    from starlette.responses import StreamingResponse

    def generate():
        yield SSEEvent(
            event="error",
            data={"reason": "unknown_session", "session_id": session_id},
        ).format()
        yield SSEEvent(
            event=TERMINAL_EVENT,
            data={"reason": "unknown_session"},
            retry=TERMINAL_RETRY_MS,
        ).format()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Chimera-Session-Status": "unknown",
        },
    )


# ── Static SPA ─────────────────────────────────────────────────────────────


@router.get("/")
async def serve_spa():
    """Serve the single-page web UI."""
    from pathlib import Path

    from fastapi.responses import HTMLResponse

    static_dir = Path(__file__).parent / "static"
    index_path = static_dir / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            "<h1>Chimera Web UI</h1><p>Static files not found. "
            "Run <code>pip install chimera-deliberation[web]</code>.</p>",
            status_code=404,
        )
    return HTMLResponse(
        content=index_path.read_text(),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )
