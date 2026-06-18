"""Web UI routes — session-backed multi-turn deliberation with SSE streaming.

Registered on the FastAPI app at ``/web/*``.  The core Engine is accessed
via ``request.app.state.engine`` (set during ``create_app()``).

Endpoints:

* ``POST /web/sessions`` — create a new session
* ``POST /web/sessions/{id}/chat`` — deliberate with session context
* ``GET  /web/sessions/{id}`` — get session history
* ``GET  /web/sse/{session_id}`` — SSE event stream
* ``GET  /web/`` — serve the SPA
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from chimera.web.session import SessionManager, Turn
from chimera.web.sse import SSEBroadcaster, SSEEvent
from chimera.web.trace_viz import trace_to_mermaid

router = APIRouter(prefix="/web", tags=["web"])

# Single shared instances, initialized when routes are registered.
_session_manager = SessionManager()
_sse_broadcaster = SSEBroadcaster()


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
async def session_chat(session_id: str, body: ChatRequest, request: Request) -> ChatResponse:
    """Run a deliberation in the context of *session_id*.

    Past turns are injected into the dispatcher's prompt as conversation
    history.  SSE events are broadcast as the deliberation progresses.
    """
    session = _session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    engine = request.app.state.engine

    # Build context-augmented prompt
    augmented = session.augmented_prompt(body.prompt)

    # Build overrides for the engine
    from chimera.config import DeliberationOverrides

    overrides = DeliberationOverrides(
        allowed_models=body.allowed_models,
        dispatcher_model=body.dispatcher_model,
        aggregator_model=body.aggregator_model,
    )

    started = time.monotonic()

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
    _sse_broadcaster.broadcast(
        session_id,
        SSEEvent(event="deliberation_done", data={
            "answer": answer,
            "total_tokens": trace.get("total_tokens", 0),
            "total_cost": trace.get("total_cost", 0.0),
            "elapsed_ms": elapsed_ms,
            "turn_number": session.turn_count,
        }),
    )

    # ── Close all SSE streams for this session ──
    # Schedule after a short grace period so late-connecting clients
    # have time to receive all buffered events before the sentinel.
    import asyncio as _asyncio

    _asyncio.get_running_loop().call_later(
        3.0, lambda: _sse_broadcaster.unsubscribe_all(session_id),
    )

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


# ── SSE endpoint ───────────────────────────────────────────────────────────


@router.get("/sse/{session_id}")
async def sse_stream(session_id: str, request: Request):
    """SSE event stream for a session.

    The client opens this as an EventSource and receives real-time updates
    as the deliberation progresses.
    """
    from starlette.responses import StreamingResponse

    session = _session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    sub = _sse_broadcaster.subscribe(session_id)

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
