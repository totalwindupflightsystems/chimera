"""Guard: no private / tailnet host addresses in tracked content (INT-CI-005).

Bane's ruling (2026-09-16): QA findings, board rows and infra diagnoses are fine
to publish on the public mirror — but bunker host IPs must not ride along. This
test enforces that: every git-tracked text file is scanned for private-range and
Tailscale/CGNAT addresses, and the suite fails if any appear.

Rationale: the mirror is public, and board/QA rows are written by automated
lanes that quote raw stderr (``dial tcp <ip>:10001: i/o timeout``). Referencing
hosts by name (``bunker-las-03``) carries the same diagnostic value with no
address disclosure, so the fix is always "use the name".
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Private ranges plus the CGNAT block Tailscale hands out for tailnet IPs.
# Assembled from parts so this file never contains an address it forbids.
_OCTET = r"\d{1,3}"
_PRIVATE_CIDRS = [
    r"10\." + r"\.".join([_OCTET] * 3),
    r"192\.168\." + r"\.".join([_OCTET] * 2),
    r"172\.(?:1[6-9]|2\d|3[01])\." + r"\.".join([_OCTET] * 2),
    r"100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\." + r"\.".join([_OCTET] * 2),
]
_PRIVATE_RE = re.compile(r"\b(?:" + "|".join(_PRIVATE_CIDRS) + r")\b")

# MagicDNS tailnet hostnames are private too.
_TAILNET_DNS_RE = re.compile(r"\b[a-z0-9][a-z0-9-]*\.ts\.net\b", re.IGNORECASE)

# Loopback / unspecified / documentation ranges are legitimate in a repo.
_ALLOWED = {"127.0.0.1", "0.0.0.0", "255.255.255.255", "1.2.3.4"}

# This file necessarily describes the patterns it forbids.
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
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable — not published as text
        rel = path.relative_to(REPO_ROOT)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in _PRIVATE_RE.finditer(line):
                if match.group(0) in _ALLOWED:
                    continue
                findings.append(f"{rel}:{lineno}: private address {match.group(0)!r}")
            for match in _TAILNET_DNS_RE.finditer(line):
                findings.append(f"{rel}:{lineno}: tailnet hostname {match.group(0)!r}")
    return findings


def test_no_private_host_addresses_in_tracked_content() -> None:
    """Tracked content must reference hosts by name, never by private address."""
    findings = _findings()
    assert not findings, (
        "Private/tailnet addresses found in tracked content (public mirror). "
        "Replace them with the host name (e.g. 'bunker-las-03'):\n  "
        + "\n  ".join(findings)
    )
