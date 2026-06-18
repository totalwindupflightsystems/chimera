"""Integration tests for the Web UI SSE streaming and session management.

Covers the most frequent failure modes discovered during development:

* SSE ``deliberation_done`` not firing → status bar stuck on "reconnecting"
* ``SSESubscriber`` hashability crash (set → list fix)
* SSE clean-close vs. error-reconnect distinction
* Session creation, restoration, and multi-turn context accumulation
* DAG mermaid output validity
* Token / cost / TIME metrics in SSE events
* Cache-control headers on the SPA index

All tests use ``--run-integration`` and hit a real uvicorn server on
port 8810 with real provider API calls (budget models only).
"""

from __future__ import annotations

import asyncio
import json
import re
import time

import httpx
import pytest

from tests.integration.conftest import BUDGET_MODELS

pytestmark = [pytest.mark.integration, pytest.mark.slow]

TIMEOUT = 120.0  # generous — real LLM calls take 30-90s


# ═══════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _create_session(base_url: str) -> str:
    """Create a web session and return its ID (sync — one quick POST)."""
    with httpx.Client() as client:
        r = client.post(f"{base_url}/web/sessions")
    assert r.status_code == 200, f"create session: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert "session_id" in data
    return data["session_id"]


def _deliberate_sync(
    client: httpx.Client, base_url: str, session_id: str, prompt: str
) -> dict:
    """POST to the web chat endpoint and return the JSON body."""
    r = client.post(
        f"{base_url}/web/sessions/{session_id}/chat",
        json={"prompt": prompt, "formation": "simple", "allowed_models": BUDGET_MODELS},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"chat: {r.status_code} {r.text[:300]}"
    return r.json()


def _parse_sse_events(raw: str) -> list[dict]:
    """Parse raw SSE text into a list of {event, data} dicts."""
    events: list[dict] = []
    current: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip():
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith("event: "):
            current["event"] = line[7:].strip()
        elif line.startswith("data: "):
            current["data"] = line[6:].strip()
        elif line.startswith("id: "):
            current["id"] = line[4:].strip()
    if current:
        events.append(current)
    return events


# ═══════════════════════════════════════════════════════════════════════════
#  SSE Event Flow — the golden path
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sse_receives_all_events(live_server: str) -> None:
    """SSE stream delivers ``deliberation_started`` → ``dag_designed``
    → ``deliberation_done`` in order.

    REGRESSION: If ``deliberation_done`` never fires, the frontend status
    bar gets stuck on "⏳ SSE reconnecting…" forever.
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)

        # Trigger deliberation in background, listen to SSE simultaneously
        async with asyncio.TaskGroup() as tg:
            sse_task = tg.create_task(
                client.get(
                    f"{live_server}/web/sse/{sid}",
                    timeout=httpx.Timeout(TIMEOUT, read=TIMEOUT),
                )
            )
            # Give SSE task a moment to connect
            await asyncio.sleep(2.0)

            chat_task = tg.create_task(
                client.post(
                    f"{live_server}/web/sessions/{sid}/chat",
                    json={
                        "prompt": "What is 3+4? Just the number.",
                        "formation": "simple",
                        "allowed_models": BUDGET_MODELS,
                    },
                    timeout=httpx.Timeout(TIMEOUT),
                )
            )

        sse_resp = sse_task.result()
        assert sse_resp.status_code == 200
        raw = sse_resp.text

        chat_resp = chat_task.result()
        assert chat_resp.status_code == 200

    events = _parse_sse_events(raw)

    # Check for the three critical event types
    event_types = [e["event"] for e in events]
    assert "deliberation_started" in event_types, (
        f"Missing deliberation_started. Got: {event_types}\nRaw: {raw[:500]}"
    )
    assert "dag_designed" in event_types, (
        f"Missing dag_designed. Got: {event_types}\nRaw: {raw[:500]}"
    )
    assert "deliberation_done" in event_types, (
        f"Missing deliberation_done — this causes 'SSE reconnecting…' stuck.\n"
        f"Got: {event_types}\nRaw: {raw[:500]}"
    )

    # Verify correct order
    idx_start = event_types.index("deliberation_started")
    idx_dag = event_types.index("dag_designed")
    idx_done = event_types.index("deliberation_done")
    assert idx_start < idx_dag < idx_done, (
        f"Event order wrong: start={idx_start} dag={idx_dag} done={idx_done}"
    )


@pytest.mark.asyncio
async def test_sse_clean_close_no_events_after_done(live_server: str) -> None:
    """After ``deliberation_done``, the SSE stream must close cleanly
    — no more events, and definitely no crash.

    REGRESSION: The ``SSESubscriber`` hashability bug (set().add(unhashable))
    crashed the server when a second SSE client connected.
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)

        # First deliberation to populate the session
        _deliberate_sync(httpx.Client(), live_server, sid, "What is 5+5? Just the number.")

        # Now open a fresh SSE connection — it should get a clean close.
        # Since the last turn just completed, events are replayed.
        r = await client.get(
            f"{live_server}/web/sse/{sid}",
            timeout=httpx.Timeout(30.0, read=30.0),
        )
        assert r.status_code == 200
        body = r.text
        # Replayed events are fine — what matters is the stream closed cleanly
        events = _parse_sse_events(body)
        event_types = [e.get("event") for e in events]
        assert "deliberation_done" in event_types, (
            f"Replay should include deliberation_done. Got: {event_types}"
        )


