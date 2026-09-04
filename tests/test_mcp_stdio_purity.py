"""Subprocess stdout-purity regression test for the MCP stdio transport.

DF-CHIMERA-0906-2: provider auto-discovery logs used to reach stdout as
structlog console lines BEFORE the initialize JSON-RPC response, breaking
real MCP clients (stdout line 1 = ``provider_cache_hit``, line 2 =
``provider_discovery_done``, initialize shifted to line 3).

This test spawns the REAL console-script entry points (``chimera-mcp`` and
the ``chimera mcp`` click path) over stdio with a temp ``chimera.yaml``
that explicitly sets ``observability.use_stdout: true`` — proving the fix
is STRUCTURAL (the MCP path forces every log sink to stderr), not a
``chimera.yaml`` flip. On pre-fix code it fails because stdout lines 1-2
are structlog console lines that do not parse as JSON-RPC.

The conversation is paced like a real MCP client: stdin stays open while
responses are read (closing stdin early races the mcp SDK's EOF shutdown
and can drop the last response), then stdin is closed and the process is
allowed to exit.
"""

from __future__ import annotations

import copy
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from tests.conftest import CONFIG_DICT

REPO = Path(__file__).resolve().parent.parent

TOOL_NAMES = {"chimera_deliberate", "chimera_formations", "chimera_models"}

MESSAGES = [
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "stdio-purity-test", "version": "0.0.1"},
        },
    },
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "chimera_models", "arguments": {}},
    },
]

SPAWN_STYLES = {
    # Console-script equivalent (chimera-mcp entry point → run()).
    "standalone": [sys.executable, "-c", "from chimera.mcp.server import run; run()"],
    # Click path: `chimera mcp` (parse_argv=False in cli/main.py).
    "cli": [sys.executable, "-m", "chimera.cli.main", "mcp"],
}


