# Benchmarks

Measured on **2026-10-17** on the Ubuntu mini PC (Intel Core i5-12600H, no GPU), headless **Chromium 153.0.8010.12**
with the `physics` profile (`../shared/README.md`), nothing else running. Replace numbers when you re-measure; dead
ends keep their one-line result in [HISTORY.md](HISTORY.md).

**Noise.** Expect about ±4% run to run on heavy pages (A-vs-A, frozen 48 pile: ratio 1.019, IQR 1.000–1.032): two
variants must differ by more than about 5% before one run of each means anything; use `ab.js` with 6 or more rounds
for smaller effects. Live 32-body runs are bimodal (16.1–16.7 or 18.0–18.8 ms). Light pages (a few ms per frame, 60
fps) are inflated by CPU frequency scaling (idle cores clock down; inferred, the governor can't be changed from the
container), so compare them only with each other, interleaved. Unpinned runs land on P-cores; E-cores are 1.9× slower.

## How to measure (tools/)

| Script | Measures |
|---|---|
| `tr.js page[,page2] [delayMs] [durMs]` | Trace: median style pass, "bigmed" (median of the big passes), fps, layout/paint per frame. `V=1` top events; `HOVER=1`/`PRESS=1`; `TRACE=t.json` (+ `CAT=…`, then `../shared/py/passprof.py`) |
| `bench.sh reps page…` | min-of-bigmed over interleaved `tr.js` repeats |
| `../shared/js/ab.js -p bigmed '…{}…' a b` | per-round ratio to the first variant (median, IQR), fresh process per run |
| `perf3.js page…` | chaos fps (first 6 s), settle time, idle / drag / hold fps |
| `freeze3.js src ms prefix tgt…` | bake the state at `ms` as wobbling constants: props recompute, gates stay fixed (`ONLYAWAKE=1`) |
| `freezegrab.js src ms out` | same while holding a grab (`BODY=k`, `TOWER=1`) |
| `ablate.py page NAME=REGEX…` | copies with families of gated blocks removed |
| `traceagg.js page delay dur` | trace events by total time; `SELF=1` main-thread self time |
| `gates.js page N ms,…`; `cen.js page ms` | active pair gates (waits cumulative); census of matched blocks with a cost model |
| `sleepy.js page N [s]` | asleep count every 0.5 s |
| `sparse.js page N [k\|c]` | drag body k (`c`: nearest the centre) through a sleeping scene for 3 s |
| `smoke.js`; `interact.js` | physics sanity, exits 1 on failure; mouse and touch grab on a PLAIN page (prints positions) |
| `stylebench.js page…` | median style pass of microbenchmark pages (`experiments/costs/`) |

**Ablation:** freeze a PLAIN page, strip gate families with `ablate.py`, compare with `bench.sh`. Removing a family
changes downstream gates, so deltas overlap. **Frozen bases are inflated:** with every gated block removed a frozen
64-body page measured 12.5 ms against 5.1 ms with static registers (2026-10-13, not re-measured): a frozen page's base
is 2–3× the live base. Freezing at a wall-clock time depends on the frame rate (one step per pass).

---

## 1. Engine performance

Pages: `COUNTS=<n> PLAIN=1 python3 src/build3d.py out/p<n>.html` (tower, half boxes, half spheres); `NBOX_FIX=4` for
4 boxes and the rest spheres.

### Build

| Bodies | Props | Groups | Levels | Registers | PLAIN CSS | Build time |
|---|---|---|---|---|---|---|
| 16 | 20,986 | 184 | 19 | 216 | 2.5 MB | 1.9 s |
| 32 | 79,131 | 624 | 35 | 424 | 9.3 MB | 7.2 s |
| 48 | 174,441 | 1,320 | 51 | 632 | 20.5 MB | 15.7 s |
| 48 (4 boxes) | 100,441 | 1,320 | 51 | 632 | 10.1 MB | 9.1 s |
| 64 | 307,002 | 2,272 | 67 | 840 | 36.0 MB | 28.6 s |
| 64 (4 boxes) | 172,042 | 2,272 | 67 | 840 | 17.0 MB | 16.1 s |
| 96 | 683,673 | 4,944 | 99 | 1,256 | 80.2 MB | 63.7 s |

