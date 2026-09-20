#!/usr/bin/env bash
# Seed a usable pytest venv in the CURRENT worktree/checkout (DF-CHIMERA-V2-31).
#
# Git ignores .venv/, so every fresh `git worktree add` starts without one and
# the first gitreins guard fails confusingly: a venv-less `pytest` resolves off
# PATH to a foreign interpreter, and tests/conftest.py dies with
# "ModuleNotFoundError: No module named 'chimera'". Run this once, from the tree
# you want to seed:
#
#     ./scripts/seed_worktree_venv.sh
#
# - A previous valid seed is reused (idempotent).
# - A dangling symlink .venv (its target was deleted) is replaced.
# - A real .venv without pytest on its PATH is REPLACED — a pre-seed guard run
#   via `uv run pytest` can leave exactly that broken tree behind.
# - Python defaults to the repo floor (requires-python ">=3.11" -> 3.11), which
#   matches the long-lived checkout and CI; override with PYTHON=3.12 if wanted.
set -euo pipefail

PYTHON_FLOOR="${PYTHON:-3.11}"   # floor from pyproject.toml requires-python

if [ -x .venv/bin/pytest ]; then
    echo ".venv already seeded ($(./.venv/bin/python --version) at ./.venv) — nothing to do."
    exit 0
fi

if [ -L .venv ] || [ -e .venv ]; then
    echo "Replacing unusable .venv (no pytest on its PATH — likely a broken pre-seed)..."
    # -L first: a symlink (possibly dangling) must not trap rm in the target.
    if [ -L .venv ]; then rm .venv; else rm -r .venv; fi
fi

echo "Seeding .venv (python ${PYTHON_FLOOR}, dev extras)..."
uv venv --python "${PYTHON_FLOOR}" .venv
uv sync --extra dev

echo "Seeded. Verify with: .venv/bin/pytest --version"
