"""FastAPI REST API.

Endpoints:
* ``POST /v1/deliberate``       — full pipeline, returns answer + trace.
* ``POST /v1/chat/completions`` — OpenAI-compatible drop-in.
* ``GET  /v1/formations``       — list formation presets.
* ``GET  /v1/models``           — list models with category weights.
* ``GET  /v1/health``           — health check (healthy/degraded/unhealthy).
* ``GET  /v1/health/ready``     — readiness probe (provider connectivity).
* ``GET  /v1/health/live``      — liveness probe (process alive).

Resilience features:
* F5 – Request queue with backpressure (max_concurrent, max_queue_depth).
* F8 – Enhanced health checks with dependency verification.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel

from chimera.api.dependencies import require_api_key
from chimera.api.rate_limit import RateLimiter
from chimera.config import ChimeraConfig, load_config
from chimera.engine import Engine
from chimera.gateway import LiteLLMGateway
from chimera.observability import configure_logging

import structlog

log = structlog.get_logger("chimera.api")


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict
mutants_xǁRequestQueueǁ__init____mutmut: MutantDict = {}  # type: ignore
mutants_xǁRequestQueueǁacquire__mutmut: MutantDict = {}  # type: ignore
mutants_xǁRequestQueueǁrelease__mutmut: MutantDict = {}  # type: ignore


# --------------------------------------------------------------------------- #
# F5: Request queue / backpressure
# --------------------------------------------------------------------------- #

class RequestQueue:
    """In-memory request queue with semaphore-based concurrency limiting (F5).

    * max_concurrent: maximum simultaneously executing requests (default 10).
    * max_queue_depth: maximum waiting requests (default 100).
    * When full, returns HTTP 503 with Retry-After header.
    """

    @_mutmut_mutated(mutants_xǁRequestQueueǁ__init____mutmut)
    def __init__(self, max_concurrent: int = 10, max_queue_depth: int = 100) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_queue_depth = max_queue_depth
        self._current_waiting = 0
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = 0
        self.total_rejected: int = 0
        self.total_completed: int = 0

    def xǁRequestQueueǁ__init____mutmut_orig(self, max_concurrent: int = 10, max_queue_depth: int = 100) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_queue_depth = max_queue_depth
        self._current_waiting = 0
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = 0
        self.total_rejected: int = 0
        self.total_completed: int = 0

    def xǁRequestQueueǁ__init____mutmut_1(self, max_concurrent: int = 11, max_queue_depth: int = 100) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_queue_depth = max_queue_depth
        self._current_waiting = 0
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = 0
        self.total_rejected: int = 0
        self.total_completed: int = 0

    def xǁRequestQueueǁ__init____mutmut_2(self, max_concurrent: int = 10, max_queue_depth: int = 101) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_queue_depth = max_queue_depth
        self._current_waiting = 0
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = 0
        self.total_rejected: int = 0
        self.total_completed: int = 0

    def xǁRequestQueueǁ__init____mutmut_3(self, max_concurrent: int = 10, max_queue_depth: int = 100) -> None:
        self._semaphore = None
        self._max_queue_depth = max_queue_depth
        self._current_waiting = 0
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = 0
        self.total_rejected: int = 0
        self.total_completed: int = 0

    def xǁRequestQueueǁ__init____mutmut_4(self, max_concurrent: int = 10, max_queue_depth: int = 100) -> None:
        self._semaphore = asyncio.Semaphore(None)
        self._max_queue_depth = max_queue_depth
        self._current_waiting = 0
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = 0
        self.total_rejected: int = 0
        self.total_completed: int = 0

    def xǁRequestQueueǁ__init____mutmut_5(self, max_concurrent: int = 10, max_queue_depth: int = 100) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_queue_depth = None
        self._current_waiting = 0
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = 0
        self.total_rejected: int = 0
        self.total_completed: int = 0

    def xǁRequestQueueǁ__init____mutmut_6(self, max_concurrent: int = 10, max_queue_depth: int = 100) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_queue_depth = max_queue_depth
        self._current_waiting = None
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = 0
        self.total_rejected: int = 0
        self.total_completed: int = 0

    def xǁRequestQueueǁ__init____mutmut_7(self, max_concurrent: int = 10, max_queue_depth: int = 100) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_queue_depth = max_queue_depth
        self._current_waiting = 1
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = 0
        self.total_rejected: int = 0
        self.total_completed: int = 0

    def xǁRequestQueueǁ__init____mutmut_8(self, max_concurrent: int = 10, max_queue_depth: int = 100) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_queue_depth = max_queue_depth
        self._current_waiting = 0
        self._lock = None
        # Stats
        self.total_queued: int = 0
        self.total_rejected: int = 0
        self.total_completed: int = 0

    def xǁRequestQueueǁ__init____mutmut_9(self, max_concurrent: int = 10, max_queue_depth: int = 100) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_queue_depth = max_queue_depth
        self._current_waiting = 0
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = None
        self.total_rejected: int = 0
        self.total_completed: int = 0

    def xǁRequestQueueǁ__init____mutmut_10(self, max_concurrent: int = 10, max_queue_depth: int = 100) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_queue_depth = max_queue_depth
        self._current_waiting = 0
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = 1
        self.total_rejected: int = 0
        self.total_completed: int = 0

    def xǁRequestQueueǁ__init____mutmut_11(self, max_concurrent: int = 10, max_queue_depth: int = 100) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_queue_depth = max_queue_depth
        self._current_waiting = 0
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = 0
        self.total_rejected: int = None
        self.total_completed: int = 0

    def xǁRequestQueueǁ__init____mutmut_12(self, max_concurrent: int = 10, max_queue_depth: int = 100) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_queue_depth = max_queue_depth
        self._current_waiting = 0
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = 0
        self.total_rejected: int = 1
        self.total_completed: int = 0

    def xǁRequestQueueǁ__init____mutmut_13(self, max_concurrent: int = 10, max_queue_depth: int = 100) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_queue_depth = max_queue_depth
        self._current_waiting = 0
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = 0
        self.total_rejected: int = 0
        self.total_completed: int = None

    def xǁRequestQueueǁ__init____mutmut_14(self, max_concurrent: int = 10, max_queue_depth: int = 100) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_queue_depth = max_queue_depth
        self._current_waiting = 0
        self._lock = asyncio.Lock()
        # Stats
        self.total_queued: int = 0
        self.total_rejected: int = 0
        self.total_completed: int = 1

    @_mutmut_mutated(mutants_xǁRequestQueueǁacquire__mutmut)
    async def acquire(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected += 1
                return False
            self._current_waiting += 1
            self.total_queued += 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting -= 1

    async def xǁRequestQueueǁacquire__mutmut_orig(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected += 1
                return False
            self._current_waiting += 1
            self.total_queued += 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting -= 1

    async def xǁRequestQueueǁacquire__mutmut_1(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting > self._max_queue_depth:
                self.total_rejected += 1
                return False
            self._current_waiting += 1
            self.total_queued += 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting -= 1

    async def xǁRequestQueueǁacquire__mutmut_2(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected = 1
                return False
            self._current_waiting += 1
            self.total_queued += 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting -= 1

    async def xǁRequestQueueǁacquire__mutmut_3(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected -= 1
                return False
            self._current_waiting += 1
            self.total_queued += 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting -= 1

    async def xǁRequestQueueǁacquire__mutmut_4(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected += 2
                return False
            self._current_waiting += 1
            self.total_queued += 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting -= 1

    async def xǁRequestQueueǁacquire__mutmut_5(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected += 1
                return True
            self._current_waiting += 1
            self.total_queued += 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting -= 1

    async def xǁRequestQueueǁacquire__mutmut_6(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected += 1
                return False
            self._current_waiting = 1
            self.total_queued += 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting -= 1

    async def xǁRequestQueueǁacquire__mutmut_7(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected += 1
                return False
            self._current_waiting -= 1
            self.total_queued += 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting -= 1

    async def xǁRequestQueueǁacquire__mutmut_8(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected += 1
                return False
            self._current_waiting += 2
            self.total_queued += 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting -= 1

    async def xǁRequestQueueǁacquire__mutmut_9(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected += 1
                return False
            self._current_waiting += 1
            self.total_queued = 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting -= 1

    async def xǁRequestQueueǁacquire__mutmut_10(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected += 1
                return False
            self._current_waiting += 1
            self.total_queued -= 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting -= 1

    async def xǁRequestQueueǁacquire__mutmut_11(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected += 1
                return False
            self._current_waiting += 1
            self.total_queued += 2

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting -= 1

    async def xǁRequestQueueǁacquire__mutmut_12(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected += 1
                return False
            self._current_waiting += 1
            self.total_queued += 1

        try:
            await self._semaphore.acquire()
            return False
        finally:
            async with self._lock:
                self._current_waiting -= 1

    async def xǁRequestQueueǁacquire__mutmut_13(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected += 1
                return False
            self._current_waiting += 1
            self.total_queued += 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting = 1

    async def xǁRequestQueueǁacquire__mutmut_14(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected += 1
                return False
            self._current_waiting += 1
            self.total_queued += 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting += 1

    async def xǁRequestQueueǁacquire__mutmut_15(self) -> bool:
        """Try to acquire a slot. Returns False if queue is full (503)."""
        async with self._lock:
            if self._current_waiting >= self._max_queue_depth:
                self.total_rejected += 1
                return False
            self._current_waiting += 1
            self.total_queued += 1

        try:
            await self._semaphore.acquire()
            return True
        finally:
            async with self._lock:
                self._current_waiting -= 2

    @_mutmut_mutated(mutants_xǁRequestQueueǁrelease__mutmut)
    def release(self) -> None:
        """Release a concurrency slot."""
        self.total_completed += 1
        self._semaphore.release()

    def xǁRequestQueueǁrelease__mutmut_orig(self) -> None:
        """Release a concurrency slot."""
        self.total_completed += 1
        self._semaphore.release()

    def xǁRequestQueueǁrelease__mutmut_1(self) -> None:
        """Release a concurrency slot."""
        self.total_completed = 1
        self._semaphore.release()

    def xǁRequestQueueǁrelease__mutmut_2(self) -> None:
        """Release a concurrency slot."""
        self.total_completed -= 1
        self._semaphore.release()

    def xǁRequestQueueǁrelease__mutmut_3(self) -> None:
        """Release a concurrency slot."""
        self.total_completed += 2
        self._semaphore.release()

    @property
    def current_waiting(self) -> int:
        return self._current_waiting

    @property
    def max_queue_depth(self) -> int:
        return self._max_queue_depth

mutants_xǁRequestQueueǁ__init____mutmut['_mutmut_orig'] = RequestQueue.xǁRequestQueueǁ__init____mutmut_orig # type: ignore # mutmut generated
mutants_xǁRequestQueueǁ__init____mutmut['xǁRequestQueueǁ__init____mutmut_1'] = RequestQueue.xǁRequestQueueǁ__init____mutmut_1 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁ__init____mutmut['xǁRequestQueueǁ__init____mutmut_2'] = RequestQueue.xǁRequestQueueǁ__init____mutmut_2 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁ__init____mutmut['xǁRequestQueueǁ__init____mutmut_3'] = RequestQueue.xǁRequestQueueǁ__init____mutmut_3 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁ__init____mutmut['xǁRequestQueueǁ__init____mutmut_4'] = RequestQueue.xǁRequestQueueǁ__init____mutmut_4 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁ__init____mutmut['xǁRequestQueueǁ__init____mutmut_5'] = RequestQueue.xǁRequestQueueǁ__init____mutmut_5 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁ__init____mutmut['xǁRequestQueueǁ__init____mutmut_6'] = RequestQueue.xǁRequestQueueǁ__init____mutmut_6 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁ__init____mutmut['xǁRequestQueueǁ__init____mutmut_7'] = RequestQueue.xǁRequestQueueǁ__init____mutmut_7 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁ__init____mutmut['xǁRequestQueueǁ__init____mutmut_8'] = RequestQueue.xǁRequestQueueǁ__init____mutmut_8 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁ__init____mutmut['xǁRequestQueueǁ__init____mutmut_9'] = RequestQueue.xǁRequestQueueǁ__init____mutmut_9 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁ__init____mutmut['xǁRequestQueueǁ__init____mutmut_10'] = RequestQueue.xǁRequestQueueǁ__init____mutmut_10 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁ__init____mutmut['xǁRequestQueueǁ__init____mutmut_11'] = RequestQueue.xǁRequestQueueǁ__init____mutmut_11 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁ__init____mutmut['xǁRequestQueueǁ__init____mutmut_12'] = RequestQueue.xǁRequestQueueǁ__init____mutmut_12 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁ__init____mutmut['xǁRequestQueueǁ__init____mutmut_13'] = RequestQueue.xǁRequestQueueǁ__init____mutmut_13 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁ__init____mutmut['xǁRequestQueueǁ__init____mutmut_14'] = RequestQueue.xǁRequestQueueǁ__init____mutmut_14 # type: ignore # mutmut generated

mutants_xǁRequestQueueǁacquire__mutmut['_mutmut_orig'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_orig # type: ignore # mutmut generated
mutants_xǁRequestQueueǁacquire__mutmut['xǁRequestQueueǁacquire__mutmut_1'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_1 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁacquire__mutmut['xǁRequestQueueǁacquire__mutmut_2'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_2 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁacquire__mutmut['xǁRequestQueueǁacquire__mutmut_3'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_3 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁacquire__mutmut['xǁRequestQueueǁacquire__mutmut_4'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_4 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁacquire__mutmut['xǁRequestQueueǁacquire__mutmut_5'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_5 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁacquire__mutmut['xǁRequestQueueǁacquire__mutmut_6'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_6 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁacquire__mutmut['xǁRequestQueueǁacquire__mutmut_7'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_7 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁacquire__mutmut['xǁRequestQueueǁacquire__mutmut_8'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_8 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁacquire__mutmut['xǁRequestQueueǁacquire__mutmut_9'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_9 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁacquire__mutmut['xǁRequestQueueǁacquire__mutmut_10'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_10 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁacquire__mutmut['xǁRequestQueueǁacquire__mutmut_11'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_11 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁacquire__mutmut['xǁRequestQueueǁacquire__mutmut_12'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_12 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁacquire__mutmut['xǁRequestQueueǁacquire__mutmut_13'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_13 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁacquire__mutmut['xǁRequestQueueǁacquire__mutmut_14'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_14 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁacquire__mutmut['xǁRequestQueueǁacquire__mutmut_15'] = RequestQueue.xǁRequestQueueǁacquire__mutmut_15 # type: ignore # mutmut generated

mutants_xǁRequestQueueǁrelease__mutmut['_mutmut_orig'] = RequestQueue.xǁRequestQueueǁrelease__mutmut_orig # type: ignore # mutmut generated
mutants_xǁRequestQueueǁrelease__mutmut['xǁRequestQueueǁrelease__mutmut_1'] = RequestQueue.xǁRequestQueueǁrelease__mutmut_1 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁrelease__mutmut['xǁRequestQueueǁrelease__mutmut_2'] = RequestQueue.xǁRequestQueueǁrelease__mutmut_2 # type: ignore # mutmut generated
mutants_xǁRequestQueueǁrelease__mutmut['xǁRequestQueueǁrelease__mutmut_3'] = RequestQueue.xǁRequestQueueǁrelease__mutmut_3 # type: ignore # mutmut generated
mutants_x_create_app__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_create_app__mutmut)
def create_app(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_orig(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_1(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = None
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_2(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config and load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_3(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(None)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_4(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_5(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=None,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_6(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=None,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_7(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_8(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_9(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = None
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_10(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title=None, version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_11(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version=None, lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_12(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=None)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_13(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_14(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_15(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", )
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_16(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="XXChimeraXX", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_17(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_18(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="CHIMERA", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_19(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="XX0.1.0XX", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_20(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = None
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_21(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = None
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_22(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine and Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_23(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(None, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_24(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, None)
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_25(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_26(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, )
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_27(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(None))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_28(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = None
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(app)
    return app


def x_create_app__mutmut_29(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = None
    _register_routes(app)
    return app


def x_create_app__mutmut_30(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(None)
    _register_routes(app)
    return app


def x_create_app__mutmut_31(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``config`` / ``engine`` are injectable for tests. In production they are
    derived from ``chimera.yaml``.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)

    # F5: Create request queue
    request_queue = RequestQueue(
        max_concurrent=cfg.queue.max_concurrent,
        max_queue_depth=cfg.queue.max_queue_depth,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Store queue on app state."""
        yield

    app = FastAPI(title="Chimera", version="0.1.0", lifespan=lifespan)
    app.state.config = cfg
    app.state.engine = engine or Engine(cfg, LiteLLMGateway(cfg))
    app.state.request_queue = request_queue
    app.state.rate_limiter = RateLimiter(cfg.rate_limit)
    _register_routes(None)
    return app

