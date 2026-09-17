"""Tests for the MCP server tools."""

from __future__ import annotations

import contextlib
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yaml

pytest.importorskip("mcp")
from mcp.server.fastmcp import FastMCP  # noqa: E402

from chimera.engine import Engine  # noqa: E402
from chimera.mcp.server import build_server, run  # noqa: E402
from tests.conftest import CONFIG_DICT, FakeGateway, dispatch_json  # noqa: E402


def _make_server(config):  # type: ignore[no-untyped-def]
    def responder(model, messages, response_format=None, **kw):
        if response_format is not None:
            return _resp(dispatch_json(), model, 100, 200)
        joined = json.dumps(messages)
        if "Upstream outputs" in joined:
            return _resp("FINAL MCP ANSWER", model, 60, 90)
        return _resp(f"worker {model}", model, 20, 40)

    engine = Engine(config, FakeGateway(responder))
    return build_server(config=config, engine=engine)


def _resp(text, model, ti, to):  # type: ignore[no-untyped-def]
    from chimera.gateway import GatewayResponse
    return GatewayResponse(text=text, model=model, tokens_input=ti, tokens_output=to)


async def _call(server: FastMCP, name: str, **arguments):  # type: ignore[no-untyped-def]
    result = await server._tool_manager.call_tool(name, arguments)
    # tools may wrap the raw string; coerce to text then parse JSON
    if isinstance(result, str):
        return json.loads(result)
    text = getattr(result, "text", None)
    if text is not None:
        return json.loads(text)
    return result


@pytest.mark.asyncio
async def test_mcp_server_registers_three_tools(config) -> None:  # type: ignore[no-untyped-def]
    server = _make_server(config)
    tools = server._tool_manager.list_tools()
    names = {t.name for t in tools}
    assert names == {"chimera_deliberate", "chimera_formations", "chimera_models"}


@pytest.mark.asyncio
async def test_mcp_deliberate_tool(config) -> None:  # type: ignore[no-untyped-def]
    server = _make_server(config)
    data = await _call(server, "chimera_deliberate", prompt="hello", formation="auto")
    assert data["answer"] == "FINAL MCP ANSWER"
    assert data["trace"]["formation"] == "auto"


@pytest.mark.asyncio
async def test_mcp_formations_tool(config) -> None:  # type: ignore[no-untyped-def]
    server = _make_server(config)
    data = await _call(server, "chimera_formations")
    assert set(data) == {"auto", "simple", "debate", "audit", "speed"}


@pytest.mark.asyncio
async def test_mcp_models_tool(config) -> None:  # type: ignore[no-untyped-def]
    server = _make_server(config)
    data = await _call(server, "chimera_models")
    assert "deepseek/deepseek-chat" in data
    assert data["deepseek/deepseek-chat"]["cost_tier"] == "budget"


@pytest.mark.asyncio
async def test_mcp_deliberate_progressive(config) -> None:  # type: ignore[no-untyped-def]
    """Progressive params are accepted by the tool."""
    server = _make_server(config)
    data = await _call(
        server, "chimera_deliberate",
        prompt="hello", formation="simple",
        progressive=True,
        wait_messages=["context chunk 1", "context chunk 2"],
        trigger="Now answer the question",
    )
    assert data["answer"] == "FINAL MCP ANSWER"
    assert data["trace"]["formation"] == "simple"


# ---------------------------------------------------------------------------
# DF-CHIMERA-V2-7 — unknown formation on the MCP surface
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mcp_deliberate_unknown_formation_returns_error(config) -> None:  # type: ignore[no-untyped-def]
    """C3: an unknown formation is an error payload, not a silent ``auto`` run.

    The tool used to pass the name straight to the engine, which logged
    ``unknown_formation`` and deliberated anyway — the mirror of the CLI's
    silent fallback (the CLI now exits 2, REST answers 422).
    """
    server = _make_server(config)
    data = await _call(server, "chimera_deliberate", prompt="hello", formation="nope")
    assert data["error"] == "unknown_formation"
    assert data["formation"] == "nope"
    assert data["available"] == ["audit", "auto", "debate", "simple", "speed"]
    assert "answer" not in data  # no deliberation result smuggled in


