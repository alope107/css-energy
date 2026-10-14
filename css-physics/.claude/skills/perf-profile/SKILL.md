---
name: perf-profile
description: Measure where style-engine time goes in a rigid3d.css page, or whether a generator change made it faster. Use for any performance question, optimization attempt or "is X cheaper than Y" microbenchmark.
---
# Profiling rigid3d.css

Everything runs in headless Chromium through `tools/` (run from the repo root; `CHROME=` picks the browser). Timings are noisy, so compare variants relatively, with interleaved repeats.

## 1. Whole-page numbers
- Step cost: `node tools/tr.js out/A.html,out/B.html 1500 1500`. `bigmed` is the median of the big (physics) passes; a live page runs about 2 physics passes per frame. `V=1` lists the top trace events.
- Comparing variants: `bash tools/bench.sh 3 out/A.html out/B.html` (min of medians), or `node ../shared/js/ab.js -p bigmed 'node tools/tr.js {} 1500 1500' out/A.html out/B.html` for the ratio to A per rotated round with its spread. Run A against itself once to see the noise floor before reading a few percent as a win.
- What the user feels: `node tools/perf3.js out/A.html` (chaos fps, settle time, idle, drag, hold).

## 2. Attribute one physics step
1. Build PLAIN: `SCENE=tower COUNTS=48 PLAIN=1 python3 src/build3d.py out/p48.html`
2. Freeze the state at an interesting moment (gates stay fixed, every prop recomputes each frame):
   `node tools/freeze3.js out/p48.html 4000 FZ out/p48.html` → `out/FZ_p48.html`
3. Strip gate families: `python3 tools/ablate.py out/FZ_p48.html pairs='--(tcp|np|p\d+_\d+(uA|uB|ov))' ac='--ac\d' nw='--nw' all=.`
4. `node tools/tr.js out/FZ_p48.html,out/FZ_p48_pairs.html,... 1500 1500`. The deltas overlap (removing a family changes later gates).
5. Active gate counts: `node tools/gates.js out/p48.html 48 1500,3000`
6. Where a pass's time goes, without double-counting nested events: `SELF=1 node tools/traceagg.js out/FZ_p48.html` (self time on the main thread).

## 3. Microbenchmarks (is construct X cheaper than Y?)
- Write a tiny page: an element animated by `@keyframes t{from{--t:0}to{--t:1000}}` on an ancestor, and the construct under test repeated 1,000–5,000× on one element. Template: `experiments/costs/mk2.py`.
- `node tools/stylebench.js a.html,b.html 500 1500` → median style pass. Divide the difference by the count to get the cost per construct.
- Inputs must change every frame (derive them from `--t`), or Chrome caches the result.
- Watch for `display:none` subtrees: they aren't styled at all. Use `position:absolute;width:0;height:0;overflow:hidden`.

## 4. Before claiming a win
- `bash tools/smoke.sh 16` must pass, and settling (`node tools/sleepy.js out/p32.html 32 25`) must not regress.
- Add the numbers to `docs/BENCHMARKS.md` (and to `docs/HISTORY.md` if the idea failed).