The deployed site (`python3 src/build3d.py`, 8–64, minified; `../deploy/assemble.sh`) builds in 33 s.

### perf3.js (tower)

| Page | Chaos fps (1 s windows) | Settled | Idle fps | Drag fps | Hold fps |
|---|---|---|---|---|---|
| 16 (8 + 8) | 48 49 50 62 62 62 | 6 s | 61 | 52 | 58 |
| 48 (24 + 24) | 13 11 10 11 10 13 | 11 s | 61 | 12 | 12 |
| 48 (4 boxes, 44 spheres) | 18 16 17 22 32 48 | 6 s | 61 | 25 | 27 |
| 64 (32 + 32) | 9 8 7 7 7 7 | not within 26 s | 8 | 7 | 7 |
| 64 (4 boxes, 60 spheres) | 13 11 11 10 11 12 | 19.5 s | 61 | 19 | 20 |

The 64 mixed page is still awake during the idle, drag and hold windows.

### One physics step, frozen (`freeze3.js` + `bench.sh 3`, bigmed)

| Page | Step |
|---|---|
| 48 mixed, frozen at 2.5 s / 4 s / 8 s | 43.1 / 43.3 / 30.2 ms |
| 48 sphere-heavy, frozen at 3 s / 8 s | 21.3 / 8.8 ms |
| 32 mixed, frozen at 6 s | 5.7 ms |
| 16 mixed, frozen at 6 s (asleep) | 4.5 ms |

**Live 48 at 2.5 s** (`V=1 tr.js out/p48.html 2500 3000`): 48.8 ms style pass, 2 passes per frame, 9 fps; layout
0.37 ms and paint 0.47 ms per frame. **Idle 32, all asleep** (`tr.js out/p32.html 20000 2000`): 2 passes of about
1.8 ms, 3.6 ms of style per frame at 61 fps (3.3 ms with `HOVER=1`).

### Ablation of the frozen 48-body pile (at 4 s)

| Removed | Step | Implied cost |
|---|---|---|
| nothing | 46.3 ms | — |
| all pair-gated blocks (np, tcp, uA, uB, ov: 3,360 blocks) | 28.8 ms | pairs ≈ 17 ms |
| per-body awake blocks (`ac`, 144 blocks, 5,088 decls) | 12.7 ms | ≈ 34 ms (overlaps with pairs) |
| tcp only (1,130 blocks) | 36.0 ms | ≈ 10 ms |
| np only (1,403 blocks) | 30.6 ms | ≈ 16 ms |
| uA/uB only (552 blocks) | 40.4 ms | ≈ 6 ms |
| plane groups (nw, 192 blocks) | 39.2 ms | ≈ 7 ms |
| every gated block (4,014) | 7.3 ms | base (ungated, registers, render) |

Read implied costs to the nearest few ms (the same page measured 43.3 ms above). Active gates (`gates.js`) at 2.5 /
4 / 8 s: np 64 / 63 / 41, tcp 16 / 15 / 11, ov 4 / 4 / 2, uA 2 / 2 / 1. Static declarations at 48 bodies: about 141
per pair (≈47 tcp + 28 np + 30 uA + 30 uB + 6 ov) and about 106 per body.

### N² costs, all awake, 48 bodies

| Item | Cost |
|---|---|
| 1,128 broadphase near tests `calc(sign(max(0, R − hypot(dx, dy, dz))))` | ≈ 3.8 ms per step, about 3.3 µs each (`mk_flags.py`: 5.58 vs 1.82 ms) |
| Pair rules with present owner name, style() false | ≈ 1.07 µs each (§2), × 3,360 ≈ 3.6 ms |
| Together | ≈ 7.4 ms, about 17% of the 43 ms frozen step. *(projected)* ≈ 13 ms at 64 bodies, ≈ 53 ms at 128 |

### Timestep vs settling (32 bodies, `sleepy.js … 32 25`)

