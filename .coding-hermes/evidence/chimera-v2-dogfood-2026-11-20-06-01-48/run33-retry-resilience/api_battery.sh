#!/usr/bin/env bash
# User-facing battery against the served API on :18766, with a flapping upstream.
set -u
HERE=/home/kara/.hermes/cache/scratch/cv2-df33
API=http://127.0.0.1:18766/v1/chat/completions

ask() { # ask <label>
  local label=$1
  local body='{"model":"auto","messages":[{"role":"user","content":"Summarise why my celery task is stuck"}]}'
  local out="$HERE/api_$label.json"
  local t
  t=$(curl -s -o "$out" -w "%{http_code} %{time_total}" -m 120 \
        -X POST "$API" -H "content-type: application/json" -d "$body")
  echo "  [$label] http=$(echo "$t" | cut -d' ' -f1) wall=$(echo "$t" | cut -d' ' -f2)s bytes=$(wc -c < "$out")"
  head -c 300 "$out" | tr -d '\n'; echo; echo
}

restart_stub() { # restart_stub <budget> <label>
  pkill -f "stub429.py 18081" 2>/dev/null; sleep 0.6
  rm -f "$HERE/api_$2.jsonl"
  nohup python3 "$HERE/stub429.py" 18081 "$1" "$HERE/api_$2.jsonl" 429 > "$HERE/api_$2.stub.log" 2>&1 &
  sleep 1
}

echo "### 1. healthy upstream (budget=0): cold + warm"
restart_stub 0 clean1
ask clean_cold
ask clean_warm
echo "  upstream arrivals: $(wc -l < "$HERE/api_clean1.jsonl")"

echo "### 2. one transient blip (budget=2, warm process): the 429-then-200 case"
restart_stub 2 blip
ask blip_warm
echo "  upstream arrivals: $(wc -l < "$HERE/api_blip.jsonl")"
cat "$HERE/api_blip.jsonl"

echo "### 3. provider hard-down (budget=99): what the user sees after retries exhaust"
restart_stub 99 down
ask down_warm
echo "  upstream arrivals: $(wc -l < "$HERE/api_down.jsonl")"

pkill -f "stub429.py 18081" 2>/dev/null
