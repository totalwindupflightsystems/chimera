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
#             1 = at least one added log is referenced nowhere.
#
# Hermetic: reads git objects and the index only, writes nothing, needs no
# network, no provider key and no Python.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$ROOT" ]; then
  echo "✓ docs index: not a git checkout — nothing to check"
  exit 0
fi
cd "$ROOT"

# The empty tree object id: a repo with no HEAD yet (first commit) has no base,
# and every staged file is "added" there.
EMPTY_TREE="4b825dc642cb6eb9a060e54bf8d69288fbee4904"
BASE="$(git rev-parse --verify -q HEAD 2>/dev/null || true)"
[ -z "$BASE" ] && BASE="$EMPTY_TREE"

ADDED="$(git diff --cached --name-only --diff-filter=A "$BASE" -- 'docs/dogfood/*.md' 2>/dev/null || true)"
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
