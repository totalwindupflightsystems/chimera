"""Structured logging (structlog) and optional Langfuse tracing.

structlog emits JSON to stderr by default, or to stdout when
``observability.use_stdout`` is true (the default, since Chimera is a CLI tool,
not a daemon). Langfuse is enabled only when configured and the ``langfuse``
package is importable.

``configure_logging(..., force_stderr=True)`` pins every log sink (structlog
AND stdlib ``logging``) to stderr regardless of ``obs.use_stdout`` — the MCP
stdio transport uses this (DF-CHIMERA-0906-2) so provider-discovery and SDK
log lines can never corrupt the JSON-RPC stream on stdout.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, TextIO

import structlog

from chimera.config import Observability

_LOGGER_CONFIGURED = False
#: Last stream/level applied by configure_logging — the once-guard is keyed on
#: these so a forced re-pin (MCP → stderr) still re-applies structlog while
#: identical re-applies stay cheap.
_CONFIGURED_STREAM: TextIO | None = None
_CONFIGURED_LEVEL: int | None = None
#: True while the process's logging is force-pinned to stderr by a
#: ``configure_logging(..., force_stderr=True)`` caller (CLI ``--quiet``/
#: ``--json`` via ``cli._load_cfg``, MCP stdio transport). Cleared by the next
#: non-forced configure. ``apply_config_observability`` (the Engine/library
#: path) defers to this pin so a config ``use_stdout: true`` flip can never
#: re-corrupt a stdout contract that another surface already pinned away
#: (DF-CHIMERA-V2-3 / DF-CHIMERA-0906-2).
_FORCED_STDERR_PIN = False
_LANGFUSE_CLIENT: Any = None


def _log_stream(obs: Observability) -> TextIO:
    """Return the stream structlog/basicConfig should write to."""
    return sys.stdout if obs.use_stdout else sys.stderr


def configure_logging(obs: Observability, *, force_stderr: bool = False) -> structlog.stdlib.BoundLogger:
    """Configure structlog (once per stream/level) and return a bound logger.

    ``force_stderr`` pins every log sink (structlog and stdlib ``logging``)
    to stderr regardless of ``obs.use_stdout``. The MCP stdio transport calls
    with ``force_stderr=True`` (DF-CHIMERA-0906-2) so no log line can reach
    stdout ahead of a JSON-RPC response — even when the user's chimera.yaml
    says ``observability.use_stdout: true``. CLI/API callers never pass
    ``force_stderr`` and keep the configured (stdout-by-default) behavior.

    The once-guard is keyed on the last-applied ``(stream, level)``: identical
    re-applies are skipped, but a forced re-pin to a different stream (MCP
    stderr after a CLI/API stdout configure) still re-applies structlog's
    configuration so earlier-created module loggers rebind to the new stream
    on their next use.
    """
    global _LOGGER_CONFIGURED, _CONFIGURED_STREAM, _CONFIGURED_LEVEL, _FORCED_STDERR_PIN
    level = getattr(logging, obs.log_level.upper(), logging.INFO)
    stream: TextIO = sys.stderr if force_stderr else _log_stream(obs)
    # Record the caller's pin intent even when the once-guard below skips the
    # re-apply: apply_config_observability consults this later (Engine
    # construction after a CLI/MCP pin must keep stderr).
    _FORCED_STDERR_PIN = force_stderr

    if not (_LOGGER_CONFIGURED and _CONFIGURED_STREAM is stream and level == _CONFIGURED_LEVEL):
        logging.basicConfig(
            format="%(message)s",
            stream=stream,
            level=level,
        )
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(level),
            logger_factory=structlog.PrintLoggerFactory(file=stream),
            # DF-CHIMERA-V2-34: NOT cached on first use. The docstring above
            # promises that "earlier-created module loggers rebind to the new
            # stream on their next use" — with caching ON they only bind ONCE,
            # so a module-level proxy materialised while another in-process
            # caller had logging on stdout (``api.server.create_app`` calls
            # ``configure_logging(cfg.observability)`` with the default
            # ``use_stdout: true``) keeps that sink forever and its records land
            # on the machine-mode stdout contract after the CLI's
            # ``force_stderr=True`` re-pin — corrupting ``--json`` (a structlog
            # line ahead of the JSON document) in exactly the degraded paths
            # this repo warns about. Resolving per emission costs one factory
            # call per log record and makes the pin authoritative; the same
            # remedy is applied per-emission in ``config._log_warning``.
            cache_logger_on_first_use=False,
        )
        _LOGGER_CONFIGURED = True
        _CONFIGURED_STREAM = stream
        _CONFIGURED_LEVEL = level

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def apply_config_observability(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Apply ``config.observability`` for in-process consumers (DF-CHIMERA-V2-113).

    ``Engine.__init__`` calls this so a library consumer — ``Engine(config,
    LiteLLMGateway(config))`` per the README block, with no CLI/API/MCP
    surface involved — gets ``observability.log_level`` and
    ``observability.use_stdout`` honoured without having to know an internal
    call name. Idempotent: the ``(stream, level)`` once-guard in
    :func:`configure_logging` makes repeated Engine constructions cheap, and
    structlog keeps a single global pipeline with no handler list to
    duplicate, so applying twice never double-prints.

    If a ``force_stderr`` pin is active in this process (CLI ``--quiet``/
    ``--json`` via ``cli._load_cfg``, or the MCP stdio transport), the pin
    wins: the stream stays on stderr and only the level/langfuse side of the
    config re-applies. That is what keeps the CLI stdout contracts
    byte-for-byte — a config ``use_stdout: true`` flip cannot re-corrupt a
    stdout contract another surface already pinned away (DF-CHIMERA-V2-3 /
    DF-CHIMERA-0906-2). Without the pin (the plain library path) this is
    exactly ``configure_logging(obs)``.
    """
    return configure_logging(obs, force_stderr=_FORCED_STDERR_PIN)