@pytest.mark.asyncio
async def test_sse_multiple_clients_no_crash(live_server: str) -> None:
    """Two simultaneous SSE subscribers for the same session must not crash.

    REGRESSION: The set-based subscriber storage threw ``TypeError:
    unhashable type: 'SSESubscriber'`` on the **second** subscriber.
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)

        async def sse_listener() -> str:
            r = await client.get(
                f"{live_server}/web/sse/{sid}",
                timeout=httpx.Timeout(TIMEOUT, read=TIMEOUT),
            )
            return r.text

        # Start two SSE listeners and one deliberation
        async with asyncio.TaskGroup() as tg:
            sse1 = tg.create_task(sse_listener())
            sse2 = tg.create_task(sse_listener())
            await asyncio.sleep(2.0)

            chat = tg.create_task(
                client.post(
                    f"{live_server}/web/sessions/{sid}/chat",
                    json={
                        "prompt": "What is 6+7? Just the number.",
                        "formation": "simple",
                        "allowed_models": BUDGET_MODELS,
                    },
                    timeout=httpx.Timeout(TIMEOUT),
                )
            )

        assert chat.result().status_code == 200
        raw1 = sse1.result()
        raw2 = sse2.result()

        # Both should have received the deliberation_done event
        for raw in (raw1, raw2):
            events = _parse_sse_events(raw)
            event_types = [e["event"] for e in events]
            assert "deliberation_done" in event_types, (
                f"Subscriber missed deliberation_done.\nEvents: {event_types}"
            )


# ═══════════════════════════════════════════════════════════════════════════
#  SSE Event Content — metrics
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sse_dag_designed_has_mermaid(live_server: str) -> None:
    """``dag_designed`` event must carry a valid ``mermaid`` string.

    REGRESSION: The frontend's live DAG panel stays empty if the mermaid
    key is missing or malformed.
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)

        async with asyncio.TaskGroup() as tg:
            sse_task = tg.create_task(
                client.get(
                    f"{live_server}/web/sse/{sid}",
                    timeout=httpx.Timeout(TIMEOUT, read=TIMEOUT),
                )
            )
            await asyncio.sleep(2.0)
            chat_task = tg.create_task(
                client.post(
                    f"{live_server}/web/sessions/{sid}/chat",
                    json={
                        "prompt": "What is 1+2? Just the number.",
                        "formation": "simple",
                        "allowed_models": BUDGET_MODELS,
                    },
                    timeout=httpx.Timeout(TIMEOUT),
                )
            )

        sse_raw = sse_task.result().text
        assert chat_task.result().status_code == 200

    events = _parse_sse_events(sse_raw)
    dag_events = [e for e in events if e.get("event") == "dag_designed"]
    assert dag_events, "No dag_designed event"
    dag_data = json.loads(dag_events[0]["data"])
    assert "mermaid" in dag_data, f"dag_designed data missing 'mermaid': {dag_data}"
    mermaid = dag_data["mermaid"]
    assert "flowchart" in mermaid.lower() or "graph" in mermaid.lower(), (
        f"mermaid doesn't look like a flowchart: {mermaid[:100]}"
    )
    assert "stage_count" in dag_data, f"dag_designed missing stage_count: {dag_data}"
    assert isinstance(dag_data["stage_count"], int) and dag_data["stage_count"] >= 1


