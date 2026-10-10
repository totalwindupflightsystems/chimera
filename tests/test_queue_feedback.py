"""DF-CHIMERA-V2-77: queue feedback for concurrent deliberations.

Under concurrency, ``POST /v1/deliberate`` requests queue on the shared
``RequestQueue`` with no per-request signal to the caller: four simultaneous
deliberations returned 18.9-49.4 s of wall-time variance and the client could
not tell it had waited behind other work at all. The fix reports each request's
*arrival rank* — how many requests, including itself, were inside the queue when
it entered — in the ``X-Chimera-Queue-Position`` response header.

These tests pin both halves of the behaviour:

* the queue accounting itself — rank assignment, the exit decrement, and the
  reject / cancellation paths that must NOT leave a request counted as queued;
  and
* the header on the wire, including a genuinely concurrent pair over a single
  semaphore slot, so the second request's rank is provably 2.

Hermetic: a ``FakeGateway`` answers every provider call (no key, no network),
and the concurrent HTTP case drives the ASGI app in-process through httpx's
``ASGITransport``. No socket is opened.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

import pytest

pytest.importorskip("fastapi")

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from chimera.api.server import (  # noqa: E402
    QUEUE_POSITION_HEADER,
    RequestQueue,
    create_app,
)
from chimera.config import ChimeraConfig  # noqa: E402
from chimera.engine import Engine  # noqa: E402
from tests.conftest import CONFIG_DICT, FakeGateway, dispatch_json, resp  # noqa: E402

#: Bounded wait for the "the request reached the queue" polls. Mirrors
#: tests/test_concurrency.py: the request under test runs as an independent
#: task, so the wait is a function of the clock, never of a fixed event-loop
#: turn count — a turn-counted poll flakes under CPU contention.
_WAIT_TIMEOUT_S = 5.0
_WAIT_POLL_S = 0.005


def _queue_config(**queue: int) -> ChimeraConfig:
    """``CONFIG_DICT`` with the ``queue`` block overridden."""
    cfg_dict: dict[str, Any] = {**CONFIG_DICT, "queue": queue}
    return ChimeraConfig.model_validate(cfg_dict)


def _responder(model: str, messages: list[dict[str, str]], response_format: Any = None, **kw: Any) -> Any:
    """Canned responder — zero network, mirroring tests/test_concurrency.py."""
    if response_format is not None:  # dispatcher
        return resp(dispatch_json(), model, 100, 200)
    if "Upstream outputs" in str(messages):  # aggregator / merge
        return resp("FINAL ANSWER", model, 60, 90)
    return resp(f"worker {model}", model, 20, 40)


def _client(config: ChimeraConfig) -> TestClient:
    gateway = FakeGateway(_responder)
    app = create_app(config=config, engine=Engine(config, gateway))
    return TestClient(app)


async def _wait_until(condition: Callable[[], bool]) -> bool:
    """Poll *condition* until it holds, or the time budget expires."""
    deadline = time.monotonic() + _WAIT_TIMEOUT_S
    while time.monotonic() < deadline:
        if condition():
            return True
        await asyncio.sleep(_WAIT_POLL_S)
    return bool(condition())


async def _acquire_recording(queue: RequestQueue, sink: list[tuple[bool, int]]) -> bool:
    """Acquire a slot and record ``(acquired, rank)`` for the CALLING task."""
    acquired = await queue.acquire()
    sink.append((acquired, queue.position_of_current_request))
    return acquired


# --------------------------------------------------------------------------- #
# RequestQueue accounting
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fresh_queue_reports_no_position() -> None:
    """Before any acquire, the queue is empty and no rank is published."""
    queue = RequestQueue(max_concurrent=2, max_queue_depth=10)
    assert queue.current_queued == 0
    assert queue.position_of_current_request == 0


@pytest.mark.asyncio
async def test_single_request_enters_at_rank_one_and_release_drains() -> None:
    queue = RequestQueue(max_concurrent=2, max_queue_depth=10)
    assert await queue.acquire() is True
    assert queue.position_of_current_request == 1
    assert queue.current_queued == 1

    queue.release()
    assert queue.current_queued == 0


@pytest.mark.asyncio
async def test_sequential_requests_each_enter_at_rank_one() -> None:
    """One at a time, every request is the only thing in the queue."""
    queue = RequestQueue(max_concurrent=2, max_queue_depth=10)
    for _ in range(2):
        assert await queue.acquire() is True
        assert queue.position_of_current_request == 1
        queue.release()
    assert queue.current_queued == 0


@pytest.mark.asyncio
async def test_concurrent_requests_get_distinct_ranks() -> None:
    """Every in-flight request reads its OWN rank; ranks are 1..N, no repeats."""
    queue = RequestQueue(max_concurrent=2, max_queue_depth=10)
    release_all = asyncio.Event()
    ranks: list[int] = []

    async def enter() -> None:
        assert await queue.acquire() is True
        ranks.append(queue.position_of_current_request)
        await release_all.wait()
        queue.release()

    tasks = [asyncio.create_task(enter()) for _ in range(3)]
    # Two take the slots, the third parks on the semaphore — but all three have
    # ENTERED the queue, so the queue depth is 3 before anything is released.
    assert await _wait_until(lambda: queue.current_queued == 3)
    assert queue.total_queued == 3

    release_all.set()
    await asyncio.gather(*tasks)

    assert sorted(ranks) == [1, 2, 3]
    assert len(set(ranks)) == 3
    assert queue.current_queued == 0


@pytest.mark.asyncio
async def test_a_parked_request_is_counted_and_gets_the_next_rank() -> None:
    """A request waiting for a busy slot is inside the queue, at rank 2."""
    queue = RequestQueue(max_concurrent=1, max_queue_depth=10)
    assert await queue.acquire() is True  # the holder, rank 1

    waiter: list[tuple[bool, int]] = []
    task = asyncio.create_task(_acquire_recording(queue, waiter))
    assert await _wait_until(lambda: queue.current_queued == 2)
    assert queue.current_waiting == 1
    assert waiter == [], "the waiter must still be parked while the slot is held"

    queue.release()  # hand the slot to the parked request
    assert await asyncio.wait_for(task, timeout=_WAIT_TIMEOUT_S) is True
    assert waiter == [(True, 2)]
    # This task still reads its OWN rank — no cross-talk between requests.
    assert queue.position_of_current_request == 1

    queue.release()  # the waiter's slot
    assert queue.current_queued == 0


@pytest.mark.asyncio
async def test_rejected_request_never_enters_the_queue() -> None:
    """Queue full: acquire returns False and no rank is assigned."""
    queue = RequestQueue(max_concurrent=1, max_queue_depth=0)

    assert await queue.acquire() is False
    assert queue.total_rejected == 1
    assert queue.current_queued == 0
    assert queue.position_of_current_request == 0


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_leak_queue_depth() -> None:
    """A waiter cancelled before it takes a slot leaves the queue clean."""
    queue = RequestQueue(max_concurrent=1, max_queue_depth=10)
    assert await queue.acquire() is True

    waiter = asyncio.create_task(queue.acquire())
    assert await _wait_until(lambda: queue.current_queued == 2)

    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    assert queue.current_queued == 1, "the cancelled waiter is no longer queued"
    assert queue.current_waiting == 0

    queue.release()
    assert queue.current_queued == 0


# --------------------------------------------------------------------------- #
# The header on the wire
# --------------------------------------------------------------------------- #


def test_deliberate_reports_its_queue_position() -> None:
    """A lone POST /v1/deliberate reports rank 1 — nothing else was queued."""
    client = _client(_queue_config(max_concurrent=10, max_queue_depth=100))

    response = client.post("/v1/deliberate", json={"prompt": "hello", "formation": "simple"})

    assert response.status_code == 200, response.text
    assert response.headers[QUEUE_POSITION_HEADER] == "1"


def test_chat_completions_reports_its_queue_position() -> None:
    """The OpenAI drop-in shares the queue and reports the same header."""
    client = _client(_queue_config(max_concurrent=10, max_queue_depth=100))

    response = client.post(
        "/v1/chat/completions",
        json={"model": "simple", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200, response.text
    assert response.headers[QUEUE_POSITION_HEADER] == "1"


def test_queue_full_refusal_carries_no_position() -> None:
    """A refused request never entered the queue, so it has no rank."""
    client = _client(_queue_config(max_concurrent=1, max_queue_depth=0))

    response = client.post("/v1/deliberate", json={"prompt": "hi", "formation": "simple"})

    assert response.status_code == 503, response.text
    assert "Retry-After" in response.headers
    assert QUEUE_POSITION_HEADER not in response.headers


@pytest.mark.asyncio
async def test_queued_deliberation_reports_rank_two() -> None:
    """The real wait: a deliberation parked behind a busy slot reports rank 2.

    One semaphore slot (``max_concurrent=1``) held by a live queue acquisition.
    The deliberation that enters next is genuinely queued — it cannot reach the
    engine until the slot is handed back — and its response must say so.
    """
    config = _queue_config(max_concurrent=1, max_queue_depth=100)
    gateway = FakeGateway(_responder)
    app = create_app(config=config, engine=Engine(config, gateway))
    transport = httpx.ASGITransport(app=app)
    hold = asyncio.Event()

    async def hold_slot() -> None:
        assert await app.state.request_queue.acquire() is True
        await hold.wait()

    async with httpx.AsyncClient(transport=transport, base_url="http://chimera.test") as client:
        holder = asyncio.create_task(hold_slot())
        assert await _wait_until(lambda: app.state.request_queue.current_queued == 1)

        parked = asyncio.create_task(
            client.post("/v1/deliberate", json={"prompt": "queued", "formation": "simple"})
        )
        assert await _wait_until(lambda: app.state.request_queue.current_queued == 2)
        # Genuinely parked: nothing has reached the providers yet.
        assert gateway.calls == []

        # Hand the slot back the way a real request's ``finally`` does.
        app.state.request_queue.release()
        response = await asyncio.wait_for(parked, timeout=_WAIT_TIMEOUT_S)

        assert response.status_code == 200, response.text
        assert response.headers[QUEUE_POSITION_HEADER] == "2"
        assert gateway.calls
        assert app.state.request_queue.current_queued == 0

        holder.cancel()

        # Queue empty again: the next request is rank 1.
        solo = await client.post("/v1/deliberate", json={"prompt": "solo", "formation": "simple"})
        assert solo.headers[QUEUE_POSITION_HEADER] == "1"
