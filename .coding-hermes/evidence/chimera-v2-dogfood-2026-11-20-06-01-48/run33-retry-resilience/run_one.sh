#!/usr/bin/env bash
# run_one.sh <label> <fail_budget> <probe_mode> [status]
set -u
HERE=/home/kara/.hermes/cache/scratch/cv2-df33
LABEL=$1; BUDGET=$2; MODE=$3; STATUS=${4:-429}
python3 - <<'PY'
import socket
s = socket.socket()
try:
    s.connect(("127.0.0.1", 18081)); s.close(); print("port busy")
except OSError:
    print("port free")
PY
pkill -f "stub429.py 18081" 2>/dev/null
sleep 0.5
rm -f "$HERE/$LABEL.jsonl"
nohup python3 "$HERE/stub429.py" 18081 "$BUDGET" "$HERE/$LABEL.jsonl" "$STATUS" > "$HERE/$LABEL.stub.log" 2>&1 &
sleep 1
cd /home/kara/chimera-v2
START=$(date +%s.%N)
timeout 200 .venv/bin/python "$HERE/probe_retry.py" "$MODE" > "$HERE/$LABEL.out" 2>&1
RC=$?
END=$(date +%s.%N)
pkill -f "stub429.py 18081" 2>/dev/null
echo "=== $LABEL rc=$RC wall=$(echo "$END $START" | awk '{printf "%.2f", $1-$2}')s ==="
echo "--- probe result ---"; grep -E "^\{'i'" "$HERE/$LABEL.out" || tail -5 "$HERE/$LABEL.out"
echo "--- upstream arrivals (n, t_rel, status, gap_s) ---"
python3 - "$HERE/$LABEL.jsonl" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
prev = None
for r in rows:
    gap = "" if prev is None else f"{r['t']-prev:+.4f}"
    print(f"  n={r['n']:2d} t={r['t']:8.4f} status={r['status']} gap={gap}")
    prev = r['t']
print(f"  TOTAL arrivals={len(rows)} statuses={[r['status'] for r in rows]}")
PY
echo "--- gateway_retry log lines: $(grep -c gateway_retry "$HERE/$LABEL.out") ---"
grep "gateway_retry" "$HERE/$LABEL.out" | head -6
echo
