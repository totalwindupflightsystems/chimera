"""Tests for the session-backed web UI, SSE transport, and DAG visualization."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import chimera.web.routes as web_routes  # noqa: E402
import chimera.web.sse as sse_module  # noqa: E402
from chimera.api.server import create_app  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from chimera.web.session import Session, SessionManager, Turn  # noqa: E402
from chimera.web.sse import SSEBroadcaster, SSEEvent  # noqa: E402
from chimera.web.trace_viz import _short_model, trace_to_mermaid  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402


def _resp(text, model, ti, to):  # type: ignore[no-untyped-def]
    from chimera.gateway import GatewayResponse

    return GatewayResponse(text=text, model=model, tokens_input=ti, tokens_output=to)


def _client(config, dispatch_messages=None):  # type: ignore[no-untyped-def]
    def responder(model, messages, response_format=None, **kw):  # type: ignore[no-untyped-def]
        if response_format is not None:
            if dispatch_messages is not None:
                dispatch_messages.append(json.dumps(messages))
            return _resp(dispatch_json(), model, 100, 200)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:
            return _resp("FINAL ANSWER", model, 60, 90)
        return _resp(f"worker {model}", model, 20, 40)

    engine = Engine(config, FakeGateway(responder))
    app = create_app(config=config, engine=engine)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_web_singletons():  # type: ignore[no-untyped-def]
    """Keep module-level web state isolated without replacing production behavior."""
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()
    yield
    web_routes._session_manager = SessionManager()
    web_routes._sse_broadcaster = SSEBroadcaster()


# ---------------------------------------------------------------------------
# Session state and context injection
# ---------------------------------------------------------------------------


def _turn(
    prompt: str,
    answer: str,
    *,
    workers: list[str] | None = None,
    timestamp: float = 1.0,
) -> Turn:
    return Turn(
        user_prompt=prompt,
        answer=answer,
        formation="simple",
        dispatch_model="zai-coding-plan/glm-5.2",
        worker_models=workers or [],
        aggregator_model="deepseek/deepseek-chat",
        total_tokens=42,
        total_cost=0.012,
        timestamp=timestamp,
    )


def test_turn_context_snippet_handles_missing_workers_and_truncates() -> None:
    turn = _turn("p" * 250, "a" * 350)

    snippet = turn.context_snippet()

    assert "workers=[unknown]" in snippet
    assert "p" * 200 in snippet
    assert "p" * 201 not in snippet
    assert "a" * 300 in snippet
    assert "a" * 301 not in snippet


def test_session_context_is_empty_until_a_turn_is_added() -> None:
    session = Session(session_id="session", created_at=1.0)

    assert session.turn_count == 0
    assert session.build_context_preamble() == ""
    assert session.augmented_prompt("new request") == "new request"

    session.add_turn(_turn("first question", "first answer", workers=["model-a"]))

    assert session.turn_count == 1
    preamble = session.build_context_preamble()
    assert preamble.startswith("## Conversation history")
    assert "### Turn 1" in preamble
    assert "first question" in preamble
    assert "workers=[model-a]" in preamble
    assert preamble.endswith("prefer formations and models that worked well.")
    assert session.augmented_prompt("follow-up") == f"{preamble}\n\nfollow-up"


def test_session_context_uses_only_the_most_recent_turns() -> None:
    session = Session(session_id="session", created_at=1.0, max_context_turns=2)
    session.add_turn(_turn("discarded", "old answer"))
    session.add_turn(_turn("retained one", "answer one"))
    session.add_turn(_turn("retained two", "answer two"))

    preamble = session.build_context_preamble()

    assert "discarded" not in preamble
    assert "retained one" in preamble
    assert "retained two" in preamble
    assert preamble.count("### Turn") == 2
    assert "### Turn 1\n" in preamble
    assert "### Turn 2\n" in preamble


def test_session_manager_create_get_delete_and_count() -> None:
    manager = SessionManager()

    assert manager.session_count == 0
    session = manager.create()

    assert len(session.session_id) == 12
    assert session.created_at > 0
    assert manager.get(session.session_id) is session
    assert manager.session_count == 1
    assert manager.delete(session.session_id) is True
    assert manager.get(session.session_id) is None
    assert manager.delete(session.session_id) is False
    assert manager.session_count == 0


# ---------------------------------------------------------------------------
# SSE formatting and broadcaster lifecycle
# ---------------------------------------------------------------------------


def test_sse_event_format_includes_all_protocol_fields() -> None:
    event = SSEEvent(
        id="event-7",
        event="stage_completed",
        data={"stage": "worker_1", "tokens": 17},
        retry=5000,
    )

    assert event.format() == (
        'id: event-7\nevent: stage_completed\ndata: {"stage": "worker_1", "tokens": 17}\nretry: 5000\n'
    )


def test_sse_event_format_omits_optional_fields() -> None:
    formatted = SSEEvent(event="", data={"ok": True}).format()

    assert formatted == 'data: {"ok": true}\n'
    assert "id:" not in formatted
    assert "event:" not in formatted
    assert "retry:" not in formatted


def test_broadcaster_subscribe_broadcast_and_unsubscribe() -> None:
    broadcaster = SSEBroadcaster()
    first = broadcaster.subscribe("session")
    second = broadcaster.subscribe("session")
    ready = broadcaster.ensure_ready("session")
    event = SSEEvent(event="update", data={"value": 1})

    assert first.queue.maxsize == 256
    assert broadcaster.ensure_ready("session") is ready
    assert ready.is_set() is False

    broadcaster.broadcast("session", event)
    broadcaster.broadcast("other-session", event)
    assert first.queue.get_nowait() is event
    assert second.queue.get_nowait() is event

    broadcaster.unsubscribe("session", first)
    assert first.queue.get_nowait() is None
    assert broadcaster._subscribers["session"] == [second]

    # Removing the same subscriber again is harmless and exercises the
    # ValueError-suppression path while another subscriber remains.
    broadcaster.unsubscribe("session", first)
    assert first.queue.get_nowait() is None
    broadcaster.unsubscribe("session", second)
    assert second.queue.get_nowait() is None
    assert "session" not in broadcaster._subscribers


def test_broadcaster_unsubscribe_all_closes_every_subscriber() -> None:
    broadcaster = SSEBroadcaster()
    first = broadcaster.subscribe("session")
    second = broadcaster.subscribe("session")
    broadcaster.ensure_ready("session").set()

    broadcaster.unsubscribe_all("session")

    assert first.queue.get_nowait() is None
    assert second.queue.get_nowait() is None
    assert "session" not in broadcaster._subscribers
    assert "session" not in broadcaster._ready
    broadcaster.unsubscribe_all("unknown-session")


def test_broadcaster_drops_events_and_sentinels_when_queue_is_full() -> None:
    broadcaster = SSEBroadcaster()
    sub = broadcaster.subscribe("session")
    queued = SSEEvent(event="queued", data={})
    for _ in range(sub.queue.maxsize):
        sub.queue.put_nowait(queued)

    broadcaster.broadcast("session", SSEEvent(event="dropped", data={}))
    broadcaster.unsubscribe_all("session")

    assert sub.queue.qsize() == sub.queue.maxsize
    assert all(sub.queue.get_nowait() is queued for _ in range(sub.queue.maxsize))


@pytest.mark.asyncio
async def test_event_stream_signals_ready_formats_events_and_stops_on_sentinel() -> None:
    broadcaster = SSEBroadcaster()
    sub = broadcaster.subscribe("session")
    ready = broadcaster.ensure_ready("session")
    sub.queue.put_nowait(SSEEvent(event="message", data={"text": "hello"}))
    sub.queue.put_nowait(None)

    output = [item async for item in broadcaster.event_stream("session", sub)]

    assert ready.is_set() is True
    assert output == ['event: message\ndata: {"text": "hello"}\n']
    assert "session" not in broadcaster._subscribers
    assert sub.queue.get_nowait() is None


@pytest.mark.asyncio
async def test_event_stream_skips_malformed_events() -> None:
    class MalformedEvent:
        def format(self) -> str:
            raise ValueError("not serializable")

    broadcaster = SSEBroadcaster()
    sub = broadcaster.subscribe("session")
    sub.queue.put_nowait(MalformedEvent())  # type: ignore[arg-type]
    sub.queue.put_nowait(SSEEvent(event="valid", data={"ok": True}))
    sub.queue.put_nowait(None)

    output = [item async for item in broadcaster.event_stream("session", sub)]

    assert output == ['event: valid\ndata: {"ok": true}\n']


@pytest.mark.asyncio
async def test_event_stream_closes_after_idle_timeout(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def raise_timeout(awaitable, *, timeout):  # type: ignore[no-untyped-def]
        del timeout
        awaitable.close()
        raise TimeoutError

    broadcaster = SSEBroadcaster()
    sub = broadcaster.subscribe("session")
    monkeypatch.setattr(sse_module.asyncio, "wait_for", raise_timeout)

    output = [item async for item in broadcaster.event_stream("session", sub)]

    assert output == []
    assert "session" not in broadcaster._subscribers


@pytest.mark.asyncio
async def test_event_stream_handles_cancellation_and_unsubscribes() -> None:
    broadcaster = SSEBroadcaster()
    sub = broadcaster.subscribe("session")
    stream = broadcaster.event_stream("session", sub)
    pending = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)

    pending.cancel()
    with pytest.raises(StopAsyncIteration):
        await pending

    assert "session" not in broadcaster._subscribers
    assert sub.queue.get_nowait() is None


# ---------------------------------------------------------------------------
# Mermaid trace visualization
# ---------------------------------------------------------------------------


def test_trace_to_mermaid_renders_stages_edges_dispatch_metrics_and_legend() -> None:
    trace = {
        "dispatch": {
            "stage_id": "dispatcher",
            "model": "openai/gpt-5",
            "tokens_input": 10,
            "tokens_output": 20,
            "latency_ms": 15,
        },
        "stages": [
            {
                "stage_id": "worker_1",
                "kind": "worker",
                "model": "openrouter/qwen/qwen3-coder",
                "tokens_input": 2,
                "tokens_output": 3,
                "latency_ms": 12,
                "depends_on": ["dispatcher"],
            },
            {
                "stage_id": "aggregator_1",
                "kind": "aggregator",
                "model": "anthropic/claude-sonnet",
                "depends_on": ["worker_1"],
            },
            {
                "stage_id": "custom_1",
                "kind": "custom",
                "model": "local-model",
                "depends_on": [],
            },
        ],
    }

    mermaid = trace_to_mermaid(trace)

    assert mermaid.startswith("flowchart TB\n")
    assert 'worker_1["worker\\nqwen/qwen3-coder\\n5 tok\\n12ms"]' in mermaid
    assert 'aggregator_1["aggregator\\nclaude-sonnet"]' in mermaid
    assert 'custom_1["custom\\nlocal-model"]' in mermaid
    assert "style custom_1 fill:#B2BEC3" in mermaid
    assert "dispatcher --> worker_1" in mermaid
    assert "worker_1 --> aggregator_1" in mermaid
    assert 'dispatcher["dispatch\\ngpt-5\\n30 tok\\n15ms"]' in mermaid
    assert "style dispatcher fill:#6C5CE7" in mermaid
    assert "subgraph Legend" in mermaid
    for kind in ("dispatch", "worker", "aggregator", "judge", "merge", "audit"):
        assert f"        {kind}[{kind}]" in mermaid
    assert mermaid.endswith("    end")


def test_trace_to_mermaid_does_not_duplicate_dispatch_stage() -> None:
    mermaid = trace_to_mermaid(
        {
            "dispatch": {
                "stage_id": "dispatch_stage",
                "model": "openai/model-from-dispatch-field",
            },
            "stages": [
                {
                    "stage_id": "dispatch_stage",
                    "kind": "dispatch",
                    "model": "openai/model-from-stages",
                }
            ],
        }
    )

    assert "model-from-stages" in mermaid
    assert "model-from-dispatch-field" not in mermaid


def test_trace_to_mermaid_handles_empty_trace() -> None:
    mermaid = trace_to_mermaid({})

    assert mermaid.startswith("flowchart TB\n\n    subgraph Legend")
    assert "style audit fill:#FD79A8" in mermaid


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("openrouter/qwen/qwen3", "qwen/qwen3"),
        ("anthropic/claude", "claude"),
        ("deepseek/v4", "v4"),
        ("openai/gpt", "gpt"),
        ("google/gemini", "gemini"),
        ("zai-coding-plan/glm", "glm"),
        ("moonshotai/kimi", "kimi"),
        ("local/model", "local/model"),
        ("", ""),
    ],
)
def test_short_model_strips_one_known_provider_prefix(model: str, expected: str) -> None:
    assert _short_model(model) == expected


# ---------------------------------------------------------------------------
# FastAPI web routes
# ---------------------------------------------------------------------------


def test_create_get_and_missing_session_routes(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)

    created = client.post("/web/sessions")
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    assert len(session_id) == 12

    fetched = client.get(f"/web/sessions/{session_id}")
    assert fetched.status_code == 200
    assert fetched.json() == {"session_id": session_id, "turn_count": 0, "turns": []}

    missing_get = client.get("/web/sessions/not-a-session")
    assert missing_get.status_code == 404
    assert "not found" in missing_get.json()["detail"]

    missing_chat = client.post(
        "/web/sessions/not-a-session/chat",
        json={"prompt": "hello"},
    )
    assert missing_chat.status_code == 404


def test_session_chat_runs_engine_records_turn_and_injects_history(config) -> None:  # type: ignore[no-untyped-def]
    dispatch_messages: list[str] = []
    client = _client(config, dispatch_messages)
    session_id = client.post("/web/sessions").json()["session_id"]

    web_routes._sse_broadcaster.ensure_ready(session_id).set()
    first = client.post(
        f"/web/sessions/{session_id}/chat",
        json={
            "prompt": "first question",
            "formation": "simple",
            "allowed_models": [
                "deepseek/deepseek-chat",
                "openrouter/google/gemini-2.5-flash",
                "zai-coding-plan/glm-5.2",
            ],
            "dispatcher_model": "zai-coding-plan/glm-5.2",
            "aggregator_model": "zai-coding-plan/glm-5.2",
        },
    )

    assert first.status_code == 200, first.text
    first_data = first.json()
    assert first_data["answer"] == "FINAL ANSWER"
    assert first_data["turn_number"] == 1
    assert first_data["trace"]["elapsed_ms"] >= 0
    assert first_data["mermaid"].startswith("flowchart TB")
    assert "Conversation history" not in dispatch_messages[0]

    session = web_routes._session_manager.get(session_id)
    assert session is not None
    assert [name for name, _ in session.last_sse_events] == [
        "deliberation_started",
        "dag_designed",
        "deliberation_done",
    ]
    assert session.last_sse_events[-1][1]["answer"] == "FINAL ANSWER"
    assert session.turns[0].worker_models
    assert session.turns[0].aggregator_model == "zai-coding-plan/glm-5.2"
    assert session_id not in web_routes._sse_broadcaster._subscribers

    # unsubscribe_all removes the readiness signal, so mark the new one ready
    # before the next request to exercise multi-turn context without a 2s wait.
    web_routes._sse_broadcaster.ensure_ready(session_id).set()
    second = client.post(
        f"/web/sessions/{session_id}/chat",
        json={"prompt": "follow-up question", "formation": "simple"},
    )

    assert second.status_code == 200, second.text
    assert second.json()["turn_number"] == 2
    assert "## Conversation history" in dispatch_messages[-1]
    assert "first question" in dispatch_messages[-1]
    assert "FINAL ANSWER" in dispatch_messages[-1]

    history = client.get(f"/web/sessions/{session_id}").json()
    assert history["turn_count"] == 2
    assert history["turns"][0]["user_prompt"] == "first question"
    assert history["turns"][0]["answer"] == "FINAL ANSWER"
    assert history["turns"][0]["formation"] == "simple"
    assert history["turns"][0]["dispatch_model"] == "zai-coding-plan/glm-5.2"
    assert history["turns"][0]["total_tokens"] > 0
    assert history["turns"][0]["timestamp"] > 0


def test_debug_reset_replaces_singletons(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)
    client.post("/web/sessions")
    old_manager = web_routes._session_manager
    old_broadcaster = web_routes._sse_broadcaster
    old_broadcaster.ensure_ready("session")

    response = client.post("/web/debug/reset")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "singletons reset"}
    assert web_routes._session_manager is not old_manager
    assert web_routes._session_manager.session_count == 0
    assert web_routes._sse_broadcaster is not old_broadcaster


@pytest.mark.asyncio
async def test_session_chat_proceeds_when_no_sse_subscriber_becomes_ready(config) -> None:  # type: ignore[no-untyped-def]
    class TimedOutReady:
        async def wait(self) -> None:
            raise TimeoutError

    client = _client(config)
    session_id = client.post("/web/sessions").json()["session_id"]
    web_routes._sse_broadcaster.ensure_ready = lambda unused_session_id: TimedOutReady()  # type: ignore[method-assign]

    response = client.post(
        f"/web/sessions/{session_id}/chat",
        json={"prompt": "continue without SSE", "formation": "simple"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["answer"] == "FINAL ANSWER"
    assert response.json()["turn_number"] == 1


def test_sse_route_replays_recent_events_and_closes(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)
    session_id = client.post("/web/sessions").json()["session_id"]
    session = web_routes._session_manager.get(session_id)
    assert session is not None
    session.add_turn(_turn("recent", "answer", timestamp=time.time()))
    session.last_sse_events = [
        ("deliberation_started", {"prompt": "recent"}),
        ("dag_designed", {"mermaid": "flowchart TB", "stage_count": 1}),
        ("deliberation_done", {"answer": "answer", "turn_number": 1}),
    ]

    response = client.get(f"/web/sse/{session_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text.count("event: ") == 3
    assert "event: deliberation_started" in response.text
    assert "event: dag_designed" in response.text
    assert "event: deliberation_done" in response.text
    assert 'data: {"answer": "answer", "turn_number": 1}' in response.text
    assert session_id not in web_routes._sse_broadcaster._subscribers


def test_sse_route_closes_stale_session_without_replay(config) -> None:  # type: ignore[no-untyped-def]
    client = _client(config)
    session_id = client.post("/web/sessions").json()["session_id"]
    session = web_routes._session_manager.get(session_id)
    assert session is not None
    session.add_turn(_turn("old", "answer", timestamp=time.time() - 31.0))
    session.last_sse_events = [("deliberation_done", {"answer": "must not replay"})]

    response = client.get(f"/web/sse/{session_id}")

    assert response.status_code == 200
    assert response.text == ""
    assert session_id not in web_routes._sse_broadcaster._subscribers


def test_sse_route_rejects_missing_session(config) -> None:  # type: ignore[no-untyped-def]
    response = _client(config).get("/web/sse/missing")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_spa_route_serves_index_without_caching(config) -> None:  # type: ignore[no-untyped-def]
    response = _client(config).get("/web/")

    assert response.status_code == 200
    assert "Chimera" in response.text
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"


@pytest.mark.asyncio
async def test_spa_route_returns_helpful_404_when_index_is_missing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(Path, "exists", lambda self: False)

    response = await web_routes.serve_spa()

    assert response.status_code == 404
    assert b"Static files not found" in response.body
    assert b"pip install chimera-deliberation[web]" in response.body
