"""Chimera-specific exception classes."""

from __future__ import annotations


def override_discard_clause(discarded: list[dict[str, object]] | None) -> str:
    """One sentence naming every request override a CONFIG LOCK discarded.

    DF-CHIMERA-V2-131: a failure that names only the LOCKED model leaves the
    caller believing its override was honoured — the exact complaint that
    produced this fix.  Both failure surfaces (the 502 no-usable-answer
    envelope and the 503 no-healthy-candidate envelope) append this clause, so
    even a client that reads nothing but ``error.message`` learns that its
    override was dropped and which config flag dropped it.

    *discarded* is the JSON-safe form of ``trace.discarded_overrides`` (dicts
    with ``field`` / ``requested`` / ``locked_by``); an empty or missing list
    yields ``""`` so the happy path's message is byte-identical to before.
    """
    if not discarded:
        return ""
    parts = [
        f"{entry.get('field')}={entry.get('requested')!r} ignored ({entry.get('locked_by')}=true)"
        for entry in discarded
    ]
    return " Request override(s) discarded by config locks: " + "; ".join(parts) + "."


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

    def __init__(
        self,
        attempts: list[dict[str, object]],
        *,
        discarded_overrides: list[dict[str, object]] | None = None,
    ) -> None:
        self.attempts = attempts
        #: Request overrides a config lock discarded on this run (DF-CHIMERA-V2-131).
        #: Carried on the exception so the API/MCP layers can serve the same
        #: field the success body carries, instead of naming only the locked model.
        self.discarded_overrides = list(discarded_overrides or [])
        providers = sorted({str(a.get("provider") or "?") for a in attempts})
        names = ", ".join(f"{a.get('model')} ({a.get('provider')}/{a.get('error_class')})" for a in attempts)
        self.message = (
            "No healthy candidate: every configured model is blocked by quota/budget "
            f"exhaustion on provider(s) {', '.join(providers)} — attempted: {names}. "
            "Top up the provider account (the block clears automatically) or configure "
            "another credentialed provider."
        ) + override_discard_clause(self.discarded_overrides)
        super().__init__(self.message)


class LaneUnreachableError(NoHealthyCandidateError):
    """Raised when no provider this run needs can serve it (DF-CHIMERA-V2-120).

    The credential-side twin of the quota arm above, and the fast-fail half of
    acceptance criterion 4: when EVERY stage's provider is provably unusable
    (no credential in a deployment that resolves credentials elsewhere, or a
    credential the provider already rejected), the run fails BEFORE the first
    provider call — milliseconds instead of the measured 83-187 s of retries
    that ended rc=2 anyway.

    It deliberately subclasses :class:`NoHealthyCandidateError` so every
    existing surface (CLI exit 2, REST 502, MCP) keeps treating it as "nothing
    could serve this run"; only the MESSAGE differs, naming each provider and
    the remedy (the env var to set) instead of talking about quota.  The
    ``attempts`` entries carry ``error_class: "credential"`` plus a ``remedy``
    key so a caller can render its own instruction.

    It is never raised on absence of credentials alone: a deployment with no
    resolvable credential anywhere keeps its documented auth-error behaviour
    (DF-CHIMERA-V2-71 — the engine fabricates one degraded placeholder per
    stage so the CLI/REST failure surfaces stay exercised).  Only a deployment
    that DOES resolve credentials somewhere, yet cannot reach any of the
    providers this run needs, is unreachable in this sense.
    """

    def __init__(
        self,
        attempts: list[dict[str, object]],
        *,
        discarded_overrides: list[dict[str, object]] | None = None,
    ) -> None:
        self.attempts = attempts
        #: Request overrides a config lock discarded on this run (DF-CHIMERA-V2-131).
        self.discarded_overrides = list(discarded_overrides or [])
        providers = sorted({str(a.get("provider") or "?") for a in attempts})
        details = "; ".join(
            f"{a.get('model')} ({a.get('remedy') or a.get('detail') or 'unreachable'})" for a in attempts
        )
        self.message = (
            f"No reachable provider: this run needs {', '.join(providers)}, but no credential "
            f"is configured for {'them' if len(providers) > 1 else 'it'} — {details}. "
            "Set the listed environment variable (or add the provider to api_keys in "
            "chimera.yaml), or point the formation at a provider you can reach; nothing "
            "was billed."
        ) + override_discard_clause(self.discarded_overrides)
        Exception.__init__(self, self.message)


class DagShapeError(ValueError):
    """A client-defined DAG is structurally invalid (not a catalog miss).

    Raised by :func:`chimera.dispatcher._validate_dag` for stage-shape
    defects: a missing worker stage or a missing aggregator/merge/audit
    stage (DF-CHIMERA-V2-85).  Subclasses ``ValueError`` so existing
    ``except ValueError`` callers keep working, while the API layer can
    distinguish "fix your DAG shape" from "fix your model catalog" and
    must NOT append the catalog hint to these messages.
    """


__all__ = [
    "BudgetExhaustedError",
    "ConfigError",
    "DagShapeError",
    "LaneUnreachableError",
    "NoHealthyCandidateError",
    "override_discard_clause",
]
