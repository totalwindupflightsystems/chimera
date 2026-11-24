#!/usr/bin/env python3
"""Refuse to certify a release tag whose acceptance evidence graded a different tree.

RELEASE-FINDING-2026-11-21-006: v0.3.0's artifact-acceptance evidence
(``​.coding-hermes/evidence/RELEASE-PARITY-2026-11-16/artifact-acceptance-0.3.0.md``)
graded the artifact at worktree HEAD ``f7cf034`` while the pushed ``v0.3.0`` tag
peeled to ``57e298c`` — 72 commits later, 11 of them touching product source. The
acceptance record certified a tree no user receives.

This check re-derives BOTH sides from the checkout and exits 0 only when the graded
SHA is the EXACT commit the tag certifies:

* The graded SHA is extracted from the evidence file, in priority order:
  1. a machine-checkable ``graded-sha: <sha>`` line (the recommended form for new
     evidence files);
  2. the ``HEAD <sha>`` form (``at HEAD `<sha>`​``, ``worktree HEAD <sha>``) that the
     0.3.0 file uses;
  3. any backtick-quoted git-SHA-shaped token (7-40 hex chars).

  64-hex ``sha256`` artifact digests are NOT git SHAs and can never be mistaken for
  one (the pattern is bounded at 40 hex, so a digest inside backticks cannot close
  the quote within the bound). More than one DISTINCT candidate from a tier is
  ambiguous and refused loudly, listing the candidates.

* The tag target is ``git rev-parse <tag>{}`` — annotated tags peel to the commit.

* EQUALITY is the bar. An ancestor relationship is NOT accepted: a graded tree with
  commits between it and the tag is exactly the 0.3.0 incident shape. The only
  escape is an explicit, machine-checkable waiver line in the evidence file::

      SCOPE-WAIVER: <graded-sha> -> <tag> <justification (>= 20 chars, same line)>

  AND a VERIFIED empty packaged-path delta: ``git diff --name-only`` between the
  graded commit and the tag target must touch none of the packaged globs
  (``--packaged-glob``, repeatable; defaults cover this repo's wheel inputs:
  ``src/**``, ``pyproject.toml``, ``uv.lock``, ``README.md``, and the two
  force-included ``chimera.yaml.*`` templates). A honored waiver is printed loudly:
  the waiver line verbatim, the justification, and every changed path.

* Every refusal exits 2 printing BOTH SHAs on one loud line::

      graded=<sha> tag=<sha> REFUSING to certify <tag>: <reason>

Usage:
    python3 scripts/release_acceptance_check.py v0.3.0
    python3 scripts/release_acceptance_check.py v0.3.0 --evidence path/to/evidence.md
    python3 scripts/release_acceptance_check.py --repo /path/to/repo v0.3.0
    GITHUB_REF_NAME=v0.3.0 python3 scripts/release_acceptance_check.py

The evidence path defaults to the tracked convention
``.coding-hermes/evidence/**/artifact-acceptance-<version>.md`` (version derived
from the tag); 0 or >1 matches refuse unless ``--evidence`` names the file. Relative
``--evidence`` paths resolve against the process cwd.
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Where evidence files live by convention (version interpolated into the name).
EVIDENCE_DIR = ".coding-hermes/evidence"

#: Strict public PEP 440 release shape — the same one release_expected_version.py
#: validates tags against. Reused here so the version interpolated into the
#: evidence-file name can contain no glob metacharacters and no path separators.
PEP440_PUBLIC_RE = re.compile(r"^[0-9]+(\.[0-9]+)*((a|b|rc)[0-9]+)?(\.post[0-9]+)?(\.dev[0-9]+)?$")

SHA = r"[0-9a-fA-F]{7,40}"

#: Tier 1 — the explicit machine-checkable line (recommended for new evidence).
GRADED_SHA_LINE_RE = re.compile(rf"^\s*graded-sha:\s*`?\s*({SHA})\s*`?\s*$", re.IGNORECASE)

#: Tier 2 — "at HEAD `f7cf034`" / "worktree HEAD `f7cf034`" / "HEAD f7cf034".
HEAD_SHA_RE = re.compile(rf"\bHEAD\s*`?\s*({SHA})")

#: Tier 3 — any backtick-quoted git-SHA-shaped token. Bounded at 40 hex so a 64-hex
#: sha256 artifact digest can never match (no closing backtick within the bound).
BACKTICK_SHA_RE = re.compile(rf"`({SHA})`")

#: The waiver escape hatch. Default is refuse; a waiver is honored only when the
#: line names THIS evidence's graded SHA and THIS tag, carries an inline
#: justification of at least 20 characters, and the packaged-path delta verifies empty.
SCOPE_WAIVER_RE = re.compile(rf"^\s*SCOPE-WAIVER:\s*({SHA})\s*->\s*(\S+)\s+(.{{20,}})$")

#: Paths that end up in the published wheel (hatch build inputs), matched with
#: fnmatch — ``*`` is not path-aware, so ``src/**`` covers src/ recursively.
DEFAULT_PACKAGED_GLOBS = (
    "src/**",
    "pyproject.toml",
    "uv.lock",
    "README.md",
    "chimera.yaml.example",
    "chimera.yaml.docker",
)


class RefusalError(Exception):
    """A loud refusal; main() prints it with the graded/tag context and exits 2."""


class GitError(Exception):
    """A git command failed."""


@dataclass(frozen=True)
class ScopeWaiver:
    """A parsed SCOPE-WAIVER line."""

    sha: str
    tag: str
    justification: str
    line: str


def derive_version(tag: str) -> str:
    """Strip the leading ``v`` and validate the version is safe for the evidence glob."""
    tag = (tag or "").strip()
    if not tag.startswith("v"):
        raise ValueError(f"tag {tag!r} does not start with 'v' (expected v<version>)")
    version = tag[1:]
    if not version or not PEP440_PUBLIC_RE.match(version):
        raise ValueError(f"tag {tag!r} derives {version!r}, which is not a safe public version")
    return version


def find_evidence(repo: Path, version: str, explicit: str | None) -> Path:
    """The acceptance-evidence markdown for ``version`` — explicit path, or the glob."""
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise RefusalError(f"--evidence path not found: {path}")
        return path
    pattern = f"artifact-acceptance-{version}.md"
    base = repo / EVIDENCE_DIR
    matches = sorted(base.rglob(pattern)) if base.is_dir() else []
    convention = f"{EVIDENCE_DIR}/**/{pattern}"
    if not matches:
        raise RefusalError(
            f"no acceptance-evidence file matches the convention {convention} under {repo} — "
            "an artifact-acceptance record is required for every cut"
        )
    if len(matches) > 1:
        listing = "\n  ".join(str(m) for m in matches)
        raise RefusalError(
            f"{len(matches)} evidence files match the convention {convention} — pass "
            f"--evidence explicitly:\n  {listing}"
        )
    return matches[0]


def extract_graded_sha(text: str) -> str:
    """The graded HEAD SHA from the evidence text; ambiguous input refuses loudly."""
    for tier_name, regex in (
        ("graded-sha:", GRADED_SHA_LINE_RE),
        ("HEAD form", HEAD_SHA_RE),
        ("backtick-quoted", BACKTICK_SHA_RE),
    ):
        candidates = sorted({m.group(1).lower() for m in regex.finditer(text)})
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise RefusalError(
                f"ambiguous graded SHA ({tier_name} names several commits: "
                f"{', '.join(candidates)}) — state it once as `graded-sha: <sha>`"
            )
    raise RefusalError(
        "no graded HEAD SHA found in the evidence — state it as `graded-sha: <sha>` "
        "(or the `at HEAD `<sha>`` form)"
    )


def find_scope_waiver(text: str) -> ScopeWaiver | None:
    """The first parseable SCOPE-WAIVER line, or None."""
    for line in text.splitlines():
        match = SCOPE_WAIVER_RE.match(line)
        if match:
            return ScopeWaiver(
                sha=match.group(1).lower(),
                tag=match.group(2),
                justification=match.group(3).strip(),
                line=line.strip(),
            )
    return None


def git(repo: Path, *args: str) -> str:
    """Run one git command in ``repo``; non-zero exit raises GitError."""
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise GitError(
            (proc.stderr.strip() or proc.stdout.strip()) or f"git {args[0]} exited {proc.returncode}"
        )
    return proc.stdout.strip()


def resolve_commit(repo: Path, rev: str, peel: bool) -> str:
    """Fully resolve a rev to a commit SHA (peeling annotated tags when asked)."""
    spec = f"{rev}^{{}}" if peel else f"{rev}^{{commit}}"
    try:
        return git(repo, "rev-parse", "--verify", spec)
    except GitError as exc:
        raise GitError(f"{rev} does not resolve to a commit ({exc})") from exc


def is_ancestor(repo: Path, older: str, newer: str) -> bool:
    """``git merge-base --is-ancestor`` as a boolean (rc 1 = no, rc >1 = error)."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", older, newer],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    raise GitError(proc.stderr.strip() or "merge-base failed")


