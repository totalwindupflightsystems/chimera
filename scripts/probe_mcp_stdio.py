#!/usr/bin/env python3
"""Raw stdio MCP stdout-purity probe / gate (DF-CHIMERA-0906-2).

Spawns the real chimera MCP entry point over stdio and drives
initialize -> notifications/initialized -> tools/list -> tools/call
chimera_models. FAILS (exit 1) if ANY stdout line is not a valid JSON-RPC
2.0 message — provider-discovery / structlog / SDK lines must never reach
stdout ahead of the initialize response.

Usage:
    python3 scripts/probe_mcp_stdio.py .venv/bin/chimera-mcp
    python3 scripts/probe_mcp_stdio.py .venv/bin/chimera mcp

Exit codes: 0 = stdout pure (all JSON-RPC, responses 1/2/3 in order, 3
tools, chimera_models returns JSON); 1 = pollution or malformed response.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

cmd = sys.argv[1:]
if not cmd:
    cmd = [os.path.join(_REPO, ".venv", "bin", "chimera-mcp")]

env = dict(os.environ)
env["PYTHONUNBUFFERED"] = "1"
proc = subprocess.Popen(
    cmd,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env=env,
    cwd=_REPO,
)
assert proc.stdin is not None and proc.stdout is not None

msgs = [
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "probe", "version": "0.0.1"},
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

proc.stdin.write("".join(json.dumps(m) + "\n" for m in msgs).encode())
proc.stdin.flush()

stdout_lines: list[str] = []
buf = b""
responses: dict[int, dict] = {}
order: list[int] = []


def _drain() -> None:
    global buf
    try:
        ready, _, _ = select.select([proc.stdout], [], [], 0)
    except (ValueError, OSError):
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


deadline = time.monotonic() + 30
while len(responses) < 3 and time.monotonic() < deadline:
    ready, _, _ = select.select([proc.stdout], [], [], 0.5)
    if ready:
        _drain()
proc.stdin.close()
while time.monotonic() < deadline + 10:
    if proc.poll() is not None:
        _drain()
        break
    ready, _, _ = select.select([proc.stdout], [], [], 0.5)
    if ready:
        _drain()
try:
    proc.wait(timeout=5)
except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait()
err = (proc.stderr.read() if proc.stderr else b"").decode(errors="replace")

bad: list[tuple[int, str]] = []
for i, line in enumerate(stdout_lines, 1):
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        bad.append((i, line[:160]))
        continue
    if not isinstance(obj, dict) or obj.get("jsonrpc") != "2.0":
        bad.append((i, line[:160]))

problems: list[str] = []
if bad:
    problems.append(f"non-JSON-RPC stdout lines: {bad}")
if order != [1, 2, 3]:
    problems.append(f"responses missing/out of order: got ids {order}, expected [1, 2, 3]")
if stdout_lines:
    try:
        first_id = json.loads(stdout_lines[0]).get("id")
        if first_id != 1:
            problems.append("initialize response is not stdout line 1")
    except json.JSONDecodeError:
        problems.append("stdout line 1 is not JSON")
tool_names = {
    t.get("name")
    for t in responses.get(2, {}).get("result", {}).get("tools", [])
}
if tool_names != {"chimera_deliberate", "chimera_formations", "chimera_models"}:
    problems.append(f"tools/list returned {tool_names}")
r3 = responses.get(3, {}).get("result", {})
r3_text = ""
for item in r3.get("content", []) if isinstance(r3.get("content"), list) else []:
    if isinstance(item, dict) and item.get("type") == "text":
        r3_text += item.get("text", "")
if not r3_text:
    r3_text = r3.get("text", "") if isinstance(r3.get("text"), str) else ""
try:
    models_data = json.loads(r3_text)
    if not isinstance(models_data, dict) or not models_data:
        problems.append("chimera_models returned empty/non-dict JSON")
except json.JSONDecodeError:
    problems.append("chimera_models did not return JSON content")

print(f"NON_JSON_RPC_STDOUT_LINES={len(bad)}")
print(f"RESPONSE_IDS={order}")
print(f"TOOL_NAMES={sorted(tool_names)}")
print(f"MODEL_COUNT={len(models_data) if 'models_data' in dir() and isinstance(models_data, dict) else 0}")
for i, line in enumerate(stdout_lines, 1):
    print(f"  stdout[{i}]: {line[:120]}")
if problems:
    print("PROBE FAIL:")
    for p in problems:
        print(f"  - {p}")
    print("=== STDERR (last 30 lines) ===")
    print("\n".join(err.splitlines()[-30:]))
    sys.exit(1)
print("PROBE OK: all stdout lines are JSON-RPC 2.0; initialize is line 1; "
      "3 tools; chimera_models returns valid JSON")
sys.exit(0)
