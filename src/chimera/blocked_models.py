"""Model-level failure registry — avoids re-selecting unusable models.

When a provider call fails with a guardrail/privacy/404-style error (e.g.
OpenRouter's ``No endpoints available matching your guardrail restrictions
and data policy``), the model is effectively unusable for this API key, yet
the dispatcher would happily pick it again on the next run.  This module
keeps a registry mapping such models to a ``blocked_until`` timestamp so the
dispatcher catalog and the category selector can exclude them.

Two failure classes block a model (DF-CHIMERA-V2-6):

* **guardrail** — a policy/privacy rejection.  A property of the
  API-key × model pair, effectively permanent for that key.
* **credential** — an authentication/authorization rejection
  (``401`` / ``AuthenticationError`` / "User not found" / invalid API key).
  The key is *present* but wrong or expired, so the model is equally
  unusable.  ``model_blocked_credential`` marks these entries with a
  non-reversible fingerprint of the key that failed, which lets the block
  self-clear the moment the operator replaces the key.

Transient errors (timeouts, 429, 5xx) are handled by retries/circuit
breakers and must NOT remove a model from candidacy.

Durability (DF-CHIMERA-V2-1, repo-scoped per CHIMERA-V2-REVIEW-03)
----------------------------
Both classes are long-lived (default 7 days) and **persisted to disk** as
wall-clock expiry timestamps.  On construction the registry reloads the
persisted state, so a fresh process never re-picks a known-blocked model,
and the block is not silently re-admitted after a short in-memory cooldown.
Expired entries are pruned on load and on read.  To clear a block manually,
delete the state file (or remove the entry from it).

The state file is **install-scoped, not machine-scoped**: the default path
is resolved at construction time by :func:`default_state_path` —

1. ``$CHIMERA_BLOCKED_MODELS_PATH`` when set (deploys can pin one file),
2. else ``<repo>/.chimera/blocked-models.json`` for the nearest enclosing
   checkout (walk up from the process cwd to the first ``pyproject.toml`` —
   the same convention ``scripts/model_sync.py`` uses for
   ``.seen_models.json``),
3. else the legacy home path ``~/.chimera/blocked-models.json`` (bare pip
   installs), with a :class:`UserWarning` because that location is shared
   by every chimera process on the machine.

Scope matters: the home-scoped default made a fresh clone inherit every
block ever recorded on the host — credential blocks for providers the new
install never configured (CHIMERA-V2-REVIEW-03).  A block recorded inside
one checkout is invisible to another; blocks recorded before this change
stay in the legacy file and are simply no longer read.  The repo-local
``.chimera/`` directory is gitignored (per-install runtime state).

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
import warnings
from collections.abc import Callable
from pathlib import Path

import structlog

log = structlog.get_logger("chimera.blocked_models")

#: How long (seconds) a model stays blocked after a guardrail-class failure.
#: Guardrail/privacy rejections do not resolve on their own within minutes,
#: so the default is long-lived: 7 days.  The expiry is persisted, so it
#: survives process restarts (DF-CHIMERA-V2-1).
DEFAULT_BLOCK_COOLDOWN_S: float = 7.0 * 24.0 * 3600.0

#: LEGACY on-disk location (machine-scoped).  No longer the default: it made
#: every chimera process on the host share one blocked-models file, so a
#: fresh clone inherited blocks for providers it had never configured
#: (CHIMERA-V2-REVIEW-03).  Kept as the last-resort fallback for bare pip
#: installs outside any repo checkout — see :func:`default_state_path`.
DEFAULT_STATE_PATH: str = "~/.chimera/blocked-models.json"

#: Environment override pinning the blocked-models state file explicitly
#: (highest-resolution priority; deploys and tests use this to opt out of
#: repo-relative resolution).
STATE_PATH_ENV: str = "CHIMERA_BLOCKED_MODELS_PATH"

#: Repo marker the default resolution walks up to (from the process cwd):
#: the first directory containing it is the install root, and the state
#: file lives at ``<root>/.chimera/blocked-models.json``.
_REPO_MARKER: str = "pyproject.toml"


def default_state_path() -> Path:
    """Resolve the default blocked-models state file for THIS install.

    Priority: the :data:`STATE_PATH_ENV` override, else the repo-local
    ``.chimera/blocked-models.json`` of the nearest enclosing checkout
    (walk up from the cwd to the first directory holding a
    ``pyproject.toml``), else the legacy :data:`DEFAULT_STATE_PATH`
    (returned UNEXPANDED, as configured) when no repo marker exists above
    the cwd.  Pure lookup — never creates directories or files.
    """
    env_path = os.environ.get(STATE_PATH_ENV)
    if env_path:
        return Path(env_path).expanduser()
    here = Path.cwd()
    for candidate in [here, *here.parents]:
        if (candidate / _REPO_MARKER).is_file():
            return candidate / ".chimera" / "blocked-models.json"
    return Path(DEFAULT_STATE_PATH)


class _DefaultPath:
    """Sentinel type: ``state_path`` not given — resolve the default now."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<default-state-path>"


