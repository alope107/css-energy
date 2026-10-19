#!/bin/bash
# fetch_tree.sh <branch-ref> <dest> <dir>...  — gitiles +archive per directory, extracted under dest/<dir>
ref=$1; dest=$2; shift 2
for d in "$@"; do
  mkdir -p "$dest/$d"
  curl -sf "https://chromium.googlesource.com/chromium/src/+archive/$ref/$d.tar.gz" | tar xzf - -C "$dest/$d" || echo "FAILED $d"
done
