"""CH-GAP-057: gate every ``bin/`` entry point on a live JSON-RPC handshake.

``docs/REPO_LAYOUT.md`` advertises both shims (``chimera-mcp-hermes``,
``chimera-mcp-wrapper``) as the repo's MCP entry points, but nothing ever ran
them: ``chimera-mcp-wrapper`` exec'd a hardcoded interpreter path belonging to
a different checkout, so every MCP client died at exec with rc=127 ("No such
file or directory") while the layout table, the docs and the guard stayed green.

The gate is structural rather than per-file: it DISCOVERS every executable file
under ``bin/`` and drives each one through the real handshake, so a third shim
added later cannot silently escape it. Each shim is spawned with the two
JSON-RPC lines a client sends first (``initialize`` + ``tools/list``), with:

* ``CHIMERA_CONFIG`` pointed at the shipped, tracked ``chimera.yaml.example`` —
  never the developer's gitignored live ``chimera.yaml`` (mirrors the conftest
  ``_config_default_resolution_for_fresh_checkout`` fixture);
* a cwd that is NOT the repo root, because a shim that only works from the repo
  root — or that discovers a foreign ``chimera.yaml`` by walking up from the
  caller's cwd — is exactly the bug class this gate exists for.

**stdin is held open until both responses arrive, and that is load-bearing.**
Closing stdin immediately is a race, not a shortcut: on EOF the server's read
loop finishes and tears the stdio session down while the ``tools/list`` request
is still being handled, so its response is lost. Measured on this repo
(CH-GAP-057): with an immediate EOF, most runs returned 1 line — for BOTH shims,
including the known-good sibling — while holding stdin open returned 2 lines on
10/10 runs across both shims (~0.6s each). The loss is a property of the stdio
session teardown, so the brief's one-liner pipe is subject to it; a real MCP
client keeps the pipe open and so does this test.

Known limit: the skip guard mirrors the shims' own resolution order and cannot
inspect architectures, so an executable repo ``.venv`` built for a different
platform than the interpreter running the tests would be attempted rather than
skipped. That case fails loudly with the child's stderr in the assertion
message, which is the honest outcome — this gate exists to catch dead shims.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
BIN_DIR = REPO / "bin"

#: Tracked and always present (force-included in the wheel), unlike the
#: gitignored live ``chimera.yaml`` — keeps the gate hermetic in a fresh clone
#: and in CI.
EXAMPLE_CONFIG = REPO / "chimera.yaml.example"

#: ``serverInfo.name`` every chimera MCP server reports in its initialize result.
EXPECTED_SERVER_NAME = "chimera"

#: Tools ``tools/list`` must advertise.
REQUIRED_TOOLS = ("chimera_deliberate", "chimera_formations", "chimera_models")

#: The two requests an MCP client sends first, newline-delimited framing.
HANDSHAKE = (
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":'
    '"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}\n'
    '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n'
)

#: One response per request above.
RESPONSE_COUNT = 2

#: Generous budget: the server loads its provider cache. Measured at ~0.6s for
#: both replies on this box; the shim itself is a pure exec wrapper.
HANDSHAKE_TIMEOUT_S = 120

#: The shims ``docs/REPO_LAYOUT.md`` advertises. Used only as the non-vacuity
#: anchor — discovery is the glob in ``_discover_shims``, so the gate cannot be
#: satisfied by an empty or missing ``bin/``.
DOCUMENTED_SHIMS = ("chimera-mcp-hermes", "chimera-mcp-wrapper")


def _is_live_executable(path: Path) -> bool:
    """True when ``path`` is an executable file, treating unreadable as absent.

    ``Path.is_file()`` RAISES PermissionError (OSError) instead of returning
    False when a path component is not traversable — e.g. a synced ``.venv``
    whose ``bin`` lives under a 0700 home. Evaluated at module import that
    interrupts collection for the WHOLE session, so every probe here must
    tolerate it (same tolerance as ``requires_repo_venv`` in
    tests/test_release_workflow.py, QA-CHIMERA-V2-18).
    """
    try:
        return path.is_file() and os.access(path, os.X_OK)
    except OSError:
        return False


def _repo_venv_chimera_mcp() -> Path:
    """The repo-local entry point a shim prefers."""
    return REPO / ".venv" / "bin" / "chimera-mcp"


def _repo_venv_python() -> Path:
    """The repo venv's own interpreter — a dead one makes every script in it dead."""
    return REPO / ".venv" / "bin" / "python3"


def _usable_chimera_mcp() -> bool:
    """Whether a shim can resolve a server at all — the shims' own order.

    Mirrors ``bin/chimera-mcp-wrapper`` exactly: the repo venv entry point when
    its interpreter is live too, else ``chimera-mcp`` from PATH. A shim cannot
    answer the handshake without one of these, so a missing pair must SKIP this
    module (never ERROR at collection) on a bare checkout or a wheel-consumer
    environment — e.g. the Windows interpreter matrix lane, which has no
    ``.venv/bin/python3``.
    """
    if _is_live_executable(_repo_venv_chimera_mcp()) and _is_live_executable(_repo_venv_python()):
        return True
    on_path = shutil.which("chimera-mcp")
    return bool(on_path) and _is_live_executable(Path(on_path))


def _discover_shims() -> list[Path]:
    """Every executable file directly under ``bin/``, sorted, or ``[]``."""
    try:
        return sorted(p for p in BIN_DIR.iterdir() if _is_live_executable(p))
    except OSError:  # pragma: no cover - unreadable bin/ is a broken checkout
        return []


