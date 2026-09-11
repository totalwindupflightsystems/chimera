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
import shutil
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from chimera.config import ChimeraConfig, FormationPreset, Observability, load_config
from chimera.engine import Engine
from chimera.gateway import LiteLLMGateway
from chimera.observability import configure_logging

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
    """Load the config, failing with a clean one-line error when missing.

    CH-GAP-050: a fresh dir with no ``chimera.yaml`` used to surface a raw
    FileNotFoundError traceback from every config-needing command. Now the
    missing-config case prints the actionable one-liner and exits 2
    (``chimera config init`` is the remedy).

    DF-CHIMERA-V2-3 (CLI stdout purity): the CLI never called
    ``configure_logging``, so provider auto-discovery (which runs INSIDE
    ``load_config`` → ``_apply_env_overrides``) hit structlog's unconfigured
    default and wrote ``provider_cache_hit`` / ``provider_fetch_ok`` /
    ``provider_discovery_done`` straight onto stdout, ahead of the rich
    table/panel. Two-phase pin, mirroring ``mcp/server.py`` (DF-CHIMERA-0906-2):

    * phase 1 — BEFORE ``load_config``: pin every log sink to stderr with a
      minimal ``Observability(use_stdout=False)`` so pre-config discovery
      logs can never touch stdout;
    * phase 2 — after a successful load: re-pin with the REAL observability
      settings (log_level/langfuse), still forced to stderr.

    ``force_stderr=True`` is structural: it overrides a chimera.yaml
    ``observability.use_stdout: true``, so CLI stdout purity cannot be
    undone by a config flip. Logs still work — on stderr.
    """
    # Phase 1: pre-config pin (catches provider-discovery logs during load).
    configure_logging(Observability(use_stdout=False), force_stderr=True)
    config_path = ctx.obj.get("config_path") if ctx.obj else None
    try:
        cfg = load_config(config_path)
    except FileNotFoundError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    # Phase 2: re-pin with the real observability config — still stderr.
    configure_logging(cfg.observability, force_stderr=True)
    return cfg


