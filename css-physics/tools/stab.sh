#!/bin/bash
# tools/stab.sh tag [count] [gen] : build a PLAIN page per scene into out/ and run the stability check on each
# (run from the repo root; MS=ms per scene, default 16000)
T=$1; N=${2:-16}; G=${3:-gen3d.py}
mkdir -p out
for sc in tower rain stack; do GEN=$G SCENE=$sc COUNTS=$N PLAIN=1 python3 src/build3d.py out/st_${T}_${sc}.html 2>/dev/null; done
for sc in tower rain stack; do node tools/sanity3.js out/st_${T}_${sc}.html ${MS:-16000}; done
