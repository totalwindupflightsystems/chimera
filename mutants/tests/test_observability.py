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
