"""DF-CHIMERA-V2-18 — the engine's optional stage observer + web SSE wiring.

Proves that stage_started/stage_completed events are emitted DURING a
deliberation (not only before/after it) and that the web layer fans them
out through the SSE broadcaster while the chat POST is still in flight.
All tests are hermetic: FakeGateway only, and the one real-socket test
shuts its uvicorn server down in a finally block.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import threading
import time
import urllib.request
from collections.abc import Callable
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
from fastapi.testclient import TestClient  # noqa: E402

import chimera.web.routes as web_routes  # noqa: E402
from chimera.api.server import create_app  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.gateway import GatewayResponse  # noqa: E402
from chimera.web.session import SessionManager  # noqa: E402
from chimera.web.sse import SSEBroadcaster  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402


def _resp(text: str, model: str, ti: int, to: int) -> GatewayResponse:
    return GatewayResponse(text=text, model=model, tokens_input=ti, tokens_output=to)


async def _delayed(response: GatewayResponse, delay: float) -> GatewayResponse:
    await asyncio.sleep(delay)
    return response


def _slow_stage_responder(payload: str, delay: float) -> Callable[..., Any]:
    """FakeGateway responder whose non-dispatch calls sleep *delay* seconds."""

    def _responder(model: str, messages: list[dict[str, str]], response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:  # dispatcher pass — no delay
            return _resp(payload, model, 100, 200)
        return _delayed(_resp(f"worker {model}", model, 20, 40), delay)

    return _responder


def _engine_with_slow_stages(config: Any, delay: float) -> Engine:
    payload = dispatch_json(
        workers=[("worker_1", "deepseek/deepseek-chat"),
                 ("worker_2", "openrouter/google/gemini-2.5-flash")],
    )
    return Engine(config, FakeGateway(_slow_stage_responder(payload, delay)))


@pytest.fixture(autouse=True)
def _reset_web_singletons():  # type: ignore[no-untyped-def]
    """Keep module-level web state isolated without replacing production behavior."""
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()
    yield
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()


async def _wait_until(
    predicate: Callable[[], bool],
    *,
    dep_task: asyncio.Task[Any] | None = None,
    timeout: float = 5.0,
) -> None:
    """Poll *predicate* until true; bail out early if *dep_task* already finished."""

    async def _poll() -> None:
        while not predicate():
            if dep_task is not None and dep_task.done():
                break  # the run ended without satisfying it — caller asserts on events
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_poll(), timeout=timeout)


# ---------------------------------------------------------------------------
# Engine-level: the observer fires mid-run with the documented payload fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stage_observer_fires_mid_run_with_documented_payloads(config) -> None:  # type: ignore[no-untyped-def]
    events: list[dict[str, Any]] = []

    def observer(payload: dict[str, Any]) -> None:
        events.append(dict(payload))

    engine = _engine_with_slow_stages(config, 0.15)
    task = asyncio.create_task(engine.deliberate("task", "auto", stage_observer=observer))

    # A stage_started for worker_1 must arrive WHILE deliberate() is still running.
    await asyncio.wait_for(
        _wait_until(
            lambda: any(e["phase"] == "started" and e["stage"] == "worker_1" for e in events),
            dep_task=task,
        ),
        timeout=5.0,
    )
    assert not task.done(), "deliberate() finished before the first stage_started fired"

    await asyncio.wait_for(task, timeout=15.0)

    # Full lifecycle: every stage of the synthetic DAG reports started + completed.
    started = sorted(e["stage"] for e in events if e["phase"] == "started")
    completed = sorted(e["stage"] for e in events if e["phase"] == "completed")
    assert started == ["aggregator", "worker_1", "worker_2"]
    assert completed == ["aggregator", "worker_1", "worker_2"]

    # Started always precedes its own completion.
    for stage in ("worker_1", "worker_2", "aggregator"):
        s_idx = next(i for i, e in enumerate(events)
                     if e["phase"] == "started" and e["stage"] == stage)
        c_idx = next(i for i, e in enumerate(events)
                     if e["phase"] == "completed" and e["stage"] == stage)
        assert s_idx < c_idx

    # Payload contracts.
    w1_start = next(e for e in events if e["phase"] == "started" and e["stage"] == "worker_1")
    assert set(w1_start) == {"phase", "stage", "kind", "model"}
    assert w1_start["kind"] == "worker"
    assert w1_start["model"] == "deepseek/deepseek-chat"
    agg_done = next(e for e in events if e["phase"] == "completed" and e["stage"] == "aggregator")
    assert {"phase", "stage", "kind", "model", "tokens_input", "tokens_output",
            "latency_ms", "cost", "degraded", "iteration"} <= set(agg_done)
    assert agg_done["kind"] == "aggregator"
    assert agg_done["tokens_input"] > 0
    assert agg_done["tokens_output"] > 0
    assert agg_done["latency_ms"] >= 0
    assert agg_done["degraded"] is False
    assert agg_done["iteration"] == 1


@pytest.mark.asyncio
async def test_stage_observer_exceptions_never_break_the_run(config) -> None:  # type: ignore[no-untyped-def]
    calls = {"n": 0}

    def broken_sync(_payload: dict[str, Any]) -> None:
        calls["n"] += 1
        raise RuntimeError("observer exploded")

    async def broken_async(_payload: dict[str, Any]) -> None:
        raise RuntimeError("async observer exploded")

    engine = _engine_with_slow_stages(config, 0.0)
    result = await engine.deliberate("task", "auto", stage_observer=broken_sync)
    assert result.answer
    assert calls["n"] >= 6  # 3 stages x (started + completed) all reached the observer
    assert engine._observer_tasks == []

    engine2 = _engine_with_slow_stages(config, 0.0)
    result2 = await engine2.deliberate("task", "auto", stage_observer=broken_async)
    assert result2.answer
    # Awaitable observer failures are drained inside deliberate(), not leaked.
    assert engine2._observer_tasks == []


def test_deliberate_signature_keeps_observer_optional() -> None:
    """REST/CLI/MCP stay byte-identical: the hook is keyword-only, default None,
    and no other caller surface references it."""
    params = inspect.signature(Engine.deliberate).parameters
    assert "stage_observer" in params
    assert params["stage_observer"].default is None
    assert params["stage_observer"].kind is inspect.Parameter.KEYWORD_ONLY

    import chimera.api.server as api_server
    import chimera.cli.main as cli_main
    import chimera.mcp.server as mcp_server

    for module in (api_server, cli_main, mcp_server):
        assert "stage_observer" not in inspect.getsource(module), module.__name__


# ---------------------------------------------------------------------------
# Web layer: session_chat fans the observer payloads out through the broadcaster
# ---------------------------------------------------------------------------


def test_session_chat_broadcasts_stage_events_during_run(config) -> None:  # type: ignore[no-untyped-def]
    client = TestClient(
        create_app(config=config, engine=_engine_with_slow_stages(config, 0.15))
    )
    session_id = client.post("/web/sessions").json()["session_id"]

    broadcaster = web_routes._sse_broadcaster
    real_broadcast = broadcaster.broadcast
    calls: list[tuple[str, str, Any]] = []  # (session_id, event_name, event)

    def spy(sid: str, event: Any) -> None:
        calls.append((sid, event.event, event))
        real_broadcast(sid, event)

    broadcaster.broadcast = spy  # type: ignore[method-assign]
    try:
        response = client.post(
            f"/web/sessions/{session_id}/chat",
            json={"prompt": "hello", "formation": "simple"},
        )
    finally:
        broadcaster.broadcast = real_broadcast  # type: ignore[method-assign]

    assert response.status_code == 200, response.text
    names = [name for _, name, _ in calls]
    # Every broadcast belongs to THIS session (per-request closure, no leaks).
    assert {sid for sid, _, _ in calls} == {session_id}
    assert names[0] == "deliberation_started"
    assert names[-1] == "deliberation_done"
    assert names.count("stage_started") == 3  # 2 workers + 1 aggregator
    assert names.count("stage_completed") == 3

    # MID-RUN proof by transitivity: dag_designed fires only AFTER
    # engine.deliberate() returns, so stage events positioned before it were
    # broadcast while the run was still executing.
    dag_idx = names.index("dag_designed")
    last_completed_idx = max(i for i, n in enumerate(names) if n == "stage_completed")
    assert last_completed_idx < dag_idx
    for stage_name in ("stage_started", "stage_completed"):
        idxs = [i for i, n in enumerate(names) if n == stage_name]
        assert all(i < dag_idx for i in idxs), stage_name

    # A stage_completed SSE payload carries the documented dashboard fields.
    completed_events = [ev for _, name, ev in calls if name == "stage_completed"]
    payload = completed_events[-1].data
    assert {"stage", "kind", "model", "tokens", "latency_ms", "cost"} <= set(payload)
    assert payload["tokens"] > 0


# ---------------------------------------------------------------------------
# End-to-end over a real socket: stage events reach the SSE stream mid-POST
# ---------------------------------------------------------------------------


def test_chat_over_real_sse_socket_streams_stage_events_mid_run(config) -> None:  # type: ignore[no-untyped-def]
    import socket as _socket

    import uvicorn

    app = create_app(config=config, engine=_engine_with_slow_stages(config, 0.4))
    uv_config = uvicorn.Config(app, log_level="warning", access_log=False)
    server = uvicorn.Server(uv_config)
    # Bind our own socket (port 0 → kernel-assigned) and hand it to uvicorn, so
    # the test reads the port without depending on uvicorn's private attributes.
    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
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

        created = urllib.request.urlopen(urllib.request.Request(
            f"{base}/web/sessions", data=b"", method="POST"), timeout=30)
        session_id = json.loads(created.read())["session_id"]
        created.close()

        sse_events: list[tuple[float, str]] = []

        def read_sse() -> None:
            try:
                with urllib.request.urlopen(f"{base}/web/sse/{session_id}", timeout=30) as resp:
                    for raw in resp:
                        line = raw.decode("utf-8").strip()
                        if line.startswith("event: "):
                            sse_events.append((time.monotonic(), line[len("event: "):]))
            except Exception:
                pass  # stream closed by the sentinel — expected

        reader = threading.Thread(target=read_sse, daemon=True)
        reader.start()

        # Wait until the SSE subscriber is ready, exactly like the SPA does,
        # so the chat's 2s readiness window cannot mask a wiring bug.
        ready_deadline = time.monotonic() + 5.0
        while time.monotonic() < ready_deadline:
            ready = web_routes._sse_broadcaster._ready.get(session_id)
            if ready is not None and ready.is_set():
                break
            time.sleep(0.02)
        assert ready is not None and ready.is_set(), "SSE subscriber never became ready"

        chat_req = urllib.request.Request(
            f"{base}/web/sessions/{session_id}/chat",
            data=json.dumps({"prompt": "hello", "formation": "simple"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        chat_started = time.monotonic()
        with urllib.request.urlopen(chat_req, timeout=30) as resp:
            assert resp.status == 200
            body = json.loads(resp.read())
        chat_done = time.monotonic()
        assert body["answer"], body

        # The reader thread is still draining the socket when the POST returns:
        # ``deliberation_done`` is written by the server after the last stage and
        # the client reads it asynchronously. Wait for the stream to close (the
        # sentinel ends the reader) or for the terminal event to land, so the
        # assertions below are not racing the reader under full-suite load.
        reader.join(timeout=10.0)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if [name for _, name in sse_events][-1:] == ["deliberation_done"]:
                break
            time.sleep(0.02)

        names = [name for _, name in sse_events]
        assert names and names[-1] == "deliberation_done", names
        assert names.count("stage_started") >= 3, names
        assert names.count("stage_completed") >= 3, names

        # THE acceptance criterion: a stage event reached the SSE stream while
        # the chat POST was still in flight (the old code could never do this).
        started_ts = [ts for ts, name in sse_events if name == "stage_started"]
        assert started_ts, names
        assert min(started_ts) < chat_done, (
            "no stage_started arrived before the chat POST returned"
        )
        assert chat_started < min(started_ts), "stage event before the POST even started"
    finally:
        server.should_exit = True
        thread.join(timeout=10.0)
