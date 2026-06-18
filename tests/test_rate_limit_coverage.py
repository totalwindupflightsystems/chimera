"""Coverage-focused tests for chimera.api.rate_limit — token bucket edge
cases, RateLimiter diagnostics methods (clear, bucket_count, get_bucket,
tokens_available property), and time_until_next_token zero-case.
"""

from __future__ import annotations

import pytest

from chimera.api.rate_limit import RateLimiter, TokenBucket
from chimera.config import RateLimitConfig


class TestTokenBucketDiagnostics:
    """Cover tokens_available, time_until_next_token edge cases."""

    def test_tokens_available_starts_at_burst(self) -> None:
        bucket = TokenBucket(rate_per_minute=60, burst_size=5)
        assert bucket.tokens_available == pytest.approx(5.0, abs=0.01)

    def test_tokens_available_decreases_after_consume(self) -> None:
        bucket = TokenBucket(rate_per_minute=60, burst_size=5)
        assert bucket.consume(2) is True
        assert bucket.tokens_available == pytest.approx(3.0, abs=0.1)

    def test_tokens_available_refills_over_time(self) -> None:
        bucket = TokenBucket(rate_per_minute=60, burst_size=3)
        # Consume all
        for _ in range(3):
            assert bucket.consume() is True
        assert bucket.tokens_available < 1.0
        # Simulate time passage
        bucket._last_refill -= 2.0  # 2 seconds at 1/sec → 2 tokens
        assert bucket.tokens_available == pytest.approx(2.0, abs=0.2)

    def test_tokens_available_capped_at_burst(self) -> None:
        bucket = TokenBucket(rate_per_minute=60, burst_size=3)
        # Simulate long time passage — should cap at burst
        bucket._last_refill -= 1000.0
        assert bucket.tokens_available == pytest.approx(3.0, abs=0.01)

    def test_time_until_next_token_zero_when_available(self) -> None:
        """Cover the early return when tokens >= 1."""
        bucket = TokenBucket(rate_per_minute=60, burst_size=5)
        # Tokens available → returns 0.0
        assert bucket.time_until_next_token() == 0.0

    def test_time_until_next_token_after_exhaustion(self) -> None:
        bucket = TokenBucket(rate_per_minute=60, burst_size=1)
        assert bucket.consume() is True
        wait = bucket.time_until_next_token()
        assert 0.5 < wait < 1.5  # ~1 second at 1/sec

    def test_consume_more_than_available(self) -> None:
        """Consuming more tokens than available returns False."""
        bucket = TokenBucket(rate_per_minute=60, burst_size=2)
        assert bucket.consume(3) is False

    def test_consume_exact_burst_then_deny(self) -> None:
        bucket = TokenBucket(rate_per_minute=6, burst_size=3)
        assert bucket.consume(3) is True
        assert bucket.consume(1) is False


class TestRateLimiterDiagnostics:
    """Cover clear(), bucket_count(), get_bucket()."""

    def test_bucket_count_starts_zero(self) -> None:
        rl = RateLimiter(RateLimitConfig(enabled=True))
        assert rl.bucket_count() == 0

    def test_bucket_count_increments(self) -> None:
        rl = RateLimiter(RateLimitConfig(enabled=True, requests_per_minute=60,
                                          burst_size=5))
        rl.allow("key-a")
        assert rl.bucket_count() == 1
        rl.allow("key-b")
        assert rl.bucket_count() == 2

    def test_get_bucket_returns_bucket_or_none(self) -> None:
        rl = RateLimiter(RateLimitConfig(enabled=True, requests_per_minute=60,
                                          burst_size=5))
        assert rl.get_bucket("nonexistent") is None
        rl.allow("real-key")
        bucket = rl.get_bucket("real-key")
        assert bucket is not None
        assert isinstance(bucket, TokenBucket)

    def test_clear_removes_all_buckets(self) -> None:
        rl = RateLimiter(RateLimitConfig(enabled=True, requests_per_minute=60,
                                          burst_size=5))
        rl.allow("key-a")
        rl.allow("key-b")
        assert rl.bucket_count() == 2
        rl.clear()
        assert rl.bucket_count() == 0
        assert rl.get_bucket("key-a") is None

    def test_disabled_does_not_create_buckets(self) -> None:
        rl = RateLimiter(RateLimitConfig(enabled=False))
        rl.allow("any-key")
        rl.allow("another-key")
        assert rl.bucket_count() == 0

    def test_repeated_key_uses_same_bucket(self) -> None:
        rl = RateLimiter(RateLimitConfig(enabled=True, requests_per_minute=60,
                                          burst_size=3))
        rl.allow("key-a")
        rl.allow("key-a")
        rl.allow("key-a")
        assert rl.bucket_count() == 1  # same key, same bucket
