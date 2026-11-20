#!/usr/bin/env bash
# retry_after.sh <retry_after_seconds> <fail_budget>
set -u
HERE=/home/kara/.hermes/cache/scratch/cv2-df33
RA=$1; BUDGET=$2
pkill -f "stub429.py 18081" 2>/dev/null; sleep 0.6
rm -f "$HERE/ra.jsonl"
nohup python3 "$HERE/stub429.py" 18081 "$BUDGET" "$HERE/ra.jsonl" 429 "$RA" > "$HERE/ra.stub.log" 2>&1 &
sleep 1
body='{"model":"auto","messages":[{"role":"user","content":"ping retry-after probe"}]}'
t=$(curl -s -o "$HERE/ra_api.json" -w "%{http_code} %{time_total}" -m 300 \
      -X POST http://127.0.0.1:18766/v1/chat/completions \
      -H "content-type: application/json" -d "$body")
pkill -f "stub429.py 18081" 2>/dev/null
echo "retry-after=$RA budget=$BUDGET -> http=$(echo "$t" | cut -d' ' -f1) wall=$(echo "$t" | cut -d' ' -f2)s arrivals=$(wc -l < "$HERE/ra.jsonl")"
cat "$HERE/ra.jsonl"
