"""Regression tests for independent retry jitter on the production retry path."""

import asyncio
import random

import httpx
import pytest

from chimera import gateway as gateway_module
from chimera.config import ChimeraConfig
from chimera.gateway import GatewayError, LiteLLMGateway


@pytest.mark.parametrize("call_count", [2, 20])
async def test_concurrent_calls_draw_independent_retry_delays(
    config: ChimeraConfig, monkeypatch: pytest.MonkeyPatch, call_count: int
) -> None:
    config.retry.max_attempts = 2
    config.retry.base_delay_ms = 1000
    config.retry.max_delay_ms = 800  # cap before jitter, not after
    config.retry.backoff_multiplier = 2.0
    gateway = LiteLLMGateway(config)
    delays: list[float] = []
    draws = iter(0.76 + 0.48 * i / (call_count - 1) for i in range(call_count))

    def uniform(low: float, high: float) -> float:
        assert (low, high) == (0.75, 1.25)
        return next(draws)

    async def fail(_kwargs: object) -> None:
        request = httpx.Request("POST", "https://example.invalid")
        raise httpx.HTTPStatusError(
            "429 rate limited", request=request, response=httpx.Response(429, request=request)
        )

    async def record_sleep(delay: float) -> None:
        delays.append(delay)
        await asyncio.sleep(0)

    monkeypatch.setattr(random, "uniform", uniform)
    monkeypatch.setattr(gateway_module, "_litellm_acomplete", fail)
    monkeypatch.setattr(gateway_module, "_sleep_ms", record_sleep)
    results = await asyncio.gather(
        *(gateway._complete_with_retry({}, "deepseek/deepseek-chat") for _ in range(call_count)),
        return_exceptions=True,
    )
    assert all(isinstance(result, GatewayError) for result in results)
    assert len(delays) == call_count
    assert all(800 * 0.75 <= delay <= 800 * 1.25 for delay in delays)
    assert len(set(delays)) == call_count, f"retry delays are correlated: {delays}"
    ordered = sorted(delays)
    p95 = ordered[(95 * call_count + 99) // 100 - 1]
    assert p95 - ordered[0] >= 0.5 * (800 * 0.5)