#: Module-import time no longer bakes in a path: resolution is deferred to
#: construction (the cwd can differ between import and use in tests/tools).
_DEFAULT_PATH = _DefaultPath()

#: Error-message signature of a guardrail/privacy/endpoint-availability
#: failure that should exclude the model from future candidate lists.
GUARDRAIL_ERROR_RE = re.compile(r"guardrail|no endpoints available|privacy", re.IGNORECASE)

#: Error-message signature of an authentication/authorization rejection: the
#: credential is present but invalid (expired key, wrong key, revoked key).
#: Deliberately narrow — it must NOT match timeouts, 429, 5xx, guardrail or
#: billing/quota wording, because those are either transient or a different
#: remedy.  ``\b`` boundaries keep ``401`` from matching inside other numbers
#: (e.g. ``1500``/``4012``).
CREDENTIAL_ERROR_RE = re.compile(
    r"authenticationerror"
    r"|permissiondeniederror"
    r"|\b401\b"
    r"|\bunauthorized\b"
    r"|invalid[ _-]*api[ _-]*key"
    r"|incorrect api key"
    r"|invalid[ _-]*key"
    r"|missing credentials"
    r"|user not found"
    r"|no auth credentials"
    r"|api key not valid"
    r"|authentication failed"
    r"|invalid bearer token",
    re.IGNORECASE,
)

#: Block classes recorded in ``reasons`` / used as the ``reason`` log field.
REASON_GUARDRAIL = "guardrail"
REASON_CREDENTIAL = "credential"

#: Persisted marker for a credential-class block recorded when NO credential
#: fingerprint could be resolved at all (DF-CHIMERA-V2-58: e.g. the engine
#: had no config, or the failing provider had no key configured).  Stored in
#: ``credential_fingerprints`` so the entry is distinguishable on load from a
#: legacy entry that simply has no fingerprint *data*: the marker means "the
#: failure happened without a resolvable credential", so ANY later non-None
#: fingerprint proves the situation changed and self-clears the stale block.
#: It is a constant, non-secret marker — never a credential, never a digest
#: of one.
NO_CREDENTIAL = "no-credential"


def is_guardrail_error(error: object) -> bool:
    """Return True when *error* looks like a guardrail/404-style rejection."""
    return bool(GUARDRAIL_ERROR_RE.search(str(error)))


def is_credential_error(error: object) -> bool:
    """Return True when *error* looks like an auth/authorization rejection.

    Covers the shapes LiteLLM/providers actually emit (``AuthenticationError``,
    ``401``, "User not found", "invalid api key", "Missing credentials", …)
    and nothing else: a timeout, a 429 or a 5xx is NOT a credential failure
    (see the module docstring for why the distinction matters).
    """
    return bool(CREDENTIAL_ERROR_RE.search(str(error)))


