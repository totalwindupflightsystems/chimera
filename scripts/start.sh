#!/usr/bin/env bash
set -e
cd /home/kara/chimera-v2

# Source environment
source .venv/bin/activate
source ~/.hermes/.env 2>/dev/null || true

# Verify keys are set
: ${DEEPSEEK_API_KEY:?DEEPSEEK_API_KEY not set}
: ${OPENROUTER_API_KEY:?OPENROUTER_API_KEY not set}
: ${GEMINI_API_KEY:?GEMINI_API_KEY not set}

# Clear stale bytecode
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

echo "Starting Chimera on port 8765..."
exec chimera serve --port 8765
