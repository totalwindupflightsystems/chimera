#!/usr/bin/env bash
# run_cfg.sh <label> <fail_budget> <config_path>
set -u
HERE=/home/kara/.hermes/cache/scratch/cv2-df33
LABEL=$1; BUDGET=$2; CFG=$3
pkill -f "stub429.py 18081" 2>/dev/null
sleep 0.5
rm -f "$HERE/$LABEL.jsonl"
nohup python3 "$HERE/stub429.py" 18081 "$BUDGET" "$HERE/$LABEL.jsonl" 429 > "$HERE/$LABEL.stub.log" 2>&1 &
sleep 1
cd /home/kara/chimera-v2
START=$(date +%s.%N)
timeout 200 .venv/bin/python "$HERE/probe_cfg.py" single "$CFG" > "$HERE/$LABEL.out" 2>&1
RC=$?
END=$(date +%s.%N)
pkill -f "stub429.py 18081" 2>/dev/null
echo "=== $LABEL rc=$RC wall=$(echo "$END $START" | awk '{printf "%.2f", $1-$2}')s arrivals=$(wc -l < "$HERE/$LABEL.jsonl") gateway_retry_lines=$(grep -c gateway_retry "$HERE/$LABEL.out") ==="
grep -E "^\{" "$HERE/$LABEL.out" | grep -v '"event"' | head -3
echo
