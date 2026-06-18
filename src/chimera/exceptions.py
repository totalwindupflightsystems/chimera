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


__all__ = ["BudgetExhaustedError"]
