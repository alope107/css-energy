#!/bin/bash
# buildrev.sh <rev> : extract HarfBuzz <rev> and build drv_<rev>
W=/tmp/claude-1000/-workspaces-css-energy/b9afb157-4cf4-4d73-85e1-e202289f19ff/scratchpad/work/07
H=$W/../../src/harfbuzz
r=$1; d=$W/bis/$r; mkdir -p $d
[ -x $W/drv/drv_$r ] && exit 0
git -C $H archive $r src | tar -x -C $d
export PYTHONPATH=$W/py
python3 -m ziglang c++ -O2 -DNDEBUG -fno-exceptions -fno-rtti -I$d/src -c $d/src/harfbuzz.cc -o $d/hb.o 2>&1 | grep error | head -3
python3 -m ziglang c++ -O2 -DNDEBUG -fno-exceptions -fno-rtti -I$d/src $W/drv/drv.cc $d/hb.o -o $W/drv/drv_$r -lpthread 2>&1 | grep error | head -3
rm -rf $d/src
ls $W/drv/drv_$r