class ModelBlockRegistry:
    """Tracks models blocked by guardrail- or credential-class failures.

    State is persisted to *state_path* (JSON) whenever a block is recorded
    and reloaded on construction, so blocks survive process restarts.  Pass
    ``state_path=None`` to disable persistence entirely.
    """

    def __init__(
        self,
        *,
        cooldown_s: float = DEFAULT_BLOCK_COOLDOWN_S,
        clock: Callable[[], float] = time.monotonic,
        state_path: str | os.PathLike[str] | None | _DefaultPath = _DEFAULT_PATH,
    ) -> None:
        if isinstance(state_path, _DefaultPath):
            state_path = default_state_path()
            if str(state_path) == DEFAULT_STATE_PATH:
                warnings.warn(
                    "blocked-models state outside any repo checkout: falling back "
                    f"to the machine-scoped {DEFAULT_STATE_PATH}. Runs from a repo "
                    "checkout keep per-install state instead (set "
                    f"{STATE_PATH_ENV} to pin a location).",
                    UserWarning,
                    stacklevel=2,
                )
        self.cooldown_s = cooldown_s
        self._clock = clock
        self._state_path = Path(state_path).expanduser() if state_path is not None else None
        self._blocked_until: dict[str, float] = {}
        #: Block class per model ("guardrail" | "credential").
        self._reasons: dict[str, str] = {}
        #: Non-reversible credential digest per model (credentials only).
        self._fingerprints: dict[str, str | None] = {}
        self._load()

    def record_failure(
        self,
        model: str,
        error: object,
        credential_fingerprint: str | None = None,
    ) -> bool:
        """Record an upstream failure for *model*.

        Returns True when the failure was guardrail-class OR credential-class
        and the model is now blocked (and the block persisted); False for
        transient failures (timeouts, 429, 5xx — never recorded).

        *credential_fingerprint* is a non-reversible digest of the credential
        that produced the failure.  It is stored for credential-class blocks
        only, and only as a digest — never the key itself, never logged.
        ``None`` (no credential could be resolved for the failing model) is
        recorded as the :data:`NO_CREDENTIAL` marker instead of being dropped
        by ``_save`` — so the block can still self-heal when a later call
        supplies a real fingerprint (DF-CHIMERA-V2-58).
        """
        if is_guardrail_error(error):
            reason = REASON_GUARDRAIL
        elif is_credential_error(error):
            reason = REASON_CREDENTIAL
        else:
            return False
        until = self._clock() + self.cooldown_s
        self._blocked_until[model] = until
        self._reasons[model] = reason
        if reason == REASON_CREDENTIAL:
            self._fingerprints[model] = credential_fingerprint or NO_CREDENTIAL
        else:
            self._fingerprints[model] = None
        log.warning(
            "model_blocked_guardrail" if reason == REASON_GUARDRAIL else "model_blocked_credential",
            model=model,
            reason=reason,
            cooldown_s=self.cooldown_s,
            error=str(error)[:200],
        )
        self._save()
        return True

    def is_blocked(self, model: str, credential_fingerprint: str | None = None) -> bool:
        """True when *model* is currently inside its block cooldown.

        When the entry was recorded for a credential-class failure WITH a
        stored fingerprint — or with the :data:`NO_CREDENTIAL` marker, i.e.
        no credential was resolvable at record time — and the caller passes
        a *different* non-``None`` fingerprint, the block is stale (the
        credential was replaced, or one now exists where none did), so it is
        cleared and ``False`` is returned (DF-CHIMERA-V2-6 self-heal,
        DF-CHIMERA-V2-58 no-credential case).  Without a fingerprint
        argument, or with a matching one, TTL behaviour is unchanged.
        Legacy entries with no fingerprint value at all keep blocking.
        """
        until = self._blocked_until.get(model)
        if until is None:
            return False
        if self._clock() >= until:
            # Cooldown expired — clear the entry so the model is a candidate again.
            self._forget(model)
            return False
        if self._reasons.get(model) == REASON_CREDENTIAL and credential_fingerprint is not None:
            stored = self._fingerprints.get(model)
            if stored == NO_CREDENTIAL or (stored is not None and stored != credential_fingerprint):
                log.info(
                    "model_block_cleared_credential_changed",
                    model=model,
                    msg="provider credential changed — stale block cleared",
                )
                self._forget(model)
                self._save()
                return False
        return True

    def blocked(self) -> set[str]:
        """The set of currently-blocked model names (expired entries pruned)."""
        now = self._clock()
        expired = [m for m, until in self._blocked_until.items() if now >= until]
        for m in expired:
            self._forget(m)
        return set(self._blocked_until)

    def block_reason(self, model: str) -> str | None:
        """The class of the active block on *model*, or ``None`` when unblocked.

        Returns ``"guardrail"`` or ``"credential"``.  Legacy entries (state
        files written before reasons existed) are reported as ``"guardrail"``.
        """
        if not self.is_blocked(model):
            return None
        return self._reasons.get(model, REASON_GUARDRAIL)

    def credential_fingerprint(self, model: str) -> str | None:
        """The persisted credential digest for *model*, or ``None``.

        The digest is non-reversible (see :func:`chimera.config.
        provider_credential_fingerprint`); the credential itself is never
        stored or returned.  ``None`` also covers the deliberate
        :data:`NO_CREDENTIAL` case (a credential-class block recorded when no
        credential could be resolved) — the marker stays an internal,
        persistence-level detail and is never returned as a digest-shaped
        value.
        """
        stored = self._fingerprints.get(model)
        return None if stored == NO_CREDENTIAL else stored

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def state_file(self) -> Path | None:
        """The state file this registry persists to (``None`` = disabled).

        The CLI renders this instead of a hardcoded location, so an operator
        following the printed path always reaches the file actually read
        (CHIMERA-V2-REVIEW-03).
        """
        return self._state_path

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _forget(self, model: str) -> None:
        """Drop every trace of *model* from the in-memory registry."""
        self._blocked_until.pop(model, None)
        self._reasons.pop(model, None)
        self._fingerprints.pop(model, None)

    def _load(self) -> None:
        """Load persisted blocks, pruning expired entries.

        Missing or corrupt state files are not errors — the registry simply
        starts empty.  ``blocked_until_epoch`` is the load-bearing key and is
        read exactly as before; ``reasons`` / ``credential_fingerprints`` are
        optional additions (a pre-DF-CHIMERA-V2-6 state file loads fine and
        its entries count as guardrail blocks with no fingerprint).  The
        :data:`NO_CREDENTIAL` marker (DF-CHIMERA-V2-58) loads as a stored
        marker value; a legacy entry whose fingerprint is missing or empty
        loads as ``None`` and keeps the legacy never-self-clears behaviour.
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
        reasons_raw = data.get("reasons")
        reasons = reasons_raw if isinstance(reasons_raw, dict) else {}
        fingerprints_raw = data.get("credential_fingerprints")
        fingerprints = fingerprints_raw if isinstance(fingerprints_raw, dict) else {}
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
            reason = reasons.get(model)
            self._reasons[model] = (
                reason if reason in (REASON_GUARDRAIL, REASON_CREDENTIAL) else REASON_GUARDRAIL
            )
            fingerprint = fingerprints.get(model)
            self._fingerprints[model] = fingerprint if isinstance(fingerprint, str) and fingerprint else None

    def _save(self) -> None:
        """Persist current blocks as wall-clock expiry timestamps.

        Best-effort: a filesystem failure logs a warning but never breaks the
        deliberation that just recorded the block.  The credential digest is
        written here and nothing else about the credential — the key itself is
        never serialized.  The :data:`NO_CREDENTIAL` marker (DF-CHIMERA-V2-58)
        is a constant, non-secret string and is persisted so the deliberate
        no-credential case survives restarts and self-clears later; entries
        with no fingerprint value (legacy) are omitted, exactly as before.
        """
        if self._state_path is None:
            return
        now_wall = time.time()
        now_clock = self._clock()
        # No version field: the loader is field-driven (it reads exactly the
        # three keys below and ignores everything else), so a version tag is
        # dead weight — written by nothing, read by nothing. Verified 2026-09-22.
        payload = {
            "blocked_until_epoch": {
                model: now_wall + (until - now_clock) for model, until in self._blocked_until.items()
            },
            "reasons": {model: self._reasons.get(model, REASON_GUARDRAIL) for model in self._blocked_until},
            "credential_fingerprints": {
                model: self._fingerprints[model]
                for model in self._blocked_until
                if self._fingerprints.get(model)
            },
        }
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_name(self._state_path.name + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
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
    "CREDENTIAL_ERROR_RE",
    "DEFAULT_BLOCK_COOLDOWN_S",
    "DEFAULT_STATE_PATH",
    "GUARDRAIL_ERROR_RE",
    "NO_CREDENTIAL",
    "REASON_CREDENTIAL",
    "REASON_GUARDRAIL",
    "STATE_PATH_ENV",
    "ModelBlockRegistry",
    "default_state_path",
    "is_credential_error",
    "is_guardrail_error",
    "set_shared_registry",
    "shared_registry",
]
