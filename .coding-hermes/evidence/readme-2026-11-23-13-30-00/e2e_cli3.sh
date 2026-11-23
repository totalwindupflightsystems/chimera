#!/bin/bash
# CLI success-path legs WITH the documented stub running.
# Start stub (exact documented command), export fixture key, run --json and
# --quiet CLI legs, then kill the stub by pid.
E2E=/home/kara/.hermes/stand-in/readme/chimera-v2/run/e2e
REPO=/home/kara/chimera-v2
V=$REPO/.venv/bin
export CHIMERA_LOCAL_FIXTURE_KEY=local-fixture-only

nohup bash $E2E/stub.sh > $E2E/stub3.log 2>&1 &
P_WRAPPER=$!
for i in $(seq 1 40); do
  S=$(ss -ltn 2>/dev/null | grep -c ':18081 ')
  [ "$S" -ge 1 ] && break
  sleep 0.5
done
P_STUB=$(ss -ltnp 2>/dev/null | grep ':18081 ' | grep -oP 'pid=\K[0-9]+' | head -1)
echo "stub_listener=$S stub_real_pid=$P_STUB"

echo "=== P13-R2: chimera --json success leg (README:56-57) ==="
$V/chimera --config $E2E/local-fixture.yaml --json "Name one HTTP status code for not found." > $E2E/cli3.json 2>$E2E/cli3.err
echo "cli_rc=$?"
python3 -c "
import json
d=json.load(open('$E2E/cli3.json'))
print('answer:',repr(d.get('answer'))[:40])
print('answer_degraded:',d.get('answer_degraded'),'answer_error:',d.get('answer_error'))
print('trace.total_tokens:',d.get('trace',{}).get('total_tokens'))
print('trace.total_cost:',d.get('trace',{}).get('total_cost'))
print('trace keys present (README:60-83 claims):',sorted(set(['request_id','formation','dispatch','stages','aggregator','answer_stage_id','total_tokens','total_cost','total_duration_ms','worker_failures','dispatch_note','dispatch_repairs']) - set(d.get('trace',{}).keys())))
print('trace.discarded_overrides:',d.get('trace',{}).get('discarded_overrides'))
"
echo "-- stdout line count:"; wc -l < $E2E/cli3.json
echo "-- stderr warnings tail (README:108 operational warnings move to stderr):"
tail -2 $E2E/cli3.err
echo "=== P13-Q2: chimera --quiet success leg (README:52 ANSWER=\$(...) contract) ==="
$V/chimera --config $E2E/local-fixture.yaml --quiet "Name one HTTP status code for not found." > $E2E/cli3q.out 2>/dev/null
echo "quiet_rc=$?"
echo "-- stdout od:"; od -c $E2E/cli3q.out | head -3

if [ -n "$P_STUB" ]; then kill "$P_STUB" 2>/dev/null && echo "killed stub $P_STUB"; fi
[ -n "$P_WRAPPER" ] && kill "$P_WRAPPER" 2>/dev/null && echo "killed wrapper $P_WRAPPER"
sleep 1; ss -ltn 2>/dev/null | grep -c ':18081 ' | sed 's/^/listeners_left=/'
echo "CLI3_DONE"
