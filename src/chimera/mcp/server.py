"""MCP server exposing Chimera as tools for agents (e.g. Hermes).

Tools:
* ``chimera_deliberate(prompt, formation?)`` — full deliberation pipeline.
* ``chimera_formations()``                   — list formation presets.
* ``chimera_models()``                        — list models with weights.
"""

from __future__ import annotations

import json
import re
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from chimera import __version__
from chimera.config import ChimeraConfig, Defaults, Observability, load_config
from chimera.engine import Engine
from chimera.gateway import LiteLLMGateway
from chimera.observability import configure_logging

#: DF-CHIMERA-V2-89: the MCP error code for a run that produced NO usable
#: answer — the same failure class ``POST /v1/deliberate`` answers HTTP 502 for
#: and the web chat surface reports as ``all_workers_failed``, spelled in this
#: tool's own error vocabulary (``unknown_formation`` / ``config_missing``).
NO_USABLE_ANSWER_ERROR = "no_usable_answer"

#: The engine's degraded-placeholder rendering (``engine._degraded_stage``):
#: ``[stage <id> (<model>) unavailable: <error>]``. Anchored, because the
#: upstream error text can itself contain brackets — only an answer that IS the
#: placeholder (nothing else) counts.
_DEGRADED_PLACEHOLDER_RE = re.compile(r"^\[stage \S+ \(\S+\) unavailable:.*\]$", re.DOTALL)

#: ``_select_answer``'s per-terminal header in a multi-terminal join:
#: ``### <stage_id> (<model>)`` on its own line.
_STAGE_HEADER_SPLIT_RE = re.compile(r"^### \S+ \(\S+\)$", re.MULTILINE)


def _is_degraded_placeholder_only(answer: Any) -> bool:
    """True when *answer* is nothing but engine-fabricated failure placeholders.

    Covers the "the answer IS the rendered error string" arm of
    DF-CHIMERA-V2-89: the single-terminal shape (the aggregator fails and its
    placeholder becomes the answer) and the multi-terminal join
    ``_select_answer`` builds when every terminal degraded. Any real content
    beside the placeholders makes it a genuine (possibly partially degraded)
    answer, which is NOT this failure class.
    """
    text = str(answer or "").strip()
    if not text:
        return False
    parts = [part.strip() for part in _STAGE_HEADER_SPLIT_RE.split(text)]
    parts = [part for part in parts if part]
    if not parts:
        return False
    return all(_DEGRADED_PLACEHOLDER_RE.match(part) for part in parts)


def _no_usable_answer_reason(result: Any) -> str | None:
    """Why a deliberation produced no usable answer — ``None`` when it did.

    Two triggers, both read off the engine's own result object (defensively, so
    a bare test double works too): ``answer_degraded`` — the flag the REST
    surface turns into HTTP 502 and the CLI into exit 2 (DF-CHIMERA-V2-71) —
    and an answer that is only the engine's degraded placeholder. Partial
    degradation (a dropped worker beside a real merged answer) is NOT a failure
    and keeps returning a successful result, exactly as on REST and the CLI.
    """
    upstream = getattr(result, "answer_error", None)
    if bool(getattr(result, "answer_degraded", False)):
        return str(upstream) if upstream else "the answer stage degraded"
    if _is_degraded_placeholder_only(getattr(result, "answer", "")):
        return str(upstream) if upstream else "the answer is the engine's degraded placeholder"
    return None


