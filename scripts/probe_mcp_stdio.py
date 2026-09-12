#!/usr/bin/env python3
"""Raw stdio MCP stdout-purity probe / gate (DF-CHIMERA-0906-2, DF-CHIMERA-0911-1).

Spawns the real chimera MCP entry point over stdio and drives
initialize -> notifications/initialized -> tools/list -> tools/call
chimera_deliberate. FAILS (exit 1) if ANY stdout line is not a valid JSON-RPC
2.0 message — provider-discovery / structlog / SDK lines must never reach
stdout ahead of the initialize response.

Depth call: a REAL ``chimera_deliberate`` tools/call (small deterministic
arithmetic prompt). A handshake/catalog probe (``chimera_models``) never
triggers the lazy LiteLLM import, so the published 0.2.3 wheel passed a
models-only probe while still polluting stdout on a real deliberation call.
This probe must NEVER regress to a shallow call — tests/test_probe_mcp_stdio.py
pins the request contract.

Formation is selectable (DF-CHIMERA-0911-1): the leak is formation-dependent
(``simple`` was clean while ``speed``'s OpenRouter leg made LiteLLM print an
ANSI "Provider List" banner to stdout), so a release gate must be able to
drive a non-default formation without editing the script:

    python3 scripts/probe_mcp_stdio.py .venv/bin/chimera-mcp
    python3 scripts/probe_mcp_stdio.py --formation=speed .venv/bin/chimera-mcp
    CHIMERA_PROBE_FORMATION=speed python3 scripts/probe_mcp_stdio.py .venv/bin/chimera-mcp

``--formation`` is a single probe-owned token (``--formation=NAME``) and is
stripped from the child command, so it can never be confused with the server
argv; the env var is invisible to the child command by construction.

The request/validation contract lives in importable pure functions
(``build_messages``, ``parse_formation``, ``is_jsonrpc_line``,
``collect_responses``, ``extract_tool_text``, ``check_depth_result``,
``check_handshake``) so the offline regression suite can verify it without
spawning chimera or touching the network; only ``main``/``drive_stdio`` do
subprocess I/O.

Usage:
    python3 scripts/probe_mcp_stdio.py .venv/bin/chimera-mcp
    python3 scripts/probe_mcp_stdio.py .venv/bin/chimera mcp

Exit codes: 0 = stdout pure (all JSON-RPC, responses 1/2/3 in order, 3
tools, chimera_deliberate returns JSON with a non-empty answer);
1 = pollution or malformed response; 2 = usage error (bad formation option).
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEPTH_TOOL = "chimera_deliberate"
DEPTH_PROMPT = "What is 17 * 23? Show the computation."
DEPTH_FORMATION = "simple"
DEPTH_ARGUMENTS: dict = {"prompt": DEPTH_PROMPT, "formation": DEPTH_FORMATION}
DEPTH_MARKER = "391"
DEPTH_MARKER_NOTE = "17 * 23 = 391"

#: Probe-owned formation selector. The option is a single ``--formation=NAME``
#: token; both the option and its value are removed from the child command.
PROBE_FORMATION_ENV = "CHIMERA_PROBE_FORMATION"
PROBE_FORMATION_OPTION = "--formation="

TOOL_INVENTORY = {"chimera_deliberate", "chimera_formations", "chimera_models"}
EXPECTED_ORDER = [1, 2, 3]

# A real deliberation spans dispatcher -> worker(s) -> aggregator LLM calls
# (network-bound), so the read deadline is minutes, not seconds.
READ_DEADLINE_S = 300
DRAIN_DEADLINE_S = 30


def parse_formation(argv: list[str], env: dict[str, str] | None = None) -> tuple[str, list[str]]:
    """Split the probe's own ``--formation=NAME`` option out of ``argv``.

    Returns ``(formation, child_cmd)``: the formation to drive and the child
    command with every probe-owned token removed. The env var
    ``CHIMERA_PROBE_FORMATION`` is honored when no option is given. The
    option must be the ``--formation=NAME`` form — a bare ``--formation NAME``
    pair is rejected by :func:`main` (exit 2) rather than guessed at, because
    the following token could equally be the child's config path.
    """
    environ = os.environ if env is None else env
    formation = (environ.get(PROBE_FORMATION_ENV) or "").strip() or DEPTH_FORMATION
    cmd: list[str] = []
    for arg in argv:
        if arg.startswith(PROBE_FORMATION_OPTION):
            value = arg[len(PROBE_FORMATION_OPTION) :].strip()
            formation = value or formation
            continue
        cmd.append(arg)
    return formation, cmd


def depth_arguments(formation: str = DEPTH_FORMATION) -> dict:
    """The chimera_deliberate arguments for one formation."""
    return {"prompt": DEPTH_PROMPT, "formation": formation}


def build_messages(formation: str = DEPTH_FORMATION) -> list[dict]:
    """The exact JSON-RPC conversation the probe drives: ids 1..3 in order."""
    return [
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
            "params": {"name": DEPTH_TOOL, "arguments": depth_arguments(formation)},
        },
    ]


def is_jsonrpc_line(line: str) -> bool:
    """A stdout line is 'pure' iff it parses as a JSON-RPC 2.0 object."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return False
    return isinstance(obj, dict) and obj.get("jsonrpc") == "2.0"


