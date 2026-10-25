#!/bin/bash
# tools/smoke.sh [count] : build a PLAIN page per scene into out/ and run the regression checks; exit 1 if any fails.
# Run from the repo root. MS = ms per scene (default 12000). Takes ~4.5 minutes at 16 bodies.
#   smoke.js       physics sanity per scene (penetration, overlap, speed, and that the solver runs: something moves)
#   statcheck.py   static: every scene declares every body's start state; boolean gates only on 0/1 flags
#   floatcheck.js  no body starts (or stays) asleep in mid-air, on load and after switching to each scene
#   grabtest.js    dragging one body doesn't move any other
#   overlaycheck.js the grab overlay (ring, pin, tether) follows the drag
#   touchcheck.js  touch dragging on a phone-sized touch screen: grab, follow, drop on release (Chromium only)
#   posecheck.js   what's drawn follows each body's pose (rotation, shadow, face colours) on every frame
#   xcheck.js      BROWSER=firefox|webkit|safari: every value on every level against Chromium's, on a state that
#                  browser reached
# BROWSER=firefox|webkit|safari runs them in that browser (safari: the Mac host's, ../shared/js/safari.js); NOIF=1 on
# copies with if( renamed iff( (a browser without if(): Firefox, Safari before 27.x).
# The builds and checks are make targets (Makefile): a check runs only when its page, its harness or the browser
# changed since it last passed here, and says "up to date" otherwise. RERUN=1 runs them all.
exec make -k -s smoke N=${1:-16}
