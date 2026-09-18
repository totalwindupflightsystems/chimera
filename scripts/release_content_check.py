#!/usr/bin/env python3
"""Release-content check — the PUBLISHED artifact carries the first-run fixes.

DF-CHIMERA-V2-9 / DF-CHIMERA-V2-8.

The release-verify job installs the EXACT published version from PyPI and then
runs the README-surface battery, the live E2E journey and the deep MCP probe.
None of those asserted the two first-run behaviours a tag can ship WITHOUT, and
both fixes landed on the branch after the tag that shipped them:

* DF-CHIMERA-V2-9 (d44599e) — the ``chimera-mcp`` initialize handshake must
  advertise CHIMERA's package version. Pre-fix it advertised the ``mcp`` SDK's
  own version (1.28.1) for a 0.2.6 build, because ``FastMCP`` takes no version
  kwarg and the low-level server falls back to ``pkg_version("mcp")``. A real
  MCP client reading the handshake could not tell which chimera build it had
  reached, while ``chimera --version`` said 0.2.6 — the same surface-parity
  class as DF-CHIMERA-V2-7.
* DF-CHIMERA-V2-8 (82fc656) — the installed ``chimera.config`` missing-config
  error must name ``chimera config init`` as the remedy. Pre-fix it only said
  "Copy chimera.yaml.example to chimera.yaml", which a bare pip install cannot
  do: the template lives inside the installed package, not in the cwd.

Both are behaviours of the INSTALLED artifact, so both are asserted by
EXECUTING the pinned venv's own code:

* ``mcp-handshake-version`` spawns ``<venv>/bin/chimera-mcp`` and drives one
  real ``initialize`` request over stdio; the response's ``serverInfo.version``
  is compared with ``--expected-version`` AND with the venv's own ``mcp``
  distribution, so a handshake that reports the SDK version is named as exactly
  that instead of as a generic mismatch;
* ``missing-config-remedy`` runs its probe through ``<venv>/bin/python``,
  imports the INSTALLED ``chimera.config`` and reads the ``FileNotFoundError``
  message ``find_config_path`` raises in a fresh empty directory;
* ``installed-dist-version`` anchors the artifact identity: the venv's own
  distribution metadata must BE ``--expected-version`` (a release gate that
  judges the checkout instead of the artifact is the defect class this whole
  file exists for).

Invariants:

* Nothing here reads the source checkout. Every child runs from a fresh empty
  temp cwd with ``PYTHONPATH`` and ``CHIMERA_CONFIG`` removed from its
  environment, so ``import chimera`` can only resolve inside the venv under
  test.
* No network and no provider credentials: an ``initialize`` handshake needs
  neither, and ``chimera.mcp.server.run`` answers it for a bare install by
  falling back to an empty default config.
* ``--expected-version`` is REQUIRED — comparing the artifact against itself
  would defeat the gate, so a missing/blank value is a usage error (exit 2),
  never a silently derived default. The version is never read back from the
  artifact under test; the caller derives it from the tag.

Usage:
    python3 scripts/release_content_check.py --venv /tmp/release-venv --expected-version 0.2.7
    python3 scripts/release_content_check.py --expected-version 0.2.7   # defaults to ./.venv

Exit codes: 0 = every release-content check passed; 1 = at least one check
failed; 2 = usage error (unknown option, missing value, missing
--expected-version, or a --venv that is not a directory).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import select
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent

#: Distribution names as the venv's own installed metadata records them.
PACKAGE_DIST = "chimera-deliberation"
MCP_DIST = "mcp"

#: The request every MCP client sends first.
INITIALIZE_REQUEST: dict[str, Any] = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "release-content-check", "version": "0.0.1"},
    },
}

#: Evidence token for a handshake/message that carries no value at all.
MISSING_VALUE = "(missing)"

#: Dropped from every child env: a pre-set config path or sys.path entry would
#: let the child read something other than the artifact under test.
UNSET_ENV_VARS = ("CHIMERA_CONFIG", "PYTHONPATH")

#: Program driven through the installed venv's interpreter. The
#: ``release-content-remedy`` marker comment is how the offline fixture in
#: tests/test_release_workflow.py recognises the probe when it stands in for a
#: venv interpreter.
REMEDY_PROBE = """\
# release-content-remedy
import json, sys
from pathlib import Path
from chimera.config import find_config_path

