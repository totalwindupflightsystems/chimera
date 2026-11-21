#!/bin/sh
H=/home/bunker-iskipchimera21r2
R=$H/results
cd "$H/empty" || exit 1
API_KEY_VAR=FIREWORKS_API_KEY
export "$API_KEY_VAR"="$(cat "$H/key")"   # value read from a private temp file at runtime, never literal
rm -f "$H/key"
cat > fireworks.yaml <<'EOF'
api_keys:
  fireworks: ${FIREWORKS_API_KEY}
defaults:
  dispatcher: fireworks/accounts/fireworks/models/llama-v3p1-8b-instruct
  default_worker: fireworks/accounts/fireworks/models/llama-v3p1-8b-instruct
  default_aggregator: fireworks/accounts/fireworks/models/llama-v3p1-8b-instruct
  lock_aggregator: true
formations:
  simple:
    workers: 1
    worker_models: [fireworks/accounts/fireworks/models/llama-v3p1-8b-instruct]
    aggregator: default
providers:
  fireworks:
    base_url: https://api.fireworks.ai/inference/v1
    api_key_env: FIREWORKS_API_KEY
models:
  fireworks/accounts/fireworks/models/llama-v3p1-8b-instruct:
    provider: fireworks
    cost_tier: budget
    categories:
      general_knowledge/reasoning/explanation: 85
observability:
  log_level: warning
  use_stdout: false
EOF
sed -i 's/llama-v3p1-8b-instruct/glm-5p3-flash/g' fireworks.yaml
"$H/venv/bin/chimera" -c fireworks.yaml -f simple run --json 'Explain in one sentence why testing a fresh install matters.' > "$R/fireworks-retry.out" 2> "$R/fireworks-retry.err"
echo $? > "$R/fireworks-retry.rc"
