"""Tests for the guardrail blocked-model registry and dropped-worker surfacing.

Covers the dogfood P2 finding (2026-08-03): a worker on a model blocked by
OpenRouter privacy guardrails failed silently for the user and the
dispatcher kept re-selecting the same blocked model.
"""

from __future__ import annotations

import pytest

from chimera import blocked_models
from chimera.blocked_models import (
    ModelBlockRegistry,
    is_guardrail_error,
    set_shared_registry,
)


@pytest.fixture(autouse=True)
def _fresh_registry():
    """Isolate the process-wide registry per test (and restore it after)."""
    original = blocked_models.shared_registry
    set_shared_registry(ModelBlockRegistry())
    yield
    set_shared_registry(original)


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


# ---------------------------------------------------------------------------
# Registry mechanics
# ---------------------------------------------------------------------------

def test_guardrail_error_detection() -> None:
    assert is_guardrail_error(
        "404 No endpoints available matching your guardrail restrictions "
        "and data policy"
    )
    assert is_guardrail_error("blocked by PRIVACY guardrail")
    assert is_guardrail_error("No endpoints available for this model")
    assert not is_guardrail_error("connection timed out after 30s")
    assert not is_guardrail_error("429 rate limit exceeded")
    assert not is_guardrail_error("500 internal server error")


def test_guardrail_failure_blocks_model() -> None:
    reg = ModelBlockRegistry()
    assert reg.record_failure(
        "openrouter/qwen/qwen3.7-plus",
        "No endpoints available matching your guardrail restrictions",
    )
    assert reg.is_blocked("openrouter/qwen/qwen3.7-plus")
    assert "openrouter/qwen/qwen3.7-plus" in reg.blocked()


def test_block_expires_after_cooldown_without_sleeping() -> None:
    clock = _FakeClock()
    reg = ModelBlockRegistry(cooldown_s=300.0, clock=clock)
    reg.record_failure("model/a", "guardrail rejection")
    assert reg.is_blocked("model/a")
    clock.now += 299.0
    assert reg.is_blocked("model/a")
    clock.now += 2.0  # past the 300s cooldown
    assert not reg.is_blocked("model/a")
    assert "model/a" not in reg.blocked()


def test_non_guardrail_failure_does_not_block() -> None:
    reg = ModelBlockRegistry()
    assert not reg.record_failure("model/a", "timed out after 120s")
    assert not reg.record_failure("model/a", "503 service unavailable")
    assert not reg.is_blocked("model/a")
    assert reg.blocked() == set()
