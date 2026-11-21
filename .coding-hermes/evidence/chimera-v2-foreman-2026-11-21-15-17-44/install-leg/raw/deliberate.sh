#!/bin/sh
H=/home/bunker-iskipchimera21r2
R=$H/results
cd "$H/empty" || exit 1
API_KEY_VAR=OPENROUTER_API_KEY
export "$API_KEY_VAR"="$(cat "$H/key")"   # value read from a private temp file at runtime, never literal
rm -f "$H/key"
cat > openrouter.yaml <<'EOF'
api_keys:
  openrouter: ${OPENROUTER_API_KEY}
defaults:
  dispatcher: openrouter/mistralai/mistral-nemo
  default_worker: openrouter/mistralai/mistral-nemo
  default_aggregator: openrouter/mistralai/mistral-nemo
  lock_aggregator: true
formations:
  simple:
    workers: 1
    worker_models: [openrouter/mistralai/mistral-nemo]
    aggregator: default
providers:
  openrouter:
    base_url: https://openrouter.ai/api/v1
models:
  openrouter/mistralai/mistral-nemo:
    provider: openrouter
    cost_tier: budget
    categories:
      general_knowledge/reasoning/explanation: 85
observability:
  log_level: warning
  use_stdout: false
EOF
"$H/venv/bin/chimera" -c openrouter.yaml -f simple run --json 'Explain in one sentence why testing a fresh install matters.' > "$R/deliberation.out" 2> "$R/deliberation.err"
echo $? > "$R/deliberation.rc"