| RATE | Result |
|---|---|
| 90 (default) | all 32 asleep at 3.5 s |
| 60 | 27 of 32 asleep from 11.5 s; bodies 0–3 and 18 never sleep |
| 45 | 12–20 of 32 asleep throughout |

48 bodies settle at 11 s and stay asleep (`sleepy.js out/p48.html 48 40`). `smoke.sh 16` tower: 679 frames in 12 s,
floor penetration 0.35 px, sphere overlap 0.09 px.

### The sparse regime (field scene)

`SCENE=field` packs every body at rest on the floor (`FIELD_GAP` apart; `TRAY=2` doubles the floor), so it loads
asleep; `sparse.js page N c` drags the body nearest the centre for 3 s. Two runs each:

| Page | Awake during the drag | Style pass | fps |
|---|---|---|---|
| 64, gap 6 (dense pile) | 9 | 53.6–55.8 ms | 8–9 |
| 64, gap 6, double tray | 17 | 44.3–44.7 ms | 10 |
| 64, gap 30, double tray (one body alone) | 2 | 16.1–17.2 ms | 23–25 |
| 96, gap 30, double tray | 4 | 33.7–34.3 ms | 12 |
| 32, gap 6 | 7 | 12.9–13.0 ms | 27–28 |

How many bodies wake depends on how far the dragged body gets, so on the frame rate.

Frozen mid-drag (`BODY=k freezegrab.js … 1500`, 64 bodies, `bench.sh 3`), step / without pair blocks / without `ac`
blocks / without sleeping-body (`as`) blocks / without any gated block: dense pile (gap 6, body 40) 61.1 / 36.9 / 21.5
/ 61.3 / 9.5 ms; one body awake (gap 30, double tray, body 59) 16.2 / 12.2 / — / 15.8 / 9.1 ms. In the dense pile the awake cluster has about 90 near and 40 touching pairs: about 24 ms of narrowphase and solves.
In the one-body drag the 6,016 pair rules cost 4 ms (0.67 µs each), nearly all rejected by an absent owner name.

### 64 and 96 bodies, live (tower)

| Page | Style pass at 3 s | fps | Active gates at 3 s |
|---|---|---|---|
| 48 | 47.7 ms | 9.5 | np 62, tcp 15, ov 4 |
| 64 | 86–89 ms | 6 | np 117, tcp 27, ov 10 |
| 96 | 159 ms | 3.5 | nothing asleep for 24 s |

Frozen at 3 s, 64 bodies: 73.2 ms; without pair blocks 36.7 (pairs ≈ 36 ms); without `ac` blocks 20.7; without any
gated block 9.4. Owner names off (`OWNSET=`) changes nothing with everything awake (82.6 vs 86.9 ms).

### Firefox

Chrome cost of the Firefox changes (ARCHITECTURE.md §6), frozen 48 pile, `ab.js` ratio to the build without them:
everything 1.057 (IQR 1.035–1.093) against an A-vs-A control of 1.037 (1.002–1.162), i.e. within that day's noise;
`BOOLQ=0` alone 1.033; `1 * hypot` alone 0.980; the Firefox-only blocks alone 0.987.

Firefox 157 against Chrome, same machine, 32 bodies (`perf3.js`): chaos 28 28 34 57 62 62 vs 25 22 24 35 62 62 fps;
idle / drag / hold 61 / 29 / 31 vs 61 / 31 / 26. Simulated seconds per second (free fall, rain 16): 0.44–0.59 vs
0.91, because Firefox runs one step per frame.

## 2. Style engine cost model (microbenchmarks)

Pages: `experiments/costs/mk*.py` in a scratch directory, then `node tools/stylebench.js <pages> 500 1500` over every
page of one generator, three interleaved rounds, median of the medians. Inputs come from an animated `--t`. "Per unit"
subtracts a baseline page (the empty `cq0.html`, 0.17 ms, unless noted) and divides by the count. Most of these pages
are light (see Noise): single rounds sometimes came in at half the median, so trust differences between pages more
than absolute values. `make engine-costs` re-checks the key rows.

