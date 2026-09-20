"""Guard: no private / tailnet host addresses in tracked content (INT-CI-005).

Bane's ruling (2026-09-16): QA findings, board rows and infra diagnoses are fine
to publish on the public mirror — but bunker host IPs must not ride along. This
test enforces that: every git-tracked text file is scanned for private-range and
Tailscale/CGNAT addresses, and the suite fails if any appear.

Rationale: the mirror is public, and board/QA rows are written by automated
lanes that quote raw stderr (``dial tcp <ip>:10001: i/o timeout``). Referencing
hosts by name (``bunker-las-03``) carries the same diagnostic value with no
address disclosure, so the fix is always "use the name".

The pattern set lives in :mod:`tests.private_host_scan` and is shared with the
pre-commit leak arm (DF-CHIMERA-V2-24), so the commit gate flags a leak with
the SAME patterns this suite guard uses — before it can be committed, not on
the next full-suite run.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.private_host_scan import scan_file

REPO_ROOT = Path(__file__).resolve().parents[1]

# This file necessarily describes the policy it forbids.
_SELF = Path(__file__).name


def _tracked_files() -> list[Path]:
    """All git-tracked files, or [] when git is unavailable (never a hard fail)."""
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [REPO_ROOT / line for line in out.stdout.splitlines() if line]


def _findings() -> list[str]:
    findings: list[str] = []
    for path in _tracked_files():
        if path.name == _SELF or not path.is_file():
            continue
        rel = path.relative_to(REPO_ROOT)
        for lineno, matched in scan_file(path):
            findings.append(f"{rel}:{lineno}: forbidden host {matched!r}")
    return findings


def test_no_private_host_addresses_in_tracked_content() -> None:
    """Tracked content must reference hosts by name, never by private address."""
    findings = _findings()
    assert not findings, (
        "Private/tailnet addresses found in tracked content (public mirror). "
        "Replace them with the host name (e.g. 'bunker-las-03'):\n  " + "\n  ".join(findings)
    )
