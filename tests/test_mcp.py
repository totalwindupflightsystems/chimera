"""Tests for the MCP server tools."""

from __future__ import annotations

import json
import sys
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
