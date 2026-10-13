# Benchmarks

Every number below was re-measured on **2026-10-13** in **headless Chromium 153.0.8010.12** (Chrome for Testing, from the Playwright 1.63 image), driven by Playwright 1.64, in the project devcontainer: **arm64, 8 vCPUs** (Docker Desktop, linuxkit kernel), no GPU. Benchmarks that were measured on code or pages that no longer exist were removed at the same time; [HISTORY.md](HISTORY.md) still narrates them.

Earlier versions of this file were measured on a 2-core VM in Chromium 141, so its numbers are not comparable with these. Timings are noisy: run interleaved repeats (`tools/bench.sh`) and compare **relative** numbers on one machine.

## How to measure (tools/)

| Script | Measures |
|---|---|
| `tr.js page[,page2] [delayMs] [durMs]` | CDP trace: median `UpdateLayoutTree` (style pass) ms, "bigmed" (median of the big passes), fps, layout/paint per frame. `V=1` prints the top trace events; `HOVER=1` / `PRESS=1` add pointer state. |
| `bench.sh reps page…` | Min-of-bigmed over interleaved repeats of `tr.js`. Use this to compare variants. |
| `perf3.js page…` | User-level: chaos fps for the first 6 s, time to settle (all asleep), idle fps, drag fps (tower top box), hold fps. |
| `freeze3.js src ms prefix tgt…` | Snapshot the state registers at `ms` and bake them into copies of `tgt` as constants with a tiny wobble, so every dependent prop recomputes every frame while all gates stay fixed. **The way to profile one physics step** without the scene evolving. `ONLYAWAKE=1` keeps sleepers frozen. |
| `freezegrab.js` | Same, while holding a grab. |
| `traceagg.js page delay dur` | Aggregates all trace events (blink, cc, animation) by total time. |
| `gates.js page N ms,ms…` | Counts active pair gates (np, tcp, ov, uA). The waits are cumulative. |
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
4. Compare the big-pass medians with `bench.sh`.

Removing gate families changes downstream gates, so the deltas overlap and don't sum exactly.

**Freezing at a wall-clock time depends on the frame rate.** The engine advances one step per physics pass, so a faster machine is further into the simulation at the same `ms`. The 8 s snapshots below are of a mostly settled pile; on the old 2-core VM they were still mid-collapse.

---

## 1. Engine performance

Pages: `COUNTS=<n> PLAIN=1 python3 src/build3d.py out/p<n>.html` (tower scene, half boxes and half spheres); `NBOX_FIX=4` for 4 boxes and the rest spheres.

### Build

| Bodies | Props | Groups | Levels | Registers | PLAIN CSS | Build time |
|---|---|---|---|---|---|---|
| 16 | 20,986 | 184 | 19 | 216 | 2.5 MB | 2 s |
| 32 | 79,131 | 624 | 35 | 424 | 9.3 MB | 6 s |
| 48 | 174,441 | 1,320 | 51 | 632 | 20.5 MB | 13 s |
| 48 (4 boxes) | 100,441 | 1,320 | 51 | 632 | 10.1 MB | 8 s |
| 64 | 307,002 | 2,272 | 67 | 840 | 36.1 MB | 26 s |
| 64 (4 boxes) | 172,042 | 2,272 | 67 | 840 | 17.0 MB | 14 s |

The published site (`tools/make_site.sh`, counts 8–64, minified) builds in 26 s; its 64-body CSS is 32.5 MB in three files.

### perf3.js (tower scene)

| Page | Chaos fps (1 s windows) | Settled | Idle fps | Drag fps | Hold fps |
|---|---|---|---|---|---|
| 16 (8 + 8) | 60 61 60 62 62 62 | 6 s | 61 | 61 | 61 |
| 48 (24 boxes, 24 spheres) | 14 12 12 12 13 17 | 9.5 s | 61 | 14 | 17 |
| 48 (4 boxes, 44 spheres) | 22 19 24 37 55 62 | 6 s | 61 | 31 | 27 |
| 64 (32 + 32) | 10 9 8 8 8 8 | not within 26 s | 8 | 7 | 8 |
| 64 (4 boxes, 60 spheres) | 15 12 12 12 14 16 | 17 s | 61 | 23 | 25 |

The 64 mixed page is still awake when the idle, drag and hold windows run, so those three are pile-up numbers.

### One physics step, frozen (`freeze3.js` + `bench.sh 3`, bigmed)

