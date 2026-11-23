#!/bin/bash
# Single-call fixture E2E: start documented stub (18081) + serve (18082), probe
# the full documented surface, run the documented regression arm, tear down by
# recorded PID. The surface kills background children between calls, so nothing
# here may outlive this invocation.
set -u
E2E=/home/kara/.hermes/stand-in/readme/chimera-v2/run/e2e
REPO=/home/kara/chimera-v2
V=$REPO/.venv/bin
STUB_LOG=$E2E/stub2.log
SERVE_LOG=$E2E/serve2.log

cd $REPO
# 1. stub: exact documented command (docs/CONFIG.md #minimal-local-fixture)
nohup bash $E2E/stub.sh > $STUB_LOG 2>&1 &
P_STUB_WRAPPER=$!
echo "stub_wrapper_pid=$P_STUB_WRAPPER"

# 2. serve: documented command with exported fixture key
nohup env CHIMERA_LOCAL_FIXTURE_KEY=local-fixture-only \
  $V/chimera --config $E2E/local-fixture.yaml serve --host 127.0.0.1 --port 18082 \
  > $SERVE_LOG 2>&1 &
P_SERVE=$!
echo "serve_pid=$P_SERVE"

# 3. wait for both listeners (bounded 30s)
for i in $(seq 1 60); do
  S1=$(ss -ltn 2>/dev/null | grep -c ':18081 ')
  S2=$(ss -ltn 2>/dev/null | grep -c ':18082 ')
  [ "$S1" -ge 1 ] && [ "$S2" -ge 1 ] && break
  sleep 0.5
done
echo "listeners: stub=$S1 serve=$S2"
ss -ltnp | grep -E ':1808[12] ' | sed 's/users://'

# the stub.sh wrapper exec'd python becomes the real stub pid; capture it
P_STUB=$(ss -ltnp 2>/dev/null | grep ':18081 ' | grep -oP 'pid=\K[0-9]+' | head -1)
echo "stub_real_pid=$P_STUB"

B=http://127.0.0.1:18082
echo "=== P1 GET /health (README:353 always-200 alias) ==="
curl -s -o $E2E/p1.body -w 'http=%{http_code}\n' --max-time 10 $B/health; head -c 200 $E2E/p1.body 2>/dev/null; echo
echo "=== P2 GET /v1/health ==="
curl -s -o $E2E/p2.body -w 'http=%{http_code}\n' --max-time 30 $B/v1/health
python3 -c "import json;d=json.load(open('$E2E/p2.body'));print('status:',d.get('status'),'unhealthy:',d.get('unhealthy_providers'),'slow:',d.get('slow_providers'));print('providers:',{n:(v.get('healthy'),v.get('error_class')) for n,v in d.get('details',{}).get('providers',{}).items()})" 2>&1
echo "=== P3 GET /v1/health/ready (200 when >=1 provider reachable) ==="
curl -s -o $E2E/p3.body -w 'http=%{http_code}\n' --max-time 30 $B/v1/health/ready
python3 -c "import json;d=json.load(open('$E2E/p3.body'));print('status:',d.get('status'),'unhealthy:',d.get('unhealthy_providers'))" 2>&1
echo "=== P4 GET /v1/health/live ==="
curl -s -o /dev/null -w 'http=%{http_code}\n' --max-time 10 $B/v1/health/live
echo "=== P5 GET /metrics (README:377 documents curl -> 200) ==="
curl -s -o $E2E/p5.body -w 'http=%{http_code} ctype=%{content_type}\n' --max-time 10 $B/metrics
grep -c '^chimera_' $E2E/p5.body 2>/dev/null; grep -E 'chimera_(requests_total|retries_total)' $E2E/p5.body 2>/dev/null | head -3
echo "=== P6 GET /docs ==="
curl -s -o /dev/null -w 'http=%{http_code}\n' --max-time 10 $B/docs
echo "=== P7 GET /web/ ==="
curl -s -o /dev/null -w 'http=%{http_code}\n' --max-time 10 $B/web/
echo "=== P8 GET /.well-known/agent-card.json (README:390-394 skills list) ==="
curl -s --max-time 10 $B/.well-known/agent-card.json -o $E2E/p8.body
python3 -c "import json;d=json.load(open('$E2E/p8.body'));print('name:',d.get('name'),'version:',d.get('version'));print('skills:',[s.get('name') for s in d.get('skills',[])])" 2>&1
echo "=== P9 GET /v1/formations ==="
curl -s --max-time 10 $B/v1/formations -o $E2E/p9.body
python3 -c "import json;d=json.load(open('$E2E/p9.body'));print('type:',type(d).__name__);print('names:',[f.get('name') for f in d.get('data',d if isinstance(d,list) else [])][:8])" 2>&1
echo "=== P10 GET /v1/models ==="
curl -s --max-time 10 $B/v1/models -o $E2E/p10.body
python3 -c "import json;d=json.load(open('$E2E/p10.body'));print('data:',[m.get('id') for m in d.get('data',[])][:5]);print('catalog keys:',list(d.get('catalog',{}))[:5])" 2>&1
echo "=== P11 POST /v1/deliberate formation=simple (README:976 STUB-OK contract) ==="
curl -s -o $E2E/p11.body -w 'http=%{http_code}\n' --max-time 60 -X POST $B/v1/deliberate \
  -H 'Content-Type: application/json' -d '{"prompt":"Name one HTTP status code for not found.","formation":"simple"}'