def _deliberate(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        click.echo(ctx.get_help())
        return
    config = _load_cfg(ctx)
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
    _print_worker_failures(result)
    _print_dispatch_degradation(result)
    console.print(Panel(result.answer, title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def _print_worker_failures(result: Any) -> None:
    """Warn (always, not just --verbose) when worker stages were dropped.

    A degraded worker still lets the deliberation produce an answer, but the
    user must know the panel is partial — otherwise a guardrail/404 failure
    is silent outside the structlog stream.
    """
    failures = getattr(getattr(result, "trace", None), "worker_failures", None) or []
    for failure in failures:
        stage_id = getattr(failure, "stage_id", "?")
        model = getattr(failure, "model", "?")
        error = str(getattr(failure, "error", "") or "unknown error")
        if len(error) > 200:
            error = error[:197] + "..."
        console.print(
            f"[yellow]warning:[/yellow] worker '{stage_id}' ({model}) "
            f"failed: {error}"
        )


def _print_dispatch_degradation(result: Any) -> None:
    """Warn (always, not just --verbose) when the dispatch degraded.

    Two degradation classes surface here:

    * ``trace.source == \"fallback\"`` — the dispatcher plan was discarded
      and the deliberation collapsed to a generic single-worker formation.
      The answer may look fine; this is the ONLY signal (CH-GAP-044).
    * a repair note (``dispatch_note`` containing \"repaired\"/\"injected\") —
      the dispatcher's DAG was structurally repaired (e.g. an aggregator
      stage referenced by edges but missing from stages was injected), so
      the design survived but the user should know it was patched.
    """
    trace = getattr(result, "trace", None)
    if trace is None:
        return
    source = getattr(trace, "source", None)
    note = getattr(trace, "dispatch_note", None)
    if source == "fallback":
        reason = note or "unknown reason"
        console.print(
            f"[yellow]warning:[/yellow] dispatch degraded — source=fallback "
            f"({reason}); the deliberation collapsed to a generic "
            f"single-worker formation"
        )
    elif note and ("repaired" in note or "injected" in note):
        console.print(f"[yellow]warning:[/yellow] dispatch repaired: {note}")


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
    note = ""
    dispatch_note = getattr(trace, "dispatch_note", None)
    if dispatch_note:
        note = f", note={dispatch_note}"
    source = getattr(trace, "source", "?")
    source_str = f"[red]source={source}[/red]" if source == "fallback" else f"source={source}"
    console.print(
        f"total: {trace.total_tokens} tokens, "
        f"{trace.total_duration_ms}ms, ${trace.total_cost:.6f} "
        f"({source_str}, answer_stage={trace.answer_stage_id}{note})"
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


def _summarize_preset(preset: FormationPreset) -> str:
    """One-line human-readable summary of a formation preset (DF-CHIMERA-V2-2).

    Replaces the raw ``json.dumps`` blob that rich truncated illegibly.
    """
    d = preset.model_dump(exclude_none=True)
    dag = d.get("dag")
    parts: list[str] = []
    if dag is not None:
        parts.append(f"dag: {len(dag.get('stages', []))} stages")
    if d.get("workers") is not None:
        parts.append(f"workers={d['workers']}")
    if d.get("mode") is not None:
        parts.append(f"mode={d['mode']}")
    for key in ("aggregator", "audit", "merge"):
        if d.get(key) is not None:
            parts.append(f"{key}={d[key]}")
    # ", " joins (not bare ",") keep the tokens breakable so rich WRAPS the
    # definition across lines at 80 columns instead of cropping it.
    if d.get("aggregators"):
        parts.append("aggregators=" + ", ".join(d["aggregators"]))
    if d.get("worker_models"):
        parts.append("worker_models=" + ", ".join(d["worker_models"]))
    return "; ".join(parts) if parts else "(empty)"


@main.command()
@click.pass_context
def formations(ctx: click.Context) -> None:
    """List available formation presets."""
    config = _load_cfg(ctx)
    table = Table(title="Formations")
    table.add_column("name", style="bold")
    table.add_column("definition")
    for name, preset in config.formations.items():
        table.add_row(name, _summarize_preset(preset))
    console.print(table)


@main.command()
@click.pass_context
def models(ctx: click.Context) -> None:
    """List available models with category weights."""
    config = _load_cfg(ctx)

    # DF-CHIMERA-V2-2: the old table added one column per category (32+ in the
    # shipped config), so an 80-column terminal truncated every cell to ~3
    # characters ("mo…", "pr…") — nothing legible. Render two tables instead:
    #
    # 1. an overview (model / provider / tier) — the three identity columns
    #    alone need only ~62 columns at natural width, so names stay fully
    #    legible even at 80 columns;
    # 2. the weight matrix TRANSPOSED: one row per (model, category) instead
    #    of one column per category — a fixed 4-column layout at any catalog
    #    size. Long model·category rows are combined into ONE foldable cell
    #    (rich wraps a single long cell across lines instead of cropping) and
    #    weights sort strongest-first per model, so truncation never returns
    #    as the catalog grows.
    table = Table(title="Models")
    table.add_column("model", style="bold", no_wrap=True)
    table.add_column("provider", no_wrap=True)
    table.add_column("tier", no_wrap=True)
    for name, entry in config.models.items():
        table.add_row(name, entry.provider, entry.cost_tier)
    console.print(table)

    detail = Table(title="Category weights (model · category)")
    detail.add_column("model · category", no_wrap=False)
    detail.add_column("weight", justify="right", no_wrap=True)
    for name, entry in config.models.items():
        pairs = sorted(
            entry.categories.items(), key=lambda kv: (-kv[1], kv[0])
        )
        for cat, weight in pairs:
            detail.add_row(f"{name} · {cat}", f"{weight:.2f}")
    console.print(detail)


@main.command()
@click.option(
    "--host",
    default=None,
    help="Bind address (default: from config or CHIMERA_HOST env var).",
)
@click.option(
    "--port",
    type=int,
    default=None,
    help="Bind port (default: from config or CHIMERA_PORT env var).",
)
@click.pass_context
def serve(ctx: click.Context, host: str | None, port: int | None) -> None:
    """Run the REST API server."""
    import os as _os

    # Load the config BEFORE importing the API server module: the config-less
    # error must be the clean one-liner even on bare wheels where the
    # [server] extra (fastapi/uvicorn) is not installed (CH-GAP-050).
    config = _load_cfg(ctx)

    from chimera.api.server import run as run_api

    host = host or _os.environ.get("CHIMERA_HOST") or config.server.host
    port = port or int(_os.environ.get("CHIMERA_PORT", 0)) or config.server.port
    run_api(host, port)


@main.command()
@click.pass_context
def mcp(ctx: click.Context) -> None:
    """Run the MCP server over stdio."""
    from chimera.mcp.server import run as run_mcp

    run_mcp(
        ctx.obj.get("config_path") if ctx.obj else None,
        parse_argv=False,  # click owns argv; sys.argv[1] is 'mcp', not a path
    )


@main.group()
def config() -> None:
    """Configuration helpers."""


@config.command("init")
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite an existing chimera.yaml.",
)
def config_init(force: bool) -> None:
    """Bootstrap chimera.yaml from the shipped chimera.yaml.example.

    CH-GAP-050: the first-run dead-end was that every config-needing
    command crashed with a raw traceback when chimera.yaml was missing —
    and the error's own remedy (\"Copy chimera.yaml.example to
    chimera.yaml\") was impossible for pip users because the example file
    was not in the wheel. This command performs the copy for them, using
    the wheel-shipped template (CH-GAP-049 force-include) when no local
    copy exists.
    """
    target = Path("chimera.yaml")
    if target.exists() and not force:
        console.print(
            "[red]error:[/red] chimera.yaml already exists. "
            "Use --force to overwrite it."
        )
        sys.exit(2)
    from chimera.config import find_example_config_path

    try:
        example = find_example_config_path()
    except FileNotFoundError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    shutil.copyfile(example, target)
    console.print(f"[green]Created {target}[/green] from {example}.")


if __name__ == "__main__":
    main()
