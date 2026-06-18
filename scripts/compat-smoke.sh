#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Compat Smoke — run the live model compatibility test suite
# ─────────────────────────────────────────────────────────────────────────────
# Usage:  scripts/compat-smoke.sh [pytest args...]
#
# Requires API keys in the environment for the models you want to test:
#   DEEPSEEK_API_KEY, ZAI_API_KEY, ANTHROPIC_API_KEY,
#   MOONSHOT_API_KEY, MINIMAX_API_KEY, GEMINI_API_KEY
#
# Missing keys → the corresponding test(s) will skip automatically.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

# Ensure the virtual env is active if present
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

echo "🔌 Running model compatibility smoke tests..."
echo "   Models: deepseek-v4-flash, deepseek-v4-pro, glm-5.2, claude-sonnet-4,"
echo "           kimi-k2.7, minimax-m3, gemini-3-flash-preview"
echo ""

exec python -m pytest tests/compat/ \
    --run-compat \
    -v \
    --tb=short \
    --timeout=40 \
    "$@"
