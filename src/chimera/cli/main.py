"""Click + Rich CLI.

Usage::

    chimera "prompt"                  # full pipeline, auto formation
    chimera -f debate "prompt"        # specific formation
    chimera formations                # list formations
    chimera models                    # list models with weights
    chimera --verbose "prompt"        # print the full trace
    chimera serve                     # run the REST API
    chimera mcp                       # run the MCP server (stdio)
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from chimera.config import ChimeraConfig, load_config
from chimera.engine import Engine
from chimera.gateway import LiteLLMGateway

# When output is piped (tests, redirection), use a wide console so tables and
# model names never get truncated. Interactive use auto-detects the terminal.
console = Console(width=None if sys.stdout.isatty() else 200)


class ChimeraGroup(click.Group):
    """A group that treats an unknown first token as a deliberation prompt.

    This lets ``chimera "what is 2+2?"`` work while still supporting named
    subcommands like ``chimera formations``.
    """

    def resolve_command(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command(ctx, "run")
        return "run", run_cmd, list(args)


@click.group(cls=ChimeraGroup, invoke_without_command=True)
@click.option("-f", "--formation", default="auto", help="Formation preset name.")
@click.option("-v", "--verbose", is_flag=True, help="Print the full trace.")
@click.option("-c", "--config", "config_path", default=None, help="Path to chimera.yaml.")
@click.option(
    "--allow-custom-dag",
    is_flag=True,
    help="Accept a client-defined DAG (requires --dag).",
)
@click.option(
    "--dag",
    "dag_json",
    default=None,
    help="Client-defined DAG as a JSON string ({stages:[...], edges:[[a,b]]}).",
)
@click.option(
    "--stage-models",
    "stage_models_json",
    default=None,
    help='Per-stage model overrides as JSON (e.g. \'{"worker_1":"zai-coding-plan/glm-5.2"}\').',
)
@click.pass_context
def main(
    ctx: click.Context,
    formation: str,
    verbose: bool,
    config_path: str | None,
    allow_custom_dag: bool,
    dag_json: str | None,
    stage_models_json: str | None,
) -> None:
    """Chimera — dynamic multi-model deliberation gateway."""
    ctx.obj = {
        "formation": formation,
        "verbose": verbose,
        "config_path": config_path,
        "allow_custom_dag": allow_custom_dag,
        "dag": _parse_json_opt(dag_json, "dag"),
        "stage_models": _parse_json_opt(stage_models_json, "stage-models"),
    }
    # Bare empty invocation (no subcommand, no prompt) → show help.
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit()


def _parse_json_opt(value: str | None, opt_name: str) -> Any:
    """Parse a CLI JSON option; ``None`` passes through untouched."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"--{opt_name} must be valid JSON: {exc}") from exc


def _load_cfg(ctx: click.Context) -> ChimeraConfig:
    config_path = ctx.obj.get("config_path") if ctx.obj else None
    return load_config(config_path)


def _deliberate(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        click.echo(ctx.get_help())
        return
    try:
        config = _load_cfg(ctx)
    except FileNotFoundError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    engine = Engine(config, LiteLLMGateway(config))
    # Only forward the new kwargs when they are actually set, so the default
    # call shape stays ``deliberate(prompt, formation)`` (backward compatible).
    extra_kwargs: dict[str, Any] = {}
    stage_models = ctx.obj.get("stage_models")
    dag = ctx.obj.get("dag")
    allow_custom_dag = ctx.obj.get("allow_custom_dag", False)
    if stage_models:
        from chimera.config import DeliberationOverrides

        extra_kwargs["overrides"] = DeliberationOverrides(stage_models=stage_models)
    if dag is not None:
        extra_kwargs["dag"] = dag
        extra_kwargs["allow_custom_dag"] = allow_custom_dag
    try:
        result = asyncio.run(
            engine.deliberate(prompt, ctx.obj["formation"], **extra_kwargs)
        )
    except ValueError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    console.print(Panel(result.answer, title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def _print_trace(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("latency", justify="right")
    table.add_column("cost", justify="right")

    def row(span: Any) -> None:
        table.add_row(
            span.stage_id,
            span.kind,
            span.model,
            str(span.tokens_input + span.tokens_output),
            f"{span.latency_ms}ms",
            f"${span.cost:.6f}",
        )

    row(trace.dispatch)
    for span in trace.stages:
        row(span)
    console.print(table)
    console.print(
        f"total: {trace.total_tokens} tokens, "
        f"{trace.total_duration_ms}ms, ${trace.total_cost:.6f} "
        f"(source={trace.source}, answer_stage={trace.answer_stage_id})"
    )
    console.print(
        Panel(
            json.dumps(trace.model_dump(mode="json"), indent=2),
            title="full trace json",
            border_style="dim",
        )
    )


@main.command()
@click.argument("prompt", nargs=-1)
@click.pass_context
def run(ctx: click.Context, prompt: tuple[str, ...]) -> None:
    """Run a full deliberation for PROMPT (default when no subcommand given)."""
    _deliberate(ctx, prompt)


@main.command()
@click.pass_context
def formations(ctx: click.Context) -> None:
    """List available formation presets."""
    config = _load_cfg(ctx)
    table = Table(title="Formations")
    table.add_column("name", style="bold")
    table.add_column("definition")
    for name, preset in config.formations.items():
        table.add_row(name, json.dumps(preset.model_dump(exclude_none=True)))
    console.print(table)


@main.command()
@click.pass_context
def models(ctx: click.Context) -> None:
    """List available models with category weights."""
    config = _load_cfg(ctx)
    categories: set[str] = set()
    for entry in config.models.values():
        categories.update(entry.categories.keys())
    sorted_cats = sorted(categories)
    table = Table(title="Models")
    table.add_column("model", style="bold")
    table.add_column("provider")
    table.add_column("tier")
    for cat in sorted_cats:
        table.add_column(cat, justify="right")
    for name, entry in config.models.items():
        table.add_row(
            name,
            entry.provider,
            entry.cost_tier,
            *(f"{entry.categories.get(cat, 0):.2f}" for cat in sorted_cats),
        )
    console.print(table)


@main.command()
@click.pass_context
def serve(ctx: click.Context) -> None:
    """Run the REST API server."""
    from chimera.api.server import run as run_api

    config = _load_cfg(ctx)
    run_api(config.server.host, config.server.port)


@main.command()
@click.pass_context
def mcp(ctx: click.Context) -> None:
    """Run the MCP server over stdio."""
    from chimera.mcp.server import run as run_mcp

    run_mcp(ctx.obj.get("config_path") if ctx.obj else None)


if __name__ == "__main__":
    main()
