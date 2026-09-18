"""Click + Rich CLI.

Usage::

    chimera "prompt"                  # full pipeline, auto formation
    chimera -f debate "prompt"        # specific formation
    chimera formations                # list formations
    chimera models                    # list models with weights
    chimera --verbose "prompt"        # print the full trace
    chimera --quiet "prompt"          # stdout = the raw answer only
    chimera --json "prompt"           # stdout = one JSON object (answer + trace)
    chimera --quiet run "prompt"      # same modes, explicit run subcommand
    chimera --json run "prompt"
    chimera --version                 # print the package version and exit
    chimera serve                     # run the REST API
    chimera mcp                       # run the MCP server (stdio)

DF-CHIMERA-0906-5 (machine-readable output): ``--quiet`` and ``--json`` are
mutually exclusive group flags placed BEFORE the subcommand (click's group
convention). In both modes stdout carries exactly ONE machine-readable
payload — the raw answer (plus one newline) or one JSON object — while every
diagnostic (dropped-worker and dispatch-degradation warnings, structlog
lines) goes to stderr, so ``chimera --json "..." > out.json`` is safe.
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
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from chimera import __version__, blocked_models
from chimera.config import (
    ChimeraConfig,
    FormationPreset,
    Observability,
    load_config,
    provider_api_key_env,
)
from chimera.engine import Engine
from chimera.exceptions import ConfigError
from chimera.gateway import LiteLLMGateway
from chimera.observability import configure_logging

# When output is piped (tests, redirection), use a wide console so tables and
# model names never get truncated. Interactive use auto-detects the terminal.
console = Console(width=None if sys.stdout.isatty() else 200)

#: Diagnostics console for the machine-readable modes (DF-CHIMERA-0906-5).
#: ``--quiet`` / ``--json`` promise that stdout holds ONLY the payload, so
#: dropped-worker / dispatch-degradation warnings are rendered here instead —
#: never suppressed, just moved off stdout. ``stderr=True`` is resolved lazily
#: by rich, so redirected/captured streams are respected.
err_console = Console(stderr=True, width=None if sys.stderr.isatty() else 200)


class MutuallyExclusiveOption(click.Option):
    """A flag that refuses to coexist with sibling flags (usage error, exit 2).

    Click has no native mutual-exclusion support (DF-CHIMERA-0906-5). Without
    this, ``--quiet --json`` would silently honour one branch and a script
    asking for JSON would receive Rich text on stdout. Raising ``UsageError``
    while parsing keeps it a conventional click usage error: exit code 2, the
    message on stderr, and no deliberation started.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.mutually_exclusive: frozenset[str] = frozenset(
            kwargs.pop("mutually_exclusive", ())
        )
        super().__init__(*args, **kwargs)

    def _display_name(self, ctx: click.Context, param_name: str) -> str:
        """The long spelling the user typed (``--json``, not ``--json_output``)."""
        if param_name == self.name:
            opts = self.opts
        else:
            sibling = next(
                (p for p in ctx.command.params if p.name == param_name), None
            )
            opts = getattr(sibling, "opts", ()) or ()
        longs = [opt for opt in opts if opt.startswith("--")]
        if longs:
            return min(longs, key=len)
        return "--" + param_name.replace("_", "-")

    def handle_parse_result(
        self, ctx: click.Context, opts: dict[str, Any], args: list[str]
    ) -> tuple[Any, list[str]]:
        if opts.get(self.name):
            clashes = sorted(name for name in self.mutually_exclusive if opts.get(name))
            if clashes:
                names = [self._display_name(ctx, self.name)] + [
                    self._display_name(ctx, name) for name in clashes
                ]
                raise click.UsageError(
                    f"{' and '.join(names)} are mutually exclusive — "
                    f"pick one output mode."
                )
        return super().handle_parse_result(ctx, opts, args)


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
@click.version_option(version=__version__, message="chimera %(version)s")
@click.option("-f", "--formation", default="auto", help="Formation preset name.")
@click.option("-v", "--verbose", is_flag=True, help="Print the full trace.")
@click.option(
    "--quiet",
    is_flag=True,
    cls=MutuallyExclusiveOption,
    mutually_exclusive={"json_output"},
    help="Print only the raw answer to stdout (warnings go to stderr).",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    cls=MutuallyExclusiveOption,
    mutually_exclusive={"quiet"},
    help="Print one JSON object (answer + full trace) to stdout.",
)
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
    quiet: bool,
    json_output: bool,
    config_path: str | None,
    allow_custom_dag: bool,
    dag_json: str | None,
    stage_models_json: str | None,
) -> None:
    """Chimera — dynamic multi-model deliberation gateway."""
    ctx.obj = {
        "formation": formation,
        "verbose": verbose,
        # DF-CHIMERA-0906-5 output modes. Group-level flags (placed before the
        # subcommand, per click's group convention) so both the implicit-prompt
        # form ``chimera --json "..."`` and the explicit form
        # ``chimera --json run "..."`` resolve the same way.
        "quiet": quiet,
        "json_output": json_output,
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
    except (FileNotFoundError, ConfigError) as exc:
        # DF-CHIMERA-V2-8: the remedy names `chimera config init`, which makes
        # the message ~200 chars — rich would hard-wrap it into three lines at
        # 80 columns (splitting the command across a boundary at some widths).
        # soft_wrap keeps the CH-GAP-050 one-liner contract: one logical line,
        # whatever the terminal width. A real terminal soft-wraps the display
        # itself, so nothing is lost on screen, and the byte stream stays one
        # line for pipes, logs and tests.
        #
        # INT-API-002: an invalid category score (out of 0-100, non-numeric) is
        # the same class of user error — one actionable line, exit 2, no
        # traceback — so ConfigError is rendered here too.
        console.print(f"[red]error:[/red] {exc}", soft_wrap=True)
        sys.exit(2)
    # Phase 2: re-pin with the real observability config — still stderr.
    configure_logging(cfg.observability, force_stderr=True)
    return cfg


def _validate_formation(cfg: ChimeraConfig, formation: str, dag: Any) -> None:
    """Reject an unknown formation before any provider call (DF-CHIMERA-V2-7).

    The three user-facing surfaces must agree on an unknown formation name.
    REST already answers 422 ``Unknown formation: <name>``; the CLI used to
    hand the name straight to the dispatcher, which logs a structlog
    ``unknown_formation`` warning and silently falls back to ``auto`` — the
    process printed an answer and exited 0, so a typo (``-f dabate``) bought a
    full deliberation on the wrong formation and billed the providers.

    The dispatcher fallback itself is INTENTIONAL and stays (it is the engine's
    internal safety net for programmatic callers, covered by
    ``tests/test_dispatcher.py::test_dispatcher_unknown_formation_uses_auto``);
    this guard belongs at the user-facing edge, mirroring the API handler's
    check in ``src/chimera/api/server.py``.

    ``dag`` exempts validation entirely: an explicit client DAG replaces
    formation selection, so ``--dag`` / ``--allow-custom-dag`` behave exactly
    as before.

    The error goes to ``err_console`` (stderr) with the house ``error:``
    prefix so CLI stdout purity holds (DF-CHIMERA-V2-3), and the process exits
    2 — the same code the other usage errors use. Zero provider calls, zero
    billing.
    """
    if dag is not None:
        return
    if formation in cfg.formations:
        return
    available = ", ".join(sorted(cfg.formations))
    err_console.print(
        f"[red]error:[/red] Unknown formation: {formation}. "
        f"Available formations: {available}. "
        f"Run `chimera formations` to list them."
    )
    sys.exit(2)


def _deliberate(ctx: click.Context, prompt_parts: tuple[str, ...]) -> None:
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        click.echo(ctx.get_help())
        return
    opts = ctx.obj or {}
    quiet = bool(opts.get("quiet"))
    json_mode = bool(opts.get("json_output"))
    machine_mode = quiet or json_mode
    config = _load_cfg(ctx)
    # DF-CHIMERA-V2-7: fail fast on an unknown formation — BEFORE the engine
    # (and therefore the gateway) is constructed, so a typo costs zero
    # provider calls and zero billing. An explicit --dag is exempt.
    _validate_formation(config, opts["formation"], opts.get("dag"))
    engine = Engine(config, LiteLLMGateway(config))
    # Only forward the new kwargs when they are actually set, so the default
    # call shape stays ``deliberate(prompt, formation)`` (backward compatible).
    extra_kwargs: dict[str, Any] = {}
    stage_models = opts.get("stage_models")
    dag = opts.get("dag")
    allow_custom_dag = opts.get("allow_custom_dag", False)
    if stage_models:
        from chimera.config import DeliberationOverrides

        extra_kwargs["overrides"] = DeliberationOverrides(stage_models=stage_models)
    if dag is not None:
        extra_kwargs["dag"] = dag
        extra_kwargs["allow_custom_dag"] = allow_custom_dag
    try:
        result = asyncio.run(
            engine.deliberate(prompt, opts["formation"], **extra_kwargs)
        )
    except ValueError as exc:
        console.print(f"[red]error:[/red] {exc}")
        sys.exit(2)
    # Operational truth is never suppressed (DF-CHIMERA-0906-5): in human mode
    # the dropped-worker / degraded-dispatch warnings stay on stdout beside the
    # panel, but in --quiet/--json they move to stderr so stdout carries ONLY
    # the machine-readable payload.
    warn_console = err_console if machine_mode else console
    _print_worker_failures(result, warn_console, config)
    _print_dispatch_degradation(result, warn_console)

    if json_mode:
        _print_json(result)
    elif quiet:
        # Exactly the raw answer + one newline: no panel, no border, no ANSI,
        # no trace — ``chimera --quiet "..." | pbcopy`` gets the answer only.
        click.echo(result.answer)
    else:
        console.print(Panel(result.answer, title="Chimera", border_style="cyan"))
        if opts.get("verbose"):
            _print_trace(result.trace)


def _print_json(result: Any) -> None:
    """Write one JSON object (``answer`` + the COMPLETE trace) to stdout.

    ``ensure_ascii=False`` keeps non-ASCII answers intact (``café`` stays
    ``café``, not ``caf\\u00e9``); click appends exactly one newline, so stdout
    is a single parseable JSON document. ``model_dump(mode="json")`` is the
    full trace serialization — every field the API/web UI sees, not a subset.
    """
    payload = {
        "answer": result.answer,
        "trace": result.trace.model_dump(mode="json"),
    }
    click.echo(json.dumps(payload, ensure_ascii=False))


def _provider_for_model(model: str, config: ChimeraConfig | None) -> str | None:
    """The provider that serves *model* (catalog entry first, name prefix after)."""
    if config is not None:
        entry = config.models.get(model)
        if entry is not None and entry.provider:
            return entry.provider
    if "/" in model:
        prefix = model.split("/", 1)[0]
        if prefix:
            return prefix
    return None


def _provider_api_key_env(provider: str, config: ChimeraConfig | None) -> str:
    """The env var that must hold *provider*'s key.

    Delegates to :func:`chimera.config.provider_api_key_env` — the same
    resolver the gateway uses to annotate a credential failure
    (DF-CHIMERA-V2-8) — so the CLI hint and the error text can never name
    different variables.  Falls back to the ``<PROVIDER>_API_KEY`` convention
    that LiteLLM itself reads; this helper is always rendering a *named*
    provider, so the "keyless local endpoint" case (``None``) still gets a
    printable name.
    """
    resolved = provider_api_key_env(config, provider)
    if resolved:
        return resolved
    return f"{provider.upper().replace('-', '_')}_API_KEY"


#: Display budget (characters) for one worker error on the CLI warning line.
#: The trace keeps the whole message; only this rendering is bounded.
_WORKER_ERROR_DISPLAY_CHARS = 200


def _elide_worker_error(
    error: str, limit: int = _WORKER_ERROR_DISPLAY_CHARS
) -> tuple[str, int]:
    """Return ``(rendered, omitted_chars)`` for a worker-failure *error*.

    An error of at most *limit* characters is returned byte-identical
    (``omitted_chars == 0``), so the short-error warning is exactly what the
    CLI has always printed. A longer one is cut at the last whitespace INSIDE
    the budget — never mid-token, because the old fixed ``error[:197] + "..."``
    slice turned a real guardrail failure into ``... and data polic...``,
    dropping the words that actually named the restriction — and the elision is
    spelled out with the number of dropped characters
    (``... [truncated 214 chars]``) so the user can tell it was shortened.

    One degenerate case is documented rather than hidden: a single unbroken
    token longer than the budget has no boundary to cut at, so the budget wins
    there (the alternative is printing the whole token).
    """
    if len(error) <= limit:
        return error, 0
    head = error[:limit]
    boundary = max(head.rfind(ch) for ch in (" ", "\n", "\t"))
    if boundary > 0:
        head = head[:boundary]
    head = head.rstrip()
    omitted = len(error) - len(head)
    return f"{head}... [truncated {omitted} chars]", omitted


def _print_worker_failures(
    result: Any,
    out: Console = console,
    config: ChimeraConfig | None = None,
) -> None:
    """Warn (always, not just --verbose) when worker stages were dropped.

    A degraded worker still lets the deliberation produce an answer, but the
    user must know the panel is partial — otherwise a guardrail/404 failure
    is silent outside the structlog stream.

    A long error is elided lossily-safely (DF-CHIMERA-V2-5): the cut lands on a
    word boundary and the elision is marked with the omitted character count,
    plus a line naming the trace as the place the complete message lives. The
    full text is never dropped silently, and an error within the display budget
    renders unchanged. The upstream error text is Rich-escaped — its own
    ``[...]`` runs would otherwise be parsed as markup and dropped.

    A **credential-class** failure (present-but-invalid provider key → 401)
    gets an actionable warning on top of the raw error: the provider, the env
    var to fix, the remedy, and the fact that the model is now excluded from
    selection. The raw CLI text used to name neither the env var nor a fix,
    so the only visible symptom was a panel that quietly shrank to one model
    (DF-CHIMERA-V2-6).

    ``out`` is the stderr console in --quiet/--json mode (DF-CHIMERA-0906-5).
    """
    failures = getattr(getattr(result, "trace", None), "worker_failures", None) or []
    for failure in failures:
        stage_id = getattr(failure, "stage_id", "?")
        model = getattr(failure, "model", "?")
        error = str(getattr(failure, "error", "") or "unknown error")
        displayed, omitted = _elide_worker_error(error)
        # ``escape`` because the error text is upstream/third-party text: an
        # unescaped "[...]" in it is parsed as Rich markup and can swallow the
        # rest of the line (including our "[truncated N chars]" marker).
        out.print(
            f"[yellow]warning:[/yellow] worker '{stage_id}' ({model}) "
            f"failed: {escape(displayed)}"
        )
        if omitted:
            # The elision must be actionable, not merely visible: name where
            # the complete text is. Both --json and --verbose dump the full
            # trace, whose worker_failures[] carries the untruncated error.
            out.print(
                "  [yellow]full error:[/yellow] the complete upstream message "
                f"({len(error)} chars) is in the trace — re-run with --json "
                "(or --verbose) to read it"
            )
        # Classify the FULL error, not the elided render: the truncation is
        # purely presentational and must never hide a credential failure.
        if not blocked_models.is_credential_error(error):
            continue
        provider = _provider_for_model(model, config)
        if provider is None:
            out.print(
                "  [yellow]credential failure:[/yellow] the provider rejected "
                "the API key for this model."
            )
        else:
            env_var = _provider_api_key_env(provider, config)
            out.print(
                f"  [yellow]credential failure:[/yellow] provider "
                f"'{provider}' rejected the API key for {model}."
            )
            out.print(
                f"  fix: set a valid {env_var} (or unset the stale one) and "
                f"re-run — the model is excluded from selection until the key "
                f"changes or the block cooldown expires "
                f"(~/.chimera/blocked-models.json)."
            )
            out.print(
                "  escape hatch: auto_formation.restrict_to_credentialed_"
                "providers: false keeps the full catalog; provider calls "
                "still fail until the key is valid."
            )


#: Self-describing repair prefixes the dispatcher already writes into
#: ``dispatch_note`` (``dispatcher.py``): the CLI must not label them twice.
_REPAIR_NOTE_PREFIXES = ("repaired:", "repaired ")


def _repair_note_detail(note: str) -> str:
    """Strip a redundant leading ``repaired:`` / ``repaired`` token from *note*.

    The dispatcher's repair notes are already self-describing — it writes
    ``"repaired: injected aggregator stage(s) …"`` / ``"repaired: added
    aggregator stage for 2 worker terminals"`` (``dispatcher.py``) — while the
    CLI prints its own ``dispatch repaired:`` label. Stacking the two made a
    real run read ``warning: dispatch repaired: repaired: injected …``
    (DF-CHIMERA-V2-5), which reads like a second, unexplained repair.

    The note itself stays the single source of truth (it is surfaced verbatim
    in the ``--json`` trace); only the CLI's rendering de-duplicates it. The
    match is anchored on a token boundary, so a note that merely starts with a
    longer word (``"repairedness check failed"``) is returned untouched rather
    than mangled. Returns ``""`` for a note that carries nothing else.
    """
    text = note.strip()
    while True:
        lowered = text.lower()
        if lowered in ("repaired", "repaired:"):
            return ""
        for prefix in _REPAIR_NOTE_PREFIXES:
            if lowered.startswith(prefix):
                text = text[len(prefix):].lstrip()
                break
        else:
            return text


def _print_dispatch_degradation(result: Any, out: Console = console) -> None:
    """Warn (always, not just --verbose) when the dispatch degraded.

    Two degradation classes surface here:

    * ``trace.source == "fallback"`` — the dispatcher plan was discarded
      and the deliberation collapsed to a generic single-worker formation.
      The answer may look fine; this is the ONLY signal (CH-GAP-044).
    * a repair note (``dispatch_note`` containing "repaired"/"injected") —
      the dispatcher's DAG was structurally repaired (e.g. an aggregator
      stage referenced by edges but missing from stages was injected), so
      the design survived but the user should know it was patched.

    ``out`` is the stderr console in --quiet/--json mode (DF-CHIMERA-0906-5).
    """
    trace = getattr(result, "trace", None)
    if trace is None:
        return
    source = getattr(trace, "source", None)
    note = getattr(trace, "dispatch_note", None)
    if source == "fallback":
        reason = note or "unknown reason"
        out.print(
            f"[yellow]warning:[/yellow] dispatch degraded — source=fallback "
            f"({reason}); the deliberation collapsed to a generic "
            f"single-worker formation"
        )
    elif note and ("repaired" in note or "injected" in note):
        # De-duplicate the label: the note already starts with "repaired: " on
        # a real run, so prefixing it again printed "dispatch repaired:
        # repaired: injected …" (DF-CHIMERA-V2-5).
        detail = _repair_note_detail(note)
        if detail:
            out.print(f"[yellow]warning:[/yellow] dispatch repaired: {detail}")
        else:
            out.print("[yellow]warning:[/yellow] dispatch repaired")


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

    # DF-CHIMERA-V2-6: make the durable exclusions visible. A model whose
    # provider key failed auth (or hit a provider guardrail) is excluded from
    # selection for the block cooldown; without this line the only trace was
    # ~/.chimera/blocked-models.json. Rendered as plain lines (not a table) so
    # an 80-column terminal can never truncate a model name into "…".
    blocked = sorted(blocked_models.shared_registry.blocked())
    if blocked:
        console.print(
            "[bold]Blocked models[/bold] (excluded from selection; "
            "state file: ~/.chimera/blocked-models.json)"
        )
        for name in blocked:
            reason = blocked_models.shared_registry.block_reason(name) or "guardrail"
            provider = _provider_for_model(name, config)
            if reason == "credential" and provider is not None:
                remedy = (
                    f"provider key rejected — set a valid "
                    f"{_provider_api_key_env(provider, config)}; the block "
                    f"self-clears when the key changes"
                )
            else:
                remedy = "provider guardrail/policy rejection — no local fix"
            console.print(f"  - {name} ({reason}) {remedy}")

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