| Page | Step |
|---|---|
| 48 mixed, frozen at 2.5 s / 4 s / 8 s | 37.2 / 36.8 / 25.4 ms |
| 48 sphere-heavy (4 boxes), frozen at 3 s / 8 s | 15.3 / 7.1 ms |
| 32 mixed, frozen at 6 s | 5.4 ms |
| 16 mixed, frozen at 6 s (asleep) | 3.8 ms |

**Live, 48 bodies at 2.5 s** (`V=1 tr.js out/p48.html 2500 3000`): a 55 ms style pass (median), 2 passes per frame, 9 fps. Layout is 0.33 ms and paint 0.43 ms per frame.

**Idle, 32 bodies, all asleep** (`tr.js out/p32.html 20000 2000`): 2 passes per frame of about 2 ms each, 4.6 ms of style per frame at 61 fps. With the pointer over the arena (`HOVER=1`): 3.6 ms per frame.

### Ablation of the frozen 48-body pile (frozen at 4 s, ≈37 ms step)

| Removed | Step | Implied cost |
|---|---|---|
| nothing | 37.1 ms | — |
| all pair-gated blocks (np, tcp, uA, uB, ov: 3,360 blocks) | 22.3 ms | pairs ≈ 15 ms |
| per-body awake blocks (`ac`, 144 blocks, 5,088 decls) | 10.5 ms | ≈ 27 ms (overlaps with pairs) |
| tcp only (1,130 blocks) | 30.0 ms | ≈ 7 ms |
| np only (1,403 blocks) | 26.0 ms | ≈ 11 ms |
| uA/uB only (552 blocks) | 34.0 ms | ≈ 3 ms |
| plane groups (nw, 192 blocks) | 34.0 ms | ≈ 3 ms |
| every gated block (4,014) | 6.1 ms | base (ungated, registers, render) |

Active gates in that pile (`gates.js out/p48.html 48 2500,1500,4000`, i.e. at 2.5 s, 4 s and 8 s):

| Time | np | tcp | ov | uA |
|---|---|---|---|---|
| 2.5 s | 64 | 16 | 4 | 2 |
| 4 s | 62 | 17 | 4 | 1 |
| 8 s | 41 | 11 | 2 | 1 |

Declarations per gate family at 48 bodies (static count, brace-matched like `ablate.py`):

| Family | Blocks | Declarations |
|---|---|---|
| tcp | 1,130 | 53,106 |
| np | 1,403 | 31,914 |
| uA | 276 | 34,065 |
| uB | 276 | 34,107 |
| ov | 275 | 6,600 |
| ac | 144 | 5,088 |
| nw | 192 | 5,376 |
| other | 318 | 4,179 |

That is about 141 declarations per pair (≈47 tcp + 28 np + 30 uA + 30 uB + 6 ov) and about 106 per body.

### N² costs, all awake, 48 bodies

| Item | Cost |
|---|---|
| 1,128 broadphase near tests `calc(sign(max(0, R − hypot(dx, dy, dz))))` | ≈ 3.3 ms per step, about 2.9 µs each (`mk_flags.py`: 5.51 vs 2.26 ms) |
| Pair rules with present owner name, style() false | ≈ 0.89 µs each (§2), × 3,360 ≈ 3.0 ms |
| Together | ≈ 6.3 ms, about 17% of the 37 ms frozen step. *(projected)* ≈ 11 ms at 64 bodies, ≈ 45 ms at 128 |

### Timestep vs settling (32 bodies, `sleepy.js … 32 25`, one at a time)

| RATE | Result |
|---|---|
| 90 (default) | all 32 asleep at 3 s |
| 60 | 27 of 32 asleep from 10.5 s to the end at 25 s; bodies 0–3 and 18 never sleep |
| 45 | 12–20 of 32 asleep throughout; 20 at 25 s |

### Settling and physics checks

- `sleepy.js out/p48.html 48 40`: all 48 asleep at 10 s, and they stay asleep.
- `smoke.sh 16` passes all three scenes:

| Scene | Frames in 12 s | Floor penetration | Sphere overlap | vmax | Asleep |
|---|---|---|---|---|---|
| tower | 372 | 1.15 px | 3.06 px | 849 | 16/16 |
| rain | 697 | 0.30 px | 0.02 px | 812 | 16/16 |
| stack | 719 | 0.35 px | 0 px | 63 | 16/16 |