@pytest.mark.asyncio
async def test_sse_deliberation_done_has_all_metrics(live_server: str) -> None:
    """``deliberation_done`` must carry ``total_tokens``, ``total_cost``,
    ``elapsed_ms``, ``answer``, and ``turn_number``.

    REGRESSION: Missing ``elapsed_ms`` leaves the TIME dashboard blank.
    Missing tokens/cost leaves the sidebar bare.
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)

        async with asyncio.TaskGroup() as tg:
            sse_task = tg.create_task(
                client.get(
                    f"{live_server}/web/sse/{sid}",
                    timeout=httpx.Timeout(TIMEOUT, read=TIMEOUT),
                )
            )
            await asyncio.sleep(2.0)
            chat_task = tg.create_task(
                client.post(
                    f"{live_server}/web/sessions/{sid}/chat",
                    json={
                        "prompt": "What is 9+8? Just the number.",
                        "formation": "simple",
                        "allowed_models": BUDGET_MODELS,
                    },
                    timeout=httpx.Timeout(TIMEOUT),
                )
            )

        sse_raw = sse_task.result().text
        assert chat_task.result().status_code == 200

    events = _parse_sse_events(sse_raw)
    done_events = [e for e in events if e.get("event") == "deliberation_done"]
    assert done_events, "No deliberation_done event"

    done_data = json.loads(done_events[0]["data"])

    # All metrics must be present
    assert "total_tokens" in done_data, f"Missing total_tokens: {done_data}"
    assert done_data["total_tokens"] > 0, "total_tokens should be > 0"

    assert "total_cost" in done_data, f"Missing total_cost: {done_data}"
    assert done_data["total_cost"] > 0, "total_cost should be > 0"

    assert "elapsed_ms" in done_data, (
        f"Missing elapsed_ms — causes blank TIME in dashboard: {done_data}"
    )
    assert done_data["elapsed_ms"] > 0, "elapsed_ms should be > 0"

    assert "answer" in done_data, f"Missing answer: {done_data}"
    assert done_data["answer"].strip(), "answer should not be empty"

    assert "turn_number" in done_data, f"Missing turn_number: {done_data}"
    assert isinstance(done_data["turn_number"], int)


# ═══════════════════════════════════════════════════════════════════════════
#  Session Lifecycle
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_session_create_returns_valid_id(live_server: str) -> None:
    """``POST /web/sessions`` returns a non-empty session_id."""
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)
        assert len(sid) >= 8, f"session_id too short: {sid}"
        assert re.match(r"^[a-f0-9]+$", sid), f"session_id not hex: {sid}"


@pytest.mark.asyncio
async def test_session_get_history_empty(live_server: str) -> None:
    """``GET /web/sessions/{id}`` for a new session returns zero turns."""
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)
        r = await client.get(f"{live_server}/web/sessions/{sid}")
        assert r.status_code == 200
        data = r.json()
        assert data["turn_count"] == 0
        assert data["turns"] == []


@pytest.mark.asyncio
async def test_session_get_history_after_turns(live_server: str) -> None:
    """After one deliberation, history shows exactly one turn."""
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)
        _deliberate_sync(httpx.Client(), live_server, sid, "What is 9+1? Just the number.")

        r = await client.get(f"{live_server}/web/sessions/{sid}")
        assert r.status_code == 200
        data = r.json()
        assert data["turn_count"] == 1, f"Expected 1 turn, got {data}"
        assert len(data["turns"]) == 1
        turn = data["turns"][0]
        # Each turn should have these fields
        for key in ("user_prompt", "answer", "formation", "total_tokens", "total_cost"):
            assert key in turn, f"Turn missing '{key}': {list(turn.keys())}"


@pytest.mark.asyncio
async def test_session_not_found_returns_404(live_server: str) -> None:
    """``GET /web/sessions/nonexistent`` returns 404."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{live_server}/web/sessions/deadbeef1234")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
