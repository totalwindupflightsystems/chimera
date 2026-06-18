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


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict
mutants_xǁChimeraGroupǁresolve_command__mutmut: MutantDict = {}  # type: ignore


class ChimeraGroup(click.Group):
    """A group that treats an unknown first token as a deliberation prompt.

    This lets ``chimera "what is 2+2?"`` work while still supporting named
    subcommands like ``chimera formations``.
    """

    @_mutmut_mutated(mutants_xǁChimeraGroupǁresolve_command__mutmut)
    def resolve_command(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command(ctx, "run")
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_orig(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command(ctx, "run")
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_1(self, ctx: click.Context, args: list[str]):
        cmd_name = None
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command(ctx, "run")
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_2(self, ctx: click.Context, args: list[str]):
        cmd_name = args[1] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command(ctx, "run")
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_3(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else "XXXX"
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command(ctx, "run")
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_4(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name not in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command(ctx, "run")
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_5(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(None, args)
        run_cmd = self.get_command(ctx, "run")
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_6(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, None)
        run_cmd = self.get_command(ctx, "run")
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_7(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(args)
        run_cmd = self.get_command(ctx, "run")
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_8(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, )
        run_cmd = self.get_command(ctx, "run")
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_9(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = None
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_10(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command(None, "run")
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_11(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command(ctx, None)
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_12(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command("run")
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_13(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command(ctx, )
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_14(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command(ctx, "XXrunXX")
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_15(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command(ctx, "RUN")
        return "run", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_16(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command(ctx, "run")
        return "XXrunXX", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_17(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command(ctx, "run")
        return "RUN", run_cmd, list(args)

    def xǁChimeraGroupǁresolve_command__mutmut_18(self, ctx: click.Context, args: list[str]):
        cmd_name = args[0] if args else ""
        if cmd_name in self.commands:
            return super().resolve_command(ctx, args)
        run_cmd = self.get_command(ctx, "run")
        return "run", run_cmd, list(None)

mutants_xǁChimeraGroupǁresolve_command__mutmut['_mutmut_orig'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_orig # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_1'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_1 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_2'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_2 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_3'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_3 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_4'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_4 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_5'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_5 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_6'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_6 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_7'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_7 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_8'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_8 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_9'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_9 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_10'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_10 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_11'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_11 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_12'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_12 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_13'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_13 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_14'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_14 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_15'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_15 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_16'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_16 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_17'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_17 # type: ignore # mutmut generated
mutants_xǁChimeraGroupǁresolve_command__mutmut['xǁChimeraGroupǁresolve_command__mutmut_18'] = ChimeraGroup.xǁChimeraGroupǁresolve_command__mutmut_18 # type: ignore # mutmut generated


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
mutants_x__parse_json_opt__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x__parse_json_opt__mutmut)
def _parse_json_opt(value: str | None, opt_name: str) -> Any:
    """Parse a CLI JSON option; ``None`` passes through untouched."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"--{opt_name} must be valid JSON: {exc}") from exc


def x__parse_json_opt__mutmut_orig(value: str | None, opt_name: str) -> Any:
    """Parse a CLI JSON option; ``None`` passes through untouched."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"--{opt_name} must be valid JSON: {exc}") from exc


def x__parse_json_opt__mutmut_1(value: str | None, opt_name: str) -> Any:
    """Parse a CLI JSON option; ``None`` passes through untouched."""
    if value is not None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"--{opt_name} must be valid JSON: {exc}") from exc


def x__parse_json_opt__mutmut_2(value: str | None, opt_name: str) -> Any:
    """Parse a CLI JSON option; ``None`` passes through untouched."""
    if value is None:
        return None
    try:
        return json.loads(None)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"--{opt_name} must be valid JSON: {exc}") from exc


def x__parse_json_opt__mutmut_3(value: str | None, opt_name: str) -> Any:
    """Parse a CLI JSON option; ``None`` passes through untouched."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(None) from exc

mutants_x__parse_json_opt__mutmut['_mutmut_orig'] = x__parse_json_opt__mutmut_orig # type: ignore # mutmut generated
mutants_x__parse_json_opt__mutmut['x__parse_json_opt__mutmut_1'] = x__parse_json_opt__mutmut_1 # type: ignore # mutmut generated
mutants_x__parse_json_opt__mutmut['x__parse_json_opt__mutmut_2'] = x__parse_json_opt__mutmut_2 # type: ignore # mutmut generated
mutants_x__parse_json_opt__mutmut['x__parse_json_opt__mutmut_3'] = x__parse_json_opt__mutmut_3 # type: ignore # mutmut generated
mutants_x__load_cfg__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x__load_cfg__mutmut)
def _load_cfg(ctx: click.Context) -> ChimeraConfig:
    config_path = ctx.obj.get("config_path") if ctx.obj else None
    return load_config(config_path)


def x__load_cfg__mutmut_orig(ctx: click.Context) -> ChimeraConfig:
    config_path = ctx.obj.get("config_path") if ctx.obj else None
    return load_config(config_path)


def x__load_cfg__mutmut_1(ctx: click.Context) -> ChimeraConfig:
    config_path = None
    return load_config(config_path)


def x__load_cfg__mutmut_2(ctx: click.Context) -> ChimeraConfig:
    config_path = ctx.obj.get(None) if ctx.obj else None
    return load_config(config_path)


def x__load_cfg__mutmut_3(ctx: click.Context) -> ChimeraConfig:
    config_path = ctx.obj.get("XXconfig_pathXX") if ctx.obj else None
    return load_config(config_path)


def x__load_cfg__mutmut_4(ctx: click.Context) -> ChimeraConfig:
    config_path = ctx.obj.get("CONFIG_PATH") if ctx.obj else None
    return load_config(config_path)


def x__load_cfg__mutmut_5(ctx: click.Context) -> ChimeraConfig:
    config_path = ctx.obj.get("config_path") if ctx.obj else None
    return load_config(None)

mutants_x__load_cfg__mutmut['_mutmut_orig'] = x__load_cfg__mutmut_orig # type: ignore # mutmut generated
mutants_x__load_cfg__mutmut['x__load_cfg__mutmut_1'] = x__load_cfg__mutmut_1 # type: ignore # mutmut generated
mutants_x__load_cfg__mutmut['x__load_cfg__mutmut_2'] = x__load_cfg__mutmut_2 # type: ignore # mutmut generated
mutants_x__load_cfg__mutmut['x__load_cfg__mutmut_3'] = x__load_cfg__mutmut_3 # type: ignore # mutmut generated
mutants_x__load_cfg__mutmut['x__load_cfg__mutmut_4'] = x__load_cfg__mutmut_4 # type: ignore # mutmut generated
mutants_x__load_cfg__mutmut['x__load_cfg__mutmut_5'] = x__load_cfg__mutmut_5 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x__deliberate__mutmut)
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


def x__deliberate__mutmut_orig(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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


def x__deliberate__mutmut_1(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = None
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


def x__deliberate__mutmut_2(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(None).strip()
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


def x__deliberate__mutmut_3(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = "XX XX".join(prompt_parts).strip()
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


def x__deliberate__mutmut_4(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if prompt:
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


def x__deliberate__mutmut_5(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        click.echo(None)
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


def x__deliberate__mutmut_6(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        click.echo(ctx.get_help())
        return
    try:
        config = None
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


def x__deliberate__mutmut_7(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        click.echo(ctx.get_help())
        return
    try:
        config = _load_cfg(None)
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


def x__deliberate__mutmut_8(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        click.echo(ctx.get_help())
        return
    try:
        config = _load_cfg(ctx)
    except FileNotFoundError as exc:
        console.print(None)
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


def x__deliberate__mutmut_9(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        click.echo(ctx.get_help())
        return
    try:
        config = _load_cfg(ctx)
    except FileNotFoundError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(None)
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


def x__deliberate__mutmut_10(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        click.echo(ctx.get_help())
        return
    try:
        config = _load_cfg(ctx)
    except FileNotFoundError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(3)
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


def x__deliberate__mutmut_11(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        click.echo(ctx.get_help())
        return
    try:
        config = _load_cfg(ctx)
    except FileNotFoundError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    engine = None
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


def x__deliberate__mutmut_12(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        click.echo(ctx.get_help())
        return
    try:
        config = _load_cfg(ctx)
    except FileNotFoundError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    engine = Engine(None, LiteLLMGateway(config))
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


def x__deliberate__mutmut_13(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        click.echo(ctx.get_help())
        return
    try:
        config = _load_cfg(ctx)
    except FileNotFoundError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    engine = Engine(config, None)
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


def x__deliberate__mutmut_14(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        click.echo(ctx.get_help())
        return
    try:
        config = _load_cfg(ctx)
    except FileNotFoundError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    engine = Engine(LiteLLMGateway(config))
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


def x__deliberate__mutmut_15(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        click.echo(ctx.get_help())
        return
    try:
        config = _load_cfg(ctx)
    except FileNotFoundError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    engine = Engine(config, )
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


def x__deliberate__mutmut_16(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        click.echo(ctx.get_help())
        return
    try:
        config = _load_cfg(ctx)
    except FileNotFoundError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    engine = Engine(config, LiteLLMGateway(None))
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


def x__deliberate__mutmut_17(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    extra_kwargs: dict[str, Any] = None
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


def x__deliberate__mutmut_18(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    stage_models = None
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


def x__deliberate__mutmut_19(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    stage_models = ctx.obj.get(None)
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


def x__deliberate__mutmut_20(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    stage_models = ctx.obj.get("XXstage_modelsXX")
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


def x__deliberate__mutmut_21(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    stage_models = ctx.obj.get("STAGE_MODELS")
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


def x__deliberate__mutmut_22(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    dag = None
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


def x__deliberate__mutmut_23(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    dag = ctx.obj.get(None)
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


def x__deliberate__mutmut_24(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    dag = ctx.obj.get("XXdagXX")
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


def x__deliberate__mutmut_25(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    dag = ctx.obj.get("DAG")
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


def x__deliberate__mutmut_26(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    allow_custom_dag = None
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


def x__deliberate__mutmut_27(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    allow_custom_dag = ctx.obj.get(None, False)
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


def x__deliberate__mutmut_28(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    allow_custom_dag = ctx.obj.get("allow_custom_dag", None)
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


def x__deliberate__mutmut_29(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    allow_custom_dag = ctx.obj.get(False)
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


def x__deliberate__mutmut_30(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    allow_custom_dag = ctx.obj.get("allow_custom_dag", )
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


def x__deliberate__mutmut_31(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    allow_custom_dag = ctx.obj.get("XXallow_custom_dagXX", False)
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


def x__deliberate__mutmut_32(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    allow_custom_dag = ctx.obj.get("ALLOW_CUSTOM_DAG", False)
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


def x__deliberate__mutmut_33(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    allow_custom_dag = ctx.obj.get("allow_custom_dag", True)
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


def x__deliberate__mutmut_34(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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

        extra_kwargs["overrides"] = None
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


def x__deliberate__mutmut_35(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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

        extra_kwargs["XXoverridesXX"] = DeliberationOverrides(stage_models=stage_models)
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


def x__deliberate__mutmut_36(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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

        extra_kwargs["OVERRIDES"] = DeliberationOverrides(stage_models=stage_models)
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


def x__deliberate__mutmut_37(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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

        extra_kwargs["overrides"] = DeliberationOverrides(stage_models=None)
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


def x__deliberate__mutmut_38(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    if dag is None:
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


def x__deliberate__mutmut_39(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
        extra_kwargs["dag"] = None
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


def x__deliberate__mutmut_40(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
        extra_kwargs["XXdagXX"] = dag
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


def x__deliberate__mutmut_41(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
        extra_kwargs["DAG"] = dag
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


def x__deliberate__mutmut_42(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
        extra_kwargs["allow_custom_dag"] = None
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


def x__deliberate__mutmut_43(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
        extra_kwargs["XXallow_custom_dagXX"] = allow_custom_dag
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


def x__deliberate__mutmut_44(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
        extra_kwargs["ALLOW_CUSTOM_DAG"] = allow_custom_dag
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


def x__deliberate__mutmut_45(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
        result = None
    except ValueError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    console.print(Panel(result.answer, title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_46(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
            None
        )
    except ValueError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    console.print(Panel(result.answer, title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_47(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
            engine.deliberate(None, ctx.obj["formation"], **extra_kwargs)
        )
    except ValueError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    console.print(Panel(result.answer, title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_48(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
            engine.deliberate(prompt, None, **extra_kwargs)
        )
    except ValueError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    console.print(Panel(result.answer, title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_49(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
            engine.deliberate(ctx.obj["formation"], **extra_kwargs)
        )
    except ValueError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    console.print(Panel(result.answer, title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_50(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
            engine.deliberate(prompt, **extra_kwargs)
        )
    except ValueError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    console.print(Panel(result.answer, title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_51(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
            engine.deliberate(prompt, ctx.obj["formation"], )
        )
    except ValueError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    console.print(Panel(result.answer, title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_52(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
            engine.deliberate(prompt, ctx.obj["XXformationXX"], **extra_kwargs)
        )
    except ValueError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    console.print(Panel(result.answer, title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_53(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
            engine.deliberate(prompt, ctx.obj["FORMATION"], **extra_kwargs)
        )
    except ValueError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    console.print(Panel(result.answer, title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_54(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
        console.print(None)
        sys.exit(2)
    console.print(Panel(result.answer, title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_55(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
        sys.exit(None)
    console.print(Panel(result.answer, title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_56(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
        sys.exit(3)
    console.print(Panel(result.answer, title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_57(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    console.print(None)
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_58(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    console.print(Panel(None, title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_59(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    console.print(Panel(result.answer, title=None, border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_60(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    console.print(Panel(result.answer, title="Chimera", border_style=None))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_61(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    console.print(Panel(title="Chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_62(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    console.print(Panel(result.answer, border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_63(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    console.print(Panel(result.answer, title="Chimera", ))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_64(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    console.print(Panel(result.answer, title="XXChimeraXX", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_65(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    console.print(Panel(result.answer, title="chimera", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_66(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    console.print(Panel(result.answer, title="CHIMERA", border_style="cyan"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_67(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    console.print(Panel(result.answer, title="Chimera", border_style="XXcyanXX"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_68(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    console.print(Panel(result.answer, title="Chimera", border_style="CYAN"))
    if ctx.obj.get("verbose"):
        _print_trace(result.trace)


def x__deliberate__mutmut_69(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    if ctx.obj.get(None):
        _print_trace(result.trace)


def x__deliberate__mutmut_70(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    if ctx.obj.get("XXverboseXX"):
        _print_trace(result.trace)


def x__deliberate__mutmut_71(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
    if ctx.obj.get("VERBOSE"):
        _print_trace(result.trace)


def x__deliberate__mutmut_72(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
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
        _print_trace(None)

mutants_x__deliberate__mutmut['_mutmut_orig'] = x__deliberate__mutmut_orig # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_1'] = x__deliberate__mutmut_1 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_2'] = x__deliberate__mutmut_2 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_3'] = x__deliberate__mutmut_3 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_4'] = x__deliberate__mutmut_4 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_5'] = x__deliberate__mutmut_5 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_6'] = x__deliberate__mutmut_6 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_7'] = x__deliberate__mutmut_7 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_8'] = x__deliberate__mutmut_8 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_9'] = x__deliberate__mutmut_9 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_10'] = x__deliberate__mutmut_10 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_11'] = x__deliberate__mutmut_11 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_12'] = x__deliberate__mutmut_12 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_13'] = x__deliberate__mutmut_13 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_14'] = x__deliberate__mutmut_14 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_15'] = x__deliberate__mutmut_15 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_16'] = x__deliberate__mutmut_16 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_17'] = x__deliberate__mutmut_17 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_18'] = x__deliberate__mutmut_18 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_19'] = x__deliberate__mutmut_19 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_20'] = x__deliberate__mutmut_20 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_21'] = x__deliberate__mutmut_21 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_22'] = x__deliberate__mutmut_22 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_23'] = x__deliberate__mutmut_23 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_24'] = x__deliberate__mutmut_24 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_25'] = x__deliberate__mutmut_25 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_26'] = x__deliberate__mutmut_26 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_27'] = x__deliberate__mutmut_27 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_28'] = x__deliberate__mutmut_28 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_29'] = x__deliberate__mutmut_29 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_30'] = x__deliberate__mutmut_30 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_31'] = x__deliberate__mutmut_31 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_32'] = x__deliberate__mutmut_32 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_33'] = x__deliberate__mutmut_33 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_34'] = x__deliberate__mutmut_34 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_35'] = x__deliberate__mutmut_35 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_36'] = x__deliberate__mutmut_36 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_37'] = x__deliberate__mutmut_37 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_38'] = x__deliberate__mutmut_38 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_39'] = x__deliberate__mutmut_39 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_40'] = x__deliberate__mutmut_40 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_41'] = x__deliberate__mutmut_41 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_42'] = x__deliberate__mutmut_42 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_43'] = x__deliberate__mutmut_43 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_44'] = x__deliberate__mutmut_44 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_45'] = x__deliberate__mutmut_45 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_46'] = x__deliberate__mutmut_46 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_47'] = x__deliberate__mutmut_47 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_48'] = x__deliberate__mutmut_48 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_49'] = x__deliberate__mutmut_49 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_50'] = x__deliberate__mutmut_50 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_51'] = x__deliberate__mutmut_51 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_52'] = x__deliberate__mutmut_52 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_53'] = x__deliberate__mutmut_53 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_54'] = x__deliberate__mutmut_54 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_55'] = x__deliberate__mutmut_55 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_56'] = x__deliberate__mutmut_56 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_57'] = x__deliberate__mutmut_57 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_58'] = x__deliberate__mutmut_58 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_59'] = x__deliberate__mutmut_59 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_60'] = x__deliberate__mutmut_60 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_61'] = x__deliberate__mutmut_61 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_62'] = x__deliberate__mutmut_62 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_63'] = x__deliberate__mutmut_63 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_64'] = x__deliberate__mutmut_64 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_65'] = x__deliberate__mutmut_65 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_66'] = x__deliberate__mutmut_66 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_67'] = x__deliberate__mutmut_67 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_68'] = x__deliberate__mutmut_68 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_69'] = x__deliberate__mutmut_69 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_70'] = x__deliberate__mutmut_70 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_71'] = x__deliberate__mutmut_71 # type: ignore # mutmut generated
mutants_x__deliberate__mutmut['x__deliberate__mutmut_72'] = x__deliberate__mutmut_72 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x__print_trace__mutmut)
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


def x__print_trace__mutmut_orig(trace: Any) -> None:
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


def x__print_trace__mutmut_1(trace: Any) -> None:
    table = None
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


def x__print_trace__mutmut_2(trace: Any) -> None:
    table = Table(title=None, show_lines=False)
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


def x__print_trace__mutmut_3(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=None)
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


def x__print_trace__mutmut_4(trace: Any) -> None:
    table = Table(show_lines=False)
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


def x__print_trace__mutmut_5(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", )
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


def x__print_trace__mutmut_6(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=True)
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


def x__print_trace__mutmut_7(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column(None, style="bold")
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


def x__print_trace__mutmut_8(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style=None)
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


def x__print_trace__mutmut_9(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column(style="bold")
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


def x__print_trace__mutmut_10(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", )
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


def x__print_trace__mutmut_11(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("XXstageXX", style="bold")
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


def x__print_trace__mutmut_12(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("STAGE", style="bold")
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


def x__print_trace__mutmut_13(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="XXboldXX")
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


def x__print_trace__mutmut_14(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="BOLD")
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


def x__print_trace__mutmut_15(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column(None)
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


def x__print_trace__mutmut_16(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("XXkindXX")
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


def x__print_trace__mutmut_17(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("KIND")
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


def x__print_trace__mutmut_18(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column(None)
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


def x__print_trace__mutmut_19(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("XXmodelXX")
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


def x__print_trace__mutmut_20(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("MODEL")
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


def x__print_trace__mutmut_21(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column(None, justify="right")
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


def x__print_trace__mutmut_22(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify=None)
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


def x__print_trace__mutmut_23(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column(justify="right")
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


def x__print_trace__mutmut_24(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", )
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


def x__print_trace__mutmut_25(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("XXtokensXX", justify="right")
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


def x__print_trace__mutmut_26(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("TOKENS", justify="right")
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


def x__print_trace__mutmut_27(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="XXrightXX")
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


def x__print_trace__mutmut_28(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="RIGHT")
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


def x__print_trace__mutmut_29(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column(None, justify="right")
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


def x__print_trace__mutmut_30(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("latency", justify=None)
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


def x__print_trace__mutmut_31(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column(justify="right")
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


def x__print_trace__mutmut_32(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("latency", )
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


def x__print_trace__mutmut_33(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("XXlatencyXX", justify="right")
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


def x__print_trace__mutmut_34(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("LATENCY", justify="right")
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


def x__print_trace__mutmut_35(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("latency", justify="XXrightXX")
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


def x__print_trace__mutmut_36(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("latency", justify="RIGHT")
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


def x__print_trace__mutmut_37(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("latency", justify="right")
    table.add_column(None, justify="right")

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


def x__print_trace__mutmut_38(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("latency", justify="right")
    table.add_column("cost", justify=None)

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


def x__print_trace__mutmut_39(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("latency", justify="right")
    table.add_column(justify="right")

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


def x__print_trace__mutmut_40(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("latency", justify="right")
    table.add_column("cost", )

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


def x__print_trace__mutmut_41(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("latency", justify="right")
    table.add_column("XXcostXX", justify="right")

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


def x__print_trace__mutmut_42(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("latency", justify="right")
    table.add_column("COST", justify="right")

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


def x__print_trace__mutmut_43(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("latency", justify="right")
    table.add_column("cost", justify="XXrightXX")

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


def x__print_trace__mutmut_44(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("latency", justify="right")
    table.add_column("cost", justify="RIGHT")

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


def x__print_trace__mutmut_45(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("latency", justify="right")
    table.add_column("cost", justify="right")

    def row(span: Any) -> None:
        table.add_row(
            None,
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


def x__print_trace__mutmut_46(trace: Any) -> None:
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
            None,
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


def x__print_trace__mutmut_47(trace: Any) -> None:
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
            None,
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


def x__print_trace__mutmut_48(trace: Any) -> None:
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
            None,
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


def x__print_trace__mutmut_49(trace: Any) -> None:
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
            None,
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


def x__print_trace__mutmut_50(trace: Any) -> None:
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
            None,
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


def x__print_trace__mutmut_51(trace: Any) -> None:
    table = Table(title=f"Trace {trace.request_id}", show_lines=False)
    table.add_column("stage", style="bold")
    table.add_column("kind")
    table.add_column("model")
    table.add_column("tokens", justify="right")
    table.add_column("latency", justify="right")
    table.add_column("cost", justify="right")

    def row(span: Any) -> None:
        table.add_row(
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


def x__print_trace__mutmut_52(trace: Any) -> None:
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


def x__print_trace__mutmut_53(trace: Any) -> None:
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


def x__print_trace__mutmut_54(trace: Any) -> None:
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


def x__print_trace__mutmut_55(trace: Any) -> None:
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


def x__print_trace__mutmut_56(trace: Any) -> None:
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


def x__print_trace__mutmut_57(trace: Any) -> None:
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
            str(None),
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


def x__print_trace__mutmut_58(trace: Any) -> None:
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
            str(span.tokens_input - span.tokens_output),
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


def x__print_trace__mutmut_59(trace: Any) -> None:
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

    row(None)
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


def x__print_trace__mutmut_60(trace: Any) -> None:
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
        row(None)
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


def x__print_trace__mutmut_61(trace: Any) -> None:
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
    console.print(None)
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


def x__print_trace__mutmut_62(trace: Any) -> None:
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
        None
    )
    console.print(
        Panel(
            json.dumps(trace.model_dump(mode="json"), indent=2),
            title="full trace json",
            border_style="dim",
        )
    )


def x__print_trace__mutmut_63(trace: Any) -> None:
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
        None
    )


def x__print_trace__mutmut_64(trace: Any) -> None:
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
            None,
            title="full trace json",
            border_style="dim",
        )
    )


def x__print_trace__mutmut_65(trace: Any) -> None:
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
            title=None,
            border_style="dim",
        )
    )


def x__print_trace__mutmut_66(trace: Any) -> None:
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
            border_style=None,
        )
    )


def x__print_trace__mutmut_67(trace: Any) -> None:
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
            title="full trace json",
            border_style="dim",
        )
    )


def x__print_trace__mutmut_68(trace: Any) -> None:
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
            border_style="dim",
        )
    )


def x__print_trace__mutmut_69(trace: Any) -> None:
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
            )
    )


def x__print_trace__mutmut_70(trace: Any) -> None:
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
            json.dumps(None, indent=2),
            title="full trace json",
            border_style="dim",
        )
    )


def x__print_trace__mutmut_71(trace: Any) -> None:
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
            json.dumps(trace.model_dump(mode="json"), indent=None),
            title="full trace json",
            border_style="dim",
        )
    )


def x__print_trace__mutmut_72(trace: Any) -> None:
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
            json.dumps(indent=2),
            title="full trace json",
            border_style="dim",
        )
    )


def x__print_trace__mutmut_73(trace: Any) -> None:
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
            json.dumps(trace.model_dump(mode="json"), ),
            title="full trace json",
            border_style="dim",
        )
    )


def x__print_trace__mutmut_74(trace: Any) -> None:
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
            json.dumps(trace.model_dump(mode=None), indent=2),
            title="full trace json",
            border_style="dim",
        )
    )


def x__print_trace__mutmut_75(trace: Any) -> None:
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
            json.dumps(trace.model_dump(mode="XXjsonXX"), indent=2),
            title="full trace json",
            border_style="dim",
        )
    )


def x__print_trace__mutmut_76(trace: Any) -> None:
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
            json.dumps(trace.model_dump(mode="JSON"), indent=2),
            title="full trace json",
            border_style="dim",
        )
    )


def x__print_trace__mutmut_77(trace: Any) -> None:
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
            json.dumps(trace.model_dump(mode="json"), indent=3),
            title="full trace json",
            border_style="dim",
        )
    )


def x__print_trace__mutmut_78(trace: Any) -> None:
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
            title="XXfull trace jsonXX",
            border_style="dim",
        )
    )


def x__print_trace__mutmut_79(trace: Any) -> None:
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
            title="FULL TRACE JSON",
            border_style="dim",
        )
    )


def x__print_trace__mutmut_80(trace: Any) -> None:
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
            border_style="XXdimXX",
        )
    )


def x__print_trace__mutmut_81(trace: Any) -> None:
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
            border_style="DIM",
        )
    )

mutants_x__print_trace__mutmut['_mutmut_orig'] = x__print_trace__mutmut_orig # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_1'] = x__print_trace__mutmut_1 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_2'] = x__print_trace__mutmut_2 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_3'] = x__print_trace__mutmut_3 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_4'] = x__print_trace__mutmut_4 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_5'] = x__print_trace__mutmut_5 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_6'] = x__print_trace__mutmut_6 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_7'] = x__print_trace__mutmut_7 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_8'] = x__print_trace__mutmut_8 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_9'] = x__print_trace__mutmut_9 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_10'] = x__print_trace__mutmut_10 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_11'] = x__print_trace__mutmut_11 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_12'] = x__print_trace__mutmut_12 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_13'] = x__print_trace__mutmut_13 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_14'] = x__print_trace__mutmut_14 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_15'] = x__print_trace__mutmut_15 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_16'] = x__print_trace__mutmut_16 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_17'] = x__print_trace__mutmut_17 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_18'] = x__print_trace__mutmut_18 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_19'] = x__print_trace__mutmut_19 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_20'] = x__print_trace__mutmut_20 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_21'] = x__print_trace__mutmut_21 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_22'] = x__print_trace__mutmut_22 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_23'] = x__print_trace__mutmut_23 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_24'] = x__print_trace__mutmut_24 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_25'] = x__print_trace__mutmut_25 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_26'] = x__print_trace__mutmut_26 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_27'] = x__print_trace__mutmut_27 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_28'] = x__print_trace__mutmut_28 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_29'] = x__print_trace__mutmut_29 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_30'] = x__print_trace__mutmut_30 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_31'] = x__print_trace__mutmut_31 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_32'] = x__print_trace__mutmut_32 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_33'] = x__print_trace__mutmut_33 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_34'] = x__print_trace__mutmut_34 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_35'] = x__print_trace__mutmut_35 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_36'] = x__print_trace__mutmut_36 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_37'] = x__print_trace__mutmut_37 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_38'] = x__print_trace__mutmut_38 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_39'] = x__print_trace__mutmut_39 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_40'] = x__print_trace__mutmut_40 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_41'] = x__print_trace__mutmut_41 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_42'] = x__print_trace__mutmut_42 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_43'] = x__print_trace__mutmut_43 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_44'] = x__print_trace__mutmut_44 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_45'] = x__print_trace__mutmut_45 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_46'] = x__print_trace__mutmut_46 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_47'] = x__print_trace__mutmut_47 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_48'] = x__print_trace__mutmut_48 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_49'] = x__print_trace__mutmut_49 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_50'] = x__print_trace__mutmut_50 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_51'] = x__print_trace__mutmut_51 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_52'] = x__print_trace__mutmut_52 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_53'] = x__print_trace__mutmut_53 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_54'] = x__print_trace__mutmut_54 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_55'] = x__print_trace__mutmut_55 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_56'] = x__print_trace__mutmut_56 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_57'] = x__print_trace__mutmut_57 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_58'] = x__print_trace__mutmut_58 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_59'] = x__print_trace__mutmut_59 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_60'] = x__print_trace__mutmut_60 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_61'] = x__print_trace__mutmut_61 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_62'] = x__print_trace__mutmut_62 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_63'] = x__print_trace__mutmut_63 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_64'] = x__print_trace__mutmut_64 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_65'] = x__print_trace__mutmut_65 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_66'] = x__print_trace__mutmut_66 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_67'] = x__print_trace__mutmut_67 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_68'] = x__print_trace__mutmut_68 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_69'] = x__print_trace__mutmut_69 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_70'] = x__print_trace__mutmut_70 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_71'] = x__print_trace__mutmut_71 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_72'] = x__print_trace__mutmut_72 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_73'] = x__print_trace__mutmut_73 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_74'] = x__print_trace__mutmut_74 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_75'] = x__print_trace__mutmut_75 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_76'] = x__print_trace__mutmut_76 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_77'] = x__print_trace__mutmut_77 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_78'] = x__print_trace__mutmut_78 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_79'] = x__print_trace__mutmut_79 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_80'] = x__print_trace__mutmut_80 # type: ignore # mutmut generated
mutants_x__print_trace__mutmut['x__print_trace__mutmut_81'] = x__print_trace__mutmut_81 # type: ignore # mutmut generated


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
