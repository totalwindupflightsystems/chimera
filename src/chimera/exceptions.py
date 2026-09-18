"""Chimera-specific exception classes."""

from __future__ import annotations


class BudgetExhaustedError(Exception):
    """Raised when a provider returns a quota/budget exhaustion error.

    This indicates the account has hit its spending limit, run out of
    credits, or has a billing issue that prevents further API calls.
    """

    def __init__(self, model: str, provider: str, details: str = "") -> None:
        self.model = model
        self.provider = provider
        self.details = details
        msg = f"Budget exhausted for model '{model}' (provider: {provider})"
        if details:
            msg = f"{msg}: {details}"
        super().__init__(msg)


class ConfigError(ValueError):
    """A ``chimera.yaml`` that parses but is semantically invalid.

    Subclasses ``ValueError`` so existing callers that catch ``ValueError``
    keep working, while the user-facing edges (the CLI's ``_load_cfg``)
    render it as ONE actionable line instead of a traceback — the
    DF-CHIMERA-V2-8 convention.  Raised by
    :func:`chimera.config.load_config` for defects the pydantic schema
    cannot express on its own, e.g. a category score on the wrong scale
    (INT-API-002).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


__all__ = ["BudgetExhaustedError", "ConfigError"]