try:
    found = find_config_path(Path.cwd())
except FileNotFoundError as exc:
    print(json.dumps({"remedy": str(exc)}))
else:
    print(json.dumps({"found": str(found)}))
    sys.exit(3)
"""

#: Exit code the probe uses when a ``chimera.yaml`` WAS found while walking up
#: from its cwd. The remedy cannot be judged then — that is a setup problem for
#: the gate, never a pass.
PROBE_FOUND_CONFIG_EXIT = 3

#: Per-check wall-clock budget. Both checks are local process spawns.
CHECK_TIMEOUT_S = 60

#: Grace after the initialize response for the server to exit on EOF.
DRAIN_GRACE_S = 5.0

USAGE_LINE = "usage: release_content_check.py --expected-version VERSION [--venv PATH]"

#: The fix each failure names, so the message tells a release operator what to
#: do next instead of only what was wrong.
VERSION_FIX = (
    "the installed build predates DF-CHIMERA-V2-9 (src/chimera/mcp/server.py must set the "
    "low-level MCP server's version inside build_server, so every transport advertises "
    "chimera's package version)"
)
REMEDY_FIX = (
    "the installed build predates DF-CHIMERA-V2-8 (src/chimera/config.py find_config_path must "
    "name `chimera config init`, which bootstraps from the wheel-shipped template)"
)


class UsageError(Exception):
    """Bad check input (exit 2) — not a failed release-content check."""


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one check, with an actionable reason either way."""

    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class InitializeOutcome:
    """What one ``initialize`` exchange produced, and how it went wrong."""

    version: str | None
    responded: bool
    problem: str | None
    stderr_tail: str


