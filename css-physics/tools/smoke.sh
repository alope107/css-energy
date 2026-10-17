#!/bin/bash
# tools/smoke.sh [count] : build a PLAIN page per scene into out/ and run the regression checks; exit 1 if any fails.
# Run from the repo root. MS = ms per scene (default 12000). Takes ~3 minutes at 16 bodies.
#   smoke.js       physics sanity per scene (penetration, overlap, speed, everything asleep at the end)
#   statcheck.py   static: every scene declares every body's start state; boolean gates only on 0/1 flags
#   floatcheck.js  no body starts (or stays) asleep in mid-air, on load and after switching to each scene
#   grabtest.js    dragging one body doesn't move any other
#   overlaycheck.js the grab overlay (ring, pin, tether) follows the drag
# The builds and checks are make targets (Makefile): a check runs only when its page, its harness or the browser
# changed since it last passed here, and says "up to date" otherwise. RERUN=1 runs them all.
exec make -k -s smoke N=${1:-16}