| Pattern (2,000 props on one element, `mk2.py`) | Per prop |
|---|---|
| registered `<number>`, constant `5` | 1.27 µs |
| registered `calc(5 * 2 + 1)` (no var) | 2.27 µs |
| registered `calc(var(--t) * k)` | 2.61 µs |
| unregistered `--x: 5` | 0.50 µs |
| unregistered `calc(var(--t) * k)` (substitution only) | 1.38 µs |
| registered, 1 var + 10 literal ops / 5 vars, about 10 ops | 2.93 / 2.85 µs |
| chain `--b{i}: calc(var(--b{i−1}) + 1)` | 2.53 µs |
| `if(style(--t: 5): 1; else: calc(…))` | 2.70 µs |

Extra tokens (1,000 props, `mk4.py`, against `k_base`): `+ j.5` literal 0.094 µs, `+ var(--u)` 0.134 µs (0.090 into an
unregistered prop), `* 1.0001` 0.098 µs, nested paren 0.087 µs, `max(var(--u), 1)` 0.27 µs. Property count, not arithmetic, is the bottleneck; don't read small per-prop differences from these.

**Container-query gating** (`mk_gating.py`, one element, an animated parent):

| Rules (baseline 0.17–0.19 ms) | Over baseline |
|---|---|
| 10,000 / 50,000 `@container zzK {…}`, name absent | 4.9 / 8.4 ms (0.49 / 0.17 µs per rule) |
| 5,000 `@container pres style(--gK: 7)` (name present, false, container restyles each frame) | 5.4 ms ⇒ **1.07 µs per rule** |
| the same 5,000 with the name absent | 0.9 ms ⇒ 0.18 µs per rule |

Absent-name rejection is not linear in the rule count; a present name with a false `style()` still costs about 6× an
absent one.

**Rule matching at scale** (`mk_part.py`, `part_depth.py`, `part_order.py`, `part_styleform.py`; 24k rules on one
element unless noted, baseline `base0` 0.21 ms):

| Form | µs per rule |
|---|---|
| absent name, 3 named ancestors of 3 names | 0.17–0.22, linear to 300k rules (24k 5.2 ms, 100k 17.1 ms, 300k 50.0 ms) |
| absent name, D named ancestors of M names each | ≈ 0.2 + 0.6–0.9 ns × D × M (D=32, M=128: 2.7; D=100, M=32: 3.2; D=100, M=128: 7.7) |
| present name, no `style()` | 0.21 |
| present name + false `style(--g: 1)` | 0.80–0.86 (independent of depth and list length: found at the parent) |
| present name + `style(--g)` (true iff value ≠ initial), false / true | 0.50 / 0.49 |
| unregistered `style(--u: 1)` / `style(--u)` | 0.59 / 0.54 |
| unnamed `style()` false / true | 0.78–0.81 / 0.71 |
| range `style(--h > 9)` false / true; `8 < --h < 9`; bound `calc(var())` | 1.68 / 1.76; 2.28; 2.19 |
| `style(--x: var(--y))` (true; 5,000 rules) | 1.07 |
| `or` of 9 `style()` (5,000 rules) | 7.4 (0.82 per disjunct) |
| nested queries | inner first, short-circuit (outer true + inner false 0.89; outer false + inner true 1.77) |
| `and` | left to right, short-circuit (false and true 0.93; true and false 1.47) |
| outer present name, inner absent + `style()` (K such rules per pair, 8,128 pairs) | 0.18–0.21 each for K = 4–9 |
| unregistered `calc(var(--t) * k)` / 4-branch `if()` producing an ident / 12-branch (2,000 props) | 1.40 / 2.62 / 2.66 |

**Feature support in 153** (`make engine-check` probes what the engine depends on): range style
queries with literal, `var()` and `calc()` bounds, and ident equality `style(--cell: var(--cell2))` work. `style(--x)`
on a registered property is true iff the computed value differs from its initial value (`--h: 7` with initial 7 is
false, `calc(1 - 1)` is false); on an unregistered one iff it is declared at all (`--u: 0` is true).

