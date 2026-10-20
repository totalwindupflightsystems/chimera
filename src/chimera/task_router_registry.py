"""Portable adapter for task-router's generated model registry.

The adapter intentionally depends only on the JSONL wire format.  Chimera wheels
must remain usable without the task-router Python package or checkout.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import structlog

TASK_ROUTER_MODELS_ENV = "CHIMERA_TASK_ROUTER_MODELS_PATH"
TASK_ROUTER_HOME_ENV = "TASK_ROUTER_HOME"

log = structlog.get_logger("chimera.task_router_registry")

#: Registry location inside a task-router checkout.
TASK_ROUTER_REGISTRY_RELATIVE_PATH = Path("data") / "tables" / "models.jsonl"

# Public provider metadata only.  These values preserve Chimera's existing
# environment-variable discovery; no credential values are read from or added
# to the task-router registry.
_PROVIDER_METADATA: dict[str, dict[str, Any]] = {
    "anthropic": {
        "env": ["ANTHROPIC_API_KEY"],
        "api": "https://api.anthropic.com/v1",
    },
    "deepseek": {
        "env": ["DEEPSEEK_API_KEY"],
        "api": "https://api.deepseek.com/v1",
    },
    "google": {
        "env": ["GEMINI_API_KEY"],
        "api": "https://generativelanguage.googleapis.com/v1beta",
    },
    "minimax": {
        "env": ["MINIMAX_API_KEY"],
        "api": "https://api.minimax.io/v1",
    },
    "openai": {
        "env": ["OPENAI_API_KEY"],
        "api": "https://api.openai.com/v1",
    },
    "openrouter": {
        "env": ["OPENROUTER_API_KEY"],
        "api": "https://openrouter.ai/api/v1",
    },
    "stepfun": {
        "env": ["STEPFUN_API_KEY"],
        "api": "https://api.stepfun.ai/v1",
    },
    "xai": {
        "env": ["XAI_API_KEY"],
        "api": "https://api.x.ai/v1",
    },
}


class TaskRouterRegistryError(ValueError):
    """The preferred task-router registry cannot be used safely."""


def _candidate_paths() -> list[Path]:
    """Return task-router table candidates in precedence order.

    An explicit file override is authoritative, including when it points to a
    missing file: callers need a clear diagnostic instead of silently reading a
    different checkout.  Otherwise use an optional task-router home followed by
    portable sibling/home checkout conventions.
    """
    explicit = os.environ.get(TASK_ROUTER_MODELS_ENV)
    if explicit:
        return [Path(explicit).expanduser()]

    candidates: list[Path] = []
    home = _home_checkout()
    if home is not None:
        candidates.append(home / TASK_ROUTER_REGISTRY_RELATIVE_PATH)

    home_candidate = Path.home() / "task-router" / TASK_ROUTER_REGISTRY_RELATIVE_PATH
    package_sibling = Path(__file__).resolve().parents[3] / "task-router" / TASK_ROUTER_REGISTRY_RELATIVE_PATH
    for candidate in (home_candidate, package_sibling):
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _home_checkout() -> Path | None:
    """Return the checkout named by ``TASK_ROUTER_HOME``, or ``None`` when unset."""
    task_router_home = os.environ.get(TASK_ROUTER_HOME_ENV)
    if not task_router_home:
        return None
    return Path(task_router_home).expanduser()


def _warn_home_registry_missing(home: Path, missing: Path, selected: Path | None) -> None:
    """Report an unusable ``TASK_ROUTER_HOME`` at the authoritative-var level.

    ``CHIMERA_TASK_ROUTER_MODELS_PATH`` is authoritative and raises when it
    points at a missing file, which its callers log as a WARNING.  A
    ``TASK_ROUTER_HOME`` checkout is only the FIRST candidate prefix, so a home
    without ``data/tables/models.jsonl`` keeps probing the portable home/sibling
    locations — that substitution must never be silent (DF-CHIMERA-V2-94), or an
    operator who named a checkout cannot tell which registry was really read.
    The selected table is named in the event AND in the human-readable reason.
    """
    outcome = "no fallback checkout was found" if selected is None else f"selected {selected} instead"
    log.warning(
        "task_router_home_registry_missing",
        env=TASK_ROUTER_HOME_ENV,
        home=str(home),
        missing=str(missing),
        fallback=None if selected is None else str(selected),
        reason=f"{TASK_ROUTER_HOME_ENV} checkout has no registry: {missing}; {outcome}",
    )


def locate_task_router_models() -> Path:
    """Locate the preferred JSONL table or raise an actionable error.

    The first existing candidate wins.  A ``TASK_ROUTER_HOME`` checkout whose
    own registry is missing is announced at WARNING level naming the table that
    was selected instead; an explicit file override remains authoritative and
    never consults the home variable at all.
    """
    explicit = os.environ.get(TASK_ROUTER_MODELS_ENV)
    candidates = _candidate_paths()
    home = None if explicit else _home_checkout()
    home_registry = None if home is None else home / TASK_ROUTER_REGISTRY_RELATIVE_PATH

    for path in candidates:
        if path.is_file():
            if home_registry is not None and path != home_registry:
                _warn_home_registry_missing(home, home_registry, path)
            return path

    if explicit:
        raise TaskRouterRegistryError(f"configured table does not exist: {candidates[0]}")
    if home_registry is not None:
        _warn_home_registry_missing(home, home_registry, None)
    tried = ", ".join(str(path) for path in candidates)
    raise TaskRouterRegistryError(f"task-router table not found (tried: {tried})")


def _is_live(row: dict[str, Any]) -> bool:
    """Return whether a task-router row is an active registry entry."""
    return not row.get("archive") and not row.get("disabled") and row.get("valid_to") is None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def load_task_router_registry(path: Path | str | None = None) -> dict[str, Any]:
    """Translate task-router JSONL into the subset of models.dev Chimera reads.

    The whole file is validated before a registry is returned. One malformed or
    unsupported row invalidates the preferred source so the caller can fall back
    to models.dev instead of accepting a misleading partial catalog.
    """
    table = Path(path).expanduser() if path is not None else locate_task_router_models()
    try:
        lines = table.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise TaskRouterRegistryError(f"cannot read {table}: {exc}") from exc

    registry: dict[str, Any] = {}
    seen: set[tuple[str, str]] = set()
    live_rows = 0

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TaskRouterRegistryError(f"malformed JSON in {table} line {line_number}: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise TaskRouterRegistryError(
                f"unsupported row in {table} line {line_number}: expected an object"
            )

        provider = row.get("provider")
        model = row.get("model")
        if not isinstance(provider, str) or not provider.strip():
            raise TaskRouterRegistryError(
                f"unsupported row in {table} line {line_number}: provider must be a string"
            )
        if not isinstance(model, str) or not model.strip():
            raise TaskRouterRegistryError(
                f"unsupported row in {table} line {line_number}: model must be a string"
            )
        if not _is_live(row):
            continue

        key = (provider, model)
        if key in seen:
            raise TaskRouterRegistryError(
                f"unsupported duplicate live row in {table} line {line_number}: {provider}/{model}"
            )
        seen.add(key)
        live_rows += 1

        provider_entry = registry.setdefault(
            provider,
            {"id": provider, "models": {}, **_PROVIDER_METADATA.get(provider, {})},
        )
        model_entry: dict[str, Any] = {
            "id": model,
            "family": "",
        }

        public_input = _number(row.get("public_in_per_m"))
        public_output = _number(row.get("public_out_per_m"))
        if public_input is not None and public_output is not None:
            model_entry["cost"] = {"input": public_input, "output": public_output}

        release_date = row.get("available_from") or row.get("valid_from")
        if isinstance(release_date, str) and release_date:
            model_entry["release_date"] = release_date

        provider_entry["models"][model] = model_entry

    if live_rows == 0:
        raise TaskRouterRegistryError(f"task-router table has no live supported rows: {table}")
    return registry


__all__ = [
    "TASK_ROUTER_HOME_ENV",
    "TASK_ROUTER_MODELS_ENV",
    "TASK_ROUTER_REGISTRY_RELATIVE_PATH",
    "TaskRouterRegistryError",
    "load_task_router_registry",
    "locate_task_router_models",
]