@pytest.mark.asyncio
async def test_mcp_unknown_formation_never_calls_the_engine(config) -> None:  # type: ignore[no-untyped-def]
    """The rejection happens before the engine — zero provider calls, no billing."""
    calls: list[tuple] = []

    class SpyEngine:
        async def deliberate(self, *args, **kwargs):  # noqa: ANN002, ANN003
            calls.append((args, kwargs))
            raise AssertionError("engine must not run for an unknown formation")

    server = build_server(config=config, engine=SpyEngine())
    data = await _call(server, "chimera_deliberate", prompt="hello", formation="nope")
    assert data["error"] == "unknown_formation"
    assert calls == []


@pytest.mark.asyncio
async def test_mcp_explicit_dag_bypasses_formation_validation(config) -> None:  # type: ignore[no-untyped-def]
    """An explicit DAG replaces formation selection, so ``formation`` is exempt."""
    calls: list[tuple] = []

    class DagEngine:
        async def deliberate(self, prompt, formation, **kwargs):  # noqa: ANN003
            calls.append((prompt, formation, kwargs))
            return SimpleNamespace(
                answer="dag answer",
                trace=SimpleNamespace(
                    model_dump=lambda mode: {"formation": formation}
                ),
            )

    server = build_server(config=config, engine=DagEngine())
    dag = {"stages": [{"id": "s1", "kind": "worker", "model": "m",
                       "depends_on": []}], "edges": []}
    data = await _call(
        server, "chimera_deliberate", prompt="hello", formation="nope",
        dag=dag, allow_custom_dag=True,
    )
    assert data["answer"] == "dag answer"
    assert len(calls) == 1
    assert calls[0][2]["dag"] == dag


def test_mcp_run_with_explicit_config_path(tmp_path) -> None:
    """``run(config_path=...)`` loads the config, builds the server, and starts it."""
    cfg_file = tmp_path / "chimera.yaml"
    cfg_file.write_text(yaml.safe_dump(CONFIG_DICT), encoding="utf-8")

    fake_server = MagicMock(spec=FastMCP)
    fake_server.run = MagicMock()
    with patch("chimera.mcp.server.build_server", return_value=fake_server) as build_mock:
        run(config_path=str(cfg_file))

    build_mock.assert_called_once()
    # The config passed to build_server must be the one loaded from cfg_file.
    from chimera.config import ChimeraConfig
    cfg_arg = build_mock.call_args.args[0]
    assert isinstance(cfg_arg, ChimeraConfig)
    fake_server.run.assert_called_once()


