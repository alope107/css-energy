# Benchmarks

Every number below was measured in **headless Chromium 141** (Playwright's build) on the Claude sandbox, a **2-core** Linux VM with software GL, unless marked 153 (`@sparticuz/chromium@153.0.0`). Absolute times are slow and noisy there: expect a desktop to be roughly 2–3× faster, and re-measure before trusting small differences. Run interleaved repeats (`tools/bench.sh`) and compare **relative** numbers.

† = from an earlier session's summary (raw logs gone). Everything else is from the last session and reproducible with the named script.

## How to measure (tools/)

| Script | Measures |
|---|---|
| `tr.js page[,page2] [delayMs] [durMs]` | CDP trace: median `UpdateLayoutTree` (style pass) ms, "bigmed" (median of the big passes), fps, layout/paint per frame. `V=1` prints the top trace events; `HOVER=1` / `PRESS=1` add pointer state. |
| `bench.sh reps page…` | Min-of-medians over interleaved repeats of `tr.js`. Use this to compare variants. |
| `perf3.js page…` | User-level: chaos fps for the first 6 s, time to settle (all asleep), idle fps, drag fps (tower top box), hold fps. |
| `freeze3.js src ms prefix tgt…` | Snapshot the state registers at `ms` and bake them into copies of `tgt` as constants with a tiny wobble, so every dependent prop recomputes every frame while all gates stay fixed. **The way to profile one physics step** without the scene evolving. `ONLYAWAKE=1` keeps sleepers frozen. |
| `freezegrab.js` | Same, while holding a grab. |
| `traceagg.js page delay dur` | Aggregates all trace events (blink, cc, animation) by total time. |
| `gates.js page N ms,ms…` | Counts active pair gates (np, tcp, ov, uA) over time. |
| `cen.js`, `grabcen.js` | Census of matched gated blocks by category, with a cost model. |
| `sleepy.js page N [s]` | Asleep count every 0.5 s. |
| `ablate.py page NAME=REGEX…` | Copies of a page with families of gated blocks removed (for cost attribution). |
| `sanity3.js`, `smoke.js` | Physics sanity (floor penetration, sphere overlap, speed, sleepers); `smoke.js` exits 1 on failure. |
| `stylebench.js page…` | Median style pass for microbenchmark pages (also used for experiments). |
| `compframes.js page…` | Compositor frames vs main-thread frames (DrawFrame vs BeginMainFrame). |

**Ablation recipe** (how the per-category costs below were found):
1. Build a PLAIN page.
2. Freeze it at the moment of interest with `freeze3.js`.
3. Make copies with categories of `@container` blocks stripped (`tools/ablate.py`).
4. Compare the big-pass medians.

Removing gate families changes downstream gates, so the deltas overlap and don't sum exactly.

---

## 1. Engine performance over time

### Phase 2 optimization, 32 bodies (old → new)†

| Metric | Old | New |
|---|---|---|
| Load | 2.9 s | 0.8 s |
| Idle style per frame | 13.6 ms | 1.0 ms |
| Hover style per frame | 28.8 ms | 2.0 ms |
| Rain chaos | 6–9 fps | 8–13 fps |
| Drag | 11 fps | 14 fps |

Also from that session: 24 bodies, drag 18 fps; 48 bodies, drag 4–5 fps and hold 8 fps; 64-body page load 3.6 s.

### perf3.js, the current engine (tower scene)

| Page | Chaos fps (1 s windows) | Settled | Idle fps | Drag fps | Hold fps |
|---|---|---|---|---|---|
| 48 (24 boxes, 24 spheres) | 12 10 8 7 9 9 | 12.5 s | 61 | 5 | 9 |
| 64 (32 + 32) | 8 6 5 6 6 6 | not in window | 6 | 3 | 4 |
| 48 (24 + 24), after sleep fix | 7 7 5 5 6 6 | 23 s | 61 | 4 | 4 |
| 48 (4 boxes, 44 spheres) | 10 10 8 9 8 11 | 12 s | 61 | 7 | 11 |
| 64 (4 boxes, 60 spheres) | 7 6 6 6 6 6 | not in window | 7 | 4 | 5 |

The two 48 mixed rows differ partly because of the scene. The sleep fix makes upper layers fall instead of floating, so there are more contacts early. The noisy VM also contributes.

### One physics step, frozen pile (`freeze3.js` + `tr.js` bigmed)

| Page | Step |
|---|---|
| 48 mixed, frozen at 2.5 s / 4 s / 8 s | 92 / 97 / 92 ms (other runs on a busier VM: 118–155 ms) |
| 48 sphere-heavy (4 boxes), frozen at 3 s / 8 s | 52 / 39 ms |
| 32 mixed, frozen at 6 s | 23 ms |
| 16 mixed, frozen at 6 s (mostly asleep) | 4.5 ms |

Live, at 48 bodies during a pile-up: a 100–260 ms style pass and 2 passes per frame (traced: 11 passes, 1,148 ms total). Paint is about 25 ms per frame at 48 bodies; layout is under 1 ms.

### Ablation of the frozen 48-body pile (≈92 ms step)

| Removed | Step | Implied cost |
|---|---|---|
| nothing | 92 ms | — |
| all pair-gated blocks (np, tcp, uA, uB, ov: 3,360 blocks) | 50 ms | pairs ≈ 42 ms |
| per-body awake blocks (`ac`, 144 blocks ≈ 5,088 decls, about 106 per body) | 42 ms | ≈ 50 ms (overlaps with pairs) |
| tcp only | 71 ms | |
| np only | 64 ms | |
| uA/uB only | 80 ms | |
| plane groups (nw) | 79 ms | |
| every gated block | 11.8 ms | base (ungated, registers, render) |

Active gates in that pile (`gates.js`): about 60 near pairs (np), about 15 touching (tcp), 3–4 box/box overlaps.

Declarations per gate family at 48 bodies (static count): tcp 53,106, uB 34,107, uA 34,065, np 31,914, ov 6,600, ac 5,088. That is about 141 per pair (≈47 tcp + 28 np + 30 uA + 30 uB + 6 ov) and about 106 per body. The generator reports 174,441 props, 1,320 groups, 51 levels and 632 registers at 48. With 4 boxes and 44 spheres: 100,441 props. At 64 bodies: 307,002 props, 67 levels, 840 registers, 31.7 MB CSS.

### N² costs, all awake, 48 bodies

| Item | Cost |
|---|---|
| 1,128 broadphase near tests `calc(sign(max(0, R − hypot(dx, dy, dz))))` | ≈ 14 ms per step, about 12.5 µs each (microbenchmark: 13–16 ms vs 1 ms baseline) |
| Pair rules with present owner name, style() false | ≈ 3.5 µs each, × 3,360 ≈ 12 ms |
| Together | ≈ 28% of a step; ≈ 50 ms at 64; ≈ 200 ms at 128 (projected) |

### Timestep vs settling (32 bodies, `sleepy.js`, 3 runs in parallel)

| RATE | Result |
|---|---|
| 90 | fully asleep at about 16 s |
| 60 | 20–22 of 32 asleep after 25 s; jitters |
| 45 | 16 of 32 asleep after 25 s |

### Sleep-start fix check (48, tower)

All 48 bodies asleep by about 30 s and nothing floating (screenshots before and after). `smoke.sh 16` passes all three scenes: floor penetration ≤ 0.35 px, sphere overlap ≤ 0.09 px, all asleep.

---

## 2. Style engine cost model (microbenchmarks)

Pages: `experiments/costs/mk*.py` → `tools/stylebench.js`. Inputs come from an animated `--t`. Costs are per pass in Chromium 141.

| Pattern (1,000–2,000 props on one element) | Cost per prop |
|---|---|
| registered `<number>`, constant `5` | 0.62 µs |
| registered `calc(5 * 2 + 1)` (no var) | 1.3 µs |
| registered `calc(var(--t) * k)` | 2.0–2.4 µs |
| unregistered `--x: 5` | 0.25 µs |
| unregistered `calc(var(--t) * k)` (substitution only) | 0.83 µs |
| registered, 1 var + 10 literal ops | 6.2 µs (≈0.35 µs per op+literal) |
| registered, 5 vars, about 10 ops | 5.0 µs |
| each extra `+ var(--u)` (registered) | +0.53 µs (substitution about 0.29, parse/eval about 0.24) |
| each extra `* 1.0001` | +0.36 µs |
| each extra nested paren | +0.12 µs |
| each `max(var(--u), 1)` | +1.1 µs |
| chain `--b{i}: calc(var(--b{i−1}) + 1)` | 2.7 µs |
| `if(style(--t: 5): 1; else: calc(…))` | 4.2 µs |
| 20 props `calc(var(--x) * a + b)` per element, 200 elements | 2.4 µs per prop |
| Chromium 153: same base / 20-var / 20-literal pages | 2.13 / 10.6 / 8.2 ms (141: 2.1 / 12.6–12.8 / 9.1–9.2 ms), ≈10–15% faster |

**Inheritance depth:** 2,000 inherited registered props set at the top of a 50-deep chain, with each level adding 1, cost 4.86 ms. The non-inherited variant and the root-set variant cost 4.86 and 4.77 ms. No per-level copy cost.

**Container-query gating** (one element, an animated parent):

| Rules | Cost |
|---|---|
| 10,000 or 50,000 `@container zzK {…}` with the name absent | ≈ 0 (0.18–0.21 ms vs 0.19 ms base) |
| 50,000 with the outer name present and the inner absent | ≈ 0 |
| 20,000 three-deep nests (present, present, absent) | ≈ 0 |
| 2,000 three-deep, all present (declaring the same prop) | ≈ 0 (container not restyling) |
| 5,000 `@container pres style(--gK: 7)` (name present, false, container restyles each frame) | 17.2–17.9 ms ⇒ **3.5 µs per rule** |
| the same 5,000 with the name absent | 0.66–0.86 ms ⇒ about 0.1 µs per rule |

**Paused-animation evaluator:** 200 elements × `animation-delay: calc(var(--x) * -1s)` paused, 20 props per keyframe set: 79 ms (one animation) and 288 ms (two, composited with add), against 12–15 ms for the calc equivalent. Roughly 400 µs per element.

## 3. Variable fonts as compute (`experiments/fonts/`)

Font builder: `vf.py` (fontTools). Axes run −16384…16384, so the CSS value equals the F2DOT14 coordinate.

**Correctness (`t1.py`, Chromium 141).** `--o: 1ch` gives the HVAR advance of "0" and `1ic` the advance of U+6C34, both exact. `1ex` and `1cap` give MVAR `xhgt`/`cpht`, exact. A bilinear A·B region is exact (for example A=4096, B=12288 → 352 px as expected). All of this resolves at style time with no layout.

**Cost (`t2.py`: one font, 2 axes, distinct coordinates per element per frame):**

| Page | Style per pass | Per element |
|---|---|---|
| 100 elements, calc baseline (same inputs) | 2.1 ms | |
| 100, font + 1ch | 3.5 ms | |
| 100, font + 4 outputs | 4.3 ms | |
| 100, fixed coordinates (cached instances) | 1.8 ms | ≈ 0 extra (a cached instance is free) |
| 400, calc | 7.3 ms | 18 µs |
| 400, font + 1ch | 13.6 ms | 34 µs (≈15–20 µs per new instance) |
| 400, font + 4 outputs | 15.3 ms | 38 µs |

There were max spikes to 100–150 ms, possibly font cache purges.

**Width scaling (`t3.py`: the parent sets NA axes, M children each pick a different font family and read 4 outputs; each output sums R random 1–2-axis regions):**

| NA axes | R regions/output | M | Style per pass | Per child instance |
|---|---|---|---|---|
| 8 | 4 | 100 | 3.5 ms | 35 µs |
| 64 | 4 | 100 | 8.1 ms | 81 µs |
| 64 | 200 | 100 | 17.1 ms | 170 µs |
| 256 | 200 | 100 | 84 ms | 840 µs |
| 64 | 2,000 | 50 | 41.6 ms | 830 µs |

That's about 0.1 µs per region term at 64 axes. Region records span every axis, so the cost grows with regions × axes.

**From a related project** (HarfBuzz/avar2 work, another conversation): new-instance cost about 50 µs; 784-axis → 64-glyph HVAR layer 2.5 ms; chained 8-bit lookups through containers 100 µs at depth 10 and 770 µs at depth 300; GSUB about 25 ns per glyph per lookup and about 16k micro-steps per shaping; a Fontations `user_to_normalized` O(axes³) slowdown avoided with NO_VARIATION_INDEX and per-output VarData; the `font` shorthand resets `font-variation-settings`.

## 4. Compositor interpolation (`experiments/compositor/`, `tools/compframes.js`)

| Page | Main-thread frames/s | Compositor draws/s |
|---|---|---|
| synthetic, 40 3D boxes, heavy style (≈110 ms per pass), `transition: transform 300ms` | 8.3 | **59** |
| same without the transition (≈62 ms per pass) | 15.7 | 15.7 |
| real engine, 48 bodies, no transition | 2.7 | 3.0 |
| real engine, 48 bodies, `.bw,.bd{transition:transform 250ms linear}` | 2.7 | 28.7 |
| same, 700 ms | — | 36 |

Transitions fire even though the pose comes from scroll-driven animations. The extra style cost is about 0.17 ms per body per main frame (40 boxes: 45.3 vs 38.2 ms per pass). The sandbox is CPU-starved (2 cores, software GL); a GPU machine should reach 60.

## 5. Process parallelism (`experiments/iframes/`)

12,000-element heavy child pages, about 17 ms per pass each:

| Setup | Renderer processes doing style | Passes/s |
|---|---|---|
| 1 iframe, same origin | 1 | 58 |
| 2 iframes, same origin | 1 | 56 total |
| 2 sandboxed iframes, `file://` or HTTP, with or without `--enable-features=IsolateSandboxedIframes` | 1 | 57–60 total |
| 2 cross-site iframes (127.0.0.1 and 127.0.0.2, parent on localhost) | **2** | **55 each** |

## 6. Misc

- `ident()` / `var(ident(…))`: unsupported in 141 and 153 (`experiments/ident/`).
- avar2: Chrome 148+ only.
- A registered number survives `var()` with **6 significant digits**, which is why the digests pack 6 bodies per decimal word.