**Register readback floor** (`mk_regs.py`: 60 levels, R register elements with two view timelines each, 2R animations
on one #LS-like element). R = 420: no timelines 4.7 ms; 7 moving registers 2.5–2.6 ms; all moving 2.9 ms (23 fps:
ticking 840 timelines costs outside style); one element per body 3.1 ms. R = 840: no timelines 4.9–5.2; 7 moving
5.2–5.7; all moving 10.5–11.4 ms (5–7 fps); per body 7.2–7.3. The no-timeline page is the most inflated by frequency
scaling. Per-body readback elements don't help.

**Inheritance.** 2,000 inherited registered props set at the top of a 50-deep chain: 5.50 ms, the same as
non-inherited. 6,000 declared at level 1: 7.0, 7.2 and 7.4 ms at 8, 66 and 130 levels deep (12.3 ms
at the root). An empty level costs about 11 µs per pass.

**Paused-animation evaluator** (200 elements, `animation-delay: calc(var(--x) * -1s)` paused, 20 props per
keyframe set): 30.2 ms with one animation, 57.4 ms with two composited with add, against 6.2–7.2 ms for calc and 4.5
ms for no props: about 128 µs per element against 9–13 µs. Dead end.

Sections 3–5 and the inheritance and paused-animation results above are dead ends (the feature-support facts are live:
`make engine-check` probes them); their scripts were removed on 2026-10-18 (`git checkout 83d4fde -- css-physics/experiments`).

## 3. Variable fonts as compute

Fonts with axes −16384…16384 (the CSS value equals the F2DOT14 coordinate). `1ch`/`1ic` give exact HVAR advances,
`1ex`/`1cap` exact MVAR values, bilinear regions included, at style time with no layout.

Cost (2 axes, distinct coordinates per element per frame), 400 elements: calc baseline 5.49 ms; font + `1ch`
6.52 ms (+2.6 µs per element over calc); font + 4 outputs 7.58 ms (+5.2 µs); fixed coordinates (cached instances)
5.50 ms; no outputs 2.66 ms + 4.1 ms layout per frame.

Width scaling (M children each pick a font family and read 4 outputs, each output sums R random
regions), per child instance: 8 axes, 4 regions 47 µs; 64 axes, 4 regions 54 µs; 64 axes, 200 regions 106 µs; 256
axes, 200 regions 398 µs; 64 axes, 2,000 regions 437 µs. *(derived)* About 0.07 µs per region term at 64 axes; cost
grows with regions × axes.

## 4. Compositor interpolation

| Page | Style per pass | Main-thread frames/s | Compositor draws/s |
|---|---|---|---|
| synthetic, 40 3D boxes, 30,000 heavy props, `transition: transform 300ms` | 219–265 ms | 3.7–4.3 | 20–29 |
| same without the transition (or with `will-change` only) | 92–95 ms | 10.3–10.7 | 10.3–10.7 |
| real engine, 48 bodies, no transition | 52–54 ms | 7.3–8.0 | 7.3–8.0 |
| real engine, 48 bodies, `.bw,.bd{transition:transform 250ms linear}` | 144 ms | 3.3 | 53–54 |

The compositor keeps drawing, but the transitions **cost the main thread more than half its frame rate**: each
transition restart costs time in proportion to the page's registered properties (synthetic page, 2026-10-13: 24.5 →
45 ms per pass registered, 10.4 → 11.3 ms unregistered). At 48 bodies (24,896 `@property` rules) that is *(derived)*
about 1.25 ms per transitioned body per pass, roughly 0.05 µs per registered property per restart. Registrations are
page-global, so CSS can't shield the bodies. A frozen page shows no cost (nothing restarts). A transition on `.bw`
never fires (its pose comes from its own animation); only `.bd` transitions. Pose interpolation is a dead end
(HISTORY.md).

## 5. Process parallelism

A 48,000-element child page, served over HTTP: one same-origin iframe 26 passes/s; two same-origin, or two sandboxed, share one process (26
and 25 total); two cross-site iframes (127.0.0.1 and 127.0.0.2) get **2** processes at 26 passes/s each.

## 6. Misc

- `ident()` / `var(ident(…))`: unsupported in 153 (`make engine-check`, probe `var-ident`).
- avar2: Chrome 148+ only.
- A registered number survives `var()` with **6 significant digits**, which is why the digests pack 6 bodies per
  decimal word.
