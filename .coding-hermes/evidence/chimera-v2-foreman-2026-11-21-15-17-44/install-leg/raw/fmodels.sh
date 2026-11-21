#!/bin/sh
H=/home/bunker-iskipchimera21r2
K=$(cat "$H/key")
rm -f "$H/key"
curl -sS --max-time 30 -H "Authorization: Bearer $K" https://api.fireworks.ai/inference/v1/models > "$H/results/fireworks-models.out" 2> "$H/results/fireworks-models.err"
echo $? > "$H/results/fireworks-models.rc"