def _parse_response(raw: str) -> dict[str, Any]:
    """Parse one JSON-RPC response line, failing with the raw text if it is not JSON."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"stdout line is not JSON: {raw!r} ({exc})") from exc
    assert isinstance(parsed, dict), f"response is not a JSON object: {raw!r}"
    return parsed


def _run_handshake(shim: Path, cwd: Path) -> tuple[int, list[str], str]:
    """Spawn ``shim``, send :data:`HANDSHAKE`, return ``(rc, stdout lines, stderr)``.

    stdin stays open until both responses arrive (or the deadline expires), then
    closes; stdout is drained to EOF, and stderr is drained in its own thread so a
    chatty server cannot fill a pipe and stall the child.
    """
    env = dict(os.environ)
    env["CHIMERA_CONFIG"] = str(EXAMPLE_CONFIG)
    proc = subprocess.Popen(  # noqa: S603 - a repo-owned path, no shell, no user input
        ["bash", str(shim)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(cwd),
        env=env,
    )
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    stdout = proc.stdout
    stderr = proc.stderr
    stdin = proc.stdin
    out_lines: list[str] = []
    err_lines: list[str] = []
    out_done = threading.Event()

    def drain_stdout() -> None:
        # Line-by-line, NOT readlines(): readlines() only returns at EOF, so the
        # wait loop below would see zero lines and sit out the whole deadline
        # even though both responses arrived in under a second.
        try:
            for raw in stdout:
                out_lines.append(raw)
        finally:
            out_done.set()

    def drain_stderr() -> None:
        for raw in stderr:
            err_lines.append(raw)

    threads = [
        threading.Thread(target=drain_stdout, daemon=True),
        threading.Thread(target=drain_stderr, daemon=True),
    ]
    for thread in threads:
        thread.start()

    stdin.write(HANDSHAKE)
    stdin.flush()
    deadline = time.monotonic() + HANDSHAKE_TIMEOUT_S
    while not out_done.is_set() and len(out_lines) < RESPONSE_COUNT and time.monotonic() < deadline:
        time.sleep(0.05)
    with contextlib.suppress(BrokenPipeError):  # pragma: no cover - child died before we closed
        stdin.close()
    try:
        rc = proc.wait(timeout=HANDSHAKE_TIMEOUT_S)
    except subprocess.TimeoutExpired:  # pragma: no cover - a hung shim is a failure
        proc.kill()
        proc.wait(timeout=10)
        rc = -1
    for thread in threads:
        thread.join(timeout=5)
    return rc, out_lines, "".join(err_lines)


#: Skip — never ERROR — when no shim could resolve a server in this environment.
requires_chimera_mcp = pytest.mark.skipif(
    not _usable_chimera_mcp(),
    reason="no usable chimera-mcp (repo .venv entry point or a PATH console script)",
)


def test_bin_shims_discovery_is_anchored() -> None:
    """Discovery must find the documented shims — the gate cannot pass vacuously.

    A glob over ``bin/`` that silently discovered nothing would make the
    handshake test below an empty parametrize list (pytest reports that as a
    pass). ``docs/REPO_LAYOUT.md`` names both shims, so their presence is the
    anchor: renaming or deleting one is a docs change too.
    """
    discovered = {p.name for p in _discover_shims()}
    assert BIN_DIR.is_dir(), f"missing shim directory: {BIN_DIR}"
    assert set(DOCUMENTED_SHIMS) <= discovered, (
        f"docs/REPO_LAYOUT.md advertises {sorted(DOCUMENTED_SHIMS)}, but bin/ has {sorted(discovered)}"
    )


@requires_chimera_mcp
@pytest.mark.timeout(HANDSHAKE_TIMEOUT_S + 30)
@pytest.mark.parametrize("shim", _discover_shims(), ids=lambda shim: shim.name)
def test_bin_shim_answers_jsonrpc_handshake(shim: Path, tmp_path: Path) -> None:
    """Every executable in ``bin/`` starts and answers the initialize handshake.

    Returns 0, answers ``initialize`` with ``serverInfo.name == "chimera"``, and
    lists the three chimera tools. The cwd is ``tmp_path``, not the repo root, so
    a shim that depends on being launched from the checkout (or on discovering a
    config by walking up from the caller's cwd) fails here.
    """
    rc, out_lines, err = _run_handshake(shim, tmp_path)
    detail = f"shim={shim.name} rc={rc}\nstdout={out_lines}\nstderr={err}"

    assert rc == 0, f"shim must exit 0\n{detail}"
    assert len(out_lines) >= RESPONSE_COUNT, f"expected {RESPONSE_COUNT} JSON-RPC responses\n{detail}"

    # The server writes JSON diagnostics to stderr by design; stderr content is
    # never an assertion — it is only reported when something above failed.
    handshake = _parse_response(out_lines[0])
    assert handshake.get("id") == 1, f"stdout line 1 must be the id=1 response\n{detail}"
    result = handshake.get("result")
    assert isinstance(result, dict), f"initialize result must be an object\n{detail}"
    server_info = result.get("serverInfo", {})
    assert server_info.get("name") == EXPECTED_SERVER_NAME, (
        f"initialize must report serverInfo.name={EXPECTED_SERVER_NAME!r}, got {server_info!r}\n{detail}"
    )

    listing = _parse_response(out_lines[1])
    assert listing.get("id") == 2, f"stdout line 2 must be the id=2 response\n{detail}"
    tools = listing.get("result", {}).get("tools", [])
    names = [tool.get("name") for tool in tools]
    missing = [name for name in REQUIRED_TOOLS if name not in names]
    assert not missing, f"tools/list must advertise {list(REQUIRED_TOOLS)}, missing {missing}\n{detail}"