@pytest.fixture
def mcp_env(tmp_path: Path) -> dict[str, str]:
    """Isolated HOME + tmp chimera.yaml + deterministic offline provider cache.

    ``observability.use_stdout`` is forced to ``true`` so the test pins that
    stdout purity holds even when the config asks for stdout — only a
    structural fix can pass.
    """
    home = tmp_path / "home"
    (home / ".chimera").mkdir(parents=True)
    cache = {
        "_fetched_at": time.time(),
        "deepseek": {
            "env": ["DEEPSEEK_API_KEY"],
            "models": {
                "deepseek-chat": {"cost": {"input": 1.0, "output": 1.0}}
            },
        },
    }
    (home / ".chimera" / "models-dev-cache.json").write_text(
        json.dumps(cache), encoding="utf-8"
    )

    cfg_dict = copy.deepcopy(CONFIG_DICT)
    cfg_dict["observability"] = {
        # info level so provider_cache_hit / provider_discovery_done pass the
        # filter and are observable on stderr (proving redirection).
        "log_level": "info",
        "trace_enabled": False,
        "use_stdout": True,  # config asks for stdout — the fix must override
        "langfuse": {"enabled": False},
    }
    cfg_dict["provider_discovery"] = True
    cfg_path = tmp_path / "chimera.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg_dict), encoding="utf-8")

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["CHIMERA_CONFIG"] = str(cfg_path)
    env["PYTHONPATH"] = str(REPO / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _response_text(result: dict) -> str:
    """Extract the tool's text payload from an MCP CallToolResult."""
    content = result.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        if parts:
            return "".join(parts)
    text = result.get("text")
    if isinstance(text, str):
        return text
    return json.dumps(result)


@pytest.mark.parametrize("style", sorted(SPAWN_STYLES), ids=sorted(SPAWN_STYLES))
def test_mcp_stdout_is_pure_json_rpc(style: str, mcp_env: dict[str, str]) -> None:
    """Every stdout line must be JSON-RPC 2.0; responses in order, 3 tools."""
    proc = subprocess.Popen(
        SPAWN_STYLES[style],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=mcp_env,
        cwd=str(REPO),
    )
    assert proc.stdin is not None and proc.stdout is not None
    payload = "".join(json.dumps(m) + "\n" for m in MESSAGES).encode()
    proc.stdin.write(payload)
    proc.stdin.flush()

    stdout_lines: list[str] = []
    buf = b""
    responses: dict[int, dict] = {}
    order: list[int] = []

    def _drain() -> None:
        """Non-blocking drain of whatever stdout currently has buffered."""
        nonlocal buf
        try:
            ready, _, _ = select.select([proc.stdout], [], [], 0)
        except (ValueError, OSError):  # pragma: no cover - pipe already closed
            return
        if not ready:
            return
        chunk = os.read(proc.stdout.fileno(), 65536)
        if not chunk:
            return
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            text = line.decode(errors="replace").strip()
            if not text:
                continue
            stdout_lines.append(text)
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(obj, dict)
                and obj.get("jsonrpc") == "2.0"
                and obj.get("id") is not None
            ):
                responses[int(obj["id"])] = obj
                order.append(int(obj["id"]))

    # Paced like a real client: read responses while stdin stays open (an
    # early EOF races the mcp SDK shutdown and can drop the last response).
    deadline = time.monotonic() + 30
    while len(responses) < 3 and time.monotonic() < deadline:
        ready, _, _ = select.select([proc.stdout], [], [], 0.5)
        if ready:
            _drain()
    proc.stdin.close()

    # Let the server exit after EOF; drain any trailing stdout lines.
    while time.monotonic() < deadline + 10:
        if proc.poll() is not None:
            _drain()
            break
        ready, _, _ = select.select([proc.stdout], [], [], 0.5)
        if ready:
            _drain()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover - defensive
        proc.kill()
        proc.wait()
    stderr_text = (proc.stderr.read() if proc.stderr else b"").decode(errors="replace")

    bad: list[tuple[int, str]] = []
    for i, line in enumerate(stdout_lines, 1):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            bad.append((i, line[:160]))
            continue
        if not isinstance(obj, dict) or obj.get("jsonrpc") != "2.0":
            bad.append((i, line[:160]))

    joined_stdout = "\n".join(stdout_lines)
    assert bad == [], (
        f"[{style}] non-JSON-RPC stdout lines (DF-CHIMERA-0906-2 regression): {bad}\n"
        f"--- full stdout ---\n{joined_stdout}"
    )
    assert order == [1, 2, 3], (
        f"[{style}] responses missing/out of order: got ids {order} "
        f"(expected [1, 2, 3]); initialize must be stdout line 1\n{joined_stdout}"
    )
    # initialize response must literally be stdout line 1.
    first = json.loads(stdout_lines[0])
    assert first.get("id") == 1, f"[{style}] initialize is not stdout line 1"

    tools_result = responses[2].get("result", {})
    tool_names = {t.get("name") for t in tools_result.get("tools", [])}
    assert tool_names == TOOL_NAMES, f"[{style}] tools/list returned {tool_names}"

    call_result = responses[3].get("result", {})
    try:
        models_data = json.loads(_response_text(call_result))
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic
        pytest.fail(f"[{style}] chimera_models did not return JSON: {exc}\n{call_result}")
    assert isinstance(models_data, dict) and models_data, (
        f"[{style}] chimera_models returned an empty result"
    )
    assert all(isinstance(v, dict) for v in models_data.values()), (
        f"[{style}] chimera_models entries are not model dicts"
    )

    # Provider discovery logs must be REDIRECTED to stderr — proving the
    # structural fix rather than a silenced-discovery config.
    assert "provider_cache_hit" in stderr_text, (
        f"[{style}] provider_cache_hit not on stderr (was it silenced?) "
        f"stderr:\n{stderr_text[-2000:]}"
    )
    assert "provider_discovery_done" in stderr_text, (
        f"[{style}] provider_discovery_done not on stderr (was it silenced?) "
        f"stderr:\n{stderr_text[-2000:]}"
    )