def test_mcp_run_tolerates_missing_config(tmp_path, monkeypatch) -> None:
    """Bare installs have no chimera.yaml — the handshake must still work (CH-GAP-041).

    ``run()`` with no config file anywhere falls back to an empty default
    config instead of crashing with FileNotFoundError.
    """
    from chimera.config import ChimeraConfig

    fake_server = MagicMock(spec=FastMCP)
    fake_server.run = MagicMock()
    # No config anywhere: CHIMERA_CONFIG outranks the cwd walk-up, so it has to
    # be cleared too (the conftest fresh-checkout fixture sets it when the repo
    # root has no live chimera.yaml).
    monkeypatch.delenv("CHIMERA_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)  # no chimera.yaml in cwd or any parent
    with patch("chimera.mcp.server.build_server", return_value=fake_server) as build_mock:
        run(config_path=None, parse_argv=False)

    build_mock.assert_called_once()
    cfg_arg = build_mock.call_args.args[0]
    assert isinstance(cfg_arg, ChimeraConfig)
    assert cfg_arg.defaults.dispatcher == ""
    fake_server.run.assert_called_once()


def test_mcp_run_falls_back_to_sys_argv(tmp_path) -> None:
    """When ``config_path`` is None and ``sys.argv[1]`` is set, it is used as the path."""
    cfg_file = tmp_path / "alt-chimera.yaml"
    cfg_file.write_text(yaml.safe_dump(CONFIG_DICT), encoding="utf-8")

    fake_server = MagicMock(spec=FastMCP)
    fake_server.run = MagicMock()
    saved_argv = sys.argv
    sys.argv = [sys.argv[0], str(cfg_file)]
    try:
        with patch("chimera.mcp.server.build_server", return_value=fake_server) as build_mock:
            run()
    finally:
        sys.argv = saved_argv

    build_mock.assert_called_once()
    fake_server.run.assert_called_once()


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_mcp_run_help_flag(capsys, flag) -> None:
    """``chimera-mcp -h/--help`` prints usage and does not build the server."""
    saved_argv = sys.argv
    sys.argv = ["chimera-mcp", flag]
    try:
        with patch("chimera.mcp.server.build_server") as build_mock:
            run()
    finally:
        sys.argv = saved_argv

    build_mock.assert_not_called()
    out = capsys.readouterr().out
    assert "usage: chimera-mcp [config_path]" in out
    assert "--version" in out


def test_mcp_run_version_flag(capsys) -> None:
    """``chimera-mcp --version`` prints the package version without building the server."""
    from chimera import __version__

    saved_argv = sys.argv
    sys.argv = ["chimera-mcp", "--version"]
    try:
        with patch("chimera.mcp.server.build_server") as build_mock:
            run()
    finally:
        sys.argv = saved_argv

    build_mock.assert_not_called()
    assert __version__ in capsys.readouterr().out


def test_run_parse_argv_flag(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """parse_argv=False (click path) must NOT consume sys.argv (CH-GAP-028).

    `chimera mcp` used to crash with FileNotFoundError: 'mcp' because run()
    re-read sys.argv — where argv[1] is the subcommand name — and treated it
    as a config path. The standalone chimera-mcp entry point still parses.
    """
    import chimera.mcp.server as mcp_server

    monkeypatch.setattr(sys, "argv", ["chimera", "mcp"])
    calls: list[str | None] = []
    monkeypatch.setattr(mcp_server, "load_config", lambda p: calls.append(p) or object())
    dummy = type("Dummy", (), {"run": lambda self: None})()
    monkeypatch.setattr(mcp_server, "build_server", lambda cfg: dummy)

    mcp_server.run(None, parse_argv=False)
    assert calls == [None], "click path: config discovery only, 'mcp' NOT consumed"

    calls.clear()
    mcp_server.run(None, parse_argv=True)
    assert calls == ["mcp"], "standalone path: first positional arg is the config path"


def test_build_server_forces_stderr_ignoring_config_use_stdout(
    monkeypatch, config  # type: ignore[no-untyped-def]
) -> None:
    """The MCP path pins every log sink to stderr even when the injected
    config says ``use_stdout=True`` — a STRUCTURAL override for the stdio
    transport (DF-CHIMERA-0906-2), not a chimera.yaml flip.
    """
    import chimera.observability as obs_mod

    monkeypatch.setattr(obs_mod, "_LOGGER_CONFIGURED", False)
    monkeypatch.setattr(obs_mod, "_CONFIGURED_STREAM", None)
    monkeypatch.setattr(obs_mod, "_CONFIGURED_LEVEL", None)

    cfg = config.model_copy(
        update={
            "observability": config.observability.model_copy(
                update={"use_stdout": True}
            )
        }
    )
    assert cfg.observability.use_stdout is True
    server = _make_server(cfg)
    assert server is not None
    # build_server(config=...) must have forced stderr despite use_stdout=True.
    assert obs_mod._CONFIGURED_STREAM is sys.stderr


# ---------------------------------------------------------------------------
# DF-CHIMERA-0917-5 — the config-less MCP surface
# ---------------------------------------------------------------------------
#
# A fresh checkout has no chimera.yaml (untracked by design) and ``run()``
# falls back to ``ChimeraConfig(defaults=Defaults.empty())`` so the initialize
# handshake still answers (CH-GAP-041). That config has NO formations, and the
# tool used to answer ``unknown_formation`` + ``available: []`` — which told an
# operator nothing about the real problem or its remedy (the 0.2.6 release gate
# failed on exactly that payload). It must now carry the actionable remedy,
# while the genuine unknown-formation case (formations DO exist) is unchanged.


def _formations_less_server():  # type: ignore[no-untyped-def]
    """A server whose config has no formations at all, with a spy engine."""
    from chimera.config import ChimeraConfig, Defaults

    calls: list[tuple] = []

    class SpyEngine:
        async def deliberate(self, *args, **kwargs):  # noqa: ANN002, ANN003
            calls.append((args, kwargs))
            raise AssertionError("a config-less server must not run a deliberation")

    cfg = ChimeraConfig(defaults=Defaults.empty())
    assert cfg.formations == {}
    return build_server(config=cfg, engine=SpyEngine()), calls


@pytest.mark.asyncio
async def test_mcp_config_less_deliberate_returns_actionable_remedy() -> None:
    """No formations → ``config_missing`` naming ``chimera config init``."""
    server, calls = _formations_less_server()
    data = await _call(server, "chimera_deliberate", prompt="hello", formation="simple")
    assert data["error"] == "config_missing"
    assert data["formation"] == "simple"
    assert "chimera config init" in data["hint"]
    assert "CHIMERA_CONFIG" in data["hint"]
    assert "answer" not in data
    assert calls == [], "the engine must not run for a config-less server"


@pytest.mark.asyncio
async def test_mcp_config_less_deliberate_default_formation_also_hints() -> None:
    """The tool's own default formation ('auto') gets the same remedy."""
    server, _ = _formations_less_server()
    data = await _call(server, "chimera_deliberate", prompt="hello")
    assert data["error"] == "config_missing"
    assert data["formation"] == "auto"


@pytest.mark.asyncio
async def test_mcp_unknown_formation_still_reported_when_formations_exist(config) -> None:  # type: ignore[no-untyped-def]
    """Parity: an unknown name with formations present keeps the old payload.

    The ``config_missing`` branch must not swallow the DF-CHIMERA-V2-7 contract
    (``unknown_formation`` + the available names).
    """
    assert config.formations, "premise: the fixture config defines formations"
    server = _make_server(config)
    data = await _call(server, "chimera_deliberate", prompt="hello", formation="nope")
    assert data["error"] == "unknown_formation"
    assert data["available"] == ["audit", "auto", "debate", "simple", "speed"]
    assert "hint" not in data or "chimera config init" not in data["hint"]


@pytest.mark.asyncio
async def test_mcp_config_less_deliberate_still_accepts_an_explicit_dag() -> None:
    """An explicit DAG replaces formation selection — the remedy must not fire."""
    from chimera.config import ChimeraConfig, Defaults

    class DagEngine:
        async def deliberate(self, prompt, formation, **kwargs):  # noqa: ANN003
            return SimpleNamespace(
                answer="dag answer",
                trace=SimpleNamespace(model_dump=lambda mode: {"formation": formation}),
            )

    cfg = ChimeraConfig(defaults=Defaults.empty())
    server = build_server(config=cfg, engine=DagEngine())
    dag = {"stages": [{"id": "s1", "kind": "worker", "model": "m", "depends_on": []}], "edges": []}
    data = await _call(
        server, "chimera_deliberate", prompt="hello", formation="nope",
        dag=dag, allow_custom_dag=True,
    )
    assert data["answer"] == "dag answer"


# ---------------------------------------------------------------------------
# DF-CHIMERA-V2-9 — the initialize handshake must report the PACKAGE version
# ---------------------------------------------------------------------------
#
# The MCP server advertised the mcp SDK's own version: ``FastMCP("chimera")``
# takes no ``version`` kwarg (nor does its Settings model), so the low-level
# server it builds keeps ``version = None`` and
# ``create_initialization_options()`` falls back to ``pkg_version("mcp")``. A
# real client therefore read
# ``serverInfo: {"name": "chimera", "version": "1.28.1"}`` for a 0.2.6 build,
# while ``chimera --version`` printed 0.2.6 — a surface-parity defect of the
# same class as DF-CHIMERA-V2-7 (REST already reports ``chimera.__version__``;
# see tests/test_version.py). The unit tests pin the wiring, the subprocess
# test pins the wire.

MCP_INITIALIZE_REQUEST = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "df-chimera-v2-9", "version": "0.0.1"},
    },
}


