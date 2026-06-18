"""Structured logging (structlog) and optional Langfuse tracing.

structlog emits JSON to stderr by default, or to stdout when
``observability.use_stdout`` is true (the default, since Chimera is a CLI tool,
not a daemon). Langfuse is enabled only when configured and the ``langfuse``
package is importable.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, TextIO

import structlog

from chimera.config import Observability

_LOGGER_CONFIGURED = False
_LANGFUSE_CLIENT: Any = None


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict


def _log_stream(obs: Observability) -> TextIO:
    """Return the stream structlog/basicConfig should write to."""
    return sys.stdout if obs.use_stdout else sys.stderr
mutants_x_configure_logging__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_configure_logging__mutmut)
def configure_logging(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_orig(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_1(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = None

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_2(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(None, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_3(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, None, logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_4(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), None)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_5(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_6(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_7(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), )

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_8(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.lower(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_9(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_10(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = None
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_11(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(None)
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_12(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
        logging.basicConfig(
            format=None,
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_13(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
        logging.basicConfig(
            format="%(message)s",
            stream=None,
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_14(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
        logging.basicConfig(
            format="%(message)s",
            stream=stream,
            level=None,
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_15(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
        logging.basicConfig(
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_16(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
        logging.basicConfig(
            format="%(message)s",
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_17(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
        logging.basicConfig(
            format="%(message)s",
            stream=stream,
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_18(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
        logging.basicConfig(
            format="XX%(message)sXX",
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_19(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
        logging.basicConfig(
            format="%(MESSAGE)S",
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

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_20(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
        logging.basicConfig(
            format="%(message)s",
            stream=stream,
            level=level,
        )
        structlog.configure(
            processors=None,
            wrapper_class=structlog.make_filtering_bound_logger(level),
            logger_factory=structlog.PrintLoggerFactory(file=stream),
            cache_logger_on_first_use=True,
        )
        _LOGGER_CONFIGURED = True

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_21(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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
            wrapper_class=None,
            logger_factory=structlog.PrintLoggerFactory(file=stream),
            cache_logger_on_first_use=True,
        )
        _LOGGER_CONFIGURED = True

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_22(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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
            logger_factory=None,
            cache_logger_on_first_use=True,
        )
        _LOGGER_CONFIGURED = True

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_23(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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
            cache_logger_on_first_use=None,
        )
        _LOGGER_CONFIGURED = True

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_24(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
        logging.basicConfig(
            format="%(message)s",
            stream=stream,
            level=level,
        )
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(level),
            logger_factory=structlog.PrintLoggerFactory(file=stream),
            cache_logger_on_first_use=True,
        )
        _LOGGER_CONFIGURED = True

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_25(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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
            logger_factory=structlog.PrintLoggerFactory(file=stream),
            cache_logger_on_first_use=True,
        )
        _LOGGER_CONFIGURED = True

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_26(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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
            cache_logger_on_first_use=True,
        )
        _LOGGER_CONFIGURED = True

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_27(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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
            )
        _LOGGER_CONFIGURED = True

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_28(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
        logging.basicConfig(
            format="%(message)s",
            stream=stream,
            level=level,
        )
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt=None),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(level),
            logger_factory=structlog.PrintLoggerFactory(file=stream),
            cache_logger_on_first_use=True,
        )
        _LOGGER_CONFIGURED = True

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_29(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
        logging.basicConfig(
            format="%(message)s",
            stream=stream,
            level=level,
        )
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="XXisoXX"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(level),
            logger_factory=structlog.PrintLoggerFactory(file=stream),
            cache_logger_on_first_use=True,
        )
        _LOGGER_CONFIGURED = True

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_30(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
        logging.basicConfig(
            format="%(message)s",
            stream=stream,
            level=level,
        )
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="ISO"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(level),
            logger_factory=structlog.PrintLoggerFactory(file=stream),
            cache_logger_on_first_use=True,
        )
        _LOGGER_CONFIGURED = True

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_31(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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
            wrapper_class=structlog.make_filtering_bound_logger(None),
            logger_factory=structlog.PrintLoggerFactory(file=stream),
            cache_logger_on_first_use=True,
        )
        _LOGGER_CONFIGURED = True

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_32(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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
            logger_factory=structlog.PrintLoggerFactory(file=None),
            cache_logger_on_first_use=True,
        )
        _LOGGER_CONFIGURED = True

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_33(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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
            cache_logger_on_first_use=False,
        )
        _LOGGER_CONFIGURED = True

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_34(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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
        _LOGGER_CONFIGURED = None

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_35(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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
        _LOGGER_CONFIGURED = False

    _configure_langfuse(obs)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_36(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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

    _configure_langfuse(None)
    return structlog.get_logger("chimera")


def x_configure_logging__mutmut_37(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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

    _configure_langfuse(obs)
    return structlog.get_logger(None)


def x_configure_logging__mutmut_38(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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

    _configure_langfuse(obs)
    return structlog.get_logger("XXchimeraXX")


def x_configure_logging__mutmut_39(obs: Observability) -> structlog.stdlib.BoundLogger:
    """Configure structlog once and return a bound logger."""
    global _LOGGER_CONFIGURED
    level = getattr(logging, obs.log_level.upper(), logging.INFO)

    if not _LOGGER_CONFIGURED:
        stream: TextIO = _log_stream(obs)
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

    _configure_langfuse(obs)
    return structlog.get_logger("CHIMERA")

mutants_x_configure_logging__mutmut['_mutmut_orig'] = x_configure_logging__mutmut_orig # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_1'] = x_configure_logging__mutmut_1 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_2'] = x_configure_logging__mutmut_2 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_3'] = x_configure_logging__mutmut_3 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_4'] = x_configure_logging__mutmut_4 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_5'] = x_configure_logging__mutmut_5 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_6'] = x_configure_logging__mutmut_6 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_7'] = x_configure_logging__mutmut_7 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_8'] = x_configure_logging__mutmut_8 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_9'] = x_configure_logging__mutmut_9 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_10'] = x_configure_logging__mutmut_10 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_11'] = x_configure_logging__mutmut_11 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_12'] = x_configure_logging__mutmut_12 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_13'] = x_configure_logging__mutmut_13 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_14'] = x_configure_logging__mutmut_14 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_15'] = x_configure_logging__mutmut_15 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_16'] = x_configure_logging__mutmut_16 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_17'] = x_configure_logging__mutmut_17 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_18'] = x_configure_logging__mutmut_18 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_19'] = x_configure_logging__mutmut_19 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_20'] = x_configure_logging__mutmut_20 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_21'] = x_configure_logging__mutmut_21 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_22'] = x_configure_logging__mutmut_22 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_23'] = x_configure_logging__mutmut_23 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_24'] = x_configure_logging__mutmut_24 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_25'] = x_configure_logging__mutmut_25 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_26'] = x_configure_logging__mutmut_26 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_27'] = x_configure_logging__mutmut_27 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_28'] = x_configure_logging__mutmut_28 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_29'] = x_configure_logging__mutmut_29 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_30'] = x_configure_logging__mutmut_30 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_31'] = x_configure_logging__mutmut_31 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_32'] = x_configure_logging__mutmut_32 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_33'] = x_configure_logging__mutmut_33 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_34'] = x_configure_logging__mutmut_34 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_35'] = x_configure_logging__mutmut_35 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_36'] = x_configure_logging__mutmut_36 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_37'] = x_configure_logging__mutmut_37 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_38'] = x_configure_logging__mutmut_38 # type: ignore # mutmut generated
mutants_x_configure_logging__mutmut['x_configure_logging__mutmut_39'] = x_configure_logging__mutmut_39 # type: ignore # mutmut generated
mutants_x_get_logger__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_get_logger__mutmut)
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


def x_get_logger__mutmut_orig(name: str = "chimera") -> structlog.stdlib.BoundLogger:
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


def x_get_logger__mutmut_1(name: str = "XXchimeraXX") -> structlog.stdlib.BoundLogger:
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


def x_get_logger__mutmut_2(name: str = "CHIMERA") -> structlog.stdlib.BoundLogger:
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


def x_get_logger__mutmut_3(name: str = "chimera") -> structlog.stdlib.BoundLogger:
    """Return a bound logger without reconfiguring."""
    if _LOGGER_CONFIGURED:
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        )
    return structlog.get_logger(name)


def x_get_logger__mutmut_4(name: str = "chimera") -> structlog.stdlib.BoundLogger:
    """Return a bound logger without reconfiguring."""
    if not _LOGGER_CONFIGURED:
        structlog.configure(
            processors=None,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        )
    return structlog.get_logger(name)


def x_get_logger__mutmut_5(name: str = "chimera") -> structlog.stdlib.BoundLogger:
    """Return a bound logger without reconfiguring."""
    if not _LOGGER_CONFIGURED:
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=None,
        )
    return structlog.get_logger(name)


def x_get_logger__mutmut_6(name: str = "chimera") -> structlog.stdlib.BoundLogger:
    """Return a bound logger without reconfiguring."""
    if not _LOGGER_CONFIGURED:
        structlog.configure(
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        )
    return structlog.get_logger(name)


def x_get_logger__mutmut_7(name: str = "chimera") -> structlog.stdlib.BoundLogger:
    """Return a bound logger without reconfiguring."""
    if not _LOGGER_CONFIGURED:
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            )
    return structlog.get_logger(name)


def x_get_logger__mutmut_8(name: str = "chimera") -> structlog.stdlib.BoundLogger:
    """Return a bound logger without reconfiguring."""
    if not _LOGGER_CONFIGURED:
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt=None),
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        )
    return structlog.get_logger(name)


def x_get_logger__mutmut_9(name: str = "chimera") -> structlog.stdlib.BoundLogger:
    """Return a bound logger without reconfiguring."""
    if not _LOGGER_CONFIGURED:
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="XXisoXX"),
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        )
    return structlog.get_logger(name)


def x_get_logger__mutmut_10(name: str = "chimera") -> structlog.stdlib.BoundLogger:
    """Return a bound logger without reconfiguring."""
    if not _LOGGER_CONFIGURED:
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="ISO"),
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        )
    return structlog.get_logger(name)


def x_get_logger__mutmut_11(name: str = "chimera") -> structlog.stdlib.BoundLogger:
    """Return a bound logger without reconfiguring."""
    if not _LOGGER_CONFIGURED:
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(file=None),
        )
    return structlog.get_logger(name)


def x_get_logger__mutmut_12(name: str = "chimera") -> structlog.stdlib.BoundLogger:
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
    return structlog.get_logger(None)

mutants_x_get_logger__mutmut['_mutmut_orig'] = x_get_logger__mutmut_orig # type: ignore # mutmut generated
mutants_x_get_logger__mutmut['x_get_logger__mutmut_1'] = x_get_logger__mutmut_1 # type: ignore # mutmut generated
mutants_x_get_logger__mutmut['x_get_logger__mutmut_2'] = x_get_logger__mutmut_2 # type: ignore # mutmut generated
mutants_x_get_logger__mutmut['x_get_logger__mutmut_3'] = x_get_logger__mutmut_3 # type: ignore # mutmut generated
mutants_x_get_logger__mutmut['x_get_logger__mutmut_4'] = x_get_logger__mutmut_4 # type: ignore # mutmut generated
mutants_x_get_logger__mutmut['x_get_logger__mutmut_5'] = x_get_logger__mutmut_5 # type: ignore # mutmut generated
mutants_x_get_logger__mutmut['x_get_logger__mutmut_6'] = x_get_logger__mutmut_6 # type: ignore # mutmut generated
mutants_x_get_logger__mutmut['x_get_logger__mutmut_7'] = x_get_logger__mutmut_7 # type: ignore # mutmut generated
mutants_x_get_logger__mutmut['x_get_logger__mutmut_8'] = x_get_logger__mutmut_8 # type: ignore # mutmut generated
mutants_x_get_logger__mutmut['x_get_logger__mutmut_9'] = x_get_logger__mutmut_9 # type: ignore # mutmut generated
mutants_x_get_logger__mutmut['x_get_logger__mutmut_10'] = x_get_logger__mutmut_10 # type: ignore # mutmut generated
mutants_x_get_logger__mutmut['x_get_logger__mutmut_11'] = x_get_logger__mutmut_11 # type: ignore # mutmut generated
mutants_x_get_logger__mutmut['x_get_logger__mutmut_12'] = x_get_logger__mutmut_12 # type: ignore # mutmut generated
mutants_x__configure_langfuse__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x__configure_langfuse__mutmut)
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


def x__configure_langfuse__mutmut_orig(obs: Observability) -> None:
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


def x__configure_langfuse__mutmut_1(obs: Observability) -> None:
    """Lazily configure a Langfuse client if enabled and installed."""
    global _LANGFUSE_CLIENT
    if obs.langfuse.enabled:
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


def x__configure_langfuse__mutmut_2(obs: Observability) -> None:
    """Lazily configure a Langfuse client if enabled and installed."""
    global _LANGFUSE_CLIENT
    if not obs.langfuse.enabled:
        return
    if _LANGFUSE_CLIENT is None:
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


def x__configure_langfuse__mutmut_3(obs: Observability) -> None:
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
            None
        )
        return
    _LANGFUSE_CLIENT = Langfuse(
        host=obs.langfuse.host,
        public_key=obs.langfuse.public_key,
        secret_key=obs.langfuse.secret_key,
    )


def x__configure_langfuse__mutmut_4(obs: Observability) -> None:
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
            "XXlangfuse.enabled=true but 'langfuse' package is not installed; skippingXX"
        )
        return
    _LANGFUSE_CLIENT = Langfuse(
        host=obs.langfuse.host,
        public_key=obs.langfuse.public_key,
        secret_key=obs.langfuse.secret_key,
    )


def x__configure_langfuse__mutmut_5(obs: Observability) -> None:
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
            "LANGFUSE.ENABLED=TRUE BUT 'LANGFUSE' PACKAGE IS NOT INSTALLED; SKIPPING"
        )
        return
    _LANGFUSE_CLIENT = Langfuse(
        host=obs.langfuse.host,
        public_key=obs.langfuse.public_key,
        secret_key=obs.langfuse.secret_key,
    )


def x__configure_langfuse__mutmut_6(obs: Observability) -> None:
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
    _LANGFUSE_CLIENT = None


def x__configure_langfuse__mutmut_7(obs: Observability) -> None:
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
        host=None,
        public_key=obs.langfuse.public_key,
        secret_key=obs.langfuse.secret_key,
    )


def x__configure_langfuse__mutmut_8(obs: Observability) -> None:
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
        public_key=None,
        secret_key=obs.langfuse.secret_key,
    )


def x__configure_langfuse__mutmut_9(obs: Observability) -> None:
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
        secret_key=None,
    )


def x__configure_langfuse__mutmut_10(obs: Observability) -> None:
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
        public_key=obs.langfuse.public_key,
        secret_key=obs.langfuse.secret_key,
    )


def x__configure_langfuse__mutmut_11(obs: Observability) -> None:
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
        secret_key=obs.langfuse.secret_key,
    )


def x__configure_langfuse__mutmut_12(obs: Observability) -> None:
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
        )

mutants_x__configure_langfuse__mutmut['_mutmut_orig'] = x__configure_langfuse__mutmut_orig # type: ignore # mutmut generated
mutants_x__configure_langfuse__mutmut['x__configure_langfuse__mutmut_1'] = x__configure_langfuse__mutmut_1 # type: ignore # mutmut generated
mutants_x__configure_langfuse__mutmut['x__configure_langfuse__mutmut_2'] = x__configure_langfuse__mutmut_2 # type: ignore # mutmut generated
mutants_x__configure_langfuse__mutmut['x__configure_langfuse__mutmut_3'] = x__configure_langfuse__mutmut_3 # type: ignore # mutmut generated
mutants_x__configure_langfuse__mutmut['x__configure_langfuse__mutmut_4'] = x__configure_langfuse__mutmut_4 # type: ignore # mutmut generated
mutants_x__configure_langfuse__mutmut['x__configure_langfuse__mutmut_5'] = x__configure_langfuse__mutmut_5 # type: ignore # mutmut generated
mutants_x__configure_langfuse__mutmut['x__configure_langfuse__mutmut_6'] = x__configure_langfuse__mutmut_6 # type: ignore # mutmut generated
mutants_x__configure_langfuse__mutmut['x__configure_langfuse__mutmut_7'] = x__configure_langfuse__mutmut_7 # type: ignore # mutmut generated
mutants_x__configure_langfuse__mutmut['x__configure_langfuse__mutmut_8'] = x__configure_langfuse__mutmut_8 # type: ignore # mutmut generated
mutants_x__configure_langfuse__mutmut['x__configure_langfuse__mutmut_9'] = x__configure_langfuse__mutmut_9 # type: ignore # mutmut generated
mutants_x__configure_langfuse__mutmut['x__configure_langfuse__mutmut_10'] = x__configure_langfuse__mutmut_10 # type: ignore # mutmut generated
mutants_x__configure_langfuse__mutmut['x__configure_langfuse__mutmut_11'] = x__configure_langfuse__mutmut_11 # type: ignore # mutmut generated
mutants_x__configure_langfuse__mutmut['x__configure_langfuse__mutmut_12'] = x__configure_langfuse__mutmut_12 # type: ignore # mutmut generated


def get_langfuse() -> Any:
    """Return the shared Langfuse client (or ``None``)."""
    return _LANGFUSE_CLIENT


__all__ = ["_log_stream", "configure_logging", "get_langfuse", "get_logger"]
