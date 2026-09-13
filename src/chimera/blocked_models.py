"""Model-level failure registry — avoids re-selecting guardrail-blocked models.

When a provider call fails with a guardrail/privacy/404-style error (e.g.
OpenRouter's ``No endpoints available matching your guardrail restrictions
and data policy``), the model is effectively unusable for this API key, yet
the dispatcher would happily pick it again on the next run.  This module
keeps a registry mapping such models to a ``blocked_until`` timestamp so the
dispatcher catalog and the category selector can exclude them.

Only guardrail-class failures block a model — transient errors (timeouts,
5xx, rate limits) are handled by retries/circuit breakers and must NOT
remove a model from candidacy.

Durability (DF-CHIMERA-V2-1)
----------------------------
A guardrail/privacy rejection is a property of the API-key × model pair, not
a transient condition, so blocks are **long-lived** (default 7 days) and
**persisted to disk** as wall-clock expiry timestamps
(``~/.chimera/blocked-models.json`` by default).  On construction the
registry reloads the persisted state, so a fresh process never re-picks a
known guardrail-blocked model, and the block is not silently re-admitted
after a short in-memory cooldown.  Expired entries are pruned on load and on
read.  To clear a block manually, delete the state file (or remove the entry
from it).

The registry uses an injectable clock so tests can advance time without
sleeping; persisted timestamps are wall-clock (``time.time()``) so they stay
meaningful across restarts.  ``state_path`` is injectable in the same style —
pass ``None`` to disable persistence (tests), or a ``tmp_path`` location.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path

import structlog

log = structlog.get_logger("chimera.blocked_models")

#: How long (seconds) a model stays blocked after a guardrail-class failure.
#: Guardrail/privacy rejections do not resolve on their own within minutes,
#: so the default is long-lived: 7 days.  The expiry is persisted, so it
#: survives process restarts (DF-CHIMERA-V2-1).
DEFAULT_BLOCK_COOLDOWN_S: float = 7.0 * 24.0 * 3600.0

#: Default on-disk location for the persisted registry.  Follows the repo's
#: state-file convention (``~/.chimera/models-dev-cache.json`` in
#: ``provider_discovery``).
DEFAULT_STATE_PATH: str = "~/.chimera/blocked-models.json"

#: Error-message signature of a guardrail/privacy/endpoint-availability
#: failure that should exclude the model from future candidate lists.
GUARDRAIL_ERROR_RE = re.compile(
    r"guardrail|no endpoints available|privacy", re.IGNORECASE
)


def is_guardrail_error(error: object) -> bool:
    """Return True when *error* looks like a guardrail/404-style rejection."""
    return bool(GUARDRAIL_ERROR_RE.search(str(error)))


class ModelBlockRegistry:
    """Tracks models blocked by guardrail-class upstream failures.

    State is persisted to *state_path* (JSON) whenever a block is recorded
    and reloaded on construction, so blocks survive process restarts.  Pass
    ``state_path=None`` to disable persistence entirely.
    """

    def __init__(
        self,
        *,
        cooldown_s: float = DEFAULT_BLOCK_COOLDOWN_S,
        clock: Callable[[], float] = time.monotonic,
        state_path: str | os.PathLike[str] | None = DEFAULT_STATE_PATH,
    ) -> None:
        self.cooldown_s = cooldown_s
        self._clock = clock
        self._state_path = (
            Path(state_path).expanduser() if state_path is not None else None
        )
        self._blocked_until: dict[str, float] = {}
        self._load()

    def record_failure(self, model: str, error: object) -> bool:
        """Record an upstream failure for *model*.

        Returns True when the failure was guardrail-class and the model is
        now blocked (and the block persisted); False for non-guardrail
        failures (never recorded).
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
        self._save()
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

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load persisted blocks, pruning expired entries.

        Missing or corrupt state files are not errors — the registry simply
        starts empty.
        """
        if self._state_path is None:
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError) as exc:
            log.warning(
                "blocked_models_state_unreadable",
                path=str(self._state_path),
                error=str(exc)[:200],
            )
            return
        if not isinstance(data, dict):
            log.warning(
                "blocked_models_state_invalid",
                path=str(self._state_path),
                reason="not a dict",
            )
            return
        entries = data.get("blocked_until_epoch")
        if not isinstance(entries, dict):
            return
        # Persisted timestamps are wall-clock; convert the remaining TTL into
        # the injected clock's units so in-memory semantics are unchanged.
        now_wall = time.time()
        for model, epoch in entries.items():
            if not isinstance(model, str) or not isinstance(epoch, (int, float)):
                continue
            remaining = float(epoch) - now_wall
            if remaining <= 0:
                continue  # expired — pruned on load
            self._blocked_until[model] = self._clock() + remaining

    def _save(self) -> None:
        """Persist current blocks as wall-clock expiry timestamps.

        Best-effort: a filesystem failure logs a warning but never breaks the
        deliberation that just recorded the block.
        """
        if self._state_path is None:
            return
        now_wall = time.time()
        now_clock = self._clock()
        payload = {
            "version": 1,
            "blocked_until_epoch": {
                model: now_wall + (until - now_clock)
                for model, until in self._blocked_until.items()
            },
        }
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_name(self._state_path.name + ".tmp")
            tmp.write_text(
                json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
            )
            os.replace(tmp, self._state_path)
        except OSError as exc:
            log.warning(
                "blocked_models_state_unwritable",
                path=str(self._state_path),
                error=str(exc)[:200],
            )


#: Process-wide shared registry.  The engine records failures here and the
#: dispatcher/selector consult it, so a model blocked by one deliberation is
#: avoided by the next — and by future processes, since the registry persists
#: to ``DEFAULT_STATE_PATH``.  Tests may replace this with a fresh instance
#: via ``set_shared_registry``.
shared_registry = ModelBlockRegistry()


def set_shared_registry(registry: ModelBlockRegistry) -> None:
    """Replace the process-wide registry (used by tests for isolation)."""
    global shared_registry
    shared_registry = registry


__all__ = [
    "DEFAULT_BLOCK_COOLDOWN_S",
    "DEFAULT_STATE_PATH",
    "GUARDRAIL_ERROR_RE",
    "ModelBlockRegistry",
    "is_guardrail_error",
    "set_shared_registry",
    "shared_registry",
]
