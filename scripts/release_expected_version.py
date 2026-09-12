#!/usr/bin/env python3
"""Derive and validate the exact PyPI version a tag release must verify (DF-CHIMERA-0911-2).

The release-verify job must install ``chimera-deliberation[full]==<version>``
for the EXACT tag that triggered the workflow — never an unpinned ``latest``.
This script turns the triggering tag into that version and refuses anything
unsafe or inconsistent:

* the tag must be ``v<release>`` where ``<release>`` is a strict public
  PEP 440 version (release segment plus optional a/b/rc, .post, .dev) — no
  shell metacharacters, no whitespace, no arbitrary pip requirement strings;
* the derived version must EXACTLY equal the ``version`` declared in
  ``pyproject.toml`` at the tagged commit, so the gate can never verify a
  package other than the one this commit declares.

Prints the bare version (e.g. ``0.2.5``) on stdout. Exit 0 on success,
exit 2 on any validation failure (message on stderr).

Usage:
    python3 scripts/release_expected_version.py v0.2.5
    python3 scripts/release_expected_version.py --pyproject path/to/pyproject.toml v0.2.5
    GITHUB_REF_NAME=v0.2.5 python3 scripts/release_expected_version.py
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Strict public PEP 440 release: 1.2 / 1.2.3 / 1.2a1 / 1.2rc1 / 1.2.post1 / 1.2.dev1
#: (and combinations of the suffixes). No local segments (+local), no
#: wildcards, no whitespace — safe to embed in a pip requirement and a shell
#: double-quoted string.
PEP440_PUBLIC_RE = re.compile(
    r"^[0-9]+(\.[0-9]+)*"
    r"((a|b|rc)[0-9]+)?"
    r"(\.post[0-9]+)?"
    r"(\.dev[0-9]+)?$"
)


def is_safe_pep440(version: str) -> bool:
    """True iff ``version`` is a strict public PEP 440 release string."""
    return bool(PEP440_PUBLIC_RE.match(version))


def derive_version(tag: str) -> str:
    """Strip the leading ``v`` from a release tag and validate the result.

    Raises ValueError on a missing ``v`` prefix or an unsafe/non-PEP-440
    remainder.
    """
    tag = (tag or "").strip()
    if not tag.startswith("v"):
        raise ValueError(f"tag {tag!r} does not start with 'v' (expected v<version>)")
    version = tag[1:]
    if not version:
        raise ValueError(f"tag {tag!r} has an empty version")
    if not is_safe_pep440(version):
        raise ValueError(f"tag {tag!r} derives {version!r}, which is not a safe public PEP 440 version")
    return version


def pyproject_version(pyproject: Path) -> str:
    """The ``project.version`` declared in a pyproject.toml."""
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"{pyproject} does not declare a project.version string")
    return version


def expected_version(tag: str, pyproject: Path | None = None) -> str:
    """The exact version the release-verify job must install for ``tag``.

    Validates the tag shape AND that the tag matches the version declared at
    the tagged commit. Raises ValueError on any mismatch.
    """
    pyproject = pyproject or (REPO / "pyproject.toml")
    version = derive_version(tag)
    declared = pyproject_version(pyproject)
    if version != declared:
        raise ValueError(
            f"tag {tag!r} derives version {version!r} but {pyproject} declares {declared!r} — "
            "refusing to verify a package other than the tagged commit's declared version"
        )
    return version


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    pyproject = REPO / "pyproject.toml"
    positional: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--pyproject":
            if i + 1 >= len(args):
                print("usage error: --pyproject requires a path", file=sys.stderr)
                return 2
            pyproject = Path(args[i + 1])
            i += 2
            continue
        if arg.startswith("--pyproject="):
            pyproject = Path(arg.split("=", 1)[1])
            i += 1
            continue
        positional.append(arg)
        i += 1

    tag = positional[0] if positional else os.environ.get("GITHUB_REF_NAME", "")
    if not tag:
        print("usage error: pass the tag as an argument or set GITHUB_REF_NAME", file=sys.stderr)
        return 2

    try:
        version = expected_version(tag, pyproject)
    except (ValueError, OSError, tomllib.TOMLDecodeError) as exc:
        print(f"invalid release tag: {exc}", file=sys.stderr)
        return 2
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
