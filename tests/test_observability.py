"""Tests for structlog configuration (Fix 5: use_stdout)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import sys
from typing import Any

import pytest

from chimera import observability as obs
from chimera.config import ChimeraConfig, Observability, RetryConfig
from chimera.engine import Engine
from chimera.gateway import GatewayError, GatewayResponse
from tests.conftest import CONFIG_DICT, FakeGateway

#: The bracket-shaped level tokens the UNCONFIGURED structlog default renders
# (``[info ] key=value`` console lines on stdout). DF-CHIMERA-V2-113: these
# must never appear on stdout from the plain library path.
STDOUT_LEVEL_RE = re.compile(r"\[(info|warning|debug|error)\]")


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


# ---------------------------------------------------------------------------
# DF-CHIMERA-V2-113: the in-process library path must honour
# ``observability.log_level`` / ``observability.use_stdout``.
#
# The CLI (--quiet/--json), the API server and the MCP transport all call
# ``configure_logging`` explicitly, so their stdout contracts were safe. A
# consumer that builds ``Engine(load_config(), LiteLLMGateway(cfg))`` used to
# leave structlog UNCONFIGURED: the module-level ``structlog.get_logger``
# loggers (engine/dispatcher/aggregator/gateway) fell back to structlog's
# default PrintLogger on STDOUT and rendered bracket-level console lines
# regardless of the config's log_level/use_stdout.
# ---------------------------------------------------------------------------


@pytest.fixture
def _reset_observability_globals(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Snapshot + reset the observability process-global state per test.

    ``configure_logging`` mutates module globals AND the stdlib root logger;
    without restoration one test's stream pin would leak into the rest of the
    suite (and root handlers would accumulate, double-printing later lines).
    """
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    level_before = root.level
    for name in ("_LOGGER_CONFIGURED", "_CONFIGURED_STREAM", "_CONFIGURED_LEVEL", "_FORCED_STDERR_PIN"):
        monkeypatch.setattr(obs, name, getattr(obs, name, False), raising=False)
    obs._LOGGER_CONFIGURED = False
    if hasattr(obs, "_FORCED_STDERR_PIN"):
        obs._FORCED_STDERR_PIN = False
    yield
    # configure_logging never force=True's basicConfig, so only handlers IT
    # added are ours; drop exactly those.
    root.handlers[:] = [h for h in root.handlers if h not in handlers_before]
    root.setLevel(level_before)


def _lib_config(**observability: Any) -> ChimeraConfig:
    """A library-path config: CONFIG_DICT with observability overrides."""
    cfg = ChimeraConfig.model_validate(CONFIG_DICT)
    obs_cfg = Observability(langfuse={"enabled": False}, **observability)
    return cfg.model_copy(
        update={"observability": obs_cfg, "retry": RetryConfig(max_attempts=1, base_delay_ms=1)}
    )


def _failing_responder(model: str, messages: list[dict[str, str]], **kwargs: Any) -> GatewayResponse:
    raise GatewayError(f"provider down (DF-CHIMERA-V2-113 probe) model={model}")


def _run_failing_deliberation(cfg: ChimeraConfig) -> Engine:
    """Build the engine the README library block does and run one deliberate.

    Every stage fails (faked gateway), so ``engine_stage_failed`` warnings
    fire deterministically — enough log output to prove stream routing.
    """
    engine = Engine(cfg, FakeGateway(responder=_failing_responder))
    with contextlib.suppress(Exception):  # the run is EXPECTED to fail; logs are the test
        asyncio.run(engine.deliberate("observability stream probe", formation="simple"))
    return engine


def test_engine_library_path_use_stdout_false_routes_to_stderr(
    _reset_observability_globals: None, capfd: pytest.CaptureFixture[str]
) -> None:
    """AC#1: warning + use_stdout=false → zero log lines on stdout, all on stderr."""
    cfg = _lib_config(log_level="warning", use_stdout=False, trace_enabled=False)
    _run_failing_deliberation(cfg)
    captured = capfd.readouterr()
    assert not STDOUT_LEVEL_RE.search(captured.out), f"stdout leaked log lines: {captured.out!r}"
    assert "engine_stage_failed" in captured.err, f"no log output routed to stderr: {captured.err!r}"
    assert "engine_stage_failed" not in captured.out


def test_engine_library_path_use_stdout_true_routes_to_stdout(
    _reset_observability_globals: None, capfd: pytest.CaptureFixture[str]
) -> None:
    """AC#2: use_stdout=true puts the lines on stdout again (field honoured, not hard-wired)."""
    cfg = _lib_config(log_level="warning", use_stdout=True, trace_enabled=False)
    _run_failing_deliberation(cfg)
    captured = capfd.readouterr()
    assert "engine_stage_failed" in captured.out, f"no log output on stdout: {captured.out!r}"
    assert "engine_stage_failed" not in captured.err, f"log lines leaked to stderr: {captured.err!r}"


def test_engine_library_path_honors_log_level_warning(
    _reset_observability_globals: None, capfd: pytest.CaptureFixture[str]
) -> None:
    """log_level=warning filters info/debug emissions on the library path."""
    cfg = _lib_config(log_level="warning", use_stdout=False, trace_enabled=False)
    Engine(cfg, FakeGateway())  # applies config.observability as a side effect of construction
    from chimera.engine import log as engine_log

    engine_log.info("level_filter_probe_info")
    engine_log.warning("level_filter_probe_warning")
    captured = capfd.readouterr()
    assert "level_filter_probe_info" not in captured.out
    assert "level_filter_probe_info" not in captured.err
    assert "level_filter_probe_warning" in captured.err


def test_engine_apply_is_idempotent_no_double_print(
    _reset_observability_globals: None, capfd: pytest.CaptureFixture[str]
) -> None:
    """Applying config.observability twice must not duplicate handlers/lines."""
    cfg = _lib_config(log_level="warning", use_stdout=False, trace_enabled=False)
    Engine(cfg, FakeGateway())
    handlers_after_first = len(logging.getLogger().handlers)
    Engine(cfg, FakeGateway())
    assert len(logging.getLogger().handlers) == handlers_after_first
    from chimera.engine import log as engine_log

    engine_log.warning("idempotency_probe_once_only")
    captured = capfd.readouterr()
    assert captured.err.count("idempotency_probe_once_only") == 1, captured.err


def test_engine_apply_respects_active_force_stderr_pin(
    _reset_observability_globals: None,
) -> None:
    """A CLI/MCP force_stderr pin wins over the config: stderr stays stderr.

    This is the structural guarantee behind the byte-for-byte ``--quiet``/
    ``--json`` stdout contracts: Engine construction after ``cli._load_cfg``
    (or the MCP stdio pin) must NOT re-pin the stream to stdout even when the
    config says ``use_stdout: true``.
    """
    obs.configure_logging(Observability(use_stdout=False), force_stderr=True)
    assert obs._FORCED_STDERR_PIN is True
    cfg = _lib_config(log_level="info", use_stdout=True, trace_enabled=False)
    Engine(cfg, FakeGateway())
    assert obs._CONFIGURED_STREAM is sys.stderr
    assert obs._FORCED_STDERR_PIN is True
