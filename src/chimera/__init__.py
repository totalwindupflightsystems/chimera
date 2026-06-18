"""Chimera — dynamic multi-model deliberation gateway.

Public core API. The optional interfaces (REST API, CLI, MCP) live in
``chimera.api``, ``chimera.cli`` and ``chimera.mcp`` and import their own
extra dependencies lazily.
"""

from __future__ import annotations

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

__version__ = "0.1.0"

__all__ = [
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
    "Judge",
    "LiteLLMGateway",
    "ModelEntry",
    "Provider",
    "Stage",
    "StageSpan",
    "WorkerPrompt",
    "__version__",
    "load_config",
]