def _mcp_console_script() -> Path:
    """The REAL ``chimera-mcp`` console script of the running interpreter's venv."""
    return Path(sys.executable).parent / "chimera-mcp"


def _read_initialize_line(cmd, cwd, env, timeout_s: float = 15.0) -> str:
    """Spawn *cmd*, send one initialize request, return its first stdout line.

    Paced like a real client: stdin stays open while the response is read, then
    the child is killed — the handshake answer is the whole contract here, and
    being killed after it is tolerated (no orderly SDK shutdown is needed).
    """
    proc = subprocess.Popen(
        [str(part) for part in cmd],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=str(cwd),
        env=env,
    )
    try:
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write((json.dumps(MCP_INITIALIZE_REQUEST) + "\n").encode())
        proc.stdin.flush()
        deadline = time.monotonic() + timeout_s
        buf = b""
        while time.monotonic() < deadline:
            ready, _, _ = select.select([proc.stdout], [], [], 0.5)
            if not ready:
                continue
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode(errors="replace").strip()
                if text:
                    return text
        raise AssertionError(f"{cmd} produced no stdout line within {timeout_s}s")
    finally:
        with contextlib.suppress(OSError):
            proc.stdin.close()
        proc.kill()
        proc.wait()


def test_build_server_reports_the_package_version(config) -> None:  # type: ignore[no-untyped-def]
    """The built server carries chimera's version, not the SDK's (unit seam)."""
    import chimera

    server = _make_server(config)
    assert server._mcp_server.version == chimera.__version__
    options = server._mcp_server.create_initialization_options()
    assert options.server_name == "chimera"
    assert options.server_version == chimera.__version__