The tower's sphere overlap (3.06 px) is the closest any check comes to its limit (4 px).

---

### The sparse regime (field scene, 2026-10-13)

`SCENE=field` packs every body at rest on the floor (`FIELD_GAP` apart; `TRAY=2` doubles the floor for benchmarks), so the scene loads asleep. `tools/sparse.js page N c` drags the body nearest the tray centre in a circle for 3 s and reports the median style pass, fps and how many bodies woke.

| Page | Awake during the drag | Style pass | fps |
|---|---|---|---|
| 64, gap 6 (dense pile) | 13–25 | 45–55 ms | 8–10 |
| 64, gap 6, double tray | 15 | 35–43 ms | 11–13 |
| 64, gap 30, double tray (one body alone) | 1–2 | 15.7–16.7 ms | 24–26 |
| 96, gap 30, double tray | 4 | 38–41 ms | 10–11 |
| 32, gap 6 | 31 (the whole pile wakes) | 14–18 ms | 22–28 |

Frozen mid-drag (`BODY=k tools/freezegrab.js`), 64 bodies, `bench.sh`:

| Removed | dense pile, 13 awake | gap 30, 1 awake |
|---|---|---|
| nothing | 52.5 | 13.1 |
| all pair blocks | 32.3 | 9.0 |
| per-body awake blocks (`ac`) | 25.8 | — |
| sleeping-body blocks (`as`) | 50.8 | 12.4 |
| every gated block | 12.5 (5.1 with static registers: the freeze's wobble of all 840 registers is 7 ms) | 7.4 |

In the dense pile the awake cluster has about 90 near and 40 touching pairs: 20 ms of narrowphase and solves. In the one-body drag the 6,016 pair rules cost 4 ms (0.67 µs each, nearly all rejected by an absent owner name: the ancestor walk costs about 0.2 + 0.01 × depth µs in the engine).

### Spatial cells A/B (`CELLS=1`, 2026-10-13; see HISTORY.md)

| Page (field, gap 30, double tray, one body dragged) | Style pass, two runs |
|---|---|
| 64, all-pairs digest (default) | 15.7, 16.7 ms |
| 64, cells | 21.6, 23.1 ms |
| 64, cells + `BOOLQ` | 24.2, 21.8 ms |
| 64, cells + `BOOLQ` + unnamed deep rules (`OWNLEV=1`) | 29.0, 29.2 ms |
| 96, digest + `BOOLQ` | 42.7, 40.5 ms |
| 96, cells + `BOOLQ` | 57.7, 63.6 ms |

Frozen one-body drag at 64: digest 13.1 ms, cells 19.3; without the sleepers' blocks 12.4 / 14.3 (the cells' per-sleeper bookkeeping is 5 ms); without the name-nested near-test rules 18.4 (4,032 rules at 0.2 µs). Frozen tower chaos at 48 with one baked state: 37.5 (p48), 38.9 (digest rebuilt), 39.9 (cells), 38.3 (cells + BOOLQ), 37.3 (+ OWNLEV=1): within noise when everything is awake.

### 64 and 96 bodies, live (tower, 2026-10-13)

| Page | Style pass at 3 s | fps | Active gates at 3 s |
|---|---|---|---|
| 48 | 49–58 ms | 8–10 | np 63, tcp 15, ov 4 |
| 64 | 80–100 ms | 5–6 | np 117, tcp 27, ov 10 |
| 96 | 183 ms | 3.3 | nothing asleep for 24 s (a second trace crashed the renderer) |

Frozen at 3 s, 64 bodies: 59.6 ms; without pair blocks 32.3 (pairs ≈ 27 ms); without `ac` blocks 18.5; without any gated block 7.7. Hiding the faces saves 8 ms per live pass, hiding the bodies' internals 12 ms (the render at 64 is about 190 µs per body per pass). Owner names off (`OWNSET=`) changes nothing with everything awake (91 vs 80–90 ms). The world-AABB broadphase would keep 107 of 124 sphere-near pairs (`tools/bpcount.js`); 32 touch.

## 2. Style engine cost model (microbenchmarks)

Pages: `experiments/costs/mk*.py`, generated in a scratch directory, then `node tools/stylebench.js <pages> 500 1500`, three interleaved repeats; each number is the median of the three medians. Inputs come from an animated `--t`. "Per unit" subtracts a baseline page and divides by the count; the baseline is the empty page (`cq0.html`, 0.28 ms) unless the row says otherwise.

