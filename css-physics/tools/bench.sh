#!/bin/bash
# bench.sh reps file1 file2 ... : min of median style-pass time over reps (interleaved)
R=$1; shift
declare -A best
for r in $(seq $R); do for f in "$@"; do
  v=$(node "$(dirname "$0")/tr.js" $f 700 1200 | awk '{print $5}')
  b=${best[$f]:-999}; best[$f]=$(python3 -c "print(min($b,$v))")
done; done
for f in "$@"; do printf "%-28s %s\n" $f ${best[$f]}; done
