#!/bin/bash
# usage: fetch.sh <ref> <path>   ref = main or 8010
W=/tmp/claude-1000/-workspaces-css-energy/b9afb157-4cf4-4d73-85e1-e202289f19ff/scratchpad/work/08/agentA
ref=$1; p=$2
if [ "$ref" = main ]; then r=main; else r=refs/branch-heads/$ref; fi
out=$W/dl/$ref/$p
mkdir -p "$(dirname "$out")"
[ -s "$out" ] && exit 0
curl -sf "https://chromium.googlesource.com/chromium/src/+/$r/$p?format=TEXT" | base64 -d > "$out" || { echo "FAIL $ref $p"; rm -f "$out"; }