def _refuse(tag: str, graded_display: str, tag_display: str, reason: str) -> int:
    print(f"graded={graded_display} tag={tag_display} REFUSING to certify {tag}: {reason}")
    return 2


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    repo = REPO
    evidence_opt: str | None = None
    packaged = list(DEFAULT_PACKAGED_GLOBS)
    positional: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        flag: str | None = None
        value: str | None = None
        if arg in ("--repo", "--evidence", "--packaged-glob"):
            if i + 1 >= len(args):
                print(f"usage error: {arg} requires a value", file=sys.stderr)
                return 2
            flag = arg
            value = args[i + 1]
            i += 2
        elif arg.startswith(("--repo=", "--evidence=", "--packaged-glob=")):
            flag, value = arg.split("=", 1)
            i += 1
        else:
            positional.append(arg)
            i += 1
            continue
        if flag == "--repo":
            repo = Path(value)
        elif flag == "--evidence":
            evidence_opt = value
        else:
            packaged.append(value)
    tag = positional[0] if positional else os.environ.get("GITHUB_REF_NAME", "")
    if not tag:
        print("usage error: pass the tag as an argument or set GITHUB_REF_NAME", file=sys.stderr)
        return 2

    try:
        version = derive_version(tag)
    except ValueError as exc:
        return _refuse(tag, "(none)", tag, f"invalid release tag: {exc}")

    try:
        evidence = find_evidence(repo, version, evidence_opt)
    except RefusalError as exc:
        return _refuse(tag, "(unreadable)", tag, str(exc))

    try:
        tag_target = resolve_commit(repo, tag, peel=True)
    except GitError as exc:
        return _refuse(tag, "?", f"{tag} (unresolvable: {exc})", "cannot resolve the tag target")

    try:
        text = evidence.read_text(encoding="utf-8")
    except OSError as exc:
        return _refuse(tag, "(unreadable)", tag_target, f"cannot read {evidence}: {exc}")

    try:
        graded = extract_graded_sha(text)
    except RefusalError as exc:
        return _refuse(tag, "(none found)", tag_target, str(exc))

    # Equality is the bar; a short graded SHA that is the tag target's prefix IS the
    # same commit, so prefix equality counts (and works on shallow checkouts where
    # the graded commit object itself is not fetched).
    if graded == tag_target.lower() or tag_target.lower().startswith(graded):
        print(
            f"graded={tag_target} tag={tag_target} OK: the acceptance evidence grades the "
            f"exact commit {tag} certifies ({evidence})"
        )
        return 0

    graded_full: str | None = None
    graded_unresolvable: str | None = None
    try:
        graded_full = resolve_commit(repo, graded, peel=False)
    except GitError as exc:
        graded_unresolvable = str(exc)

    # The ONLY escape from exact equality: an explicit waiver line plus a VERIFIED
    # empty packaged-path delta. Anything short of that refuses below.
    waiver = find_scope_waiver(text)
    if waiver is not None and waiver.sha == graded and waiver.tag == tag and graded_full is not None:
        changed = git(repo, "diff", "--name-only", graded_full, tag_target).splitlines()
        offending = [p for p in changed if any(fnmatch.fnmatch(p, glob) for glob in packaged)]
        if offending:
            print(
                f"graded={graded} tag={tag_target} REFUSING to certify {tag}: the SCOPE-WAIVER "
                f"claims non-packaged-only drift, but packaged paths changed: {', '.join(offending)}"
            )
            return 2
        print(f"SCOPE-WAIVER honored ({evidence}):")
        print(f"  waiver line: {waiver.line}")
        print(f"  justification: {waiver.justification}")
        print(f"  packaged globs checked: {', '.join(packaged)}")
        print(f"  changed paths ({len(changed)}), none packaged:")
        for path in changed:
            print(f"    {path}")
        print(
            f"graded={graded_full} tag={tag_target} OK (waived): the tag drifts from the graded "
            "tree ONLY in non-packaged paths"
        )
        return 0

    if graded_full is None:
        return _refuse(
            tag,
            graded,
            tag_target,
            f"the acceptance evidence grades a different tree, and the graded commit is not "
            f"resolvable in this checkout to verify anything further ({graded_unresolvable})",
        )

    reason = "the acceptance evidence grades a different tree"
    if is_ancestor(repo, graded_full, tag_target):
        between = git(repo, "rev-list", "--count", f"{graded_full}..{tag_target}")
        reason = (
            f"the acceptance evidence grades a different tree (ancestor-only: {between} commits "
            "landed after the grading run — ancestry is not certification)"
        )
    if waiver is not None:
        reason += (
            f" (the evidence's SCOPE-WAIVER line names {waiver.sha} -> {waiver.tag}, "
            "not this graded SHA/tag pair, so it cannot apply)"
        )
    return _refuse(tag, graded_full, tag_target, reason)


if __name__ == "__main__":
    sys.exit(main())
