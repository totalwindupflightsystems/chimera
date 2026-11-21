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


__all__ = ["BudgetExhaustedError", "ConfigError", "NoHealthyCandidateError"]


class NoHealthyCandidateError(Exception):
    """Raised when EVERY candidate model is quota-blocked, so a run cannot serve.

    The all-candidates-dead arm of DF-CHIMERA-V2-130.  It is raised *before*
    any provider call, only on positive evidence: the models were dropped by
    the quota class (a live ``error_class: quota`` health verdict, or a block
    recorded from a real quota failure), never because credentials are merely
    absent — that condition keeps its own (auth-error) behaviour.

    Machine-readable on purpose: ``attempts`` names every candidate that was
    skipped, one entry per model, with the provider and the failure class that
    dropped it, plus the seconds left on the block.  The API layer renders it
    verbatim, so a caller can tell "wait for the top-up" from "this deployment
    has no route to any provider" without string-matching a 502 message.
    ``attempts`` entry shape::

        {"provider": "deepseek", "model": "deepseek/deepseek-chat",
         "error_class": "quota", "retry_after_s": 742.0, "detail": "..."}
    """

    def __init__(self, attempts: list[dict[str, object]]) -> None:
        self.attempts = attempts
        providers = sorted({str(a.get("provider") or "?") for a in attempts})
        names = ", ".join(f"{a.get('model')} ({a.get('provider')}/{a.get('error_class')})" for a in attempts)
        self.message = (
            "No healthy candidate: every configured model is blocked by quota/budget "
            f"exhaustion on provider(s) {', '.join(providers)} — attempted: {names}. "
            "Top up the provider account (the block clears automatically) or configure "
            "another credentialed provider."
        )
        super().__init__(self.message)


class DagShapeError(ValueError):
    """A client-defined DAG is structurally invalid (not a catalog miss).

    Raised by :func:`chimera.dispatcher._validate_dag` for stage-shape
    defects: a missing worker stage or a missing aggregator/merge/audit
    stage (DF-CHIMERA-V2-85).  Subclasses ``ValueError`` so existing
    ``except ValueError`` callers keep working, while the API layer can
    distinguish "fix your DAG shape" from "fix your model catalog" and
    must NOT append the catalog hint to these messages.
    """