def get_logger(name: str = "chimera") -> structlog.stdlib.BoundLogger:
    """Return a bound logger without reconfiguring."""
    if not _LOGGER_CONFIGURED:
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        )
    return structlog.get_logger(name)


def _configure_langfuse(obs: Observability) -> None:
    """Lazily configure a Langfuse client if enabled and installed."""
    global _LANGFUSE_CLIENT
    if not obs.langfuse.enabled:
        return
    if _LANGFUSE_CLIENT is not None:
        return
    try:
        from langfuse import Langfuse  # type: ignore[import-not-found]
    except ImportError:
        get_logger().warning("langfuse.enabled=true but 'langfuse' package is not installed; skipping")
        return
    _LANGFUSE_CLIENT = Langfuse(
        host=obs.langfuse.host,
        public_key=obs.langfuse.public_key,
        secret_key=obs.langfuse.secret_key,
    )


def get_langfuse() -> Any:
    """Return the shared Langfuse client (or ``None``)."""
    return _LANGFUSE_CLIENT


# DF-CHIMERA-V2-113: route the UNCONFIGURED structlog default to stderr.
#
# Every chimera module (engine, dispatcher, aggregator, gateway,
# provider_discovery, task_router_registry) grabs ``structlog.get_logger`` at
# import time. When nothing ever calls ``configure_logging`` — the plain
# library path before ``Engine.__init__`` applies ``config.observability`` —
# structlog's stock default prints bracket-level console lines to STDOUT, so
# even the ``load_config()``-phase provider-discovery lines polluted stdout
# ahead of Engine construction. Configuring a conservative stderr default at
# import (only when structlog is still unconfigured — a host application that
# configured structlog BEFORE importing chimera keeps its own pipeline) makes
# stderr the sink for that window; ``configure_logging`` /
# ``apply_config_observability`` remain the authoritative re-apply afterwards.
if not structlog.is_configured():
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


__all__ = ["_log_stream", "apply_config_observability", "configure_logging", "get_langfuse", "get_logger"]
