#!/bin/bash
# bench.sh [rounds] [programs...] — main's stack CPU vs the register CPU on CPU-only pages, interleaved (../shared/js/ab.js):
# run time (first step -> HALT, machine/halttime.js runMs) per program. Pages: build/base/<p>.html (machine/gen_css.py on
# compiler/mkimage.py --ram) and build/reg/<p>.html (gen_rcss.py on exp/regvm/mkimage.py); VARIANTS="base reg regl" adds
# more build/<dir>/ (regl: LOOPCOPY=2). Waits for a quiet machine first (1-minute load below MAXLOAD, default 2.5).
cd "$(dirname "$0")/../.."
R=${1:-3}; shift; PROGS=${@:-primes collatz func_recursion fib fizzbuzz gcd is_prime nested_loops cond_logic else_if_long}
until [ "$(awk -v m=${MAXLOAD:-2.5} '{print ($1 < m)}' /proc/loadavg)" = 1 ]; do sleep 10; done
echo "start $(date +%T) load $(cut -d' ' -f1-3 /proc/loadavg)"
for p in $PROGS; do
  echo "== $p"
  node ../shared/js/ab.js -r $R -p runMs "IMG={}.json POLL=30 node machine/halttime.js {}.html 300" $(for v in ${VARIANTS:-base reg}; do echo build/$v/$p; done)
done
echo "end $(date +%T) load $(cut -d' ' -f1-3 /proc/loadavg)"
