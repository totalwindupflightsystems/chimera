"""MCP server exposing Chimera as tools for agents (e.g. Hermes).

Tools:
* ``chimera_deliberate(prompt, formation?)`` — full deliberation pipeline.
* ``chimera_formations()``                   — list formation presets.
* ``chimera_models()``                        — list models with weights.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from chimera.config import ChimeraConfig, load_config
from chimera.engine import Engine
from chimera.gateway import LiteLLMGateway
from chimera.observability import configure_logging


def build_server(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastMCP:
    """Construct the MCP ``FastMCP`` server.

    ``config``/``engine`` are injectable for tests.
    """
    cfg = config or load_config()
    configure_logging(cfg.observability)
    server = FastMCP("chimera")
    state = {"engine": engine or Engine(cfg, LiteLLMGateway(cfg)), "config": cfg}

    @server.tool()
    async def chimera_deliberate(
        prompt: str,
        formation: str = "auto",
        stage_models: dict[str, str] | None = None,
        dag: dict[str, Any] | None = None,
        allow_custom_dag: bool = False,
    ) -> str:
        """Run a full multi-model deliberation and return the merged answer + trace.

        ``stage_models`` forces models per stage (stage_id → model).
        ``dag`` defines a full client DAG (requires ``allow_custom_dag=True``).
        """
        from chimera.config import DeliberationOverrides

        overrides = DeliberationOverrides(stage_models=stage_models)
        result = await state["engine"].deliberate(
            prompt,
            formation,
            overrides=overrides,
            dag=dag,
            allow_custom_dag=allow_custom_dag,
        )
        return json.dumps(
            {"answer": result.answer, "trace": result.trace.model_dump(mode="json")},
            indent=2,
        )

    @server.tool()
    async def chimera_formations() -> str:
        """List the available formation presets."""
        cfg: ChimeraConfig = state["config"]
        return json.dumps(
            {
                name: preset.model_dump(exclude_none=True)
                for name, preset in cfg.formations.items()
            },
            indent=2,
        )

    @server.tool()
    async def chimera_models() -> str:
        """List the available models with their category weights."""
        cfg: ChimeraConfig = state["config"]
        return json.dumps(
            {
                name: {
                    "categories": entry.categories,
                    "cost_tier": entry.cost_tier,
                    "provider": entry.provider,
                }
                for name, entry in cfg.models.items()
            },
            indent=2,
        )

    return server


def run(config_path: str | None = None) -> None:
    """Run the MCP server over stdio.

    Accepts an optional config path as the first CLI argument, or falls
    back to ``find_config_path()`` (walks up from CWD).
    """
    import sys
    if config_path is None and len(sys.argv) > 1:
        config_path = sys.argv[1]
    config = load_config(config_path)
    server = build_server(config)
    server.run()


__all__ = ["build_server", "run"]