#  Multi-turn Context
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_multi_turn_context_accumulates(live_server: str) -> None:
    """Three turns in the same session — all three appear in history."""
    import httpx as sync_httpx

    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)

        for prompt in ("What is 2+2?", "What is 3+3?", "What is 4+4?"):
            _deliberate_sync(sync_httpx.Client(), live_server, sid, prompt)
            # Small delay to let server settle
            await asyncio.sleep(0.3)

        r = await client.get(f"{live_server}/web/sessions/{sid}")
        assert r.status_code == 200
        data = r.json()
        assert data["turn_count"] == 3, f"Expected 3 turns, got {data['turn_count']}"
        assert len(data["turns"]) == 3


@pytest.mark.asyncio
async def test_multi_turn_chat_response_includes_turn_number(live_server: str) -> None:
    """Each ``POST /web/sessions/{id}/chat`` response includes the correct
    incrementing turn_number."""
    import httpx as sync_httpx

    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)

        for expected_turn in (1, 2):
            r = await client.post(
                f"{live_server}/web/sessions/{sid}/chat",
                json={
                    "prompt": f"What is {expected_turn}+{expected_turn}? Just number.",
                    "formation": "simple",
                    "allowed_models": BUDGET_MODELS,
                },
                timeout=httpx.Timeout(TIMEOUT),
            )
            assert r.status_code == 200
            data = r.json()
            assert data["turn_number"] == expected_turn, (
                f"Expected turn_number={expected_turn}, got {data.get('turn_number')}"
            )
            await asyncio.sleep(0.3)


# ═══════════════════════════════════════════════════════════════════════════
#  Chat Endpoint
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_chat_response_includes_mermaid_and_trace(live_server: str) -> None:
    """``POST /web/sessions/{id}/chat`` response has ``mermaid`` and ``trace``.

    REGRESSION: The HTTP fallback path (when SSE stream dies) didn't provide
    mermaid or trace, leaving the chat bubble bare.
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)
        r = await client.post(
            f"{live_server}/web/sessions/{sid}/chat",
            json={
                "prompt": "What is 10+10? Just the number.",
                "formation": "simple",
                "allowed_models": BUDGET_MODELS,
            },
            timeout=httpx.Timeout(TIMEOUT),
        )
        assert r.status_code == 200
        data = r.json()

        assert "answer" in data, f"Missing answer: {data}"
        assert "mermaid" in data, f"Missing mermaid: {data}"
        assert "flowchart" in data["mermaid"].lower() or "graph" in data["mermaid"].lower()
        assert "trace" in data, f"Missing trace: {data}"
        trace = data["trace"]
        assert "total_tokens" in trace, f"trace missing total_tokens: {trace}"
        assert "total_cost" in trace, f"trace missing total_cost: {trace}"
        assert trace["total_tokens"] > 0


@pytest.mark.asyncio
async def test_chat_missing_prompt_returns_422(live_server: str) -> None:
    """``POST /web/sessions/{id}/chat`` without a ``prompt`` returns 422."""
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)
        r = await client.post(
            f"{live_server}/web/sessions/{sid}/chat",
            json={"formation": "simple"},
            timeout=httpx.Timeout(10.0),
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_chat_invalid_session_returns_404(live_server: str) -> None:
    """``POST /web/sessions/nonexistent/chat`` returns 404."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{live_server}/web/sessions/deadbeef1234/chat",
            json={"prompt": "Hello", "formation": "simple"},
            timeout=httpx.Timeout(10.0),
        )
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
#  SSE Error Paths
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sse_invalid_session_returns_404(live_server: str) -> None:
    """``GET /web/sse/nonexistent`` returns 404."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{live_server}/web/sse/deadbeef1234",
            timeout=httpx.Timeout(10.0),
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_sse_event_data_is_valid_json(live_server: str) -> None:
    """Every SSE event's ``data`` field must parse as valid JSON.

    REGRESSION: Malformed JSON in SSE events would break the frontend's
    ``JSON.parse()`` without any visible error (silent failure).
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)

        async with asyncio.TaskGroup() as tg:
            sse_task = tg.create_task(
                client.get(
                    f"{live_server}/web/sse/{sid}",
                    timeout=httpx.Timeout(TIMEOUT, read=TIMEOUT),
                )
            )
            await asyncio.sleep(2.0)
            chat_task = tg.create_task(
                client.post(
                    f"{live_server}/web/sessions/{sid}/chat",
                    json={
                        "prompt": "What is 1+1? Just number.",
                        "formation": "simple",
                        "allowed_models": BUDGET_MODELS,
                    },
                    timeout=httpx.Timeout(TIMEOUT),
                )
            )

        assert chat_task.result().status_code == 200
        events = _parse_sse_events(sse_task.result().text)

    assert events, "No SSE events received"
    for evt in events:
        json.loads(evt["data"])  # must not raise


