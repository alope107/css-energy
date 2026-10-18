---
name: perf-profile
description: Measure where style-engine time goes in a rigid3d.css page, or whether a generator change made it faster. Use for any performance question, optimization attempt or "is X cheaper than Y" microbenchmark.
---
# Profiling rigid3d.css

Everything runs in headless Chromium through `tools/`, from the repo root. Tool index and noise floor:
`docs/BENCHMARKS.md` ("How to measure", "Noise"). Compare variants relatively, with interleaved repeats.

## 1. Whole-page numbers
- Step cost: `node tools/tr.js out/A.html,out/B.html 1500 1500`. `bigmed` is the median of the big (physics) passes;
  a live page runs about 2 physics passes per frame.
- Variants: `bash tools/bench.sh 3 out/A.html out/B.html`, or `node ../shared/js/ab.js -p bigmed 'node tools/tr.js {}
  1500 1500' out/A.html out/B.html` for per-round ratios with their spread. Run A against itself before reading a few
  percent as a win.
- What the user feels: `node tools/perf3.js out/A.html`.

## 2. Attribute one physics step
1. `SCENE=tower COUNTS=48 PLAIN=1 python3 src/build3d.py out/p48.html`
2. Freeze (gates fixed, every prop recomputes each frame): `node tools/freeze3.js out/p48.html 4000 FZ out/p48.html`
   → `out/FZ_p48.html`
3. Strip gate families: `python3 tools/ablate.py out/FZ_p48.html pairs='--(tcp|np|p\d+_\d+(uA|uB|ov))' ac='--ac\d' nw='--nw' all=.`
4. `node tools/tr.js out/FZ_p48.html,out/FZ_p48_pairs.html,... 1500 1500`. Deltas overlap; frozen bases are 2–3× live.
5. Active gates: `node tools/gates.js out/p48.html 48 1500,3000`. Self time per event: `SELF=1 node tools/traceagg.js out/FZ_p48.html`.

## 3. Microbenchmarks (is construct X cheaper than Y?)
- A tiny page: `@keyframes t{from{--t:0}to{--t:1000}}` on an ancestor, the construct repeated 1,000–5,000× on one
  element. Template: `experiments/costs/mk2.py`.
- `node tools/stylebench.js a.html,b.html 500 1500` → median style pass; divide the difference by the count.
- Inputs must change every frame (derive them from `--t`), or Chrome caches the result.
- `display:none` subtrees aren't styled; use `position:absolute;width:0;height:0;overflow:hidden`.
- Light pages are inflated by frequency scaling: compare them only with each other.

## 4. Before claiming a win
- `bash tools/smoke.sh 16` passes, and settling (`node tools/sleepy.js out/p32.html 32 25`) doesn't regress.
- Put the numbers in `docs/BENCHMARKS.md` (and the idea in `docs/HISTORY.md` if it failed).
