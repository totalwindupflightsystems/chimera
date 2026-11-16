"""Code under review — a realistic ~35-line module with ONE deliberate, findable
logic bug (a stale-cache invalidation hole) plus a lesser null-handling smell.

A real user would hand the panel a file like this and ask "what is wrong with
this?" — the value question is whether the multi-model panel actually finds the
planted defect, not whether the process exits 0.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class Entry:
    key: str
    value: float
    expires_at: float


class TTLCache:
    """Small TTL cache with per-key expiry and a capacity bound."""

    def __init__(self, capacity: int = 128, ttl_s: float = 60.0) -> None:
        self.capacity = capacity
        self.ttl_s = ttl_s
        self._data: dict[str, Entry] = {}

    def _now(self) -> float:
        return time.monotonic()

    def get(self, key: str, default: float | None = None) -> float | None:
        entry = self._data.get(key)
        if entry is None:
            return default
        if entry.expires_at <= self._now():
            del self._data[key]
            return default
        return entry.value

    def set(self, key: str, value: float) -> None:
        if len(self._data) >= self.capacity:
            self._evict_one()
        self._data[key] = Entry(key=key, value=value, expires_at=self._now() + self.ttl_s)

    def invalidate(self, key: str) -> None:
        # BUG: pops the expiry bookkeeping but leaves the entry readable, so
        # invalidate() appears to work and get() still serves the stale value
        # until the TTL elapses on its own.
        self._data.get(key, Entry(key=key, value=0.0, expires_at=0.0))

    def _evict_one(self) -> None:
        oldest = min(self._data.values(), key=lambda e: e.expires_at)
        del self._data[oldest.key]

    def stats(self) -> dict[str, int]:
        return {"size": len(self._data), "capacity": self.capacity}
