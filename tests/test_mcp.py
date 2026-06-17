"""Tests for the MCP server tools."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("mcp")
from mcp.server.fastmcp import FastMCP  # noqa: E402

from chimera.engine import Engine  # noqa: E402
from chimera.mcp.server import build_server  # noqa: E402
from tests.conftest import FakeGateway, dispatch_json  # noqa: E402


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
    assert set(data) == {"auto", "simple", "debate", "audit"}


@pytest.mark.asyncio
async def test_mcp_models_tool(config) -> None:  # type: ignore[no-untyped-def]
    server = _make_server(config)
    data = await _call(server, "chimera_models")
    assert "deepseek/deepseek-chat" in data
    assert data["deepseek/deepseek-chat"]["cost_tier"] == "budget"