def collect_responses(stdout_lines: list[str]) -> tuple[list[int], dict[int, dict]]:
    """Extract response ids (in arrival order) and responses by id."""
    order: list[int] = []
    responses: dict[int, dict] = {}
    for text in stdout_lines:
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("jsonrpc") == "2.0" and obj.get("id") is not None:
            responses[int(obj["id"])] = obj
            order.append(int(obj["id"]))
    return order, responses


def extract_tool_text(result: dict) -> str:
    """Extract the tool's text payload from an MCP CallToolResult shape."""
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
    return ""


def check_depth_result(r3: dict) -> tuple[list[str], dict]:
    """Validate the tools/call chimera_deliberate result.

    Returns (problems, info). ``info["answer"]`` carries the merged answer
    when the call succeeded; ``info["marker_hit"]`` says whether the
    deterministic arithmetic marker (17 * 23 = 391) appears in it.
    """
    problems: list[str] = []
    info: dict = {}
    if r3.get("isError"):
        problems.append(f"{DEPTH_TOOL} returned an error result")
    text = extract_tool_text(r3)
    if not text:
        problems.append(f"{DEPTH_TOOL} returned no text content")
        return problems, info
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        problems.append(f"{DEPTH_TOOL} did not return JSON content")
        return problems, info
    if not isinstance(payload, dict):
        problems.append(f"{DEPTH_TOOL} JSON is not an object")
        return problems, info
    answer = payload.get("answer", "")
    if not (isinstance(answer, str) and answer.strip()):
        problems.append(f"{DEPTH_TOOL} returned an empty answer")
        return problems, info
    info["answer"] = answer
    info["marker_hit"] = DEPTH_MARKER in answer
    return problems, info


def check_handshake(stdout_lines: list[str], order: list[int], responses: dict[int, dict]) -> list[str]:
    """Purity + ordering + inventory checks shared by every probe run."""
    problems: list[str] = []
    bad = [(i, line[:160]) for i, line in enumerate(stdout_lines, 1) if not is_jsonrpc_line(line)]
    if bad:
        problems.append(f"non-JSON-RPC stdout lines: {bad}")
    if order != EXPECTED_ORDER:
        problems.append(f"responses missing/out of order: got ids {order}, expected {EXPECTED_ORDER}")
    if stdout_lines:
        try:
            first_id = json.loads(stdout_lines[0]).get("id")
            if first_id != 1:
                problems.append("initialize response is not stdout line 1")
        except json.JSONDecodeError:
            problems.append("stdout line 1 is not JSON")
    tool_names = {t.get("name") for t in responses.get(2, {}).get("result", {}).get("tools", [])}
    if tool_names != TOOL_INVENTORY:
        problems.append(f"tools/list returned {tool_names}")
    return problems


