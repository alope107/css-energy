#!/bin/bash
# usage: fetch.sh <ref> <path> <outdir>
ref=$1; f=$2; out=$3; n=$(echo $f | tr / _)
for i in 1 2 3 4; do
  curl -s "https://chromium.googlesource.com/chromium/src/+/$ref/$f?format=TEXT" -o $out/$n.b64
  if base64 -d $out/$n.b64 > $out/$n 2>/dev/null && [ -s $out/$n ]; then rm $out/$n.b64; echo "$n $(wc -l < $out/$n)"; exit 0; fi
  sleep 1
done
echo "FAIL $f"
