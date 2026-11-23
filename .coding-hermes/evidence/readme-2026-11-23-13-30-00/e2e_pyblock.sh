#!/bin/bash
# (a) Run README:125-134's Python recipe VERBATIM through the fixture (CHIMERA_CONFIG
#     env override is README:198's documented mechanism), probing the attribute paths
#     DF-CHIMERA-V2-115 names. (b) Keyless GET on the lane-owned live instance :8765.
E2E=/home/kara/.hermes/stand-in/readme/chimera-v2/run/e2e
REPO=/home/kara/chimera-v2
V=$REPO/.venv/bin
mkdir -p $E2E/pyblock; cd $E2E/pyblock

# write the README recipe EXACTLY (lines 125-134, plus stdout for the answer)
cat > recipe.py <<'PYEOF'
import asyncio

from chimera import Engine, LiteLLMGateway, load_config

config = load_config()
engine = Engine(config, LiteLLMGateway(config))
result = asyncio.run(engine.deliberate("Explain quantum computing."))
print(result.answer)  # merged output from multiple models
# --- probe arm (documented nowhere; attribute-path check for DF-CHIMERA-V2-115) ---
print("ATTR_PROBE total_cost:", result.trace.total_cost)
print("ATTR_PROBE request_id:", result.trace.request_id)
print("ATTR_PROBE worker_failures:", result.trace.worker_failures)
PYEOF

nohup bash $E2E/stub.sh > $E2E/stub5.log 2>&1 &
P_WRAPPER=$!
for i in $(seq 1 40); do S=$(ss -ltn 2>/dev/null | grep -c ':18081 '); [ "$S" -ge 1 ] && break; sleep 0.5; done
P_STUB=$(ss -ltnp 2>/dev/null | grep ':18081 ' | grep -oP 'pid=\K[0-9]+' | head -1)
echo "stub=$S stub_pid=$P_STUB"

echo "=== README Python block run verbatim (CHIMERA_CONFIG=fixture per README:198) ==="
CHIMERA_CONFIG=$E2E/local-fixture.yaml CHIMERA_LOCAL_FIXTURE_KEY=local-fixture-only $V/python recipe.py > recipe.out 2> recipe.err
echo "recipe_rc=$?"
echo "-- stdout:"; head -6 recipe.out
echo "-- stderr tail (warnings):"; tail -3 recipe.err
$V/python -c "
src=open('$REPO/README.md').read().splitlines()
blk=src[124:134]
print('README:125-134 mentions total_cost:', any('total_cost' in l for l in blk))
print('README:125-134 mentions request_id:', any('request_id' in l for l in blk))
print('README:125-134 mentions formation:', any('formation' in l for l in blk))
"
if [ -n "$P_STUB" ]; then kill "$P_STUB" && echo killed_stub; fi
[ -n "$P_WRAPPER" ] && kill "$P_WRAPPER" && echo killed_wrapper

echo "=== (b) lane-owned live instance :8765 (RELEASE-FINDING-2026-11-21-008 premise) ==="
curl -s --max-time 5 http://127.0.0.1:8765/v1/health -o $E2E/live8765.json -w 'http=%{http_code}\n'
$V/python -c "
import json
try:
    d=json.load(open('$E2E/live8765.json'))
    print('status:',d.get('status'),'commit:',d.get('details',{}).get('commit'),'version:',d.get('details',{}).get('version'))
except Exception as e:
    print('unreadable:',e)
"
echo "PROBE5_DONE"
