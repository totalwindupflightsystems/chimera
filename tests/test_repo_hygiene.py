"""CLN-1: repository-root hygiene — no scratch files, no leaking local artifacts.

The repo root accumulated two classes of junk that nothing guarded:

1. Four tracked 33-byte foreman scratch files at the root (``_foreman_`` prefix,
   ``.py`` suffix — the ``check_duckbrain``, ``check_scheduler``, ``set_cooldown``
   and ``verify_cooldown`` suffixes — committed 2026-07-26, mode 600, body
   ``#!/usr/bin/env python3`` + ``# Cleaned``). They were foreman/fleet run
   leftovers, not project code: no test, script, workflow or doc imported or
   mentioned them, yet they were tracked in the public mirror
   (github.com/totalwindupflightsystems/chimera).
2. Ignore gaps around derived local state: the GitReins guard logs
   (``.gitreins/logs/``, one file per guard run), the SQLite sidecars
   (``dagger.db-wal`` / ``dagger.db-shm``) and two hilo graph caches
   (``.vfs/graph/.parse_cache.json``, ``.vfs/graph/.last_reconcile``) were not
   ignored — which is why ``git status -s`` showed ``?? .gitreins/logs/``,
   ``?? .vfs/graph/``, ``?? dagger.db-wal`` and ``?? dagger.db-shm`` after every
   guard run. One accidental ``git add -A`` would have committed 20 guard logs,
   a write-ahead log and a parse cache into a public repo.

Both are invariants of the repository *state*, so they are asserted offline
against git itself rather than against running code: stdlib + the ``git`` binary
only — no network, no imports of ``chimera`` — so the contract still holds in a
bare checkout (or a wheel-consumer environment) where the app dependencies are
absent. Paths resolve from this file's location, never the process cwd.

On the pre-fix tree these tests FAIL: ``git ls-files`` lists the four
``_foreman_*.py`` scratch files, and ``git check-ignore -q`` exits 1 for every
artifact path below.

The removed filenames are written pattern-first (``_foreman_`` + verb suffix)
on purpose: CLN-1's acceptance criterion is that ``git grep`` at HEAD for the
removed paths is empty and nothing under ``tests/``, ``docs/``, ``scripts/`` or
``.github/`` references them. Keep it that way — match the pattern, not the
literal names.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Root-level foreman/fleet scratch naming pattern (deleted by CLN-1).
SCRATCH_PREFIX = "_foreman_"
SCRATCH_SUFFIX = ".py"

#: Derived local artifacts that must never be committable. Each entry was proven
#: unignored at CLN-1 open time; every one of them is rebuildable local state.
IGNORED_ARTIFACTS = (
    ".gitreins/logs/guard.log",
    "dagger.db-wal",
    "dagger.db-shm",
    ".vfs/graph/.parse_cache.json",
    ".vfs/graph/.last_reconcile",
)

#: A root file that must stay tracked, so the scratch check cannot pass vacuously
#: on an empty index (an exported tarball with no git metadata would otherwise
#: look "clean").
ANCHOR_TRACKED_FILE = "pyproject.toml"

#: ``git ls-files`` on this repo is a sub-second command.
GIT_TIMEOUT_S = 30


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    """Run git in the repo root; a non-zero exit is data, not an exception."""
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_S,
        check=False,
    )


def _require_git_checkout() -> None:
    """Skip cleanly (never fail) where git or a git checkout is unavailable."""
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    if _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("not a git checkout — the hygiene guard does not apply")


def _tracked_root_entries() -> list[str]:
    """Tracked INDEX entries that live directly at the repository root."""
    tracked = _git("ls-files")
    assert tracked.returncode == 0, tracked.stderr
    return sorted(name for name in tracked.stdout.splitlines() if name and "/" not in name)


def test_root_scratch_check_has_a_real_index() -> None:
    """Premise guard: the index is readable and non-empty.

    Without this, a git invocation that silently returned nothing (or a stripped
    checkout) would make the scratch check below pass while proving nothing.
    """
    _require_git_checkout()
    entries = _tracked_root_entries()
    assert entries, "no tracked root entries — the index read is not trustworthy"
    assert ANCHOR_TRACKED_FILE in entries, (
        f"{ANCHOR_TRACKED_FILE} is missing from the tracked root entries "
        f"(read {len(entries)}): this test is running against the wrong tree"
    )


def test_no_tracked_foreman_scratch_files_at_root() -> None:
    """No ``_foreman_*.py`` scratch file may be tracked at the repo root.

    Checked against the INDEX, not ``HEAD``: the CLN-1 removal commit is the very
    commit this guard runs inside (the pre-commit hook executes the suite), so a
    HEAD-strict assertion would block the fix it protects. Once committed, index
    and HEAD agree and a re-added scratch file is caught immediately.
    """
    _require_git_checkout()
    offenders = [
        name
        for name in _tracked_root_entries()
        if name.startswith(SCRATCH_PREFIX) and name.endswith(SCRATCH_SUFFIX)
    ]
    assert not offenders, (
        f"foreman/fleet scratch files are tracked at the repo root: {offenders} — "
        f"they are foreman run leftovers, not project code (removed by CLN-1); "
        f"delete them and keep run scratch outside the repo"
    )


@pytest.mark.parametrize("artifact", IGNORED_ARTIFACTS)
def test_local_artifact_is_gitignored(artifact: str) -> None:
    """Every derived local artifact is ignored, so it can never be committed."""
    _require_git_checkout()
    result = _git("check-ignore", "--quiet", artifact)
    assert result.returncode == 0, (
        f"{artifact} is not gitignored (git check-ignore -q exited "
        f"{result.returncode}) — an accidental `git add -A` would commit local "
        f"state; verbose match: "
        f"{_git('check-ignore', '-v', artifact).stdout.strip() or 'no rule matched'}"
    )
