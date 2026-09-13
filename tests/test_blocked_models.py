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
    set_shared_registry(ModelBlockRegistry(state_path=None))
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
    reg = ModelBlockRegistry(state_path=None)
    assert reg.record_failure(
        "openrouter/qwen/qwen3.7-plus",
        "No endpoints available matching your guardrail restrictions",
    )
    assert reg.is_blocked("openrouter/qwen/qwen3.7-plus")
    assert "openrouter/qwen/qwen3.7-plus" in reg.blocked()


def test_block_expires_after_cooldown_without_sleeping() -> None:
    clock = _FakeClock()
    reg = ModelBlockRegistry(cooldown_s=300.0, clock=clock, state_path=None)
    reg.record_failure("model/a", "guardrail rejection")
    assert reg.is_blocked("model/a")
    clock.now += 299.0
    assert reg.is_blocked("model/a")
    clock.now += 2.0  # past the 300s cooldown
    assert not reg.is_blocked("model/a")
    assert "model/a" not in reg.blocked()


def test_non_guardrail_failure_does_not_block() -> None:
    reg = ModelBlockRegistry(state_path=None)
    assert not reg.record_failure("model/a", "timed out after 120s")
    assert not reg.record_failure("model/a", "503 service unavailable")
    assert not reg.is_blocked("model/a")
    assert reg.blocked() == set()


# ---------------------------------------------------------------------------
# Persistence across restarts (DF-CHIMERA-V2-1)
# ---------------------------------------------------------------------------

_GUARDRAIL_ERR = "404 No endpoints available matching your guardrail restrictions"


def _read_state(path) -> dict:  # type: ignore[no-untyped-def]
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def test_record_failure_persists_block_to_disk(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import time

    path = tmp_path / "blocked.json"
    reg = ModelBlockRegistry(state_path=path)
    assert reg.record_failure("openrouter/qwen/qwen3.7-plus", _GUARDRAIL_ERR)
    data = _read_state(path)
    entries = data["blocked_until_epoch"]
    assert set(entries) == {"openrouter/qwen/qwen3.7-plus"}
    # Persisted as a wall-clock expiry ~cooldown seconds into the future.
    epoch = entries["openrouter/qwen/qwen3.7-plus"]
    assert epoch > time.time() + reg.cooldown_s - 60


def test_block_survives_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A new registry instance on the same path still blocks the model —
    no provider call needed, no 300s-only self-heal."""
    path = tmp_path / "blocked.json"
    ModelBlockRegistry(state_path=path).record_failure("model/a", _GUARDRAIL_ERR)
    # Simulate a fresh process: brand-new registry, same state file.
    reg2 = ModelBlockRegistry(state_path=path)
    assert reg2.is_blocked("model/a")
    assert "model/a" in reg2.blocked()


def test_block_survives_restart_with_different_clock_base(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Persisted timestamps are wall-clock: a fresh process whose monotonic
    clock has a completely different base still honors the block."""
    path = tmp_path / "blocked.json"
    ModelBlockRegistry(state_path=path, clock=_FakeClock(1000.0)).record_failure(
        "model/a", _GUARDRAIL_ERR
    )
    reg2 = ModelBlockRegistry(state_path=path, clock=_FakeClock(0.0))
    assert reg2.is_blocked("model/a")


def test_default_cooldown_is_long_lived() -> None:
    """Guardrail blocks must not self-heal after the old 300s window."""
    from chimera.blocked_models import DEFAULT_BLOCK_COOLDOWN_S

    assert DEFAULT_BLOCK_COOLDOWN_S >= 24.0 * 3600.0


def test_corrupt_state_file_starts_empty(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "blocked.json"
    path.write_text("{ not json !!", encoding="utf-8")
    reg = ModelBlockRegistry(state_path=path)  # must not raise
    assert reg.blocked() == set()
    # And the registry still works (and overwrites the corrupt file).
    assert reg.record_failure("model/a", _GUARDRAIL_ERR)
    assert ModelBlockRegistry(state_path=path).is_blocked("model/a")


def test_missing_state_file_starts_empty(tmp_path) -> None:  # type: ignore[no-untyped-def]
    reg = ModelBlockRegistry(state_path=tmp_path / "nope" / "blocked.json")
    assert reg.blocked() == set()


def test_expired_entries_pruned_on_load(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json
    import time

    path = tmp_path / "blocked.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "blocked_until_epoch": {
                    "model/expired": time.time() - 10.0,
                    "model/live": time.time() + 3600.0,
                },
            }
        ),
        encoding="utf-8",
    )
    reg = ModelBlockRegistry(state_path=path)
    assert not reg.is_blocked("model/expired")
    assert reg.is_blocked("model/live")
    assert reg.blocked() == {"model/live"}


def test_non_guardrail_failure_writes_no_state(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "blocked.json"
    reg = ModelBlockRegistry(state_path=path)
    assert not reg.record_failure("model/a", "timed out after 120s")
    assert not reg.record_failure("model/a", "500 internal server error")
    assert not reg.record_failure("model/a", "401 unauthorized")
    assert not path.exists()


def test_persistence_disabled_with_none_path() -> None:
    reg = ModelBlockRegistry(state_path=None)
    assert reg.record_failure("model/a", _GUARDRAIL_ERR)
    assert reg._state_path is None


# ---------------------------------------------------------------------------
# Selector / dispatcher exclusion of persisted blocks (zero provider calls)
# ---------------------------------------------------------------------------


class _FakeEntry:
    """Minimal model entry for selector tests (mirrors test_selector)."""

    def __init__(self, categories: dict[str, float]) -> None:
        self.categories = categories
        self.enabled = True


def test_selector_excludes_persisted_block_after_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from chimera.selector import CategorySelector

    path = tmp_path / "blocked.json"
    ModelBlockRegistry(state_path=path).record_failure(
        "anthropic/claude-sonnet-4", _GUARDRAIL_ERR
    )
    # Fresh process: new registry instance reloaded from disk.
    set_shared_registry(ModelBlockRegistry(state_path=path))
    models = {
        "anthropic/claude-sonnet-4": _FakeEntry(
            {"technology_code/code_generation/python": 90}
        ),
        "deepseek/deepseek-v4-flash": _FakeEntry(
            {"technology_code/code_generation/python": 88}
        ),
    }
    sel = CategorySelector(models)
    scores = sel.score("Write Python code")
    assert "anthropic/claude-sonnet-4" not in scores
    assert "deepseek/deepseek-v4-flash" in scores
    assert "anthropic/claude-sonnet-4" not in sel.select("Write Python code")


def test_dispatcher_catalog_excludes_persisted_block_after_restart(
    tmp_path, config
) -> None:  # type: ignore[no-untyped-def]
    from chimera.dispatcher import build_dispatcher_prompt

    path = tmp_path / "blocked.json"
    ModelBlockRegistry(state_path=path).record_failure(
        "openrouter/qwen/qwen3-coder", _GUARDRAIL_ERR
    )
    # Fresh process: new registry instance reloaded from disk — the catalog
    # exclusion must happen without any provider call being burned.
    set_shared_registry(ModelBlockRegistry(state_path=path))
    system = build_dispatcher_prompt("task", config)[0]["content"]
    assert "openrouter/qwen/qwen3-coder" not in system
    # Healthy models remain visible to the dispatcher.
    assert "deepseek/deepseek-chat" in system