def drive_stdio(
    cmd: list[str], env: dict[str, str], cwd: str, formation: str = DEPTH_FORMATION
) -> tuple[list[str], list[int], dict[int, dict], str]:
    """Run the JSON-RPC conversation against ``cmd`` over real stdio pipes.

    Paced like a real MCP client: stdin stays open while responses are read
    (closing stdin early races the mcp SDK's EOF shutdown and can drop the
    last response), then stdin is closed and the process is allowed to exit.
    """
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=cwd,
    )
    assert proc.stdin is not None and proc.stdout is not None

    msgs = build_messages(formation)
    proc.stdin.write("".join(json.dumps(m) + "\n" for m in msgs).encode())
    proc.stdin.flush()

    stdout_lines: list[str] = []
    buf = b""

    def _drain() -> None:
        nonlocal buf
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
            if text:
                stdout_lines.append(text)

    deadline = time.monotonic() + READ_DEADLINE_S
    while len(collect_responses(stdout_lines)[0]) < 3 and time.monotonic() < deadline:
        ready, _, _ = select.select([proc.stdout], [], [], 0.5)
        if ready:
            _drain()
    proc.stdin.close()
    while time.monotonic() < deadline + DRAIN_DEADLINE_S:
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
    order, responses = collect_responses(stdout_lines)
    return stdout_lines, order, responses, err


def main(argv: list[str] | None = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]
    if any(a == PROBE_FORMATION_OPTION.rstrip("=") for a in raw):
        print(
            f"usage error: pass the formation as {PROBE_FORMATION_OPTION}NAME "
            f"(a single token) or set {PROBE_FORMATION_ENV}",
            file=sys.stderr,
        )
        return 2
    formation, cmd = parse_formation(raw)
    if not cmd:
        cmd = [os.path.join(REPO, ".venv", "bin", "chimera-mcp")]

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    stdout_lines, order, responses, err = drive_stdio(cmd, env, _repo_cwd(), formation)

    problems = check_handshake(stdout_lines, order, responses)
    depth_problems, depth_info = check_depth_result(responses.get(3, {}).get("result", {}))
    problems.extend(depth_problems)

    tool_names = {t.get("name") for t in responses.get(2, {}).get("result", {}).get("tools", [])}
    print(f"CHILD_CMD={' '.join(cmd)}")
    print(f"FORMATION={formation}")
    print(f"NON_JSON_RPC_STDOUT_LINES={sum(1 for ln in stdout_lines if not is_jsonrpc_line(ln))}")
    print(f"RESPONSE_IDS={order}")
    print(f"TOOL_NAMES={sorted(tool_names)}")
    print(f"DEPTH_TOOL={DEPTH_TOOL}")
    answer = depth_info.get("answer", "")
    if isinstance(answer, str) and answer.strip():
        first_line = next((ln.strip() for ln in answer.splitlines() if ln.strip()), "")
        marker = "hit" if depth_info.get("marker_hit") else "NOT stated verbatim"
        print(f"ANSWER_CHARS={len(answer)}")
        print(f"ANSWER_MARKER={DEPTH_MARKER_NOTE}: {marker}")
        print(f"ANSWER_HEAD={first_line[:120]!r}")
    for i, line in enumerate(stdout_lines, 1):
        print(f"  stdout[{i}]: {line[:120]}")
    if problems:
        print("PROBE FAIL:")
        for p in problems:
            print(f"  - {p}")
        print("=== STDERR (last 30 lines) ===")
        print("\n".join(err.splitlines()[-30:]))
        return 1
    print(
        f"PROBE OK: all stdout lines are JSON-RPC 2.0; initialize is line 1; "
        f"3 tools; {DEPTH_TOOL} returned a non-empty merged answer"
    )
    return 0


def _repo_cwd() -> str:
    """cwd for the spawned server: the repo root (finds its chimera.yaml)."""
    return REPO


if __name__ == "__main__":
    sys.exit(main())
