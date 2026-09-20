"""Shared private-host leak scanner (DF-CHIMERA-V2-24).

ONE pattern set, TWO consumers:

* the INT-CI-005 suite guard (``tests/test_no_private_host_leaks.py``), which
  scans every git-tracked file, and
* the pre-commit leak arm in ``.gitreins/pre-commit``, which scans every staged
  text file and blocks the commit — so a leak is caught BEFORE it reaches the
  public mirror, not on the next full-suite run.

Bane's ruling (2026-09-16): QA findings, board rows and infra diagnoses are
fine to publish — but bunker host addresses must not ride along. Referencing
hosts by name (``bunker-las-03``) carries the same diagnostic value with no
address disclosure.

The patterns are assembled from parts so this module — like the guard test
that begat it — never contains an address it forbids: the whole-tree suite
guard would flag a literal one.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

# Private ranges plus the CGNAT block Tailscale hands out for tailnet IPs.
# Assembled from parts so this file never contains an address it forbids.
_OCTET = r"\d{1,3}"
_PRIVATE_CIDRS = [
    r"10\." + r"\.".join([_OCTET] * 3),
    r"192\.168\." + r"\.".join([_OCTET] * 2),
    r"172\.(?:1[6-9]|2\d|3[01])\." + r"\.".join([_OCTET] * 2),
    r"100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\." + r"\.".join([_OCTET] * 2),
]

#: Compiled: private-range / CGNAT dotted-quad addresses.
PRIVATE_RE = re.compile(r"\b(?:" + "|".join(_PRIVATE_CIDRS) + r")\b")

#: Compiled: MagicDNS tailnet hostnames are private too.
TAILNET_DNS_RE = re.compile(r"\b[a-z0-9][a-z0-9-]*\.ts\.net\b", re.IGNORECASE)

# Loopback / unspecified / documentation ranges are legitimate in a repo.
ALLOWED_ADDRESSES = frozenset({"127.0.0.1", "0.0.0.0", "255.255.255.255", "1.2.3.4"})


def _is_cidr_suffix(line: str, match: re.Match[str]) -> bool:
    """CIDR notation documents a range, not a host: a trailing ``/`` is prose."""
    return line[match.end() : match.end() + 1] == "/"


def iter_line_hits(text: str) -> Iterator[tuple[int, str]]:
    """Yield ``(lineno, matched)`` for every forbidden host in ``text``.

    Applies the same exclusions as the suite guard: allowlisted addresses are
    skipped, and a match directly followed by ``/`` is CIDR notation —
    describing the policy must not itself trip the policy.
    """
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in PRIVATE_RE.finditer(line):
            if match.group(0) in ALLOWED_ADDRESSES or _is_cidr_suffix(line, match):
                continue
            yield lineno, match.group(0)
        for match in TAILNET_DNS_RE.finditer(line):
            yield lineno, match.group(0)


def find_private_hosts(text: str) -> list[str]:
    """The forbidden host values in ``text``: private/CGNAT addresses AND
    tailnet hostnames, in line order, duplicates preserved."""
    return [value for _, value in iter_line_hits(text)]


def scan_file(path: Path) -> list[tuple[int, str]]:
    """Scan one file; binary/unreadable files yield no hits (never raises).

    A non-UTF-8 file is "binary-looking" and is not published as text by this
    repo, so it is skipped rather than a hard error — the same semantics the
    suite guard applies to unreadable tracked files.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    return list(iter_line_hits(text))


def main(argv: list[str] | None = None) -> int:
    """CLI for the pre-commit arm: ``python tests/private_host_scan.py --scan FILE``.

    Prints ``<path>:<lineno>: <matched>`` per hit and exits 1 when any hit was
    found, 0 on a clean (or unreadable/binary) file, 2 on a usage error.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Find private/tailnet host addresses in a file.")
    parser.add_argument("--scan", required=True, metavar="FILE", help="the file to scan")
    args = parser.parse_args(argv)

    hits = scan_file(Path(args.scan))
    for lineno, matched in hits:
        print(f"{args.scan}:{lineno}: {matched}")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
