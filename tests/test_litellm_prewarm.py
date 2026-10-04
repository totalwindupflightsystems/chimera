"""CHIMERA-V2-REVIEW-04 — LiteLLM pre-warm at API-server startup.

The first ``POST /v1/deliberate`` on a cold process pays litellm's one-time
initialization inside the dispatch stage (measured ~2.6s against an instant
mock provider).  The fix fires the same one-time work in the background at
startup: ``chimera.api.server``'s lifespan calls
:func:`chimera.gateway.prewarm_litellm_background`, gated by
``server.litellm_prewarm`` (default True).

These tests are fully offline and never import the real ``litellm``: they
inject fakes through the same seams the production code reads (the injectable
``litellm_module`` / ``mock_completion`` parameters and a monkeypatched
``chimera.api.server.prewarm_litellm_background``).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from chimera import gateway
from chimera.api.server import create_app
from chimera.config import ChimeraConfig


class _FakeLiteLLM:
    """A fake litellm module: records the warm-up completion call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def acompletion(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"choices": [{"message": {"content": "ok"}}]}  # non-awaitable, accepted


class _FailingLiteLLM:
    """A fake litellm module whose acompletion raises."""

    def acompletion(self, **kwargs: Any) -> Any:
        raise RuntimeError("provider exploded")

    def __getattr__(self, name: str) -> Any:
        # ensure_litellm_quiet sets attributes on the module; accept them.
        raise AttributeError(name)


def _set_quiet_attrs(module: Any) -> None:
    """Mirror ensure_litellm_quiet's writes on a fake module."""
    module.suppress_debug_info = True
    module.set_verbose = False


# --------------------------------------------------------------------------- #
# prewarm_litellm — the warm-up trigger itself
# --------------------------------------------------------------------------- #


async def test_prewarm_calls_mock_completion_on_injected_module() -> None:
    fake = _FakeLiteLLM()
    ok = await gateway.prewarm_litellm(fake)
    assert ok is True
    assert len(fake.calls) == 1
    kwargs = fake.calls[0]
    # The trigger must be an instant mock completion: no network shape.
    assert kwargs["mock_response"] == "ok"
    assert "/" in kwargs["model"]  # a provider-prefixed model string
    assert kwargs["num_retries"] == 0


async def test_prewarm_swallows_module_failure_and_returns_false() -> None:
    ok = await gateway.prewarm_litellm(_FailingLiteLLM())
    assert ok is False  # never raises into the caller


async def test_prewarm_awaits_async_acompletion() -> None:
    class _AsyncFake:
        def __init__(self) -> None:
            self.awaited = 0

        async def acompletion(self, **kwargs: Any) -> dict[str, Any]:
            self.awaited += 1
            await asyncio.sleep(0)
            return {"choices": [{"message": {"content": "ok"}}]}

    fake = _AsyncFake()
    ok = await gateway.prewarm_litellm(fake)
    assert ok is True
    assert fake.awaited == 1


# --------------------------------------------------------------------------- #
# prewarm_litellm_background — scheduling on the running loop
# --------------------------------------------------------------------------- #


async def test_background_returns_task_and_runs_mock_completion() -> None:
    fake = _FakeLiteLLM()
    task = gateway.prewarm_litellm_background(fake)
    assert task is not None
    assert await asyncio.wait_for(task, timeout=5) is True
    assert len(fake.calls) == 1


async def test_background_accepts_mock_completion_shim() -> None:
    ran = 0

    async def shim() -> None:
        nonlocal ran
        ran += 1

    task = gateway.prewarm_litellm_background(mock_completion=shim)
    assert task is not None
    await task
    assert ran == 1  # real litellm module was never touched


async def test_background_returns_none_without_running_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gateway.asyncio, "get_running_loop", _raise_no_loop, raising=True)
    assert gateway.prewarm_litellm_background(_FakeLiteLLM()) is None


def _raise_no_loop() -> Any:
    raise RuntimeError("no running loop")


# --------------------------------------------------------------------------- #
# The startup hook — create_app's lifespan fires (or skips) the warm-up
# --------------------------------------------------------------------------- #


def _install_prewarm_recorder(
    monkeypatch: pytest.MonkeyPatch,
) -> list[asyncio.Task[bool] | None]:
    """Replace the server's prewarm entry point with a recording fake.

    Returns the list the fake appends its return value to (one entry per
    lifespan entry).  The fake itself schedules nothing.
    """
    recorded: list[asyncio.Task[bool] | None] = []

    def fake_background(*args: Any, **kwargs: Any) -> None:
        recorded.append(None)
        return None

    monkeypatch.setattr("chimera.api.server.prewarm_litellm_background", fake_background)
    return recorded


def test_startup_fires_prewarm_when_enabled(
    config: ChimeraConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lifespan schedules the background warm-up (default flag = ON)."""
    recorded = _install_prewarm_recorder(monkeypatch)
    app = create_app(config=config)
    with _open_client(app):
        pass
    assert len(recorded) == 1


def test_startup_skips_prewarm_when_disabled(
    config: ChimeraConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``server.litellm_prewarm=False`` must not schedule anything."""
    recorded = _install_prewarm_recorder(monkeypatch)
    disabled = config.model_copy(
        update={"server": config.server.model_copy(update={"litellm_prewarm": False})}
    )
    app = create_app(config=disabled)
    with _open_client(app):
        pass
    assert recorded == []


def test_config_default_is_on() -> None:
    from chimera.config import ServerConfig

    assert ServerConfig().litellm_prewarm is True


def test_flag_is_documented_with_task_id() -> None:
    """The field docstring names this task id (brief requirement 2).

    Read from source: this repo's pydantic config does not enable
    ``use_attribute_docstrings``, so attribute docstrings never reach
    ``model_fields[...].description`` (verified: even the documented
    ``health_probe_grace_s`` field carries an empty description).
    """
    import inspect

    from chimera.config import ServerConfig

    src = inspect.getsource(ServerConfig)
    assert "litellm_prewarm: bool = True" in src
    assert "CHIMERA-V2-REVIEW-04" in src


def _open_client(app: Any) -> Any:
    from fastapi.testclient import TestClient

    return TestClient(app)


# --------------------------------------------------------------------------- #
# Behavioural sanity — the REAL litellm module (already in the dev venv),
# proving the default-path warm-up genuinely completes.  Skips when litellm
# is absent so collection never depends on the heavy import.
# --------------------------------------------------------------------------- #


def test_real_litellm_prewarm_completes_offline() -> None:
    litellm = pytest.importorskip("litellm")
    ok = asyncio.run(gateway.prewarm_litellm(litellm))
    assert ok is True
