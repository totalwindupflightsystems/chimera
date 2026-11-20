#!/usr/bin/env bash
# Docs-index gate — INT-CI-014-R2.
#
# A dated dogfood run log that lands without an index line leaves main RED on
# every Python version: tests/test_docs_index.py derives its parameter list from
# `git ls-files docs/`, so a tracked file that neither README.md nor
# docs/README.md names fails the suite on the NEXT push (fifth recurrence of this
# class: CI-FIX-001, DOC-2, INT-CI-014, INT-CI-014-R2).
#
# This gate is the same-commit rule that failure was missing: the run log and the
# index line that names it must be in the SAME commit, checked against the INDEX
# AS IT WOULD BE COMMITTED (`git show :docs/README.md`, not the working tree), so
# a staged-but-unstaged-index mismatch cannot slip through.
#
# Scope: newly ADDED `docs/dogfood/*.md` files. `diagnostics.md` is the undated
# catch-all, not a run log, so it is exempt. Every other dated run log must be
# named by full path or basename in the committed index.
#
# Exit codes: 0 = every added log is indexed (or nothing was added);
#             1 = at least one added log is referenced nowhere;
#             2 = the gate COULD NOT GRADE (no git checkout, unreadable index).
#
# Fail closed (DF-CHIMERA-V2-135): this script runs inside a commit hook, so a
# silent pass is indistinguishable from a broken gate. Every input it needs is
# checked, and "I could not look" exits 2 rather than reporting a clean pass.
#
# Hermetic: reads git objects and the index only, writes nothing, needs no
# network, no provider key and no Python.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$ROOT" ]; then
  echo "✗ docs index: cannot grade this commit — this is not a git checkout." >&2
  echo "  The gate refuses an unindexed dogfood log at commit time; when it cannot" >&2
  echo "  see the repository it must NOT report a pass (DF-CHIMERA-V2-135)." >&2
  exit 2
fi
cd "$ROOT"

# The empty tree object id: a repo with no HEAD yet (first commit) has no base,
# and every staged file is "added" there.
EMPTY_TREE="4b825dc642cb6eb9a060e54bf8d69288fbee4904"
BASE="$(git rev-parse --verify -q HEAD 2>/dev/null || true)"
[ -z "$BASE" ] && BASE="$EMPTY_TREE"

# A FAILED `git diff --cached` (unreadable index, corrupt object) must not be
# read as "nothing was added": `|| true` here is how commit 194dcaf's class of
# miss stays invisible, so the rc is handled explicitly.
ADDED="$(git diff --cached --name-only --diff-filter=A "$BASE" -- 'docs/dogfood/*.md')" || {
  echo "✗ docs index: could not list the staged files (git diff --cached failed)." >&2
  echo "  Refusing to pass blind: an unreadable index may be hiding an unindexed" >&2
  echo "  run log, and a blind pass is the failure this gate exists to stop." >&2
  exit 2
}
if [ -z "$ADDED" ]; then
  echo "✓ docs index: no dogfood log added in this commit"
  exit 0
fi

# The index AS COMMITTED — not the working tree. A run log whose index line is
# only written to the worktree (staged later, or forgotten) is still an orphan in
# the commit, which is exactly the recurring defect.
INDEX_TEXT="$(
  { git show :docs/README.md 2>/dev/null || true
    git show :README.md 2>/dev/null || true
  }
)"

FAILED=0
while IFS= read -r path; do
  [ -z "$path" ] && continue
  name="${path##*/}"
  [ "$name" = "diagnostics.md" ] && continue
  case "$INDEX_TEXT" in
    *"$path"* | *"$name"*) continue ;;
  esac
  echo "✗ $path is added but referenced nowhere" >&2
  FAILED=1
done <<< "$ADDED"

if [ "$FAILED" -eq 1 ]; then
  echo "" >&2
  echo "COMMIT BLOCKED: a dogfood run log was added without its index line" >&2
  echo "  Add it to '## Dogfood run logs' in docs/README.md IN THIS COMMIT:" >&2
  echo "    - [dogfood/<file>](dogfood/<file>) — <what the run found> (<date>)" >&2
  echo "  tests/test_docs_index.py derives its parameter list from git ls-files," >&2
  echo "  so an unindexed log turns main red on the next push." >&2
  exit 1
fi

echo "✓ docs index: every added dogfood log is indexed"