| Pattern (2,000 props on one element, `mk2.py`) | Style pass | Per prop |
|---|---|---|
| registered `<number>`, constant `5` | 3.43 ms | 1.57 µs |
| registered `calc(5 * 2 + 1)` (no var) | 4.20 ms (2.5–4.4, noisy) | 1.96 µs |
| registered `calc(var(--t) * k)` | 4.58 ms | 2.15 µs |
| unregistered `--x: 5` | 1.26 ms | 0.49 µs |
| unregistered `calc(var(--t) * k)` (substitution only) | 2.95 ms | 1.33 µs |
| registered, 1 var + 10 literal ops | 6.58 ms | 3.15 µs |
| registered, 5 vars, about 10 ops | 6.16 ms | 2.94 µs |
| chain `--b{i}: calc(var(--b{i−1}) + 1)` | 5.36 ms | 2.54 µs |
| `if(style(--t: 5): 1; else: calc(…))` | 5.52 ms | 2.62 µs |

| Extra token (1,000 props, `mk4.py`, vs `k_base` 3.41 ms) | Per token |
|---|---|
| each `+ j.5` literal (20 per prop) | +0.12 µs |
| each `+ var(--u)` (registered, 20 per prop) | +0.17 µs |
| each `* 1.0001` (20 per prop) | +0.13 µs |
| each nested paren (20 per prop) | +0.08 µs |
| each `max(var(--u), 1)` (10 per prop) | +0.33 µs |
| each `+ var(--u)` into an unregistered prop (20 per prop) | +0.10 µs |

Compared with the Chromium 141 numbers, expression tokens cost about a third as much, while the cheapest forms (a constant into a registered property) measured higher. The second effect is not understood; don't read small per-prop differences from this table.

**Inheritance depth** (`mk.py`): 2,000 inherited registered props set at the top of a 50-deep chain, with each level adding 1: 4.66 ms. Non-inherited: 4.48 ms. Set on the root: 5.75 ms. Still no per-level copy cost.

**Container-query gating** (`mk_gating.py`, one element, an animated parent):

| Rules | Style pass | Over baseline |
|---|---|---|
| none (`cq0`, `n0`, `sq0`) | 0.28–0.30 ms | — |
| 10,000 `@container zzK {…}` with the name absent | 4.37 ms | 4.1 ms (0.41 µs per rule) |
| 50,000 with the name absent | 6.97 ms | 6.7 ms (0.13 µs per rule) |
| 10,000 / 50,000 with the outer name present and the inner absent | 3.95 / 7.26 ms | 3.7 / 7.0 ms |
| 10,000 / 50,000 with two absent names | 3.90 / 7.24 ms | 3.6 / 7.0 ms |
| 20,000 three-deep nests (present, present, absent) | 4.55 ms | 4.3 ms |
| 20,000 three-deep nests (absent, present, present) | 5.08 ms | 4.8 ms |
| 2,000 three-deep, all present (declaring the same prop) | 1.81 ms | 1.5 ms |
| 5,000 `@container pres style(--gK: 7)` (name present, false, container restyles each frame) | 4.75 ms | 4.5 ms ⇒ **0.89 µs per rule** |
| the same 5,000 with the name absent | 1.00 ms | 0.7 ms ⇒ 0.14 µs per rule |

**Rule matching at scale** (`experiments/costs/mk_part.py`, `part_depth.py`, `part_order.py`, `part_styleform.py`; 24k rules on one element unless noted, baseline subtracted; 2026-10-13):

| Form | µs per rule |
|---|---|
| absent name, 3 named ancestors of 3 names | 0.09–0.13, linear to 300k rules (24k 2.3 ms, 100k 11 ms, 300k 38 ms) |
| absent name, D named ancestors of M names each | ≈ 0.2 + 0.6 ns × D × M (D=32, M=128: 2.1; D=100, M=32: 2.0; D=100, M=128: 8.2) |
| present name, no `style()` | 0.07–0.16 |
| present name + false `style(--g: 1)` | 0.56–0.74 (independent of depth and list length: found at the parent) |
| present name + `style(--g)` (true iff value ≠ initial), false / true | 0.40 / 0.41 |
| unregistered `style(--u: 1)` / `style(--u)` | 0.51 / 0.43 |
| unnamed `style()` false / true | 0.58 / 0.48 |
| range `style(--h > 9)` false / true; `8 < --h < 9`; bound `calc(var())` | 1.57 / 1.66; 2.24; 1.95 |
| `style(--x: var(--y))` (true) | 0.64 |
| `or` of 9 `style()` | 5.2 (0.58 per disjunct) |
| nested queries | inner first, short-circuit (outer true + inner false 0.63; outer false + inner true 1.27) |
| `and` | left to right, short-circuit (false and true 0.64; true and false 1.19) |
| outer present name, inner absent + `style()` (K such rules per pair) | 0.10 each |
| unregistered `calc(var(--t) * k)` / 4-branch `if()` producing an ident / 12-branch | 1.25 / 2.0 / 2.6 |