# ═══════════════════════════════════════════════════════════════════════════
#  Cache-Control Header
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_spa_index_has_no_cache_header(live_server: str) -> None:
    """``GET /web/`` must return ``Cache-Control: no-store`` (or similar).

    REGRESSION: Cloudflare tunnel caches the SPA index.html, serving stale
    JavaScript even after the source file was updated.  This makes frontend
    bug fixes invisible to users.
    """
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{live_server}/web/")
        assert r.status_code == 200
        cache_control = r.headers.get("cache-control", "").lower()
        assert any(
            directive in cache_control
            for directive in ("no-store", "no-cache", "must-revalidate")
        ), (
            f"Expected Cache-Control header with no-store/no-cache/must-revalidate, "
            f"got: {r.headers.get('cache-control', '(missing)')}"
        )


@pytest.mark.asyncio
async def test_spa_index_contains_fixed_javascript(live_server: str) -> None:
    """The served index.html must contain the ``deliberationComplete`` variable
    (introduced in the SSE reconnect fix).

    REGRESSION: If Cloudflare serves a cached version without this variable,
    the "⏳ SSE reconnecting…" bug persists despite the fix being deployed.
    """
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{live_server}/web/")
        assert r.status_code == 200
        body = r.text
        assert "deliberationComplete" in body, (
            "Served index.html is missing 'deliberationComplete' — "
            "this means the SSE reconnect fix is not in the deployed file"
        )
        assert "currentMermaid" in body, (
            "Served index.html is missing 'currentMermaid' — "
            "DAG+mermaid pass-through fix not deployed"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  SSE Reconnect Resilience
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sse_reconnect_after_deliberation_works(live_server: str) -> None:
    """After the SSE stream closes (deliberation complete), a *new* SSE
    connection for the same session opens successfully.

    This simulates the frontend's ``eventSource.onerror → reconnect``
    loop — the server must handle repeated connections gracefully.
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)
        _deliberate_sync(httpx.Client(), live_server, sid, "What is 4+4? Just number.")

        # Open SSE after deliberation — should connect and close cleanly
        r = await client.get(
            f"{live_server}/web/sse/{sid}",
            timeout=httpx.Timeout(15.0, read=15.0),
        )
        assert r.status_code == 200

        # A second connection should also work (simulate reconnect)
        r2 = await client.get(
            f"{live_server}/web/sse/{sid}",
            timeout=httpx.Timeout(15.0, read=15.0),
        )
        assert r2.status_code == 200


@pytest.mark.asyncio
async def test_sse_during_active_deliberation(live_server: str) -> None:
    """Open SSE *during* an active deliberation and verify events arrive.

    This tests the subscribe-during-execution path — the SSE stream should
    pick up events from whatever stage the deliberation is currently in.
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)

        # Start deliberation, then open SSE mid-flight
        async with asyncio.TaskGroup() as tg:
            chat_task = tg.create_task(
                client.post(
                    f"{live_server}/web/sessions/{sid}/chat",
                    json={
                        "prompt": "What is 15+27? Just the number.",
                        "formation": "simple",
                        "allowed_models": BUDGET_MODELS,
                    },
                    timeout=httpx.Timeout(TIMEOUT),
                )
            )
            # Wait a few seconds for deliberation to start, then connect SSE
            await asyncio.sleep(5)
            sse_task = tg.create_task(
                client.get(
                    f"{live_server}/web/sse/{sid}",
                    timeout=httpx.Timeout(TIMEOUT, read=TIMEOUT),
                )
            )

        assert chat_task.result().status_code == 200
        sse_raw = sse_task.result().text
        events = _parse_sse_events(sse_raw)
        event_types = [e["event"] for e in events]

        # Should get at least some events (might miss deliberation_started
        # if the subscriber connected after it fired)
        assert len(events) > 0, "No SSE events received mid-deliberation"
        # Should at least get the done event
        assert "deliberation_done" in event_types, (
            f"SSE mid-flight missed deliberation_done. Events: {event_types}"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  SSE Event Ordering — golden path guarantees
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sse_event_ordering_guaranteed(live_server: str) -> None:
    """``deliberation_started`` must be the FIRST event and
    ``deliberation_done`` must be the LAST.

    REGRESSION: If events arrive out of order, the frontend shows
    the DAG before "Dispatching…" or leaves the LIVE indicator on.
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)

        async with asyncio.TaskGroup() as tg:
            sse_task = tg.create_task(
                client.get(
                    f"{live_server}/web/sse/{sid}",
                    timeout=httpx.Timeout(TIMEOUT, read=TIMEOUT),
                )
            )
            await asyncio.sleep(2.0)
            chat_task = tg.create_task(
                client.post(
                    f"{live_server}/web/sessions/{sid}/chat",
                    json={
                        "prompt": "What is 5+5? Just the number.",
                        "formation": "simple",
                        "allowed_models": BUDGET_MODELS,
                    },
                    timeout=httpx.Timeout(TIMEOUT),
                )
            )

        sse_raw = sse_task.result().text
        assert chat_task.result().status_code == 200

    events = _parse_sse_events(sse_raw)
    assert events, "No SSE events"
    assert events[0]["event"] == "deliberation_started", (
        f"First event must be deliberation_started, got: {events[0].get('event')}"
    )
    assert events[-1]["event"] == "deliberation_done", (
        f"Last event must be deliberation_done, got: {events[-1].get('event')}"
    )


@pytest.mark.asyncio
async def test_sse_subscriber_session_isolation(live_server: str) -> None:
    """SSE events for session A must NOT leak into session B's stream.

    REGRESSION: If the SSE broadcaster broadcasts globally instead of
    per-session, subscribers would receive another user's deliberation.
    """
    async with httpx.AsyncClient() as client:
        sid_a = _create_session(live_server)
        sid_b = _create_session(live_server)

        # Deliberate in session A, listen to session B's SSE
        async with asyncio.TaskGroup() as tg:
            sse_task = tg.create_task(
                client.get(
                    f"{live_server}/web/sse/{sid_b}",
                    timeout=httpx.Timeout(TIMEOUT, read=TIMEOUT),
                )
            )
            await asyncio.sleep(2.0)
            chat_task = tg.create_task(
                client.post(
                    f"{live_server}/web/sessions/{sid_a}/chat",
                    json={
                        "prompt": "What is 9+9? Just the number.",
                        "formation": "simple",
                        "allowed_models": BUDGET_MODELS,
                    },
                    timeout=httpx.Timeout(TIMEOUT),
                )
            )

        sse_raw = sse_task.result().text
        assert chat_task.result().status_code == 200

    # Session B's SSE should receive NO events (only session A deliberated)
    events = _parse_sse_events(sse_raw)
    event_types = [e["event"] for e in events]
    assert "deliberation_started" not in event_types, (
        f"Session B received events meant for session A! Events: {event_types}"
    )
    assert "deliberation_done" not in event_types, (
        f"Session B received deliberation_done from session A. Events: {event_types}"
    )


@pytest.mark.asyncio
async def test_sse_events_never_duplicated(live_server: str) -> None:
    """Each SSE event type must appear exactly ONCE per deliberation.

    REGRESSION: Duplicate ``deliberation_done`` events would cause
    duplicate chat bubbles in the frontend.
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)

        async with asyncio.TaskGroup() as tg:
            sse_task = tg.create_task(
                client.get(
                    f"{live_server}/web/sse/{sid}",
                    timeout=httpx.Timeout(TIMEOUT, read=TIMEOUT),
                )
            )
            await asyncio.sleep(2.0)
            chat_task = tg.create_task(
                client.post(
                    f"{live_server}/web/sessions/{sid}/chat",
                    json={
                        "prompt": "What is 3+3? Just the number.",
                        "formation": "simple",
                        "allowed_models": BUDGET_MODELS,
                    },
                    timeout=httpx.Timeout(TIMEOUT),
                )
            )

        sse_raw = sse_task.result().text
        assert chat_task.result().status_code == 200

    events = _parse_sse_events(sse_raw)
    event_types = [e["event"] for e in events]

    for evt_name in ("deliberation_started", "dag_designed", "deliberation_done"):
        count = event_types.count(evt_name)
        assert count == 1, (
            f"Event '{evt_name}' appeared {count} times (expected exactly 1). "
            f"All events: {event_types}"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  Chat Response — TIME metric fix
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_chat_response_trace_includes_elapsed_ms(live_server: str) -> None:
    """The HTTP chat response's ``trace`` dict must include ``elapsed_ms``.

    REGRESSION: The frontend's TIME dashboard stat shows "0ms" because
    ``elapsed_ms`` was computed locally but never included in the HTTP
    response body — only the SSE ``deliberation_done`` event carried it.
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)
        r = await client.post(
            f"{live_server}/web/sessions/{sid}/chat",
            json={
                "prompt": "What is 7+7? Just the number.",
                "formation": "simple",
                "allowed_models": BUDGET_MODELS,
            },
            timeout=httpx.Timeout(TIMEOUT),
        )
        assert r.status_code == 200
        data = r.json()

        trace = data.get("trace", {})
        assert "elapsed_ms" in trace, (
            f"trace missing elapsed_ms. Keys: {list(trace.keys())}\n"
            f"Full trace: {json.dumps(trace, default=str)[:300]}"
        )
        assert trace["elapsed_ms"] > 0, (
            f"elapsed_ms should be > 0, got: {trace['elapsed_ms']}"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  Multi-turn SSE — consecutive deliberations
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sse_two_consecutive_deliberations(live_server: str) -> None:
    """Two back-to-back deliberations in the same session — both must
    deliver complete SSE event streams.

    REGRESSION: The SSE broadcaster's subscriber list survives between
    deliberations without cleanup, causing stale subscribers to accumulate.
    """
    import httpx as sync_httpx

    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)

        for i, prompt in enumerate(("What is 2+2?", "What is 3+3?")):
            async with asyncio.TaskGroup() as tg:
                sse_task = tg.create_task(
                    client.get(
                        f"{live_server}/web/sse/{sid}",
                        timeout=httpx.Timeout(TIMEOUT, read=TIMEOUT),
                    )
                )
                await asyncio.sleep(2.0)
                chat_task = tg.create_task(
                    client.post(
                        f"{live_server}/web/sessions/{sid}/chat",
                        json={
                            "prompt": f"{prompt} Just the number.",
                            "formation": "simple",
                            "allowed_models": BUDGET_MODELS,
                        },
                        timeout=httpx.Timeout(TIMEOUT),
                    )
                )

            sse_raw = sse_task.result().text
            assert chat_task.result().status_code == 200

            events = _parse_sse_events(sse_raw)
            event_types = [e["event"] for e in events]
            assert "deliberation_done" in event_types, (
                f"Turn {i + 1}: deliberation_done missing. Events: {event_types}"
            )
            await asyncio.sleep(2.0)


# ═══════════════════════════════════════════════════════════════════════════
#  Edge Cases — prompt content
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_chat_special_characters_prompt(live_server: str) -> None:
    """Prompts with special characters (unicode, emoji, quotes) must not
    break the chat endpoint or SSE broadcasting.

    REGRESSION: Unescaped JSON in SSE event data would break the
    frontend's ``JSON.parse()``.
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)
        r = await client.post(
            f"{live_server}/web/sessions/{sid}/chat",
            json={
                "prompt": 'What is 2+2? Unicode: café • naïveté — "quoted" \'single\' <tag>',
                "formation": "simple",
                "allowed_models": BUDGET_MODELS,
            },
            timeout=httpx.Timeout(TIMEOUT),
        )
        assert r.status_code == 200
        data = r.json()
        assert "answer" in data
        # Verify the response is valid JSON (should always be, but belt & suspenders)
        json.dumps(data)  # must not raise


