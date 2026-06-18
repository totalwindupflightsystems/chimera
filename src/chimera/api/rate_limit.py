"""In-memory token-bucket rate limiter for the REST API.

Per-API-key rate limiting using a simple token bucket algorithm.
No external dependencies (no Redis). Buckets are stored in a dict
keyed by the API key string.

Configuration comes from ``chimera.yaml``:

.. code-block:: yaml

    rate_limit:
      enabled: true
      requests_per_minute: 60
      burst_size: 10
"""

from __future__ import annotations

import time
from collections.abc import MutableMapping
from typing import Any

import structlog

from chimera.config import RateLimitConfig

log = structlog.get_logger("chimera.rate_limit")


class TokenBucket:
    """A single token bucket for one API key.

    Tokens refill at a steady rate (requests_per_minute / 60 per second).
    Burst size allows for brief spikes above the steady rate.
    """

    __slots__ = ("_tokens", "_last_refill", "_rate_per_sec", "_burst_size")

    def __init__(self, rate_per_minute: float, burst_size: int) -> None:
        self._rate_per_sec = rate_per_minute / 60.0
        self._burst_size = burst_size
        self._tokens = float(burst_size)
        self._last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume *tokens*. Returns True if allowed, False if denied."""
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    @property
    def tokens_available(self) -> float:
        """Current tokens available (for diagnostics)."""
        self._refill()
        return self._tokens

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = min(self._burst_size, self._tokens + elapsed * self._rate_per_sec)

    def time_until_next_token(self) -> float:
        """Estimate seconds until at least one token is available."""
        self._refill()
        if self._tokens >= 1:
            return 0.0
        return (1.0 - self._tokens) / self._rate_per_sec


class RateLimiter:
    """In-memory rate limiter with per-key token buckets.

    When ``config.enabled`` is False, ``allow()`` always returns True.
    """

    def __init__(self, config: RateLimitConfig) -> None:
        self.config = config
        self._buckets: MutableMapping[str, TokenBucket] = {}

    def allow(self, key: str) -> tuple[bool, float]:
        """Check if a request is allowed for *key*.

        Returns:
            (allowed, retry_after_seconds)
        """
        if not self.config.enabled:
            return True, 0.0

        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(
                rate_per_minute=self.config.requests_per_minute,
                burst_size=self.config.burst_size,
            )
            self._buckets[key] = bucket

        if bucket.consume(1):
            return True, 0.0

        retry_after = bucket.time_until_next_token()
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def clear(self) -> None:
        """Remove all buckets (useful in tests)."""
        self._buckets.clear()

    def bucket_count(self) -> int:
        """Number of active buckets (for diagnostics)."""
        return len(self._buckets)

    def get_bucket(self, key: str) -> TokenBucket | None:
        return self._buckets.get(key)