def build_server(
    config: ChimeraConfig | None = None,
    engine: Engine | None = None,
) -> FastMCP:
    """Construct the MCP ``FastMCP`` server.

    ``config``/``engine`` are injectable for tests.

    MCP stdio purity (DF-CHIMERA-0906-2): every log sink is forced to stderr
    — when ``config`` is None this happens BEFORE ``load_config()`` because
    provider auto-discovery logs (``provider_cache_hit`` /
    ``provider_discovery_done``) fire inside the config load and would
    otherwise hit structlog's unconfigured stdout default and corrupt the
    JSON-RPC stream. ``force_stderr=True`` also overrides a chimera.yaml
    ``observability.use_stdout: true``, so the purity is structural and cannot
    be undone by a config flip.
    """
    if config is None:
        configure_logging(Observability(use_stdout=False), force_stderr=True)
        cfg = load_config()
    else:
        cfg = config
    # Re-pin with the real config (honors log_level/langfuse) — still stderr.
    configure_logging(cfg.observability, force_stderr=True)
    server = FastMCP("chimera")
    # DF-CHIMERA-V2-9: the initialize handshake must report CHIMERA's version,
    # not the mcp SDK's. mcp 1.28.1's ``FastMCP`` accepts no ``version`` kwarg
    # (its Settings model has no version field either), so the low-level server
    # it builds keeps ``version = None`` and ``create_initialization_options()``
    # falls back to ``pkg_version("mcp")`` — advertising 1.28.1 for a 0.2.6
    # build. The low-level server is the single object every transport reads
    # (stdio, sse, streamable-http), so setting it here covers the
    # ``chimera-mcp`` entry point and the ``chimera mcp`` click path alike.
    # Re-check this seam when the mcp pin is bumped: a future SDK that exposes
    # the kwarg should be used instead of this private assignment.
    server._mcp_server.version = __version__
    state = {"engine": engine or Engine(cfg, LiteLLMGateway(cfg)), "config": cfg}

    @server.tool()
    async def chimera_deliberate(
        prompt: str,
        formation: str = "auto",
        stage_models: dict[str, str] | None = None,
        dag: dict[str, Any] | None = None,
        allow_custom_dag: bool = False,
        progressive: bool = False,
        wait_messages: list[str] | None = None,
        trigger: str | None = None,
    ) -> str:
        """Run a full multi-model deliberation and return the merged answer + trace.

        ``stage_models`` forces models per stage (stage_id → model).
        ``dag`` defines a full client DAG (requires ``allow_custom_dag=True``).
        ``progressive=True`` turns progressive prompting ON for every worker
        stage of the run (inherited stages included), whether or not
        ``wait_messages`` is given; it never turns it off. ``wait_messages``
        feeds those context messages one at a time and is itself sufficient to
        enable progressive prompting, so ``progressive`` alone adds no extra
        provider calls: the stage prompt is then sent once, exactly as in a
        non-progressive run. ``trigger`` overrides the final message that asks
        for the real output and is only used when ``wait_messages`` is set.

        DF-CHIMERA-V2-7: an unknown ``formation`` returns an error payload
        (``unknown_formation`` + the available names) instead of silently
        deliberating with the dispatcher's ``auto`` fallback — the same rule
        the CLI (exit 2) and ``POST /v1/deliberate`` (HTTP 422) enforce. An
        explicit ``dag`` replaces formation selection and is exempt. The
        success payload shape is unchanged.

        DF-CHIMERA-0917-5: when the server holds NO formations at all (no
        config was found / the config defines no presets — e.g. a fresh
        checkout where ``chimera.yaml`` is untracked, or a bare pip install),
        the payload is ``config_missing`` with the actionable remedy
        (``chimera config init`` / ``CHIMERA_CONFIG``) instead of
        ``unknown_formation`` + ``available: []``, which told an operator
        nothing about how to fix it. The ``unknown_formation`` + ``available``
        payload is unchanged for the case where formations DO exist.

        DF-CHIMERA-V2-89: a run that produced NO usable answer is reported as
        an MCP ERROR (``isError: true``) instead of a success whose ``answer``
        happens to be the engine's failure text. That happens when every
        provider call fails (e.g. no credentials) so the answer stage degrades.
        The failed result still carries the FULL payload — ``answer`` +
        ``trace`` incl. ``worker_failures`` and the dispatch info — plus the
        machine-readable markers ``error: "no_usable_answer"``,
        ``answer_degraded`` and ``answer_error``, so a scripted client can act
        on the failure without pattern-matching prose. The same failure class
        is HTTP 502 on ``POST /v1/deliberate`` and exit 2 on the CLI. The
        success payload is unchanged: ``isError: false`` with the merged answer.
        """
        from chimera.config import DeliberationOverrides

        cfg: ChimeraConfig = state["config"]
        # DF-CHIMERA-V2-33: `auto` is a built-in formation backed by
        # `Config.auto_formation` — valid even when the config lists no
        # `auto:` entry (the docs example's shape). EXCEPTION: a config with
        # NO formations at all still answers ``config_missing`` (DF-CHIMERA-
        # 0917-5) — the auto dispatcher has no catalog to design from, so
        # "auto is built-in" cannot conjure one.
        fmts = cfg.formations
        auto_ok = formation == "auto" and fmts
        if dag is None and formation not in fmts and not auto_ok:
            if not cfg.formations:
                return json.dumps(
                    {
                        "error": "config_missing",
                        "formation": formation,
                        "hint": (
                            "No formations are configured. Run `chimera config init` "
                            "in the working directory (or set CHIMERA_CONFIG) and "
                            "restart the MCP server."
                        ),
                    },
                    indent=2,
                )
            return json.dumps(
                {
                    "error": "unknown_formation",
                    "formation": formation,
                    "available": sorted(cfg.formations),
                    "hint": "Call chimera_formations to list available formations.",
                },
                indent=2,
            )
        overrides = DeliberationOverrides(
            stage_models=stage_models,
            progressive=progressive,
            wait_messages=wait_messages,
            trigger=trigger,
        )
        result = await state["engine"].deliberate(
            prompt,
            formation,
            overrides=overrides,
            dag=dag,
            allow_custom_dag=allow_custom_dag,
        )
        payload: dict[str, Any] = {
            "answer": result.answer,
            "trace": result.trace.model_dump(mode="json"),
        }
        reason = _no_usable_answer_reason(result)
        if reason is None:
            return json.dumps(payload, indent=2)
        # DF-CHIMERA-V2-89: the engine could not produce a real answer — the
        # answer stage degraded (all workers failed / the aggregator failed) or
        # the "answer" is nothing but the engine's degraded placeholder. Flag it
        # as an MCP error AND keep the whole payload (incl. the trace) so a
        # consumer still gets worker_failures and the dispatch info. Markers
        # mirror the CLI's ``--json`` payload (DF-CHIMERA-V2-71) so every
        # surface reports the same failure class the same way.
        answer_error = getattr(result, "answer_error", None)
        payload["error"] = NO_USABLE_ANSWER_ERROR
        payload["answer_degraded"] = True
        payload["answer_error"] = answer_error
        payload["message"] = (
            f"Deliberation failed: no usable answer produced. Upstream error: {answer_error or reason}"
        )
        text = json.dumps(payload, indent=2)
        # A returned ``CallToolResult`` is passed through verbatim by the SDK's
        # tool runner (``func_metadata.convert_result``), which is how the
        # ``isError`` flag is set — raising instead would replace the payload
        # with the generic ``Error executing tool …`` text. It carries BOTH
        # channels the success arm produces: ``content`` (the JSON text a
        # scripted client parses) and ``structuredContent`` in the wrapped
        # ``{"result": …}`` shape the declared ``-> str`` output schema
        # requires (the SDK validates it before handing the result over).
        return CallToolResult(
            content=[TextContent(type="text", text=text)],
            structuredContent={"result": text},
            isError=True,
        )

    @server.tool()
    async def chimera_formations() -> str:
        """List the available formation presets."""
        cfg: ChimeraConfig = state["config"]
        return json.dumps(
            {name: preset.model_dump(exclude_none=True) for name, preset in cfg.formations.items()},
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


def run(config_path: str | None = None, parse_argv: bool = True) -> None:
    """Run the MCP server over stdio.

    Accepts an optional config path as the first CLI argument, or falls
    back to ``find_config_path()`` (walks up from CWD).

    ``parse_argv`` scans ``sys.argv`` for a positional config path. It is
    only true for the standalone ``chimera-mcp`` entry point — when the
    click CLI invokes us (``chimera mcp``), click has already consumed the
    args and ``sys.argv[1]`` is the subcommand name ``mcp``, which must NOT
    be treated as a config path (CH-GAP-028).
    """
    import sys

    if parse_argv and config_path is None and len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg in ("-h", "--help"):
                print(_USAGE, end="")
                return
            if arg == "--version":
                print(f"chimera {__version__}")
                return
            if not arg.startswith("-"):
                config_path = arg
                break
    # MCP stdio purity (DF-CHIMERA-0906-2): force every log sink to stderr
    # BEFORE load_config — provider auto-discovery runs inside the config
    # load and its structlog lines must never reach stdout ahead of the
    # JSON-RPC initialize response. build_server re-applies force_stderr with
    # the real config (log_level/langfuse) once it is loaded.
    configure_logging(Observability(use_stdout=False), force_stderr=True)
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        # Bare installs have no chimera.yaml (CH-GAP-041): the MCP
        # initialize handshake must still answer. Fall back to a default
        # config — tool calls then fail with a clear no-providers error
        # instead of crashing at handshake time.
        config = ChimeraConfig(defaults=Defaults.empty())
    server = build_server(config)
    server.run()


_USAGE = """\
usage: chimera-mcp [config_path]

Run the Chimera MCP server over stdio.

positional arguments:
  config_path   path to a Chimera config YAML (optional; when omitted,
                the config is discovered by walking up from the CWD)

options:
  -h, --help    show this help message and exit
  --version     show the package version and exit
"""


__all__ = ["build_server", "run"]