Feature support in 153 (`part_feat.py`): range style queries with literal, `var()` and `calc()` bounds, and ident equality `style(--cell: var(--cell2))` all work. `style(--x)` on a registered property is true iff the computed value differs from its initial value (`--h: 7` with initial 7 is false, `calc(1 - 1)` is false); on an unregistered one iff it is declared at all (`--u: 0` is true).

**Register readback floor** (`mk_regs.py`: 60 levels, R register elements with two view timelines each, 2R animations on one #LS-like element): R = 420: no timelines 1.6 ms; 7 moving registers 2.3 ms; all moving 2.4 ms (and the frame rate halves: ticking 840 timelines costs outside style); #LS split into one element per body 2.7 ms. R = 840: 3.0 / 5.2 / 10 ms. About 2 µs per static register element per pass; per-body readback elements don't help.

**Inherited custom properties down a deep chain** (`mk_inherit2.py`): 6,000 inherited registered properties declared at level 1 cost 7.1 ms at 8, 66 and 130 levels deep (at the root: 10 ms). No depth × properties term. An empty level costs about 15 µs per pass (66 levels 1.3 ms, 130 levels 2.1 ms).

**Absent container names are no longer free.** In Chromium 141, 50,000 absent-name rules cost nothing measurable (0.18–0.21 ms against a 0.19 ms base). Here they cost about 7 ms per pass, and the cost is not linear in the rule count. Gating by owner name still pays: a present name with a false `style()` costs about 6× an absent one. The engine has about 4,000 gated blocks at 48 bodies, so this overhead is small next to its step.

**Paused-animation evaluator** (`mk3.py`): 200 elements × `animation-delay: calc(var(--x) * -1s)` paused, 20 props per keyframe set. 21.5 ms with one animation and 55 ms (44–63, noisy) with two composited with add, against 6.5–7.2 ms for the calc equivalent and 4.1 ms for no props. That's about 87 µs per element, against 12–15 µs for calc. Still a dead end.

## 3. Variable fonts as compute (`experiments/fonts/`)

Font builder: `vf.py` (fontTools). Axes run −16384…16384, so the CSS value equals the F2DOT14 coordinate.

**Correctness (`t1.py` + `t1.js`).** `1ch` gives the HVAR advance of "0" and `1ic` the advance of U+6C34, both exact. `1ex` and `1cap` give MVAR `xhgt`/`cpht`, exact. A bilinear A·B region is exact (A=4096, B=12288 → 352 px). All of this resolves at style time with no layout.

**Cost (`t2.py`: one font, 2 axes, distinct coordinates per element per frame):**

| Page | 100 elements | 400 elements |
|---|---|---|
| calc baseline (same inputs) | 3.95 ms | 5.42 ms |
| font + `1ch` | 3.93 ms | 6.89 ms (17 µs per element; +3.7 µs over calc) |
| font + 4 outputs | 3.85 ms | 7.11 ms (+4.2 µs over calc) |
| fixed coordinates (cached instances) | 3.33 ms | 4.86 ms |
| font with no outputs | 2.06 ms + 2.1 ms layout per frame | 2.75 ms + 3.9 ms layout per frame |

At 100 elements every variant sits at the same floor; the 400-element pages separate them. Max spikes of up to 44 ms appear on the font pages.

**Width scaling (`t3.py NA R M tag`: the parent sets NA axes, M children each pick a different font family and read 4 outputs; each output sums R random 1–2-axis regions):**

| NA axes | R regions/output | M | Style per pass | Per child instance |
|---|---|---|---|---|
| 8 | 4 | 100 | 3.5 ms | 35 µs |
| 64 | 4 | 100 | 5.2 ms | 52 µs |
| 64 | 200 | 100 | 8.2 ms | 82 µs |
| 256 | 200 | 100 | 41.6 ms | 416 µs |
| 64 | 2,000 | 50 | 16.5 ms | 330 µs |

*(derived)* About 0.04 µs per region term at 64 axes (rows 2 and 3: 3.0 ms over 100 × 196 × 4 extra terms). Region records span every axis, so the cost grows with regions × axes.

## 4. Compositor interpolation (`experiments/compositor/`, `tools/compframes.js`)

| Page | Style per pass | Main-thread frames/s | Compositor draws/s |
|---|---|---|---|
| synthetic, 40 3D boxes, 30,000 heavy props (`mk.py c_tr.html 30000 tr`), `transition: transform 300ms` | 165 ms | 6.0 | **55–61** |
| same without the transition (`… no`) | 92 ms | 10.7 | 10.7 |
| real engine, 48 bodies, no transition | 49 ms | 8.7 | 8.7 |
| real engine, 48 bodies, `.bw,.bd{transition:transform 250ms linear}` | 109 ms | 4.3 | **60** |
| same, 700 ms | 125 ms | 4.0 | 61 |

The compositor draws at 60 fps. **But the transitions cost the main thread about half its frame rate**, and in the `.bw,.bd` rows only the rotation is interpolated (see below). The heavy-prop count of the synthetic page in the earlier measurement was not recorded; 30,000 was chosen here.

**Why** (2026-10-13, two interleaved repeats each, `compframes.js`):

- **Each transition restart costs time in proportion to the number of registered properties on the page.** On the synthetic page, the same 10,000 heavy declarations cost 24.5 → 45 ms per pass with the transition when registered, and 10.4 → 11.3 ms when unregistered. The 48-body page has 24,896 `@property` rules; *(derived)* about 1.25 ms per transitioned body per pass, roughly 0.05 µs per registered property per restart.
- It scales with the number of transitioned bodies: 1 body 49.6 ms (no change), 8 bodies 59–63 ms, 48 bodies 108–113 ms, against 47–53 ms without.
- Passes per frame don't change (2.0 without, 1.9 with), and each pass still runs one `Document::recalcStyle`; that recalc just takes longer.
- `will-change: transform` alone, and an unrelated element with a compositor `@keyframes` animation, cost nothing. Neither restarts a transition.
- A frozen page (`FZ4000_p48.html`) shows no cost (35.5 vs 35.9 ms): frozen poses barely move, so nothing restarts.
- **A transition on `.bw` never fires** (draws stay at 9/s). `.bw` gets its pose from its own animation, and changes caused by an element's own animations don't start transitions. Only `.bd`, which inherits the quaternion, transitions, so `.bw,.bd{transition…}` smooths rotation only.
- Registrations are page-global, so CSS can't shield the bodies from them. Avoiding the cost would mean fewer registered properties in the engine.
- This is not new in Chromium 153. The 141 synthetic pages showed the same ratio: 110 vs 62 ms per pass, 8.3 vs 15.7 main frames/s. In 141 the real engine's main-thread rate didn't change (2.7 fps with and without); that is unexplained.

Interpolating body poses this way was tried and dropped: transitions on `.bd` restart from the spawn pose, so bodies jump back and forth. See [HISTORY.md](HISTORY.md).

## 5. Process parallelism (`experiments/iframes/`)

`mkchild.py` writes a 12,000-element child. In this environment that child costs only 7 ms per pass, and every setup runs each child at 60 fps, so nothing saturates. Measured with a **48,000-element** child (the same page with the element count raised in the scratch copy; about 26 ms per pass):

| Setup | Renderer processes doing style | Passes/s |
|---|---|---|
| 1 iframe, same origin | 1 | 39 |
| 2 iframes, same origin | 1 | 39 total (≈20 each) |
| 2 sandboxed iframes, `file://` or HTTP | 1 | 38 total |
| 2 cross-site iframes (127.0.0.1 and 127.0.0.2, parent on localhost) | **2** | **37 and 38** |

With the 12,000-element child, `--enable-features=IsolateSandboxedIframes` also left the sandboxed pair in one process.

## 6. Misc

- `ident()` / `var(ident(…))`: unsupported in 153 (`experiments/ident/run.js` prints `--op=-99 --op3=-99`).
- avar2: Chrome 148+ only.
- A registered number survives `var()` with **6 significant digits**, which is why the digests pack 6 bodies per decimal word.
