"""Tests for structlog configuration (Fix 5: use_stdout)."""

from __future__ import annotations

import sys

import pytest

from chimera import observability as obs
from chimera.config import Observability


def test_use_stdout_defaults_to_true() -> None:
    assert Observability().use_stdout is True


def test_log_stream_is_stdout_when_enabled() -> None:
    assert obs._log_stream(Observability(use_stdout=True)) is sys.stdout


def test_log_stream_is_stderr_when_disabled() -> None:
    assert obs._log_stream(Observability(use_stdout=False)) is sys.stderr


def test_configure_logging_honors_use_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    """configure_logging must accept use_stdout without error and set the flag."""
    monkeypatch.setattr(obs, "_LOGGER_CONFIGURED", False)
    logger = obs.configure_logging(
        Observability(use_stdout=True, log_level="info", langfuse={"enabled": False})
    )
    assert obs._LOGGER_CONFIGURED is True
    assert logger is not None


def test_get_logger_auto_configures_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_logger() must configure a default logger when _LOGGER_CONFIGURED is False."""
    monkeypatch.setattr(obs, "_LOGGER_CONFIGURED", False)
    logger = obs.get_logger("test-fallback")
    assert logger is not None


def test_configure_langfuse_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When langfuse is enabled but the package is not installed, warn and skip."""
    monkeypatch.setattr(obs, "_LOGGER_CONFIGURED", True)
    monkeypatch.setattr(obs, "_LANGFUSE_CLIENT", None)

    import builtins
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "langfuse" or name.startswith("langfuse."):
            raise ImportError("No module named 'langfuse'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    cfg = Observability(
        use_stdout=True,
        log_level="info",
        langfuse={"enabled": True, "host": "http://localhost", "public_key": "pk", "secret_key": "sk"},
    )
    # Should not raise — skips with warning
    obs._configure_langfuse(cfg)
    assert obs._LANGFUSE_CLIENT is None


def test_configure_langfuse_disabled_returns_early(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When langfuse is disabled, _configure_langfuse is a no-op."""
    monkeypatch.setattr(obs, "_LANGFUSE_CLIENT", None)
    cfg = Observability(use_stdout=True, log_level="info", langfuse={"enabled": False})
    obs._configure_langfuse(cfg)
    assert obs._LANGFUSE_CLIENT is None


def test_configure_langfuse_already_initialized_returns_early(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When _LANGFUSE_CLIENT is already set, skip re-init."""
    fake = object()
    monkeypatch.setattr(obs, "_LANGFUSE_CLIENT", fake)
    cfg = Observability(use_stdout=True, log_level="info", langfuse={"enabled": True})
    obs._configure_langfuse(cfg)
    assert obs._LANGFUSE_CLIENT is fake


def test_get_langfuse_returns_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_langfuse() returns the shared _LANGFUSE_CLIENT."""
    fake = object()
    monkeypatch.setattr(obs, "_LANGFUSE_CLIENT", fake)
    assert obs.get_langfuse() is fake


def test_get_langfuse_returns_none_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_langfuse() returns None when no client is configured."""
    monkeypatch.setattr(obs, "_LANGFUSE_CLIENT", None)
    assert obs.get_langfuse() is None


def test_configure_langfuse_successful_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When langfuse is enabled and importable, initialise the client."""
    monkeypatch.setattr(obs, "_LOGGER_CONFIGURED", True)
    monkeypatch.setattr(obs, "_LANGFUSE_CLIENT", None)

    class FakeLangfuse:
        def __init__(self, host, public_key, secret_key):
            pass

    import sys

    monkeypatch.setitem(sys.modules, "langfuse", type(sys)("langfuse"))
    sys.modules["langfuse"].Langfuse = FakeLangfuse

    monkeypatch.setattr(obs, "_LANGFUSE_CLIENT", None)

    cfg = Observability(
        use_stdout=True,
        log_level="info",
        langfuse={
            "enabled": True,
            "host": "http://localhost",
            "public_key": "pk",
            "secret_key": "sk",
        },
    )
    obs._configure_langfuse(cfg)
    assert obs._LANGFUSE_CLIENT is not None
    assert isinstance(obs._LANGFUSE_CLIENT, FakeLangfuse)
