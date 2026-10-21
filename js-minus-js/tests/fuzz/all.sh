#!/bin/sh
# all.sh [seed] — the full differential run (make fuzz): every level without a browser, on many programs. Prints ALL OK
# when every part passed. Another seed (SEED=2 make fuzz RERUN=1) explores other programs; the default is reproducible.
s=${1:-${SEED:-1}}; cd "$(dirname "$0")/../.." || exit 2
F="python3 tests/fuzz/fuzz.py"; ok=1
$F fmt --l2                       || ok=0     # the suite in every layout, L1 + the page text + L2
$F gen -n 3000 -s "$s"            || ok=0     # generated programs, L1 (+ the page text when they fit)
$F gen -n 400 -s "$((s + 1000))" --l2 --c1 || ok=0     # fewer, through the DSL and the CSS CPU's model too
$F mut -n 3000 -s "$s" --l2       || ok=0     # one-token edits: rejects agree with Node, and the DSL with cc_ref
[ $ok = 1 ] && echo 'ALL OK' || { echo FAILURES; exit 1; }