def test_build_server_reports_the_package_version_without_a_config() -> None:
    """A config-less server (bare install / fresh checkout) reports it too."""
    import chimera
    from chimera.config import ChimeraConfig, Defaults

    server = build_server(config=ChimeraConfig(defaults=Defaults.empty()), engine=object())
    options = server._mcp_server.create_initialization_options()
    assert options.server_version == chimera.__version__


def test_real_mcp_entry_point_reports_the_package_version(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """E2E: the REAL ``chimera-mcp`` handshake advertises the package version.

    Hermetic: the child runs in an empty temp cwd with ``CHIMERA_CONFIG``
    removed, so it loads the config-less fallback and touches no live config or
    provider. A config-less server must still handshake — that is the intended
    behaviour (CH-GAP-041).
    """
    from importlib.metadata import version as dist_version

    import chimera

    entry = _mcp_console_script()
    assert entry.is_file(), f"{entry} does not exist — cannot drive the real entry point"
    env = {k: v for k, v in os.environ.items() if k != "CHIMERA_CONFIG"}
    env["PYTHONUNBUFFERED"] = "1"

    line = _read_initialize_line([entry], tmp_path, env)
    payload = json.loads(line)
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 1
    info = payload["result"]["serverInfo"]
    assert info["name"] == "chimera"
    assert info["version"] == chimera.__version__
    assert info["version"] != dist_version("mcp"), "the mcp SDK version leaked into the handshake"