python3 -c "import json;d=json.load(open('$E2E/p11.body'));print('answer:',repr(d.get('answer'))[:60]);print('request_id top-level:',bool(d.get('request_id')));print('trace.request_id:',bool(d.get('trace',{}).get('request_id')));print('total_cost:',d.get('trace',{}).get('total_cost'));print('aggregator_model:',d.get('trace',{}).get('aggregator_model'));print('aggregator.stage_id:',d.get('trace',{}).get('aggregator',{}).get('stage_id'));print('worker_failures:',d.get('trace',{}).get('worker_failures'))" 2>&1
echo "=== P12 POST /v1/chat/completions model=simple (README:597 formation-not-model-id) ==="
curl -s -o $E2E/p12.body -w 'http=%{http_code}\n' --max-time 60 -X POST $B/v1/chat/completions \
  -H 'Content-Type: application/json' -d '{"model":"simple","messages":[{"role":"user","content":"Hello"}]}'
python3 -c "import json;d=json.load(open('$E2E/p12.body'));print('id:',str(d.get('id'))[:30]);print('model:',d.get('model'));print('content:',repr((d.get('choices') or [{}])[0].get('message',{}).get('content'))[:50]);print('usage:',d.get('usage'));print('total_cost key in usage:', 'total_cost' in (d.get('usage') or {}))" 2>&1
echo "=== P13 CLI --json leg through the SAME fixture (README:56-57 jq contract) ==="
$V/chimera --config $E2E/local-fixture.yaml --json "Name one HTTP status code for not found." > $E2E/cli.json 2>$E2E/cli.err
echo "cli_rc=$?"
python3 -c "import json;d=json.load(open('$E2E/cli.json'));print('answer:',repr(d.get('answer'))[:50]);print('exit2 fields: answer_degraded=',d.get('answer_degraded'),'answer_error=',d.get('answer_error'));print('trace keys sample:',sorted(d.get('trace',{}))[:10])" 2>&1
echo "-- stdout line count (promise: exactly ONE payload):"; wc -l < $E2E/cli.json
echo "-- stderr tail:"; tail -3 $E2E/cli.err
echo "=== P14 documented regression arm (docs/CONFIG.md #minimal-local-fixture) ==="
cd $REPO && .venv/bin/python -m pytest tests/test_credential_source.py -k documented_local_fixture -q 2>&1 | tail -4; echo "pytest_rc=${PIPESTATUS[0]}"

echo "=== TEARDOWN (kill by recorded pid only) ==="
for P in $P_SERVE $P_STUB $P_STUB_WRAPPER; do
  if kill -0 $P 2>/dev/null; then kill $P; echo "killed $P rc=$?"; else echo "$P already gone"; fi
done
sleep 1
ss -ltn 2>/dev/null | grep -c -E ':1808[12] ' | sed 's/^/listeners_left=/'
echo "E2E_DONE"
