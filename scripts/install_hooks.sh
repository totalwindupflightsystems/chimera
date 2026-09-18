#!/usr/bin/env bash
# Install the tracked GitReins pre-commit gate into this clone's .git/hooks/.
#
#   bash scripts/install_hooks.sh            # install / repair (idempotent)
#   bash scripts/install_hooks.sh --check    # verify parity, write nothing
#   bash scripts/install_hooks.sh --dry-run  # print the plan, write nothing
#
# Why a copy instead of core.hooksPath: .git/hooks/ already carries the fleet
# `prepare-commit-msg` hook that appends the `Co-authored-by:` trailer to every
# commit. Setting core.hooksPath moves git's whole hook lookup to another
# directory and would silently shadow that trailer hook, so the gate is copied
# in beside it (and --check is how you prove the copy is current).
set -euo pipefail

SRC_REL=".gitreins/pre-commit"
DEST_REL=".git/hooks/pre-commit"

usage() {
  cat <<'EOF'
Install the tracked GitReins pre-commit hook into .git/hooks/.

Usage:
  bash scripts/install_hooks.sh [--check | --dry-run]

Options:
  --check     Verify .git/hooks/pre-commit is byte-identical to
              .gitreins/pre-commit. Exit 0 when it matches, non-zero when it
              is missing or differs. Writes nothing.
  --dry-run   Print what would be done and change nothing.
  -h, --help  Show this help.
EOF
}

CHECK=0
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --check) CHECK=1 ;;
    --dry-run|-n) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "error: unknown argument: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SRC="$ROOT/$SRC_REL"
DEST="$ROOT/$DEST_REL"
HOOK_DIR="$(dirname "$DEST")"

if [ ! -f "$SRC" ]; then
  echo "error: $SRC_REL is missing — there is nothing to install" >&2
  exit 1
fi
if [ ! -d "$HOOK_DIR" ]; then
  echo "error: $HOOK_DIR is not a directory — is this a normal clone (not a bare repo)?" >&2
  exit 1
fi

hash_of() { git hash-object "$1"; }
size_of() { wc -c < "$1" | tr -d ' '; }

report_other_hooks() {
  local others
  others="$(ls -1 "$HOOK_DIR" | grep -v '\.sample$' | grep -vx 'pre-commit' | tr '\n' ' ' || true)"
  if [ -n "${others// /}" ]; then
    echo "Other hooks present and left untouched: ${others% }"
  else
    echo "No other active hooks in .git/hooks/."
  fi
}

# ── --check: parity only, never a write ────────────────────────────────────
if [ "$CHECK" -eq 1 ]; then
  if [ ! -f "$DEST" ]; then
    echo "FAIL: $DEST_REL is not installed (run: bash scripts/install_hooks.sh)" >&2
    exit 1
  fi
  if cmp -s "$SRC" "$DEST"; then
    echo "OK: $DEST_REL is byte-identical to $SRC_REL ($(size_of "$SRC") bytes, $(hash_of "$SRC"))"
    if [ -x "$DEST" ]; then
      echo "OK: $DEST_REL is executable"
    else
      echo "FAIL: $DEST_REL is not executable — run: bash scripts/install_hooks.sh" >&2
      exit 1
    fi
    exit 0
  fi
  echo "FAIL: $DEST_REL differs from $SRC_REL" >&2
  echo "  tracked:   $(hash_of "$SRC") ($(size_of "$SRC") bytes)" >&2
  echo "  installed: $(hash_of "$DEST") ($(size_of "$DEST") bytes)" >&2
  echo "  run: bash scripts/install_hooks.sh" >&2
  exit 1
fi

# ── --dry-run: print the plan, change nothing ──────────────────────────────
if [ "$DRY_RUN" -eq 1 ]; then
  echo "DRY RUN — nothing written."
  if [ -f "$DEST" ] && cmp -s "$SRC" "$DEST"; then
    echo "  would skip the copy: $DEST_REL already matches $SRC_REL"
    [ -x "$DEST" ] || echo "  would restore the executable bit on $DEST_REL"
  else
    echo "  would copy: $SRC_REL -> $DEST_REL (mktemp + mv, then chmod +x)"
  fi
  report_other_hooks
  exit 0
fi

# ── install / repair ──────────────────────────────────────────────────────
TMP=""
cleanup() {
  if [ -n "$TMP" ] && [ -f "$TMP" ]; then
    rm -f "$TMP"
  fi
  return 0
}
trap cleanup EXIT

if [ -f "$DEST" ] && cmp -s "$SRC" "$DEST"; then
  if [ -x "$DEST" ]; then
    echo "Already installed: $DEST_REL matches $SRC_REL — nothing to do."
  else
    chmod +x "$DEST"
    echo "Already installed: $DEST_REL matched $SRC_REL; restored the executable bit."
  fi
else
  # Never write over a live hook in place: stage beside it, then rename.
  TMP="$(mktemp "$HOOK_DIR/.pre-commit.XXXXXX")"
  cp "$SRC" "$TMP"
  chmod +x "$TMP"
  mv -f "$TMP" "$DEST"
  TMP=""
  echo "Installed: $SRC_REL -> $DEST_REL ($(size_of "$DEST") bytes, $(hash_of "$SRC"))"
fi

report_other_hooks
