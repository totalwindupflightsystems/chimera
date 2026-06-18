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

import structlog

from chimera.config import RateLimitConfig

log = structlog.get_logger("chimera.rate_limit")


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict
mutants_xǁTokenBucketǁ__init____mutmut: MutantDict = {}  # type: ignore
mutants_xǁTokenBucketǁconsume__mutmut: MutantDict = {}  # type: ignore
mutants_xǁTokenBucketǁ_refill__mutmut: MutantDict = {}  # type: ignore
mutants_xǁTokenBucketǁtime_until_next_token__mutmut: MutantDict = {}  # type: ignore


class TokenBucket:
    """A single token bucket for one API key.

    Tokens refill at a steady rate (requests_per_minute / 60 per second).
    Burst size allows for brief spikes above the steady rate.
    """

    __slots__ = ("_tokens", "_last_refill", "_rate_per_sec", "_burst_size")

    @_mutmut_mutated(mutants_xǁTokenBucketǁ__init____mutmut)
    def __init__(self, rate_per_minute: float, burst_size: int) -> None:
        self._rate_per_sec = rate_per_minute / 60.0
        self._burst_size = burst_size
        self._tokens = float(burst_size)
        self._last_refill = time.monotonic()

    def xǁTokenBucketǁ__init____mutmut_orig(self, rate_per_minute: float, burst_size: int) -> None:
        self._rate_per_sec = rate_per_minute / 60.0
        self._burst_size = burst_size
        self._tokens = float(burst_size)
        self._last_refill = time.monotonic()

    def xǁTokenBucketǁ__init____mutmut_1(self, rate_per_minute: float, burst_size: int) -> None:
        self._rate_per_sec = None
        self._burst_size = burst_size
        self._tokens = float(burst_size)
        self._last_refill = time.monotonic()

    def xǁTokenBucketǁ__init____mutmut_2(self, rate_per_minute: float, burst_size: int) -> None:
        self._rate_per_sec = rate_per_minute * 60.0
        self._burst_size = burst_size
        self._tokens = float(burst_size)
        self._last_refill = time.monotonic()

    def xǁTokenBucketǁ__init____mutmut_3(self, rate_per_minute: float, burst_size: int) -> None:
        self._rate_per_sec = rate_per_minute / 61.0
        self._burst_size = burst_size
        self._tokens = float(burst_size)
        self._last_refill = time.monotonic()

    def xǁTokenBucketǁ__init____mutmut_4(self, rate_per_minute: float, burst_size: int) -> None:
        self._rate_per_sec = rate_per_minute / 60.0
        self._burst_size = None
        self._tokens = float(burst_size)
        self._last_refill = time.monotonic()

    def xǁTokenBucketǁ__init____mutmut_5(self, rate_per_minute: float, burst_size: int) -> None:
        self._rate_per_sec = rate_per_minute / 60.0
        self._burst_size = burst_size
        self._tokens = None
        self._last_refill = time.monotonic()

    def xǁTokenBucketǁ__init____mutmut_6(self, rate_per_minute: float, burst_size: int) -> None:
        self._rate_per_sec = rate_per_minute / 60.0
        self._burst_size = burst_size
        self._tokens = float(None)
        self._last_refill = time.monotonic()

    def xǁTokenBucketǁ__init____mutmut_7(self, rate_per_minute: float, burst_size: int) -> None:
        self._rate_per_sec = rate_per_minute / 60.0
        self._burst_size = burst_size
        self._tokens = float(burst_size)
        self._last_refill = None

    @_mutmut_mutated(mutants_xǁTokenBucketǁconsume__mutmut)
    def consume(self, tokens: int = 1) -> bool:
        """Try to consume *tokens*. Returns True if allowed, False if denied."""
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def xǁTokenBucketǁconsume__mutmut_orig(self, tokens: int = 1) -> bool:
        """Try to consume *tokens*. Returns True if allowed, False if denied."""
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def xǁTokenBucketǁconsume__mutmut_1(self, tokens: int = 2) -> bool:
        """Try to consume *tokens*. Returns True if allowed, False if denied."""
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def xǁTokenBucketǁconsume__mutmut_2(self, tokens: int = 1) -> bool:
        """Try to consume *tokens*. Returns True if allowed, False if denied."""
        self._refill()
        if self._tokens > tokens:
            self._tokens -= tokens
            return True
        return False

    def xǁTokenBucketǁconsume__mutmut_3(self, tokens: int = 1) -> bool:
        """Try to consume *tokens*. Returns True if allowed, False if denied."""
        self._refill()
        if self._tokens >= tokens:
            self._tokens = tokens
            return True
        return False

    def xǁTokenBucketǁconsume__mutmut_4(self, tokens: int = 1) -> bool:
        """Try to consume *tokens*. Returns True if allowed, False if denied."""
        self._refill()
        if self._tokens >= tokens:
            self._tokens += tokens
            return True
        return False

    def xǁTokenBucketǁconsume__mutmut_5(self, tokens: int = 1) -> bool:
        """Try to consume *tokens*. Returns True if allowed, False if denied."""
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return False
        return False

    def xǁTokenBucketǁconsume__mutmut_6(self, tokens: int = 1) -> bool:
        """Try to consume *tokens*. Returns True if allowed, False if denied."""
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return True

    @property
    def tokens_available(self) -> float:
        """Current tokens available (for diagnostics)."""
        self._refill()
        return self._tokens

    @_mutmut_mutated(mutants_xǁTokenBucketǁ_refill__mutmut)
    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = min(self._burst_size, self._tokens + elapsed * self._rate_per_sec)

    def xǁTokenBucketǁ_refill__mutmut_orig(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = min(self._burst_size, self._tokens + elapsed * self._rate_per_sec)

    def xǁTokenBucketǁ_refill__mutmut_1(self) -> None:
        now = None
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = min(self._burst_size, self._tokens + elapsed * self._rate_per_sec)

    def xǁTokenBucketǁ_refill__mutmut_2(self) -> None:
        now = time.monotonic()
        elapsed = None
        self._last_refill = now
        self._tokens = min(self._burst_size, self._tokens + elapsed * self._rate_per_sec)

    def xǁTokenBucketǁ_refill__mutmut_3(self) -> None:
        now = time.monotonic()
        elapsed = now + self._last_refill
        self._last_refill = now
        self._tokens = min(self._burst_size, self._tokens + elapsed * self._rate_per_sec)

    def xǁTokenBucketǁ_refill__mutmut_4(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = None
        self._tokens = min(self._burst_size, self._tokens + elapsed * self._rate_per_sec)

    def xǁTokenBucketǁ_refill__mutmut_5(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = None

    def xǁTokenBucketǁ_refill__mutmut_6(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = min(None, self._tokens + elapsed * self._rate_per_sec)

    def xǁTokenBucketǁ_refill__mutmut_7(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = min(self._burst_size, None)

    def xǁTokenBucketǁ_refill__mutmut_8(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = min(self._tokens + elapsed * self._rate_per_sec)

    def xǁTokenBucketǁ_refill__mutmut_9(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = min(self._burst_size, )

    def xǁTokenBucketǁ_refill__mutmut_10(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = min(self._burst_size, self._tokens - elapsed * self._rate_per_sec)

    def xǁTokenBucketǁ_refill__mutmut_11(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = min(self._burst_size, self._tokens + elapsed / self._rate_per_sec)

    @_mutmut_mutated(mutants_xǁTokenBucketǁtime_until_next_token__mutmut)
    def time_until_next_token(self) -> float:
        """Estimate seconds until at least one token is available."""
        self._refill()
        if self._tokens >= 1:
            return 0.0
        return (1.0 - self._tokens) / self._rate_per_sec

    def xǁTokenBucketǁtime_until_next_token__mutmut_orig(self) -> float:
        """Estimate seconds until at least one token is available."""
        self._refill()
        if self._tokens >= 1:
            return 0.0
        return (1.0 - self._tokens) / self._rate_per_sec

    def xǁTokenBucketǁtime_until_next_token__mutmut_1(self) -> float:
        """Estimate seconds until at least one token is available."""
        self._refill()
        if self._tokens > 1:
            return 0.0
        return (1.0 - self._tokens) / self._rate_per_sec

    def xǁTokenBucketǁtime_until_next_token__mutmut_2(self) -> float:
        """Estimate seconds until at least one token is available."""
        self._refill()
        if self._tokens >= 2:
            return 0.0
        return (1.0 - self._tokens) / self._rate_per_sec

    def xǁTokenBucketǁtime_until_next_token__mutmut_3(self) -> float:
        """Estimate seconds until at least one token is available."""
        self._refill()
        if self._tokens >= 1:
            return 1.0
        return (1.0 - self._tokens) / self._rate_per_sec

    def xǁTokenBucketǁtime_until_next_token__mutmut_4(self) -> float:
        """Estimate seconds until at least one token is available."""
        self._refill()
        if self._tokens >= 1:
            return 0.0
        return (1.0 - self._tokens) * self._rate_per_sec

    def xǁTokenBucketǁtime_until_next_token__mutmut_5(self) -> float:
        """Estimate seconds until at least one token is available."""
        self._refill()
        if self._tokens >= 1:
            return 0.0
        return (1.0 + self._tokens) / self._rate_per_sec

    def xǁTokenBucketǁtime_until_next_token__mutmut_6(self) -> float:
        """Estimate seconds until at least one token is available."""
        self._refill()
        if self._tokens >= 1:
            return 0.0
        return (2.0 - self._tokens) / self._rate_per_sec

mutants_xǁTokenBucketǁ__init____mutmut['_mutmut_orig'] = TokenBucket.xǁTokenBucketǁ__init____mutmut_orig # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ__init____mutmut['xǁTokenBucketǁ__init____mutmut_1'] = TokenBucket.xǁTokenBucketǁ__init____mutmut_1 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ__init____mutmut['xǁTokenBucketǁ__init____mutmut_2'] = TokenBucket.xǁTokenBucketǁ__init____mutmut_2 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ__init____mutmut['xǁTokenBucketǁ__init____mutmut_3'] = TokenBucket.xǁTokenBucketǁ__init____mutmut_3 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ__init____mutmut['xǁTokenBucketǁ__init____mutmut_4'] = TokenBucket.xǁTokenBucketǁ__init____mutmut_4 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ__init____mutmut['xǁTokenBucketǁ__init____mutmut_5'] = TokenBucket.xǁTokenBucketǁ__init____mutmut_5 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ__init____mutmut['xǁTokenBucketǁ__init____mutmut_6'] = TokenBucket.xǁTokenBucketǁ__init____mutmut_6 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ__init____mutmut['xǁTokenBucketǁ__init____mutmut_7'] = TokenBucket.xǁTokenBucketǁ__init____mutmut_7 # type: ignore # mutmut generated

mutants_xǁTokenBucketǁconsume__mutmut['_mutmut_orig'] = TokenBucket.xǁTokenBucketǁconsume__mutmut_orig # type: ignore # mutmut generated
mutants_xǁTokenBucketǁconsume__mutmut['xǁTokenBucketǁconsume__mutmut_1'] = TokenBucket.xǁTokenBucketǁconsume__mutmut_1 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁconsume__mutmut['xǁTokenBucketǁconsume__mutmut_2'] = TokenBucket.xǁTokenBucketǁconsume__mutmut_2 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁconsume__mutmut['xǁTokenBucketǁconsume__mutmut_3'] = TokenBucket.xǁTokenBucketǁconsume__mutmut_3 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁconsume__mutmut['xǁTokenBucketǁconsume__mutmut_4'] = TokenBucket.xǁTokenBucketǁconsume__mutmut_4 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁconsume__mutmut['xǁTokenBucketǁconsume__mutmut_5'] = TokenBucket.xǁTokenBucketǁconsume__mutmut_5 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁconsume__mutmut['xǁTokenBucketǁconsume__mutmut_6'] = TokenBucket.xǁTokenBucketǁconsume__mutmut_6 # type: ignore # mutmut generated

mutants_xǁTokenBucketǁ_refill__mutmut['_mutmut_orig'] = TokenBucket.xǁTokenBucketǁ_refill__mutmut_orig # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ_refill__mutmut['xǁTokenBucketǁ_refill__mutmut_1'] = TokenBucket.xǁTokenBucketǁ_refill__mutmut_1 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ_refill__mutmut['xǁTokenBucketǁ_refill__mutmut_2'] = TokenBucket.xǁTokenBucketǁ_refill__mutmut_2 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ_refill__mutmut['xǁTokenBucketǁ_refill__mutmut_3'] = TokenBucket.xǁTokenBucketǁ_refill__mutmut_3 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ_refill__mutmut['xǁTokenBucketǁ_refill__mutmut_4'] = TokenBucket.xǁTokenBucketǁ_refill__mutmut_4 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ_refill__mutmut['xǁTokenBucketǁ_refill__mutmut_5'] = TokenBucket.xǁTokenBucketǁ_refill__mutmut_5 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ_refill__mutmut['xǁTokenBucketǁ_refill__mutmut_6'] = TokenBucket.xǁTokenBucketǁ_refill__mutmut_6 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ_refill__mutmut['xǁTokenBucketǁ_refill__mutmut_7'] = TokenBucket.xǁTokenBucketǁ_refill__mutmut_7 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ_refill__mutmut['xǁTokenBucketǁ_refill__mutmut_8'] = TokenBucket.xǁTokenBucketǁ_refill__mutmut_8 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ_refill__mutmut['xǁTokenBucketǁ_refill__mutmut_9'] = TokenBucket.xǁTokenBucketǁ_refill__mutmut_9 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ_refill__mutmut['xǁTokenBucketǁ_refill__mutmut_10'] = TokenBucket.xǁTokenBucketǁ_refill__mutmut_10 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁ_refill__mutmut['xǁTokenBucketǁ_refill__mutmut_11'] = TokenBucket.xǁTokenBucketǁ_refill__mutmut_11 # type: ignore # mutmut generated

mutants_xǁTokenBucketǁtime_until_next_token__mutmut['_mutmut_orig'] = TokenBucket.xǁTokenBucketǁtime_until_next_token__mutmut_orig # type: ignore # mutmut generated
mutants_xǁTokenBucketǁtime_until_next_token__mutmut['xǁTokenBucketǁtime_until_next_token__mutmut_1'] = TokenBucket.xǁTokenBucketǁtime_until_next_token__mutmut_1 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁtime_until_next_token__mutmut['xǁTokenBucketǁtime_until_next_token__mutmut_2'] = TokenBucket.xǁTokenBucketǁtime_until_next_token__mutmut_2 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁtime_until_next_token__mutmut['xǁTokenBucketǁtime_until_next_token__mutmut_3'] = TokenBucket.xǁTokenBucketǁtime_until_next_token__mutmut_3 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁtime_until_next_token__mutmut['xǁTokenBucketǁtime_until_next_token__mutmut_4'] = TokenBucket.xǁTokenBucketǁtime_until_next_token__mutmut_4 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁtime_until_next_token__mutmut['xǁTokenBucketǁtime_until_next_token__mutmut_5'] = TokenBucket.xǁTokenBucketǁtime_until_next_token__mutmut_5 # type: ignore # mutmut generated
mutants_xǁTokenBucketǁtime_until_next_token__mutmut['xǁTokenBucketǁtime_until_next_token__mutmut_6'] = TokenBucket.xǁTokenBucketǁtime_until_next_token__mutmut_6 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut: MutantDict = {}  # type: ignore
mutants_xǁRateLimiterǁallow__mutmut: MutantDict = {}  # type: ignore
mutants_xǁRateLimiterǁget_bucket__mutmut: MutantDict = {}  # type: ignore


class RateLimiter:
    """In-memory rate limiter with per-key token buckets.

    When ``config.enabled`` is False, ``allow()`` always returns True.
    """

    @_mutmut_mutated(mutants_xǁRateLimiterǁ__init____mutmut)
    def __init__(self, config: RateLimitConfig) -> None:
        self.config = config
        self._buckets: MutableMapping[str, TokenBucket] = {}

    def xǁRateLimiterǁ__init____mutmut_orig(self, config: RateLimitConfig) -> None:
        self.config = config
        self._buckets: MutableMapping[str, TokenBucket] = {}

    def xǁRateLimiterǁ__init____mutmut_1(self, config: RateLimitConfig) -> None:
        self.config = None
        self._buckets: MutableMapping[str, TokenBucket] = {}

    def xǁRateLimiterǁ__init____mutmut_2(self, config: RateLimitConfig) -> None:
        self.config = config
        self._buckets: MutableMapping[str, TokenBucket] = None

    @_mutmut_mutated(mutants_xǁRateLimiterǁallow__mutmut)
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

    def xǁRateLimiterǁallow__mutmut_orig(self, key: str) -> tuple[bool, float]:
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

    def xǁRateLimiterǁallow__mutmut_1(self, key: str) -> tuple[bool, float]:
        """Check if a request is allowed for *key*.

        Returns:
            (allowed, retry_after_seconds)
        """
        if self.config.enabled:
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

    def xǁRateLimiterǁallow__mutmut_2(self, key: str) -> tuple[bool, float]:
        """Check if a request is allowed for *key*.

        Returns:
            (allowed, retry_after_seconds)
        """
        if not self.config.enabled:
            return False, 0.0

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

    def xǁRateLimiterǁallow__mutmut_3(self, key: str) -> tuple[bool, float]:
        """Check if a request is allowed for *key*.

        Returns:
            (allowed, retry_after_seconds)
        """
        if not self.config.enabled:
            return True, 1.0

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

    def xǁRateLimiterǁallow__mutmut_4(self, key: str) -> tuple[bool, float]:
        """Check if a request is allowed for *key*.

        Returns:
            (allowed, retry_after_seconds)
        """
        if not self.config.enabled:
            return True, 0.0

        bucket = None
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

    def xǁRateLimiterǁallow__mutmut_5(self, key: str) -> tuple[bool, float]:
        """Check if a request is allowed for *key*.

        Returns:
            (allowed, retry_after_seconds)
        """
        if not self.config.enabled:
            return True, 0.0

        bucket = self._buckets.get(None)
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

    def xǁRateLimiterǁallow__mutmut_6(self, key: str) -> tuple[bool, float]:
        """Check if a request is allowed for *key*.

        Returns:
            (allowed, retry_after_seconds)
        """
        if not self.config.enabled:
            return True, 0.0

        bucket = self._buckets.get(key)
        if bucket is not None:
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

    def xǁRateLimiterǁallow__mutmut_7(self, key: str) -> tuple[bool, float]:
        """Check if a request is allowed for *key*.

        Returns:
            (allowed, retry_after_seconds)
        """
        if not self.config.enabled:
            return True, 0.0

        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = None
            self._buckets[key] = bucket

        if bucket.consume(1):
            return True, 0.0

        retry_after = bucket.time_until_next_token()
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_8(self, key: str) -> tuple[bool, float]:
        """Check if a request is allowed for *key*.

        Returns:
            (allowed, retry_after_seconds)
        """
        if not self.config.enabled:
            return True, 0.0

        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(
                rate_per_minute=None,
                burst_size=self.config.burst_size,
            )
            self._buckets[key] = bucket

        if bucket.consume(1):
            return True, 0.0

        retry_after = bucket.time_until_next_token()
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_9(self, key: str) -> tuple[bool, float]:
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
                burst_size=None,
            )
            self._buckets[key] = bucket

        if bucket.consume(1):
            return True, 0.0

        retry_after = bucket.time_until_next_token()
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_10(self, key: str) -> tuple[bool, float]:
        """Check if a request is allowed for *key*.

        Returns:
            (allowed, retry_after_seconds)
        """
        if not self.config.enabled:
            return True, 0.0

        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(
                burst_size=self.config.burst_size,
            )
            self._buckets[key] = bucket

        if bucket.consume(1):
            return True, 0.0

        retry_after = bucket.time_until_next_token()
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_11(self, key: str) -> tuple[bool, float]:
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
                )
            self._buckets[key] = bucket

        if bucket.consume(1):
            return True, 0.0

        retry_after = bucket.time_until_next_token()
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_12(self, key: str) -> tuple[bool, float]:
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
            self._buckets[key] = None

        if bucket.consume(1):
            return True, 0.0

        retry_after = bucket.time_until_next_token()
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_13(self, key: str) -> tuple[bool, float]:
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

        if bucket.consume(None):
            return True, 0.0

        retry_after = bucket.time_until_next_token()
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_14(self, key: str) -> tuple[bool, float]:
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

        if bucket.consume(2):
            return True, 0.0

        retry_after = bucket.time_until_next_token()
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_15(self, key: str) -> tuple[bool, float]:
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
            return False, 0.0

        retry_after = bucket.time_until_next_token()
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_16(self, key: str) -> tuple[bool, float]:
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
            return True, 1.0

        retry_after = bucket.time_until_next_token()
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_17(self, key: str) -> tuple[bool, float]:
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

        retry_after = None
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_18(self, key: str) -> tuple[bool, float]:
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
        log.info(None, key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_19(self, key: str) -> tuple[bool, float]:
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
        log.info("rate_limit_hit", key=None, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_20(self, key: str) -> tuple[bool, float]:
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
        log.info("rate_limit_hit", key=key, retry_after_seconds=None)
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_21(self, key: str) -> tuple[bool, float]:
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
        log.info(key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_22(self, key: str) -> tuple[bool, float]:
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
        log.info("rate_limit_hit", retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_23(self, key: str) -> tuple[bool, float]:
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
        log.info("rate_limit_hit", key=key, )
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_24(self, key: str) -> tuple[bool, float]:
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
        log.info("XXrate_limit_hitXX", key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_25(self, key: str) -> tuple[bool, float]:
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
        log.info("RATE_LIMIT_HIT", key=key, retry_after_seconds=round(retry_after, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_26(self, key: str) -> tuple[bool, float]:
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
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(None, 2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_27(self, key: str) -> tuple[bool, float]:
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
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(retry_after, None))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_28(self, key: str) -> tuple[bool, float]:
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
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(2))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_29(self, key: str) -> tuple[bool, float]:
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
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(retry_after, ))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_30(self, key: str) -> tuple[bool, float]:
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
        log.info("rate_limit_hit", key=key, retry_after_seconds=round(retry_after, 3))
        return False, retry_after

    def xǁRateLimiterǁallow__mutmut_31(self, key: str) -> tuple[bool, float]:
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
        return True, retry_after

    def clear(self) -> None:
        """Remove all buckets (useful in tests)."""
        self._buckets.clear()

    def bucket_count(self) -> int:
        """Number of active buckets (for diagnostics)."""
        return len(self._buckets)

    @_mutmut_mutated(mutants_xǁRateLimiterǁget_bucket__mutmut)
    def get_bucket(self, key: str) -> TokenBucket | None:
        return self._buckets.get(key)

    def xǁRateLimiterǁget_bucket__mutmut_orig(self, key: str) -> TokenBucket | None:
        return self._buckets.get(key)

    def xǁRateLimiterǁget_bucket__mutmut_1(self, key: str) -> TokenBucket | None:
        return self._buckets.get(None)

mutants_xǁRateLimiterǁ__init____mutmut['_mutmut_orig'] = RateLimiter.xǁRateLimiterǁ__init____mutmut_orig # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut['xǁRateLimiterǁ__init____mutmut_1'] = RateLimiter.xǁRateLimiterǁ__init____mutmut_1 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁ__init____mutmut['xǁRateLimiterǁ__init____mutmut_2'] = RateLimiter.xǁRateLimiterǁ__init____mutmut_2 # type: ignore # mutmut generated

mutants_xǁRateLimiterǁallow__mutmut['_mutmut_orig'] = RateLimiter.xǁRateLimiterǁallow__mutmut_orig # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_1'] = RateLimiter.xǁRateLimiterǁallow__mutmut_1 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_2'] = RateLimiter.xǁRateLimiterǁallow__mutmut_2 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_3'] = RateLimiter.xǁRateLimiterǁallow__mutmut_3 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_4'] = RateLimiter.xǁRateLimiterǁallow__mutmut_4 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_5'] = RateLimiter.xǁRateLimiterǁallow__mutmut_5 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_6'] = RateLimiter.xǁRateLimiterǁallow__mutmut_6 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_7'] = RateLimiter.xǁRateLimiterǁallow__mutmut_7 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_8'] = RateLimiter.xǁRateLimiterǁallow__mutmut_8 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_9'] = RateLimiter.xǁRateLimiterǁallow__mutmut_9 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_10'] = RateLimiter.xǁRateLimiterǁallow__mutmut_10 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_11'] = RateLimiter.xǁRateLimiterǁallow__mutmut_11 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_12'] = RateLimiter.xǁRateLimiterǁallow__mutmut_12 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_13'] = RateLimiter.xǁRateLimiterǁallow__mutmut_13 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_14'] = RateLimiter.xǁRateLimiterǁallow__mutmut_14 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_15'] = RateLimiter.xǁRateLimiterǁallow__mutmut_15 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_16'] = RateLimiter.xǁRateLimiterǁallow__mutmut_16 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_17'] = RateLimiter.xǁRateLimiterǁallow__mutmut_17 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_18'] = RateLimiter.xǁRateLimiterǁallow__mutmut_18 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_19'] = RateLimiter.xǁRateLimiterǁallow__mutmut_19 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_20'] = RateLimiter.xǁRateLimiterǁallow__mutmut_20 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_21'] = RateLimiter.xǁRateLimiterǁallow__mutmut_21 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_22'] = RateLimiter.xǁRateLimiterǁallow__mutmut_22 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_23'] = RateLimiter.xǁRateLimiterǁallow__mutmut_23 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_24'] = RateLimiter.xǁRateLimiterǁallow__mutmut_24 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_25'] = RateLimiter.xǁRateLimiterǁallow__mutmut_25 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_26'] = RateLimiter.xǁRateLimiterǁallow__mutmut_26 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_27'] = RateLimiter.xǁRateLimiterǁallow__mutmut_27 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_28'] = RateLimiter.xǁRateLimiterǁallow__mutmut_28 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_29'] = RateLimiter.xǁRateLimiterǁallow__mutmut_29 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_30'] = RateLimiter.xǁRateLimiterǁallow__mutmut_30 # type: ignore # mutmut generated
mutants_xǁRateLimiterǁallow__mutmut['xǁRateLimiterǁallow__mutmut_31'] = RateLimiter.xǁRateLimiterǁallow__mutmut_31 # type: ignore # mutmut generated

mutants_xǁRateLimiterǁget_bucket__mutmut['_mutmut_orig'] = RateLimiter.xǁRateLimiterǁget_bucket__mutmut_orig # type: ignore # mutmut generated
mutants_xǁRateLimiterǁget_bucket__mutmut['xǁRateLimiterǁget_bucket__mutmut_1'] = RateLimiter.xǁRateLimiterǁget_bucket__mutmut_1 # type: ignore # mutmut generated
