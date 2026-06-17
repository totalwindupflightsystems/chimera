"""Structured logging (structlog) and optional Langfuse tracing.

structlog emits JSON to stderr. Langfuse is enabled only when configured and
the ``langfuse`` package is importable.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from chimera.config import Observability

_LOGGER_CONFIGURED = False
_LANGFUSE_CLIENT: Any = None


def configure_logging(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stderr,
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
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
            cache_logger_on_first_use=True,
        )
        _LOGGER_CONFIGURED = True

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


__all__ = ["configure_logging", "get_langfuse", "get_logger"]
