#!/bin/bash
# tools/smoke.sh [count] : build a PLAIN page per scene into out/ and run the regression checks; exit 1 if any fails.
# Run from the repo root. MS = ms per scene (default 12000). Takes ~3 minutes at 16 bodies.
#   smoke.js       physics sanity per scene (penetration, overlap, speed, everything asleep at the end)
#   statcheck.py   static: every scene declares every body's start state; boolean gates only on 0/1 flags
#   floatcheck.js  no body starts (or stays) asleep in mid-air, on load and after switching to each scene
#   grabtest.js    dragging one body doesn't move any other
#   overlaycheck.js the grab overlay (ring, pin, tether) follows the drag
N=${1:-16}; set -o pipefail; mkdir -p out; rc=0
for sc in tower rain stack; do
  SCENE=$sc COUNTS=$N PLAIN=1 python3 src/build3d.py out/smoke_${N}_${sc}.html 2>/dev/null || { echo "BUILD FAIL $sc"; rc=1; continue; }
  node tools/smoke.js out/smoke_${N}_${sc}.html ${MS:-12000} || rc=1
  python3 tools/statcheck.py out/smoke_${N}_${sc}.html || rc=1
done
node tools/floatcheck.js out/smoke_${N}_tower.html out/smoke_${N}_rain.html || rc=1
node tools/overlaycheck.js out/smoke_${N}_tower.html || rc=1
# (a spread-out field with no gravity, shaken awake: other bodies drift freely, so a leaked grab force shows)
SCENE=field FIELD_GAP=30 COUNTS=$N PLAIN=1 python3 src/build3d.py out/smoke_${N}_field.html 2>/dev/null || { echo "BUILD FAIL field"; rc=1; }
node tools/grabtest.js out/smoke_${N}_field.html || rc=1
exit $rc