@dataclass
class ReleaseContentProbe:
    """The release-content checks, run against one installed venv."""

    venv: Path
    expected_version: str
    timeout: int = CHECK_TIMEOUT_S
    evidence: dict[str, str] = field(default_factory=dict)

    def run(self) -> list[CheckResult]:
        """Every check, in report order (identity first, then the two fixes)."""
        return [
            self.check_installed_dist_version(),
            self.check_mcp_handshake(),
            self.check_missing_config_remedy(),
        ]

    # ------------------------------------------------------------------ #
    # check 1 — the venv really is the pinned published artifact
    # ------------------------------------------------------------------ #

    def check_installed_dist_version(self) -> CheckResult:
        name = "installed-dist-version"
        actual = installed_dist_version(self.venv, PACKAGE_DIST)
        self.evidence["CHIMERA_DIST_VERSION"] = actual or MISSING_VALUE
        self.evidence["MCP_SDK_VERSION"] = (
            installed_dist_version(self.venv, MCP_DIST) or MISSING_VALUE
        )
        if actual == self.expected_version:
            return CheckResult(name, True, f"installed {PACKAGE_DIST} is {actual}")
        return CheckResult(
            name,
            False,
            f"installed {PACKAGE_DIST} metadata says {actual or MISSING_VALUE}, expected "
            f"{self.expected_version}: this venv does not hold the pinned published version, so "
            "the release-content checks would judge the wrong artifact",
        )

    # ------------------------------------------------------------------ #
    # check 2 — DF-CHIMERA-V2-9 (MCP initialize advertises the package version)
    # ------------------------------------------------------------------ #

    def check_mcp_handshake(self) -> CheckResult:
        name = "mcp-handshake-version"
        binary = venv_executable(self.venv, "chimera-mcp")
        if not binary.exists():
            self.evidence["HANDSHAKE_VERSION"] = f"(no {binary})"
            return CheckResult(
                name,
                False,
                f"{binary} does not exist: the installed wheel ships no chimera-mcp console "
                "script, so no MCP client can reach this build",
            )
        sdk_version = installed_dist_version(self.venv, MCP_DIST)
        with tempfile.TemporaryDirectory(prefix="chimera-release-content-") as workdir:
            outcome = drive_initialize([str(binary)], child_env(), workdir, self.timeout)
        if outcome.problem is not None:
            self.evidence["HANDSHAKE_VERSION"] = "(no response)"
            return CheckResult(name, False, outcome.problem)
        self.evidence["HANDSHAKE_VERSION"] = outcome.version or MISSING_VALUE
        problem = handshake_version_problem(self.expected_version, outcome.version, sdk_version)
        if problem is not None:
            return CheckResult(name, False, problem)
        return CheckResult(name, True, f"initialize handshake advertises {outcome.version}")

    # ------------------------------------------------------------------ #
    # check 3 — DF-CHIMERA-V2-8 (missing-config remedy names config init)
    # ------------------------------------------------------------------ #

    def check_missing_config_remedy(self) -> CheckResult:
        name = "missing-config-remedy"
        python = venv_executable(self.venv, "python")
        if not python.exists():
            self.evidence["MISSING_CONFIG_REMEDY"] = f"(no {python})"
            return CheckResult(
                name, False, f"{python} does not exist: cannot execute the installed package"
            )
        with tempfile.TemporaryDirectory(prefix="chimera-release-content-") as workdir:
            try:
                proc = subprocess.run(
                    [str(python), "-c", REMEDY_PROBE],
                    cwd=workdir,
                    env=child_env(),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
            except subprocess.TimeoutExpired:
                return CheckResult(name, False, f"probe timed out after {self.timeout}s")
            except OSError as exc:  # pragma: no cover - unreadable interpreter
                return CheckResult(name, False, f"could not run {python}: {exc}")

        payload = last_json_object(proc.stdout)
        message = payload.get("remedy") if payload else None
        self.evidence["MISSING_CONFIG_REMEDY"] = one_line(message or MISSING_VALUE)

        if proc.returncode == PROBE_FOUND_CONFIG_EXIT:
            found = (payload or {}).get("found", "unknown path")
            return CheckResult(
                name,
                False,
                f"a chimera.yaml was found at {found} while walking up from the probe cwd, so the "
                "missing-config remedy could not be exercised — remove the stray config (the "
                "check must never run inside a tree that has one) and re-run",
            )
        if proc.returncode != 0:
            return CheckResult(
                name,
                False,
                f"probe exited {proc.returncode}: {one_line(proc.stderr) or '(no stderr)'}",
            )
        problem = remedy_problem(message)
        if problem is not None:
            return CheckResult(name, False, problem)
        return CheckResult(
            name,
            True,
            f"missing-config error names `chimera config init`: {one_line(str(message))}",
        )


# --------------------------------------------------------------------------- #
# Pure helpers (importable for offline coverage)
# --------------------------------------------------------------------------- #


def one_line(text: str, limit: int = 240) -> str:
    """Collapse output to a single bounded line for a check's verdict."""
    collapsed = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(collapsed) > limit:
        collapsed = collapsed[: limit - 3] + "..."
    return collapsed


def server_info_version(result: Mapping[str, Any] | None) -> str | None:
    """The ``serverInfo.version`` an initialize result reports, or ``None``.

    ``None`` covers both "no initialize response at all" and "the response
    carried no version" — a missing version must never be read as a match.
    """
    if not isinstance(result, Mapping):
        return None
    info = result.get("serverInfo")
    if not isinstance(info, Mapping):
        return None
    version = info.get("version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def handshake_version_problem(
    expected: str, actual: str | None, sdk_version: str | None
) -> str | None:
    """The actionable failure for a handshake that does not advertise *expected*.

    ``None`` means the handshake is correct. A handshake reporting the ``mcp``
    distribution's version is named as that specific defect (the pre-0.2.6
    shape) rather than as a generic mismatch, so the failure is greppable.
    """
    if actual == expected:
        return None
    if actual is None:
        return (
            "the initialize handshake carried no serverInfo.version at all, so a client cannot "
            f"tell which chimera build it reached (expected {expected}); {VERSION_FIX}"
        )
    if sdk_version and actual == sdk_version:
        return (
            f"the initialize handshake advertises the mcp SDK version {actual} instead of the "
            f"package version {expected}, so a client cannot tell which chimera build it reached; "
            f"{VERSION_FIX}"
        )
    return (
        f"the initialize handshake advertises {actual} instead of the package version {expected}; "
        f"{VERSION_FIX}"
    )


def remedy_problem(message: str | None) -> str | None:
    """The actionable failure for a missing-config remedy that is not runnable.

    ``None`` means the installed package's missing-config error names the
    remedy a bare pip install can actually run.
    """
    if message is None:
        return (
            "the installed missing-config probe produced no error message at all, so the remedy "
            f"cannot be judged; {REMEDY_FIX}"
        )
    if "chimera config init" in message:
        return None
    return (
        f"the installed missing-config error does not name `chimera config init`: {one_line(message)} "
        "— a copy-from-cwd remedy is impossible for a bare pip install (the wheel-shipped template "
        f"is not in the cwd); {REMEDY_FIX}"
    )


def normalize_dist(name: str) -> str:
    """PEP 503-normalize a distribution name for comparison."""
    return re.sub(r"[-_.]+", "-", name).lower()


def site_packages_dirs(venv: Path) -> list[Path]:
    """The venv's site-packages directories (POSIX and Windows layouts)."""
    dirs: list[Path] = []
    for pattern in ("lib/python*/site-packages", "Lib/site-packages"):
        dirs.extend(sorted(path for path in venv.glob(pattern) if path.is_dir()))
    return dirs


def installed_dist_version(venv: Path, dist: str) -> str | None:
    """The version *venv*'s installed metadata records for *dist*, or ``None``.

    Read straight off the ``*.dist-info`` directory the installer wrote, so the
    answer belongs to the venv under test and cannot be shadowed by an import
    from the source checkout.
    """
    wanted = normalize_dist(dist)
    for site in site_packages_dirs(venv):
        for info in sorted(site.glob("*.dist-info")):
            name, _, version = info.name[: -len(".dist-info")].rpartition("-")
            if name and normalize_dist(name) == wanted:
                return version or None
    return None


def last_json_object(output: str) -> dict[str, Any] | None:
    """The last line of *output* that parses as a JSON object, or ``None``."""
    for line in reversed(output.splitlines()):
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def venv_executable(venv: Path, name: str) -> Path:
    """Locate a console script or interpreter inside *venv*.

    The path is made ABSOLUTE (never resolved): every check runs in a temp cwd,
    so a relative ``--venv`` would otherwise be interpreted against that temp
    directory — while resolving would follow a venv's ``bin/python`` symlink to
    the base interpreter, whose prefix is no longer the venv.
    """
    candidates = [
        venv / "bin" / name,
        venv / "Scripts" / f"{name}.exe",
        venv / "Scripts" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return Path(os.path.abspath(candidate))
    return Path(os.path.abspath(candidates[0]))


def child_env() -> dict[str, str]:
    """The child environment: caller env minus the variables that mask the artifact."""
    env = dict(os.environ)
    for name in UNSET_ENV_VARS:
        env.pop(name, None)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def drive_initialize(
    cmd: Sequence[str], env: Mapping[str, str], cwd: str, timeout: int
) -> InitializeOutcome:
    """Send one ``initialize`` request to *cmd* over stdio and read the answer.

    Paced like a real MCP client: stdin stays open while the response is read,
    then closed so the server exits on EOF. Every process-level failure is
    returned as a named ``problem`` — never raised — so the caller always
    reports a verdict.
    """
    request = json.dumps(INITIALIZE_REQUEST) + "\n"
    try:
        proc = subprocess.Popen(
            list(cmd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(env),
            cwd=cwd,
        )
    except FileNotFoundError:
        return InitializeOutcome(None, False, f"{cmd[0]} does not exist", "")
    except OSError as exc:  # pragma: no cover - unspawnable binary
        return InitializeOutcome(None, False, f"could not run {cmd[0]}: {exc}", "")

    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    response: dict[str, Any] | None = None
    buf = b""
    deadline = time.monotonic() + timeout
    try:
        proc.stdin.write(request.encode())
        proc.stdin.flush()
        while response is None and time.monotonic() < deadline:
            ready, _, _ = select.select([proc.stdout], [], [], 0.5)
            if not ready:
                if proc.poll() is not None:
                    break
                continue
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf and response is None:
                line, buf = buf.split(b"\n", 1)
                parsed = last_json_object(line.decode(errors="replace")) if line.strip() else None
                if parsed is not None and parsed.get("id") == 1:
                    response = parsed
    finally:
        with contextlib.suppress(OSError, ValueError):
            proc.stdin.close()
        # Let the server finish on EOF, then reap it — a lingering child would
        # hold the temp cwd open.
        grace = time.monotonic() + DRAIN_GRACE_S
        while proc.poll() is None and time.monotonic() < grace:
            ready, _, _ = select.select([proc.stdout], [], [], 0.2)
            if ready and not os.read(proc.stdout.fileno(), 65536):
                break
        if proc.poll() is None:
            proc.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=DRAIN_GRACE_S)

    stderr_tail = one_line(proc.stderr.read().decode(errors="replace"))
    if response is None:
        detail = f"no JSON-RPC initialize response within {timeout}s"
        if stderr_tail:
            detail += f" (stderr: {stderr_tail})"
        elif proc.returncode not in (None, 0):
            detail += f" (child exited {proc.returncode})"
        return InitializeOutcome(None, False, detail, stderr_tail)
    version = server_info_version(response.get("result"))
    return InitializeOutcome(version, True, None, stderr_tail)


def parse_args(argv: list[str]) -> tuple[Path, str]:
    """Parse ``--venv`` / ``--expected-version``; raise UsageError on bad input."""
    venv: str | None = None
    expected_version: str | None = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--venv", "--expected-version") or arg.startswith(
            ("--venv=", "--expected-version=")
        ):
            if "=" in arg:
                option, value = arg.split("=", 1)
                i += 1
            else:
                option = arg
                if i + 1 >= len(argv):
                    raise UsageError(f"{option} requires a value")
                value = argv[i + 1]
                i += 2
            if not value.strip():
                raise UsageError(f"{option} requires a non-empty value")
            if option == "--venv":
                venv = value
            else:
                expected_version = value
            continue
        if arg.startswith("-"):
            raise UsageError(f"unknown option {arg!r}")
        raise UsageError(f"unexpected argument {arg!r}")
    if expected_version is None:
        raise UsageError(
            "--expected-version is required (the check must know the version the artifact "
            "claims, or it would only compare the artifact against itself)"
        )
    venv_path = Path(os.path.abspath(venv)) if venv else Path(os.path.abspath(REPO / ".venv"))
    if not venv_path.is_dir():
        raise UsageError(f"--venv {venv_path} is not a directory")
    return venv_path, expected_version


def main(argv: list[str] | None = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]
    if "-h" in raw or "--help" in raw:
        print(__doc__.strip())
        return 0
    try:
        venv, expected_version = parse_args(raw)
    except UsageError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        print(USAGE_LINE, file=sys.stderr)
        return 2

    probe = ReleaseContentProbe(venv=venv, expected_version=expected_version)
    print(f"VENV={venv}")
    print(f"EXPECTED_VERSION={expected_version}")
    results = probe.run()
    for key, value in probe.evidence.items():
        print(f"{key}={value}")
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.name}: {result.detail}")

    failed = [result for result in results if not result.ok]
    print(f"CHECKS_PASSED={len(results) - len(failed)} CHECKS_FAILED={len(failed)}")
    if failed:
        print("FAILED CHECKS:")
        for result in failed:
            print(f"  - {result.name}: {result.detail}")
        print(
            f"RELEASE CONTENT FAIL: {len(failed)}/{len(results)} release-content checks failed "
            f"against {venv} (expected version {expected_version})"
        )
        return 1
    print(
        f"RELEASE CONTENT OK: {len(results)}/{len(results)} release-content checks passed "
        f"against {venv} (version {expected_version})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
