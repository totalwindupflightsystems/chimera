#!/usr/bin/env bash
# Run 34 -- "abandon / resume" arm: what happens when a real user walks away
# from a slow deliberation (curl timeout, CLI Ctrl-C, closed tab)?
#
# Measures, from OUTSIDE Chimera:
#   1. wall time of a control request (queue.max_concurrent: 1, 4s stub)
#   2. does an ABANDONED request keep its concurrency slot?
#      -> the next request's wall + X-Chimera-Queue-Position
#   3. does an abandoned request keep SPENDING upstream calls?
#      -> stub arrival log, counted per prompt marker after the client left
#   4. what does /metrics say about a request no client ever received?
#
# Everything here is a read of the product; no repo file is modified.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
REPO=/home/kara/chimera-v2
PORT=18791
STUBPORT=18091
DELAY=4
LOG="$DIR/stub-arrivals.jsonl"
RES="$DIR/run34-results.txt"
: >"$LOG"
: >"$RES"

say() { printf '%s\n' "$*" | tee -a "$RES"; }
now() { date +%s.%N; }
wall() { awk -v a="$1" -v b="$2" 'BEGIN{printf "%.2f", b-a}'; }

say "== run34 abandon/resume  $(date -Is)"

# ---- 0. upstream stub + scratch instance -----------------------------------
python3 "$DIR/stub_slow.py" "$STUBPORT" "$DELAY" "$LOG" &
STUB=$!
export CHIMERA_CONFIG="$DIR/fixture.yaml"
export CHIMERA_LOCAL_FIXTURE_KEY=stub-key
"$REPO/.venv/bin/chimera" serve --host 127.0.0.1 --port "$PORT" >"$DIR/serve.log" 2>&1 &
SRV=$!
say "stub pid=$STUB srv pid=$SRV port=$PORT delay=${DELAY}s max_concurrent=1"

for i in $(seq 1 60); do
  curl -s -m 2 -o /dev/null "http://127.0.0.1:$PORT/health" && break
  sleep 0.5
done
curl -s -m 5 "http://127.0.0.1:$PORT/health" >>"$RES"
say ""

# ---- 1. control ------------------------------------------------------------
T0=$(now)
CTRL_BODY="$DIR/ctrl1.json"
curl -s -m 120 -D "$DIR/ctrl1.headers" -o "$CTRL_BODY" \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"CTRL1-name-one-http-status-code","formation":"simple"}' \
  "http://127.0.0.1:$PORT/v1/deliberate"
T1=$(now)
say "A1 control wall=$(wall "$T0" "$T1")s http=$(awk 'NR==1{print $2}' "$DIR/ctrl1.headers") queue=$(grep -i '^x-chimera-queue-position' "$DIR/ctrl1.headers" | tr -d '\r' | awk '{print $2}')"
say "A1 answer=$(jq -r '.answer // .final_answer // (.response|tostring) // "?"' "$CTRL_BODY" 2>/dev/null | head -c 80)"

# ---- 2. abandon: client leaves at 2s; immediately retry --------------------
T2=$(now)
curl -s -m 2 -o /dev/null -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"ABORT1-name-one-http-status-code","formation":"simple"}' \
  "http://127.0.0.1:$PORT/v1/deliberate" >"$DIR/abort1.code" 2>"$DIR/abort1.err"
ABORT_RC=$?
T3=$(now)
say "A2 abandoned client: curl rc=$ABORT_RC (28 = client gave up) after $(wall "$T2" "$T3")s, body=$(cat "$DIR/abort1.code")"

# retry immediately, as a user would
T4=$(now)
curl -s -m 180 -D "$DIR/after1.headers" -o "$DIR/after1.json" \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"AFTER1-name-one-http-status-code","formation":"simple"}' \
  "http://127.0.0.1:$PORT/v1/deliberate"
T5=$(now)
say "A3 retry-during-orphan wall=$(wall "$T4" "$T5")s queue=$(grep -i '^x-chimera-queue-position' "$DIR/after1.headers" | tr -d '\r' | awk '{print $2}')"
say "A3 answer=$(jq -r '.answer // .final_answer // (.response|tostring) // "?"' "$DIR/after1.json" 2>/dev/null | head -c 80)"

curl -s -m 10 "http://127.0.0.1:$PORT/metrics" >"$DIR/metrics-after-abort.txt"
say "A4 metrics POST /v1/deliberate rows:"
grep -E '^chimera_requests_total\{method="POST",route="/v1/deliberate"' "$DIR/metrics-after-abort.txt" | sed 's/^/    /' | tee -a "$RES"

# ---- 3. CLI Ctrl-C (the real human gesture) --------------------------------
T6=$(now)
( cd "$REPO" && timeout -s INT 2 .venv/bin/chimera --json --formation simple \
    "CLIABORT-name-one-http-status-code" ) >"$DIR/cli-abort.out" 2>"$DIR/cli-abort.err"
CLI_RC=$?
T7=$(now)
say "A5 CLI Ctrl-C at 2s: exit=$CLI_RC wall=$(wall "$T6" "$T7")s stderr_bytes=$(wc -c <"$DIR/cli-abort.err") out_bytes=$(wc -c <"$DIR/cli-abort.out")"
say "A5 stderr: $(tr '\n' '|' <"$DIR/cli-abort.err" | head -c 300)"

sleep 16   # let any orphan finish
curl -s -m 10 "http://127.0.0.1:$PORT/metrics" >"$DIR/metrics-final.txt"
say "A6 metrics POST /v1/deliberate rows (final):"
grep -E '^chimera_requests_total\{method="POST",route="/v1/deliberate"' "$DIR/metrics-final.txt" | sed 's/^/    /' | tee -a "$RES"
say "A6 duration histogram for POST /v1/deliberate (final):"
grep -E '^chimera_request_duration_seconds_(count|sum)\{method="POST",route="/v1/deliberate"' "$DIR/metrics-final.txt" | sed 's/^/    /' | tee -a "$RES"

# ---- 4. upstream evidence: who kept spending after the client left? --------
say "A7 upstream arrivals per marker (3 stages = dispatcher+worker+aggregator):"
jq -r 'select(.arrival) | .marker' "$LOG" 2>/dev/null | sort | uniq -c | sed 's/^/    /' | tee -a "$RES"
say "A7 last upstream service times:"
jq -r 'select(.served) | "    served=\(.served) t_out=\(.t_out) marker=\(.marker)"' "$LOG" 2>/dev/null | tee -a "$RES"

say "A8 still-alive upstream calls at exit: $(jq -r 'select(.arrival)|.arrival' "$LOG" 2>/dev/null | wc -l) arrivals, $(jq -r 'select(.served)|.served' "$LOG" 2>/dev/null | wc -l) served"
say "A9 server log tail:"; tail -12 "$DIR/serve.log" | sed 's/^/    /' | tee -a "$RES"

kill "$SRV" "$STUB" 2>/dev/null
wait "$SRV" "$STUB" 2>/dev/null
say "== done"
