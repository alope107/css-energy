#!/bin/bash
# tools/smoke.sh [count] : build a PLAIN page per scene into out/ and run tools/smoke.js on each; exit 1 if any fails.
# Run from the repo root. MS = ms per scene (default 12000). Takes ~1 minute at 16 bodies.
N=${1:-16}; set -o pipefail; mkdir -p out; rc=0
for sc in tower rain stack; do
  SCENE=$sc COUNTS=$N PLAIN=1 python3 src/build3d.py out/smoke_${N}_${sc}.html 2>/dev/null || { echo "BUILD FAIL $sc"; rc=1; continue; }
  node tools/smoke.js out/smoke_${N}_${sc}.html ${MS:-12000} || rc=1
done
exit $rc
