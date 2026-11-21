#!/bin/sh
H=/home/bunker-iskipchimera21r2
R=$H/results
cd "$H/empty" || exit 1
API_KEY_VAR=ROUTER9_API_KEY
export "$API_KEY_VAR"="$(cat "$H/key")"   # value read from a private temp file at runtime, never literal
rm -f "$H/key"
cat > router.yaml <<'EOF'
api_keys:
  router9: ${ROUTER9_API_KEY}
defaults:
  dispatcher: router9/cx/gpt-6.1-terra
  default_worker: router9/cx/gpt-6.1-terra
  default_aggregator: router9/cx/gpt-6.1-terra
  lock_aggregator: true
formations:
  simple:
    workers: 1
    worker_models: [router9/cx/gpt-6.1-terra]
    aggregator: default
providers:
  router9:
    base_url: http://master001:20128/v1
    api_key_env: ROUTER9_API_KEY
models:
  router9/cx/gpt-6.1-terra:
    provider: router9
    cost_tier: budget
    categories:
      general_knowledge/reasoning/explanation: 85
observability:
  log_level: warning
  use_stdout: false
EOF
"$H/venv/bin/chimera" -c router.yaml -f simple run --json 'Explain in one sentence why testing a fresh install matters.' > "$R/router9.out" 2> "$R/router9.err"
echo $? > "$R/router9.rc"
