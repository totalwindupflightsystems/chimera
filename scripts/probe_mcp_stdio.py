#!/usr/bin/env python3
"""Raw stdio MCP probe: initialize -> tools/list -> tools/call, print raw JSON-RPC."""
import json, subprocess, sys, os

cmd = sys.argv[1:]
if not cmd:
    cmd = [os.path.join(os.path.dirname(__file__), "..", ".venv", "bin", "chimera-mcp")]
env = dict(os.environ)
env["PYTHONUNBUFFERED"] = "1"
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, env=env, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
msgs = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "probe", "version": "0.0.1"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "chimera_models", "arguments": {}}},
]
for m in msgs:
    proc.stdin.write((json.dumps(m) + "\n").encode())
    proc.stdin.flush()
    if m.get("id"):
        line = proc.stdout.readline().decode(errors="replace").strip()
        print(f"-> {json.dumps(m)}\n<- {line}\n")
proc.stdin.close()
try:
    proc.wait(timeout=10)
except subprocess.TimeoutExpired:
    proc.kill()
err = proc.stderr.read().decode(errors="replace")
if err:
    print("=== STDERR (last 30 lines) ===")
    print("\n".join(err.splitlines()[-30:]))
