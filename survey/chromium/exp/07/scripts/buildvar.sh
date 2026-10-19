#!/bin/bash
# buildvar.sh <name> <patch-args...> : copy hbc, apply patchvar.py variants, build drv_<name>
W=/tmp/claude-1000/-workspaces-css-energy/b9afb157-4cf4-4d73-85e1-e202289f19ff/scratchpad/work/07
n=$1; shift; d=$W/var/$n; rm -rf $d; mkdir -p $d; cp -r $W/hbc/src $d/
for v in "$@"; do python3 $W/scripts/patchvar.py $d/src $v || exit 1; done
export PYTHONPATH=$W/py
python3 -m ziglang c++ -O2 -DNDEBUG -fno-exceptions -fno-rtti -I$d/src -c $d/src/harfbuzz.cc -o $d/hb.o 2>&1 | grep error | head -3
python3 -m ziglang c++ -O2 -DNDEBUG -fno-exceptions -fno-rtti -I$d/src $W/drv/drv.cc $d/hb.o -o $W/drv/drv_$n -lpthread 2>&1 | grep error | head -3
rm -rf $d/src; ls $W/drv/drv_$n
