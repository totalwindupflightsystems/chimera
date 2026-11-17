"""CHIMERA-V2-REVIEW-07: drain LiteLLM callbacks before their loop closes."""

from __future__ import annotations

import asyncio
import warnings

import pytest
from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER


def test_runner_teardown_awaits_queued_logging_callback() -> None:
    worker = GLOBAL_LOGGING_WORKER
    completed: list[str] = []

    async def callback() -> None:
        await asyncio.sleep(0)
        completed.append("queued")

    async def enqueue() -> None:
        worker.ensure_initialized_and_enqueue(callback())
        # Return without giving the worker a turn: Runner's normal blanket
        # cancellation can cancel it before _worker_loop's cleanup even starts.
        assert worker._queue.qsize() == 1

    asyncio.run(enqueue())
    assert completed == ["queued"]
    assert worker._queue.empty()
    assert worker._worker_task is None
    assert not worker._running_tasks


def test_runner_teardown_waits_for_in_flight_logging_callback() -> None:
    worker = GLOBAL_LOGGING_WORKER
    completed: list[str] = []

    async def callback(started: asyncio.Event) -> None:
        started.set()
        await asyncio.sleep(0.01)
        completed.append("in-flight")

    async def enqueue() -> None:
        started = asyncio.Event()
        worker.ensure_initialized_and_enqueue(callback(started))
        await started.wait()
        # queue.empty() alone would miss this callback; flush() uses join().
        assert worker._queue.empty()
        assert worker._running_tasks

    asyncio.run(enqueue())
    assert completed == ["in-flight"]
    assert worker._worker_task is None
    assert not worker._running_tasks


def test_logging_worker_restarts_on_successive_test_loops() -> None:
    worker = GLOBAL_LOGGING_WORKER
    completed: list[int] = []

    async def callback(index: int) -> None:
        completed.append(index)

    async def enqueue(index: int) -> None:
        worker.ensure_initialized_and_enqueue(callback(index))

    for index in range(2):
        asyncio.run(enqueue(index))
        assert completed == list(range(index + 1))
        assert worker._worker_task is None


def test_unrelated_runtime_warning_remains_visible() -> None:
    # Do not install an "always" override: exercise the suite's actual filters.
    with warnings.catch_warnings(record=True) as caught:
        warnings.warn("unrelated lifecycle regression", RuntimeWarning, stacklevel=1)
    assert len(caught) == 1
    assert caught[0].category is RuntimeWarning
    assert str(caught[0].message) == "unrelated lifecycle regression"


def test_unrelated_runtime_warning_can_still_be_an_error() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        with pytest.raises(RuntimeWarning, match="unrelated lifecycle regression"):
            warnings.warn("unrelated lifecycle regression", RuntimeWarning, stacklevel=1)
