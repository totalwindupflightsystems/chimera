"""Chimera — dynamic multi-model deliberation gateway.

Public core API. The optional interfaces (REST API, CLI, MCP) live in
``chimera.api``, ``chimera.cli`` and ``chimera.mcp`` and import their own
extra dependencies lazily.
"""

from __future__ import annotations

from importlib.metadata import (
    PackageNotFoundError as _PackageNotFoundError,
)
from importlib.metadata import (
    version as _dist_version,
)
from typing import Any as _Any

from chimera.aggregator import Aggregator
from chimera.config import (
    ChimeraConfig,
    Defaults,
    FormationPreset,
    ModelEntry,
    Provider,
    load_config,
)
from chimera.dispatcher import (
    Dispatcher,
    DispatchOutcome,
    DispatchResult,
    FormationDAG,
    Stage,
    WorkerPrompt,
)
from chimera.engine import DeliberationResult, DeliberationTrace, Engine, StageSpan
from chimera.exceptions import BudgetExhaustedError
from chimera.gateway import Gateway, GatewayResponse, LiteLLMGateway


def __getattr__(name: str) -> _Any:
    """Lazily resolve ``trace_to_mermaid`` (PEP 562).

    Importing the core package must NOT pull in ``chimera.web`` (FastAPI,
    SSE, session store) — those live in the ``[server]``/``[full]`` extras.
    The web symbol is only materialized on first attribute access, so a
    bare ``pip install chimera-deliberation`` + ``from chimera import
    Engine`` works without fastapi installed (CH-GAP-026).
    """
    if name == "trace_to_mermaid":
        from chimera.web.trace_viz import trace_to_mermaid

        return trace_to_mermaid
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# Single source of truth for the version: pyproject.toml (via installed dist
# metadata). The fallback only fires for source-tree runs where the
# ``chimera-deliberation`` dist metadata is missing.
_FALLBACK_VERSION = "0.2.1"

try:
    __version__ = _dist_version("chimera-deliberation")
except _PackageNotFoundError:
    __version__ = _FALLBACK_VERSION

__all__ = [
    "Aggregator",
    "BudgetExhaustedError",
    "ChimeraConfig",
    "Defaults",
    "DeliberationResult",
    "DeliberationTrace",
    "DispatchOutcome",
    "DispatchResult",
    "Dispatcher",
    "Engine",
    "FormationDAG",
    "FormationPreset",
    "Gateway",
    "GatewayResponse",
    "LiteLLMGateway",
    "ModelEntry",
    "Provider",
    "Stage",
    "StageSpan",
    "WorkerPrompt",
    "load_config",
    "trace_to_mermaid",
    "__version__",
]
