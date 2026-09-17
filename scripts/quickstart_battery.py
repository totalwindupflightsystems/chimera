#!/usr/bin/env python3
"""README quickstart CLI-surface battery (DF-CHIMERA-0916B-3).

The release-verify job installs the EXACT published wheel and then runs a
fresh-user journey — but it never asserted the CLI *surface* the README
quickstart documents. 0.2.5 shipped with ``chimera --version`` exiting 2
(``Error: No such option '--version'.``) because the tag was cut from a commit
two days older than the ``--version`` commit (d6f144c): the published wheel
genuinely rejects a flag the repo's own README tells users to run. That is
recurrence #4 of the repo-HEAD-vs-published-artifact class (DF-CHIMERA-0911-2,
CH-GAP-040), so the surface itself is asserted against the published artifact.

The battery points at an installed venv and runs the commands from README's
"Quickstart" block, each as its own named check:

* ``cli-version`` — ``chimera --version`` exits 0 and prints the expected
  version (README: "chimera --version  # print the package version");
* ``module-version`` — ``python -m chimera --version`` (the README's documented
  fallback for a fresh clone / non-activated venv / bare wheel) prints the same
  version;
* ``cli-help`` — ``chimera --help`` exits 0 (the console script is installed
  and click can parse its own argv);
* ``config-init`` — ``chimera config init`` creates ``chimera.yaml`` in an
  EMPTY temp cwd, the first-run remedy the README and every missing-config
  error message point at.

Invariants:

* Every check runs in its own fresh empty temp directory, so the battery can
  never read, create, or clobber the caller's ``chimera.yaml`` — in particular
  it never runs a quickstart command in the repo root.
* The child env has ``CHIMERA_CONFIG`` removed: the battery asserts
  out-of-the-box first-run behaviour, and a pre-set config path would mask the
  very fresh-user journey it guards.
* ``--expected-version`` is REQUIRED — comparing the artifact against itself
  would defeat the gate, so a missing/blank value is a usage error (exit 2),
  never a silently derived default.
* No network, no provider keys: every check is local.

Usage:
    python3 scripts/quickstart_battery.py --venv /tmp/release-venv --expected-version 0.2.5
    python3 scripts/quickstart_battery.py --expected-version 0.2.5   # defaults to ./.venv

Exit codes: 0 = every check passed; 1 = at least one check failed; 2 = usage
error (unknown option, missing value, missing --expected-version, or a --venv
that is not a directory).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Per-check wall-clock budget. Every quickstart command is local (click argv
#: parsing plus a file copy), so minutes here would only hide a hang.
CHECK_TIMEOUT_S = 120

#: Dropped from every child env — see the module docstring's invariants.
UNSET_ENV_VARS = ("CHIMERA_CONFIG",)

USAGE_LINE = "usage: quickstart_battery.py --expected-version VERSION [--venv PATH]"


class UsageError(Exception):
    """Bad battery input (exit 2) — not a failed quickstart check."""


@dataclass(frozen=True)
class Check:
    """One README quickstart assertion.

    ``version_expected`` requires the command's combined output to carry the
    expected version as a whole token; ``expect_file`` requires that path
    (relative to the check's temp cwd) to exist after a zero-exit run.
    """

    name: str
    command: list[str]
    description: str
    version_expected: bool = False
    expect_file: str | None = None


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one check, with a human-readable reason either way."""

    name: str
    command: list[str]
    ok: bool
    detail: str


def version_token_present(output: str, expected_version: str) -> bool:
    """True iff ``output`` carries ``expected_version`` as a whole token.

    Boundary-anchored so ``0.2.5`` can never be satisfied by ``0.2.50``,
    ``0.2.5rc1`` or a filename that merely embeds the digits.
    """
    pattern = rf"(?<![\w.]){re.escape(expected_version)}(?![\w.])"
    return re.search(pattern, output) is not None


def venv_executable(venv: Path, name: str) -> Path:
    """Locate a console script or interpreter inside ``venv`` (POSIX/Windows).

    The path is made ABSOLUTE (never resolved): every check runs in a temp cwd,
    so a relative ``--venv`` would otherwise be interpreted against that temp
    directory — while resolving would follow a venv's ``bin/python`` symlink to
    the base interpreter, whose prefix is no longer the venv (``python -m
    chimera`` then dies with "No module named chimera").
    """
    candidates = [venv / "bin" / name, venv / "Scripts" / f"{name}.exe", venv / "Scripts" / name]
    for candidate in candidates:
        if candidate.exists():
            return Path(os.path.abspath(candidate))
    return Path(os.path.abspath(candidates[0]))


def build_checks(venv: Path) -> list[Check]:
    """The README quickstart CLI surface, in documented order."""
    cli = str(venv_executable(venv, "chimera"))
    python = str(venv_executable(venv, "python"))
    return [
        Check(
            "cli-version",
            [cli, "--version"],
            "README: chimera --version prints the package version",
            version_expected=True,
        ),
        Check(
            "module-version",
            [python, "-m", "chimera", "--version"],
            "README fallback: python -m chimera --version prints the same version",
            version_expected=True,
        ),
        Check(
            "cli-help",
            [cli, "--help"],
            "README: the chimera console script runs (click parses its own argv)",
        ),
        Check(
            "config-init",
            [cli, "config", "init"],
            "README first run: chimera config init creates chimera.yaml in an empty dir",
            expect_file="chimera.yaml",
        ),
    ]


def child_env() -> dict[str, str]:
    """The child environment: caller env minus the variables that mask first run."""
    env = dict(os.environ)
    for name in UNSET_ENV_VARS:
        env.pop(name, None)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _one_line(text: str, limit: int = 240) -> str:
    """Collapse output to a single bounded line for the check's verdict."""
    collapsed = " | ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(collapsed) > limit:
        collapsed = collapsed[: limit - 3] + "..."
    return collapsed


def run_check(check: Check, expected_version: str, timeout: int = CHECK_TIMEOUT_S) -> CheckResult:
    """Run one check in a fresh empty temp cwd and classify the outcome.

    A non-zero exit, a missing version token, a missing expected file, a
    missing/non-executable binary and a timeout are ALL failures (never
    exceptions escaping to the caller), so the battery always reports every
    check it was asked to run.
    """

    def failed(detail: str) -> CheckResult:
        return CheckResult(check.name, check.command, False, detail)

    with tempfile.TemporaryDirectory(prefix="chimera-quickstart-") as workdir:
        try:
            proc = subprocess.run(
                check.command,
                cwd=workdir,
                env=child_env(),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            return failed(f"not found: {check.command[0]}")
        except PermissionError:
            return failed(f"not executable: {check.command[0]}")
        except subprocess.TimeoutExpired:
            return failed(f"timed out after {timeout}s")

        output = f"{proc.stdout}\n{proc.stderr}"
        if proc.returncode != 0:
            return failed(f"exited {proc.returncode} (expected 0): {_one_line(output)}")
        if check.version_expected and not version_token_present(output, expected_version):
            return failed(
                f"exit 0 but output lacks version {expected_version!r}: {_one_line(output)}"
            )
        if check.expect_file is not None and not (Path(workdir) / check.expect_file).is_file():
            return failed(f"exit 0 but {check.expect_file} was not created in the cwd")

    detail = "exit 0"
    if check.version_expected:
        detail += f", output contains {expected_version}"
    if check.expect_file is not None:
        detail += f", created {check.expect_file}"
    return CheckResult(check.name, check.command, True, detail)


def run_battery(
    checks: list[Check],
    expected_version: str,
    on_result: Callable[[CheckResult], None] | None = None,
    timeout: int = CHECK_TIMEOUT_S,
) -> tuple[list[CheckResult], int]:
    """Run every check; return ``(results, 0|1)`` — 1 iff any check failed."""
    results: list[CheckResult] = []
    for check in checks:
        result = run_check(check, expected_version, timeout)
        results.append(result)
        if on_result is not None:
            on_result(result)
    return results, (0 if all(r.ok for r in results) else 1)


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
            "--expected-version is required (the battery must know the version the "
            "artifact claims, or it would only compare the artifact against itself)"
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

    checks = build_checks(venv)
    print(f"VENV={venv}")
    print(f"EXPECTED_VERSION={expected_version}")

    def report(result: CheckResult) -> None:
        status = "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.name}: {' '.join(result.command)} -> {result.detail}")

    results, code = run_battery(checks, expected_version, on_result=report)
    failed = [r for r in results if not r.ok]
    print(f"CHECKS_PASSED={len(results) - len(failed)} CHECKS_FAILED={len(failed)}")
    if failed:
        print("FAILED CHECKS:")
        for result in failed:
            print(f"  - {result.name}: {result.detail}")
        print(
            f"QUICKSTART BATTERY FAIL: {len(failed)}/{len(results)} README quickstart "
            f"checks failed against {venv} (expected version {expected_version})"
        )
    else:
        print(
            f"QUICKSTART BATTERY OK: {len(results)}/{len(results)} README quickstart "
            f"checks passed against {venv} (version {expected_version})"
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
