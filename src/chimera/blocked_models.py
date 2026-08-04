"""Model-level failure registry — avoids re-selecting guardrail-blocked models.

When a provider call fails with a guardrail/privacy/404-style error (e.g.
OpenRouter's ``No endpoints available matching your guardrail restrictions
and data policy``), the model is effectively unusable for this API key, yet
the dispatcher would happily pick it again on the next run.  This module
keeps a small in-memory registry mapping such models to a ``blocked_until``
timestamp so the dispatcher catalog and the category selector can exclude
them for a cooldown window.

Only guardrail-class failures block a model — transient errors (timeouts,
5xx, rate limits) are handled by retries/circuit breakers and must NOT
remove a model from candidacy.

The registry is process-local (deliberations run in one process) and uses an
injectable clock so tests can advance time without sleeping.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable

import structlog

log = structlog.get_logger("chimera.blocked_models")

#: How long (seconds) a model stays blocked after a guardrail-class failure.
DEFAULT_BLOCK_COOLDOWN_S: float = 300.0

#: Error-message signature of a guardrail/privacy/endpoint-availability
#: failure that should exclude the model from future candidate lists.
GUARDRAIL_ERROR_RE = re.compile(
    r"guardrail|no endpoints available|privacy", re.IGNORECASE
)


def is_guardrail_error(error: object) -> bool:
    """Return True when *error* looks like a guardrail/404-style rejection."""
    return bool(GUARDRAIL_ERROR_RE.search(str(error)))


class ModelBlockRegistry:
    """Tracks models temporarily blocked by guardrail-class upstream failures."""

    def __init__(
        self,
        *,
        cooldown_s: float = DEFAULT_BLOCK_COOLDOWN_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cooldown_s = cooldown_s
        self._clock = clock
        self._blocked_until: dict[str, float] = {}

    def record_failure(self, model: str, error: object) -> bool:
        """Record an upstream failure for *model*.

        Returns True when the failure was guardrail-class and the model is
        now blocked; False for non-guardrail failures (not recorded).
        """
        if not is_guardrail_error(error):
            return False
        until = self._clock() + self.cooldown_s
        self._blocked_until[model] = until
        log.warning(
            "model_blocked_guardrail",
            model=model,
            cooldown_s=self.cooldown_s,
            error=str(error)[:200],
        )
        return True

    def is_blocked(self, model: str) -> bool:
        """True when *model* is currently inside its block cooldown."""
        until = self._blocked_until.get(model)
        if until is None:
            return False
        if self._clock() >= until:
            # Cooldown expired — clear the entry so the model is a candidate again.
            del self._blocked_until[model]
            return False
        return True

    def blocked(self) -> set[str]:
        """The set of currently-blocked model names (expired entries pruned)."""
        now = self._clock()
        expired = [m for m, until in self._blocked_until.items() if now >= until]
        for m in expired:
            del self._blocked_until[m]
        return set(self._blocked_until)


#: Process-wide shared registry.  The engine records failures here and the
#: dispatcher/selector consult it, so a model blocked by one deliberation is
#: avoided by the next.  Tests may replace this with a fresh instance via
#: ``set_shared_registry``.
shared_registry = ModelBlockRegistry()


def set_shared_registry(registry: ModelBlockRegistry) -> None:
    """Replace the process-wide registry (used by tests for isolation)."""
    global shared_registry
    shared_registry = registry


__all__ = [
    "DEFAULT_BLOCK_COOLDOWN_S",
    "GUARDRAIL_ERROR_RE",
    "ModelBlockRegistry",
    "is_guardrail_error",
    "set_shared_registry",
    "shared_registry",
]
