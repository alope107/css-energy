#!/bin/bash
# logged.sh LOG [-t N] [-p PASS_RE]... [-f FAIL_RE]... -- command...
# Runs a check for shared/make/checks.mk. Its output (stderr merged into stdout) shows as it comes. On a pass the
# output becomes LOG, the make target that stands for the pass; on a failure LOG is removed and the output is kept in
# LOG.failed. A pass: exit 0, a line matching every -p regex, no line matching any -f regex (grep -E). The -p and -f
# regexes are for harnesses that exit 0 whatever happens and only say so in their output. -t N shows only the last N
# lines, at the end (what `| tail -N` did, without hiding the exit status).
set -o pipefail
log=$1; shift; pass=(); fail=(); tail=
while [ "$1" != -- ]; do
  case $1 in -t) tail=$2 ;; -p) pass+=("$2") ;; -f) fail+=("$2") ;; *) echo "logged.sh: unknown option $1" >&2; exit 2 ;; esac
  shift 2
done
shift
mkdir -p "$(dirname "$log")"; rm -f "$log" "$log.failed"
if [ -n "$tail" ]; then "$@" > "$log.tmp" 2>&1; rc=$?; tail -n "$tail" "$log.tmp"; else "$@" 2>&1 | tee "$log.tmp"; rc=$?; fi
why=
[ $rc -ne 0 ] && why="exit $rc"
for r in "${pass[@]}"; do grep -Eq -- "$r" "$log.tmp" || why="${why:+$why, }no line matches $r"; done
for r in "${fail[@]}"; do grep -Eq -- "$r" "$log.tmp" && why="${why:+$why, }a line matches $r"; done
if [ -n "$why" ]; then
  mv "$log.tmp" "$log.failed"; echo "FAILED ($why): output in $log.failed" >&2; exit $(( rc ? rc : 1 ))
fi
mv "$log.tmp" "$log"
