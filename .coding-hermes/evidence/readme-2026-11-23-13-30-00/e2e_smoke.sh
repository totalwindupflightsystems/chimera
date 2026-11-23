#!/bin/bash
# Live smoke test section (README:492-528) run against the fixture deployment.
E2E=/home/kara/.hermes/stand-in/readme/chimera-v2/run/e2e
REPO=/home/kara/chimera-v2
V=$REPO/.venv/bin
export CHIMERA_LOCAL_FIXTURE_KEY=local-fixture-only

nohup bash $E2E/stub.sh > $E2E/stub4.log 2>&1 &
P_WRAPPER=$!
nohup $V/chimera --config $E2E/local-fixture.yaml serve --host 127.0.0.1 --port 18082 > $E2E/serve4.log 2>&1 &
P_SERVE=$!
for i in $(seq 1 60); do
  S1=$(ss -ltn 2>/dev/null | grep -c ':18081 '); S2=$(ss -ltn 2>/dev/null | grep -c ':18082 ')
  [ "$S1" -ge 1 ] && [ "$S2" -ge 1 ] && break; sleep 0.5
done
P_STUB=$(ss -ltnp 2>/dev/null | grep ':18081 ' | grep -oP 'pid=\K[0-9]+' | head -1)
echo "listeners stub=$S1 serve=$S2 stub_pid=$P_STUB serve_pid=$P_SERVE"

cd $REPO
echo "=== README:499 arm: python scripts/smoke_live.py --base-url <fixture> (default formation simple) ==="
.venv/bin/python scripts/smoke_live.py --base-url http://127.0.0.1:18082 --formation simple > $E2E/smoke1.out 2>$E2E/smoke1.err
echo "smoke_rc=$?"
echo "-- stdout:"; cat $E2E/smoke1.out | head -30
echo "-- stderr tail:"; tail -3 $E2E/smoke1.err
echo "=== README:511 --formation auto arm unavailable in fixture -> skip; --allow-stale not needed (parity expected) ==="

for P in $P_SERVE $P_STUB $P_WRAPPER; do
  if [ -n "$P" ] && kill -0 $P 2>/dev/null; then kill $P; echo "killed $P"; fi
done
P_STUB2=$(ss -ltnp 2>/dev/null | grep ':18081 ' | grep -oP 'pid=\K[0-9]+' | head -1)
[ -n "$P_STUB2" ] && kill "$P_STUB2" && echo "killed stub $P_STUB2"
sleep 1; ss -ltn 2>/dev/null | grep -c -E ':1808[12] ' | sed 's/^/listeners_left=/'
echo "SMOKE_DONE"