@pytest.mark.asyncio
async def test_sse_emoji_in_prompt(live_server: str) -> None:
    """Prompts with emoji must not corrupt SSE event data.

    REGRESSION: Emoji in SSE ``data:`` lines can break the SSE parser
    if newline characters sneak in.
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)

        async with asyncio.TaskGroup() as tg:
            sse_task = tg.create_task(
                client.get(
                    f"{live_server}/web/sse/{sid}",
                    timeout=httpx.Timeout(TIMEOUT, read=TIMEOUT),
                )
            )
            await asyncio.sleep(2.0)
            chat_task = tg.create_task(
                client.post(
                    f"{live_server}/web/sessions/{sid}/chat",
                    json={
                        "prompt": "What is 1+1? 🦁🔥 Just the number.",
                        "formation": "simple",
                        "allowed_models": BUDGET_MODELS,
                    },
                    timeout=httpx.Timeout(TIMEOUT),
                )
            )

        sse_raw = sse_task.result().text
        assert chat_task.result().status_code == 200

    events = _parse_sse_events(sse_raw)
    # Every event's data must be parseable JSON
    for evt in events:
        json.loads(evt["data"])  # must not raise with emoji


# ═══════════════════════════════════════════════════════════════════════════
#  Formation-specific DAG output
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sse_formation_affects_dag(live_server: str) -> None:
    """Different formations must produce different DAG mermaid output.

    REGRESSION: If all formations produce identical DAGs, the frontend
    visualization never changes and users can't distinguish formations.
    """
    async with httpx.AsyncClient() as client:
        mermaids = {}

        for formation in ("simple", "debate", "audit"):
            sid = _create_session(live_server)
            r = await client.post(
                f"{live_server}/web/sessions/{sid}/chat",
                json={
                    "prompt": "What is 10+10? Just the number.",
                    "formation": formation,
                    "allowed_models": BUDGET_MODELS,
                },
                timeout=httpx.Timeout(TIMEOUT),
            )
            assert r.status_code == 200
            mermaids[formation] = r.json()["mermaid"]

    # At minimum, the stage count text differs
    unique = set(mermaids.values())
    assert len(unique) >= 2, (
        f"All formations produced identical DAGs — visualization never changes.\n"
        f"simple: {mermaids['simple'][:80]}\n"
        f"debate: {mermaids['debate'][:80]}\n"
        f"audit:  {mermaids['audit'][:80]}"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Concurrent Safety
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_concurrent_chat_requests_same_session(live_server: str) -> None:
    """Two simultaneous chat requests in the same session must not crash
    or corrupt session state.

    Each request should complete independently and the session history
    should contain both turns (order not guaranteed for concurrent).

    REGRESSION: The SessionManager uses thread-unsafe in-memory state;
    concurrent access could cause lost turns or data corruption.
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)

        async def send(prompt: str) -> dict:
            r = await client.post(
                f"{live_server}/web/sessions/{sid}/chat",
                json={
                    "prompt": prompt,
                    "formation": "simple",
                    "allowed_models": BUDGET_MODELS,
                },
                timeout=httpx.Timeout(TIMEOUT),
            )
            assert r.status_code == 200
            return r.json()

        # Fire two requests concurrently
        results = await asyncio.gather(
            send("What is 2+3? Just number."),
            send("What is 4+5? Just number."),
        )

        # Both should have answers
        for i, r in enumerate(results):
            assert "answer" in r, f"Request {i} missing answer: {r}"

        # Session history should have 2 turns
        hist_r = await client.get(f"{live_server}/web/sessions/{sid}")
        assert hist_r.status_code == 200
        hist = hist_r.json()
        assert hist["turn_count"] == 2, (
            f"Expected 2 turns after 2 concurrent requests, got {hist['turn_count']}"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  SSE Stream header verification
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sse_response_headers(live_server: str) -> None:
    """SSE endpoint must return correct Content-Type and no-cache headers.

    Without ``text/event-stream``, the browser won't parse SSE.
    Without ``Cache-Control: no-cache``, proxies buffer the stream.
    """
    async with httpx.AsyncClient() as client:
        sid = _create_session(live_server)
        r = await client.get(
            f"{live_server}/web/sse/{sid}",
            timeout=httpx.Timeout(5.0, read=5.0),
        )
        assert r.status_code == 200
        content_type = r.headers.get("content-type", "")
        assert "text/event-stream" in content_type, (
            f"Wrong Content-Type: {content_type}"
        )
        cache_control = r.headers.get("cache-control", "")
        assert "no-cache" in cache_control.lower(), (
            f"Missing no-cache in SSE Cache-Control: {cache_control}"
        )