mutants_x_create_app__mutmut['_mutmut_orig'] = x_create_app__mutmut_orig # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_1'] = x_create_app__mutmut_1 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_2'] = x_create_app__mutmut_2 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_3'] = x_create_app__mutmut_3 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_4'] = x_create_app__mutmut_4 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_5'] = x_create_app__mutmut_5 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_6'] = x_create_app__mutmut_6 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_7'] = x_create_app__mutmut_7 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_8'] = x_create_app__mutmut_8 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_9'] = x_create_app__mutmut_9 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_10'] = x_create_app__mutmut_10 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_11'] = x_create_app__mutmut_11 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_12'] = x_create_app__mutmut_12 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_13'] = x_create_app__mutmut_13 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_14'] = x_create_app__mutmut_14 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_15'] = x_create_app__mutmut_15 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_16'] = x_create_app__mutmut_16 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_17'] = x_create_app__mutmut_17 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_18'] = x_create_app__mutmut_18 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_19'] = x_create_app__mutmut_19 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_20'] = x_create_app__mutmut_20 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_21'] = x_create_app__mutmut_21 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_22'] = x_create_app__mutmut_22 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_23'] = x_create_app__mutmut_23 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_24'] = x_create_app__mutmut_24 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_25'] = x_create_app__mutmut_25 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_26'] = x_create_app__mutmut_26 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_27'] = x_create_app__mutmut_27 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_28'] = x_create_app__mutmut_28 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_29'] = x_create_app__mutmut_29 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_30'] = x_create_app__mutmut_30 # type: ignore # mutmut generated
mutants_x_create_app__mutmut['x_create_app__mutmut_31'] = x_create_app__mutmut_31 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut: MutantDict = {}  # type: ignore


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


