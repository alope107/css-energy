#!/bin/bash
# report.sh START LINES LOG... — for shared/make/checks.mk: each check whose log is older than START (when this make
# began, in ns) was up to date, so make didn't run it. Say so, with the last LINES lines of the pass the log stands for.
start=$1 n=$2; shift 2
for log; do
  m=$(stat -c %.9Y "$log"); [ "${m/./}" -lt "$start" ] || continue
  echo "up to date: $log passed $(date -r "$log" '+%F %T'); nothing it depends on has changed since (RERUN=1 runs it). It ended:"
  tail -n "$n" "$log"
done
