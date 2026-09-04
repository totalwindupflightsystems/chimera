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
_LANGFUSE_CLIENT: Any = None


def _log_stream(obs: Observability) -> TextIO:
    """Return the stream structlog/basicConfig should write to."""
    return sys.stdout if obs.use_stdout else sys.stderr


def configure_logging(
    obs: Observability, *, force_stderr: bool = False
) -> structlog.stdlib.BoundLogger:
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
    global _LOGGER_CONFIGURED, _CONFIGURED_STREAM, _CONFIGURED_LEVEL
    level = getattr(logging, obs.log_level.upper(), logging.INFO)
    stream: TextIO = sys.stderr if force_stderr else _log_stream(obs)

    if not (
        _LOGGER_CONFIGURED and _CONFIGURED_STREAM is stream and level == _CONFIGURED_LEVEL
    ):
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
            cache_logger_on_first_use=True,
        )
        _LOGGER_CONFIGURED = True
        _CONFIGURED_STREAM = stream
        _CONFIGURED_LEVEL = level

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


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
        get_logger().warning(
            "langfuse.enabled=true but 'langfuse' package is not installed; skipping"
        )
        return
    _LANGFUSE_CLIENT = Langfuse(
        host=obs.langfuse.host,
        public_key=obs.langfuse.public_key,
        secret_key=obs.langfuse.secret_key,
    )


def get_langfuse() -> Any:
    """Return the shared Langfuse client (or ``None``)."""
    return _LANGFUSE_CLIENT


__all__ = ["_log_stream", "configure_logging", "get_langfuse", "get_logger"]
