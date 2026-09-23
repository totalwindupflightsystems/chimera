#!/bin/bash
# chimera-mcp liveness proof (item 61): count + RSS + orphan check.
# Orphan = chimera-mcp whose parent no longer exists (ppid reparented to 1
# or parent pid dead).
ps -eo pid,ppid,etime,rss,args | grep '[c]himera-mcp' | while read -r pid ppid etime rss rest; do
  if ! ps -p "$ppid" > /dev/null 2>&1; then
    echo "ORPHAN pid=$pid ppid=$ppid etime=$etime rss_kb=$rss"
  fi
done
COUNT=$(ps -eo args | grep -c '[c]himera-mcp')
RSS=$(ps -eo rss,args | grep '[c]himera-mcp' | awk '{s+=$1} END {print s}')
echo "count=$COUNT total_rss_kb=$RSS"