@_mutmut_mutated(mutants_x__check_rate_limit__mutmut)
def _check_rate_limit(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_orig(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_1(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = None
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_2(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = None
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_3(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(None)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_4(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_5(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=None,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_6(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=None,
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_7(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers=None,
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_8(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_9(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_10(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_11(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "XXerrorXX": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_12(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "ERROR": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_13(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "XXrate_limitedXX",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_14(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "RATE_LIMITED",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_15(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "XXmessageXX": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_16(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "MESSAGE": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_17(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "XXToo many requests. Please wait before retrying.XX",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_18(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "too many requests. please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_19(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "TOO MANY REQUESTS. PLEASE WAIT BEFORE RETRYING.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_20(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"XXRetry-AfterXX": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_21(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"retry-after": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_22(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"RETRY-AFTER": str(max(1, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_23(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(None)},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_24(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(None, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_25(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, None))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_26(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_27(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, ))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_28(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(2, int(retry_after + 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_29(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(None)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_30(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after - 1)))},
        )


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def x__check_rate_limit__mutmut_31(request: Request, key: str) -> None:
    """Check rate limit for *key*; raise HTTP 429 if exhausted."""
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "message": "Too many requests. Please wait before retrying.",
            },
            headers={"Retry-After": str(max(1, int(retry_after + 2)))},
        )

mutants_x__check_rate_limit__mutmut['_mutmut_orig'] = x__check_rate_limit__mutmut_orig # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_1'] = x__check_rate_limit__mutmut_1 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_2'] = x__check_rate_limit__mutmut_2 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_3'] = x__check_rate_limit__mutmut_3 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_4'] = x__check_rate_limit__mutmut_4 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_5'] = x__check_rate_limit__mutmut_5 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_6'] = x__check_rate_limit__mutmut_6 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_7'] = x__check_rate_limit__mutmut_7 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_8'] = x__check_rate_limit__mutmut_8 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_9'] = x__check_rate_limit__mutmut_9 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_10'] = x__check_rate_limit__mutmut_10 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_11'] = x__check_rate_limit__mutmut_11 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_12'] = x__check_rate_limit__mutmut_12 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_13'] = x__check_rate_limit__mutmut_13 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_14'] = x__check_rate_limit__mutmut_14 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_15'] = x__check_rate_limit__mutmut_15 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_16'] = x__check_rate_limit__mutmut_16 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_17'] = x__check_rate_limit__mutmut_17 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_18'] = x__check_rate_limit__mutmut_18 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_19'] = x__check_rate_limit__mutmut_19 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_20'] = x__check_rate_limit__mutmut_20 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_21'] = x__check_rate_limit__mutmut_21 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_22'] = x__check_rate_limit__mutmut_22 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_23'] = x__check_rate_limit__mutmut_23 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_24'] = x__check_rate_limit__mutmut_24 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_25'] = x__check_rate_limit__mutmut_25 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_26'] = x__check_rate_limit__mutmut_26 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_27'] = x__check_rate_limit__mutmut_27 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_28'] = x__check_rate_limit__mutmut_28 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_29'] = x__check_rate_limit__mutmut_29 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_30'] = x__check_rate_limit__mutmut_30 # type: ignore # mutmut generated
mutants_x__check_rate_limit__mutmut['x__check_rate_limit__mutmut_31'] = x__check_rate_limit__mutmut_31 # type: ignore # mutmut generated


# --------------------------------------------------------------------------- #
# Request / response models
# --------------------------------------------------------------------------- #


class DeliberateRequest(BaseModel):
    prompt: str
    formation: str = "auto"
    # Request-level overrides — maximum flexibility
    allowed_models: list[str] | None = None      # Only these models allowed
    disallowed_models: list[str] | None = None    # Exclude these models
    dispatcher_model: str | None = None           # Override dispatcher
    aggregator_model: str | None = None                # Override aggregator
    worker_model: str | None = None               # Override default worker
    output_schema: dict[str, Any] | None = None   # JSON Schema for final answer
    stage_models: dict[str, str] | None = None    # Per-stage model overrides (stage_id → model)
    # Client-defined DAG (Feature 1) — disabled unless allow_custom_dag=True
    dag: dict[str, Any] | None = None             # Full DAG definition from client
    allow_custom_dag: bool = False                # Must be True to accept client DAG


class DeliberateResponse(BaseModel):
    answer: str
    trace: dict[str, Any]
    request_id: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "auto"
    messages: list[ChatMessage]
    temperature: float | None = None
    response_format: dict[str, Any] | None = None  # OpenAI-compatible structured output
    # Request-level overrides (passed as extra fields)
    allowed_models: list[str] | None = None
    disallowed_models: list[str] | None = None
    dispatcher_model: str | None = None
    aggregator_model: str | None = None
    worker_model: str | None = None
    stage_models: dict[str, str] | None = None    # Per-stage model overrides (stage_id → model)
    # Client-defined DAG (Feature 1) — disabled unless allow_custom_dag=True
    dag: dict[str, Any] | None = None             # Full DAG definition from client
    allow_custom_dag: bool = False                # Must be True to accept client DAG


class ChatChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatChoiceMessage
    finish_reason: str = "stop"


class ChatUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: ChatUsage


# --------------------------------------------------------------------------- #
# Route registration
# --------------------------------------------------------------------------- #

def _register_routes(app: FastAPI) -> None:

    # ---------------------------------------------------------------- #
    # F8: Enhanced health checks
    # ---------------------------------------------------------------- #

    @app.get("/v1/health")
    async def health(request: Request) -> dict[str, Any]:
        """Health check — returns healthy, degraded, or unhealthy.

        Verifies: config loaded, at least one provider reachable.
        Backward compatible: always returns 200 with a JSON body.
        """
        cfg: ChimeraConfig = request.app.state.config
        details: dict[str, Any] = {
            "config_loaded": True,
            "models_configured": len(cfg.models),
            "providers_configured": len(cfg.providers),
        }

        # Optional provider connectivity check
        try:
            gw = request.app.state.engine.gateway
            provider_status = await _check_providers(cfg, gw)
            details["providers"] = provider_status

            if all(p["healthy"] for p in provider_status.values()):
                return {"status": "healthy", "details": details}
            if any(p["healthy"] for p in provider_status.values()):
                return {"status": "degraded", "details": details}
            return {"status": "degraded", "details": details}
        except Exception as exc:
            log.warning("health_check_error", error=str(exc))
            # Don't fail health check — report degraded
            return {
                "status": "degraded",
                "details": {**details, "error": str(exc)[:200]},
            }

    @app.get("/v1/health/ready")
    async def readiness(request: Request) -> dict[str, Any]:
        """Readiness probe — checks provider connectivity.

        Returns 200 if at least one provider is reachable, 503 otherwise.
        """
        cfg: ChimeraConfig = request.app.state.config
        try:
            gw = request.app.state.engine.gateway
            provider_status = await _check_providers(cfg, gw)
            ready = any(p["healthy"] for p in provider_status.values())
            if ready:
                return {"status": "ready", "providers": provider_status}
            raise HTTPException(
                status_code=503,
                detail="Not ready — no providers reachable",
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Not ready: {str(exc)[:200]}",
            )

    @app.get("/v1/health/live")
    async def liveness(request: Request) -> dict[str, Any]:
        """Liveness probe — just checks the process is alive.

        Always returns 200.
        """
        cfg: ChimeraConfig = request.app.state.config
        return {
            "status": "alive",
            "uptime_models": len(cfg.models),
        }

    @app.get("/v1/formations")
    async def formations(request: Request) -> dict[str, Any]:
        cfg: ChimeraConfig = request.app.state.config
        return {
            name: preset.model_dump(exclude_none=True)
            for name, preset in cfg.formations.items()
        }

    @app.get("/v1/models")
    async def models(request: Request) -> dict[str, Any]:
        cfg: ChimeraConfig = request.app.state.config
        return {
            name: {
                "categories": entry.categories,
                "cost_tier": entry.cost_tier,
                "provider": entry.provider,
            }
            for name, entry in cfg.models.items()
        }

    @app.post("/v1/deliberate", response_model=DeliberateResponse)
    async def deliberate(
        request: Request,
        body: DeliberateRequest,
        api_key: Annotated[str, Depends(require_api_key)],
    ) -> DeliberateResponse:
        # F2: Rate limiting
        _check_rate_limit(request, api_key)

        # F5: Queue/backpressure check
        queue: RequestQueue = request.app.state.request_queue
        acquired = await queue.acquire()
        if not acquired:
            raise HTTPException(
                status_code=503,
                detail="Server busy — queue full. Retry later.",
                headers={"Retry-After": "5"},
            )

        try:
            engine: Engine = request.app.state.engine
            if body.dag is not None and not body.allow_custom_dag:
                raise HTTPException(
                    status_code=400,
                    detail="Custom DAG requires allow_custom_dag=true",
                )
            from chimera.config import DeliberationOverrides
            overrides = DeliberationOverrides(
                allowed_models=body.allowed_models,
                disallowed_models=body.disallowed_models,
                dispatcher_model=body.dispatcher_model,
                aggregator_model=body.aggregator_model,
                worker_model=body.worker_model,
                output_schema=body.output_schema,
                stage_models=body.stage_models,
            )
            try:
                result = await engine.deliberate(
                    body.prompt, body.formation, overrides=overrides,
                    dag=body.dag, allow_custom_dag=body.allow_custom_dag,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            return DeliberateResponse(
                answer=result.answer,
                trace=result.trace.model_dump(mode="json"),
                request_id=result.trace.request_id,
            )
        finally:
            queue.release()

    @app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
    async def chat_completions(
        request: Request,
        body: ChatCompletionRequest,
        api_key: Annotated[str, Depends(require_api_key)],
    ) -> ChatCompletionResponse:
        # F2: Rate limiting
        _check_rate_limit(request, api_key)

        # F5: Queue/backpressure check
        queue: RequestQueue = request.app.state.request_queue
        acquired = await queue.acquire()
        if not acquired:
            raise HTTPException(
                status_code=503,
                detail="Server busy — queue full. Retry later.",
                headers={"Retry-After": "5"},
            )

        try:
            engine: Engine = request.app.state.engine
            if body.dag is not None and not body.allow_custom_dag:
                raise HTTPException(
                    status_code=400,
                    detail="Custom DAG requires allow_custom_dag=true",
                )
            prompt = "\n".join(m.content for m in body.messages if m.role != "system")
            formation = body.model or "auto"
            from chimera.config import DeliberationOverrides
            overrides = DeliberationOverrides(
                allowed_models=body.allowed_models,
                disallowed_models=body.disallowed_models,
                dispatcher_model=body.dispatcher_model,
                aggregator_model=body.aggregator_model,
                worker_model=body.worker_model,
                stage_models=body.stage_models,
            )
            # Extract output schema from OpenAI-style response_format
            output_schema = None
            if body.response_format:
                rf = body.response_format
                if rf.get("type") == "json_schema":
                    output_schema = rf.get("json_schema", {}).get("schema")
                elif rf.get("type") == "json_object":
                    output_schema = {"type": "object"}  # generic object
            try:
                result = await engine.deliberate(
                    prompt, formation, overrides=overrides, output_schema=output_schema,
                    dag=body.dag, allow_custom_dag=body.allow_custom_dag,
                )
            except (KeyError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"Unknown model/formation: {exc}")
            trace = result.trace
            completion_tokens = trace.total_tokens - trace.dispatch.tokens_input
            return ChatCompletionResponse(
                id=f"chatcmpl-{trace.request_id}",
                created=int(time.time()),
                model=formation,
                choices=[ChatChoice(message=ChatChoiceMessage(content=result.answer))],
                usage=ChatUsage(
                    prompt_tokens=trace.dispatch.tokens_input,
                    completion_tokens=max(completion_tokens, 0),
                    total_tokens=trace.total_tokens,
                ),
            )
        finally:
            queue.release()
mutants_x__check_providers__mutmut: MutantDict = {}  # type: ignore


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

@_mutmut_mutated(mutants_x__check_providers__mutmut)
async def _check_providers(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_orig(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_1(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = None

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_2(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = None
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_3(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                None,
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_4(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_5(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_6(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider != provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_7(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is not None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_8(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = None
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_9(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "XXhealthyXX": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_10(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "HEALTHY": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_11(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": False,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_12(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "XXnoteXX": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_13(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "NOTE": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_14(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "XXno models configured for providerXX",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_15(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "NO MODELS CONFIGURED FOR PROVIDER",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_16(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                break

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_17(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    None,
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_18(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=None,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_19(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_20(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_21(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        None,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_22(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        None,
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_23(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=None,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_24(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_25(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_26(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_27(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"XXroleXX": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_28(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"ROLE": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_29(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "XXuserXX", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_30(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "USER", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_31(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "XXcontentXX": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_32(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "CONTENT": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_33(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "XXpingXX"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_34(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "PING"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_35(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=1.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_36(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=6.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_37(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = None
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_38(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "XXhealthyXX": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_39(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "HEALTHY": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_40(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": False,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_41(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "XXmodel_testedXX": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_42(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "MODEL_TESTED": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_43(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = None
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_44(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "XXhealthyXX": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_45(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "HEALTHY": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_46(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": True,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_47(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "XXerrorXX": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_48(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "ERROR": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_49(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "XXtimeoutXX",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_50(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "TIMEOUT",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_51(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = None
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_52(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "XXhealthyXX": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_53(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "HEALTHY": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_54(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": True,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_55(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "XXerrorXX": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_56(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "ERROR": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_57(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(None)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_58(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:201],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_59(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = None

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_60(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "XXhealthyXX": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_61(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "HEALTHY": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_62(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": True,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_63(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "XXerrorXX": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_64(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "ERROR": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_65(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(None)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_66(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:201],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_67(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if status:
        status["_none"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_68(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = None

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_69(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["XX_noneXX"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_70(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_NONE"] = {"healthy": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_71(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"XXhealthyXX": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_72(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"HEALTHY": True, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_73(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": False, "note": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_74(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "XXnoteXX": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_75(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "NOTE": "no providers configured"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_76(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "XXno providers configuredXX"}

    return status


# --------------------------------------------------------------------------- #
# F8: Provider connectivity check helper
# --------------------------------------------------------------------------- #

async def x__check_providers__mutmut_77(
    config: ChimeraConfig, gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Check connectivity to each configured provider.

    Returns a dict mapping provider name → {healthy: bool, error?: str}.
    Does a quick test call to determine if the provider API is reachable.
    """
    status: dict[str, dict[str, Any]] = {}

    for provider_name, provider_cfg in config.providers.items():
        try:
            # Use a simple model entry test by picking any model from that provider
            test_model = next(
                (name for name, entry in config.models.items()
                 if entry.provider == provider_name),
                None,
            )
            if test_model is None:
                status[provider_name] = {
                    "healthy": True,
                    "note": "no models configured for provider",
                }
                continue

            # Quick ping: try a trivial completion with very short timeout
            try:
                await asyncio.wait_for(
                    gateway.complete(
                        test_model,
                        [{"role": "user", "content": "ping"}],
                        temperature=0.0,
                    ),
                    timeout=5.0,
                )
                status[provider_name] = {
                    "healthy": True,
                    "model_tested": test_model,
                }
            except asyncio.TimeoutError:
                status[provider_name] = {
                    "healthy": False,
                    "error": "timeout",
                }
            except Exception as exc:
                status[provider_name] = {
                    "healthy": False,
                    "error": str(exc)[:200],
                }
        except Exception as exc:
            status[provider_name] = {
                "healthy": False,
                "error": str(exc)[:200],
            }

    # If no providers, still report something useful
    if not status:
        status["_none"] = {"healthy": True, "note": "NO PROVIDERS CONFIGURED"}

    return status

mutants_x__check_providers__mutmut['_mutmut_orig'] = x__check_providers__mutmut_orig # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_1'] = x__check_providers__mutmut_1 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_2'] = x__check_providers__mutmut_2 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_3'] = x__check_providers__mutmut_3 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_4'] = x__check_providers__mutmut_4 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_5'] = x__check_providers__mutmut_5 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_6'] = x__check_providers__mutmut_6 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_7'] = x__check_providers__mutmut_7 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_8'] = x__check_providers__mutmut_8 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_9'] = x__check_providers__mutmut_9 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_10'] = x__check_providers__mutmut_10 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_11'] = x__check_providers__mutmut_11 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_12'] = x__check_providers__mutmut_12 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_13'] = x__check_providers__mutmut_13 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_14'] = x__check_providers__mutmut_14 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_15'] = x__check_providers__mutmut_15 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_16'] = x__check_providers__mutmut_16 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_17'] = x__check_providers__mutmut_17 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_18'] = x__check_providers__mutmut_18 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_19'] = x__check_providers__mutmut_19 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_20'] = x__check_providers__mutmut_20 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_21'] = x__check_providers__mutmut_21 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_22'] = x__check_providers__mutmut_22 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_23'] = x__check_providers__mutmut_23 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_24'] = x__check_providers__mutmut_24 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_25'] = x__check_providers__mutmut_25 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_26'] = x__check_providers__mutmut_26 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_27'] = x__check_providers__mutmut_27 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_28'] = x__check_providers__mutmut_28 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_29'] = x__check_providers__mutmut_29 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_30'] = x__check_providers__mutmut_30 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_31'] = x__check_providers__mutmut_31 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_32'] = x__check_providers__mutmut_32 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_33'] = x__check_providers__mutmut_33 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_34'] = x__check_providers__mutmut_34 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_35'] = x__check_providers__mutmut_35 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_36'] = x__check_providers__mutmut_36 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_37'] = x__check_providers__mutmut_37 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_38'] = x__check_providers__mutmut_38 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_39'] = x__check_providers__mutmut_39 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_40'] = x__check_providers__mutmut_40 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_41'] = x__check_providers__mutmut_41 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_42'] = x__check_providers__mutmut_42 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_43'] = x__check_providers__mutmut_43 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_44'] = x__check_providers__mutmut_44 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_45'] = x__check_providers__mutmut_45 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_46'] = x__check_providers__mutmut_46 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_47'] = x__check_providers__mutmut_47 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_48'] = x__check_providers__mutmut_48 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_49'] = x__check_providers__mutmut_49 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_50'] = x__check_providers__mutmut_50 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_51'] = x__check_providers__mutmut_51 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_52'] = x__check_providers__mutmut_52 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_53'] = x__check_providers__mutmut_53 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_54'] = x__check_providers__mutmut_54 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_55'] = x__check_providers__mutmut_55 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_56'] = x__check_providers__mutmut_56 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_57'] = x__check_providers__mutmut_57 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_58'] = x__check_providers__mutmut_58 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_59'] = x__check_providers__mutmut_59 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_60'] = x__check_providers__mutmut_60 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_61'] = x__check_providers__mutmut_61 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_62'] = x__check_providers__mutmut_62 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_63'] = x__check_providers__mutmut_63 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_64'] = x__check_providers__mutmut_64 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_65'] = x__check_providers__mutmut_65 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_66'] = x__check_providers__mutmut_66 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_67'] = x__check_providers__mutmut_67 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_68'] = x__check_providers__mutmut_68 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_69'] = x__check_providers__mutmut_69 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_70'] = x__check_providers__mutmut_70 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_71'] = x__check_providers__mutmut_71 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_72'] = x__check_providers__mutmut_72 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_73'] = x__check_providers__mutmut_73 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_74'] = x__check_providers__mutmut_74 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_75'] = x__check_providers__mutmut_75 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_76'] = x__check_providers__mutmut_76 # type: ignore # mutmut generated
mutants_x__check_providers__mutmut['x__check_providers__mutmut_77'] = x__check_providers__mutmut_77 # type: ignore # mutmut generated
mutants_x_run__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_run__mutmut)
def run(host: str | None = None, port: int | None = None) -> None:
    """Run the API server with uvicorn (``chimera serve`` entrypoint)."""
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        create_app(cfg),
        host=host or cfg.server.host,
        port=port or cfg.server.port,
    )


def x_run__mutmut_orig(host: str | None = None, port: int | None = None) -> None:
    """Run the API server with uvicorn (``chimera serve`` entrypoint)."""
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        create_app(cfg),
        host=host or cfg.server.host,
        port=port or cfg.server.port,
    )


def x_run__mutmut_1(host: str | None = None, port: int | None = None) -> None:
    """Run the API server with uvicorn (``chimera serve`` entrypoint)."""
    import uvicorn

    cfg = None
    uvicorn.run(
        create_app(cfg),
        host=host or cfg.server.host,
        port=port or cfg.server.port,
    )


def x_run__mutmut_2(host: str | None = None, port: int | None = None) -> None:
    """Run the API server with uvicorn (``chimera serve`` entrypoint)."""
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        None,
        host=host or cfg.server.host,
        port=port or cfg.server.port,
    )


def x_run__mutmut_3(host: str | None = None, port: int | None = None) -> None:
    """Run the API server with uvicorn (``chimera serve`` entrypoint)."""
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        create_app(cfg),
        host=None,
        port=port or cfg.server.port,
    )


def x_run__mutmut_4(host: str | None = None, port: int | None = None) -> None:
    """Run the API server with uvicorn (``chimera serve`` entrypoint)."""
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        create_app(cfg),
        host=host or cfg.server.host,
        port=None,
    )


def x_run__mutmut_5(host: str | None = None, port: int | None = None) -> None:
    """Run the API server with uvicorn (``chimera serve`` entrypoint)."""
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        host=host or cfg.server.host,
        port=port or cfg.server.port,
    )


def x_run__mutmut_6(host: str | None = None, port: int | None = None) -> None:
    """Run the API server with uvicorn (``chimera serve`` entrypoint)."""
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        create_app(cfg),
        port=port or cfg.server.port,
    )


def x_run__mutmut_7(host: str | None = None, port: int | None = None) -> None:
    """Run the API server with uvicorn (``chimera serve`` entrypoint)."""
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        create_app(cfg),
        host=host or cfg.server.host,
        )


def x_run__mutmut_8(host: str | None = None, port: int | None = None) -> None:
    """Run the API server with uvicorn (``chimera serve`` entrypoint)."""
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        create_app(None),
        host=host or cfg.server.host,
        port=port or cfg.server.port,
    )


def x_run__mutmut_9(host: str | None = None, port: int | None = None) -> None:
    """Run the API server with uvicorn (``chimera serve`` entrypoint)."""
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        create_app(cfg),
        host=host and cfg.server.host,
        port=port or cfg.server.port,
    )


def x_run__mutmut_10(host: str | None = None, port: int | None = None) -> None:
    """Run the API server with uvicorn (``chimera serve`` entrypoint)."""
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        create_app(cfg),
        host=host or cfg.server.host,
        port=port and cfg.server.port,
    )

mutants_x_run__mutmut['_mutmut_orig'] = x_run__mutmut_orig # type: ignore # mutmut generated
mutants_x_run__mutmut['x_run__mutmut_1'] = x_run__mutmut_1 # type: ignore # mutmut generated
mutants_x_run__mutmut['x_run__mutmut_2'] = x_run__mutmut_2 # type: ignore # mutmut generated
mutants_x_run__mutmut['x_run__mutmut_3'] = x_run__mutmut_3 # type: ignore # mutmut generated
mutants_x_run__mutmut['x_run__mutmut_4'] = x_run__mutmut_4 # type: ignore # mutmut generated
mutants_x_run__mutmut['x_run__mutmut_5'] = x_run__mutmut_5 # type: ignore # mutmut generated
mutants_x_run__mutmut['x_run__mutmut_6'] = x_run__mutmut_6 # type: ignore # mutmut generated
mutants_x_run__mutmut['x_run__mutmut_7'] = x_run__mutmut_7 # type: ignore # mutmut generated
mutants_x_run__mutmut['x_run__mutmut_8'] = x_run__mutmut_8 # type: ignore # mutmut generated
mutants_x_run__mutmut['x_run__mutmut_9'] = x_run__mutmut_9 # type: ignore # mutmut generated
mutants_x_run__mutmut['x_run__mutmut_10'] = x_run__mutmut_10 # type: ignore # mutmut generated


__all__ = ["RequestQueue", "create_app", "run"]
