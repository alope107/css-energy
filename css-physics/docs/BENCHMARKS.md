# Benchmarks

Every number below was re-measured on **2026-10-17** on the **Ubuntu mini PC**: Intel Core i5-12600H (4 P-cores
with 2 threads each and 8 E-cores, 16 threads; P-cores up to 4.5 GHz, E-cores up to 3.3 GHz), 30 GB RAM, host kernel
Linux 7.0, no GPU, cpufreq governor `powersave` with energy preference `balance_performance`. The browser is
**headless Chromium 153.0.8010.12** (Chrome for Testing, `CHROME=/usr/local/bin/chromium` in the devcontainer), driven
by Playwright 1.64 with the `physics` profile. That is the same Chromium build as the previous numbers, so the
differences come from the machine. Nothing else was running. [HISTORY.md](HISTORY.md) narrates benchmarks of code
that no longer exists.

The previous version of this file was measured on 2026-10-13 on an **arm64 Docker Desktop VM with 8 vCPUs**. Where
an old number helps read a new one it is given as "(old: …)". Earlier versions came from a 2-core VM in Chromium 141.
Timings are noisy: run interleaved repeats (`tools/bench.sh`, `ab.js`) and compare **relative** numbers on one machine.

### Noise on this machine (A-vs-A, 2026-10-17)

`node ../shared/js/ab.js -r 8 -v -p bigmed 'node tools/tr.js {} …' page page`, the same page as both variants, 8
rotated rounds, each run a fresh browser:

| Page | bigmed, median (min–max) of 16 runs | Ratio B/A, median (IQR) |
|---|---|---|
| frozen 48-body pile (`FZ4000_p48`, `tr.js … 700 1200`) | 46.7 ms (43.9–47.6) | 1.019 (1.000–1.032) |
| live 32 bodies at 1.5 s (`tr.js … 1500 1500`) | 17.1 ms (16.1–18.8) | 0.988 (0.961–1.098) |
| live 16 bodies at 1.5 s | 9.3 ms (8.8–10.2) | 0.999 (0.964–1.013) |

- **Expect about ±4% run to run on heavy pages.** Two variants need to differ by more than about 5% before one run
  of each means anything; use `ab.js` with 6 or more rounds for smaller effects.
- The live 32-body runs are **bimodal**: they land at 16.1–16.7 ms or at 18.0–18.8 ms, with little in between.
  Pinning to the P-cores doesn't remove this (`taskset -c 0-7`: 15.8–18.3 ms). Unpinned runs already land on P-cores:
  unpinned and P-pinned medians agree (16.3 vs 16.8–17.1 ms). Pinned to the **E-cores** (`taskset -c 8-15`) the same
  page takes **31.0–31.5 ms**: 1.9× slower, but the steadiest of all.
- **Light pages are inflated by frequency scaling** (inferred, not proven: the governor can't be changed from inside
  the container). A page that keeps the CPU busy runs at full clock. One that finishes its frame in a few ms and idles
  lets the core clock down (idle P-cores read 400 MHz), and its style passes measure slower. Signs of this:
  - microbenchmarks at 60 fps cluster near 5 ms, with an occasional round at half that (§2);
  - a register page *without* timelines measures 4.7 ms while the busier pages with timelines measure 2.6–2.9 ms
    (§2, register readback);
  - per-token costs (differences between busy pages) came out *lower* than on the old machine, while base costs came
    out higher.

  Setting the host governor to `performance` (or the energy preference to `performance`) should remove this. Until
  then, compare light pages only with each other, interleaved.

### The new machine against the old one (same pages, same Chromium)

| Measure | Old (arm64 VM) | Mini PC | Change |
|---|---|---|---|
| Builds (16 / 32 / 48 / 64 bodies) | 2 / 6 / 13 / 26 s | 1.9 / 7.2 / 15.7 / 28.6 s | +0 to +20% |
| Published site build | 26 s | 33 s | +27% |
| Frozen 48-body step at 2.5 / 4 / 8 s | 37.2 / 36.8 / 25.4 ms | 43.1 / 43.3 / 30.2 ms | +16 to +19% |
| Frozen 48 sphere-heavy at 3 / 8 s | 15.3 / 7.1 ms | 21.3 / 8.8 ms | +39% / +23% |
| Frozen 16 / 32 | 3.8 / 5.4 ms | 4.5 / 5.7 ms | +18% / +5% |
| Live 48 at 2.5 s (style pass) | 55 ms, 9 fps | 48.8 ms, 9 fps | −11% |
| Live 64 / 96 at 3 s | 80–100 / 183 ms | 86–89 / 159 ms | about equal / −13% |
| Sparse drag, 64 bodies gap 30 | 15.7–16.7 ms | 16.1–17.2 ms | equal |
| Style-engine microbenchmarks (§2) | | | mostly +10 to +60%; see the frequency note |

*(derived)* Frozen steps run about 15–20% slower here, while live heavy pages run equal or faster. Every physics
result (settle times, gate counts, which bodies stay awake at RATE 60) is the same as before.

## How to measure (tools/)

| Script | Measures |
|---|---|
| `tr.js page[,page2] [delayMs] [durMs]` | CDP trace: median `UpdateLayoutTree` (style pass) ms, "bigmed" (median of the big passes), fps, layout/paint per frame. `V=1` prints the top trace events; `HOVER=1` / `PRESS=1` add pointer state; `TRACE=t.json` saves the trace (with `CAT=blink,devtools.timeline,disabled-by-default-devtools.timeline,cc`, `python3 ../shared/py/passprof.py t.json` gives passes and style+layout ms per frame). |
| `bench.sh reps page…` | Min-of-bigmed over interleaved repeats of `tr.js`. Use this to compare variants. |
| `../shared/js/ab.js -p bigmed 'node tools/tr.js {} 1500 1500' a.html b.html` | Ratio of each variant's bigmed to the first's per rotated round (median and IQR), each run a fresh process. Pass one page twice for the noise floor: an A-vs-A run of 6 rounds can still land a few percent off 1. Shared with js-minus-js (`shared/README.md`). |
| `perf3.js page…` | User-level: chaos fps for the first 6 s, time to settle (all asleep), idle fps, drag fps (tower top box), hold fps. |
| `freeze3.js src ms prefix tgt…` | Snapshot the state registers at `ms` and bake them into copies of `tgt` as constants with a tiny wobble, so every dependent prop recomputes every frame while all gates stay fixed. **The way to profile one physics step** without the scene evolving. `ONLYAWAKE=1` keeps sleepers frozen. |
| `freezegrab.js src ms out` | Same, while holding a grab (`BODY=k` grabs body k wherever it is; `TOWER=1` the tower's top box). |
| `traceagg.js page delay dur` | Aggregates all trace events (blink, cc, animation) by total time; `SELF=1` by self time on the main thread (totals double-count nested events). |
| `gates.js page N ms,ms…` | Counts active pair gates (np, tcp, ov, uA). The waits are cumulative. |
| `cen.js`, `grabcen.js` | Census of matched gated blocks by category, with a cost model. |
| `sleepy.js page N [s]` | Asleep count every 0.5 s. |
| `sparse.js page N [k\|c]` | The sparse regime: drags body k (`c`: the one nearest the tray centre) through a sleeping scene for 3 s; median style pass, fps, bodies woken, time to settle again. Use with `SCENE=field`. |
| `bpcount.js page N ms,…` | Broadphase candidates from live state: bounding-sphere pairs, world-AABB pairs, touching pairs. |
| `cellcheck.js page N [k]` | `CELLS=1` pages only: during a drag, checks that every sleeper in reach of an awake body is present. |
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

---

## 1. Engine performance

Pages: `COUNTS=<n> PLAIN=1 python3 src/build3d.py out/p<n>.html` (tower scene, half boxes and half spheres); `NBOX_FIX=4` for 4 boxes and the rest spheres.

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

The generator is deterministic: every count above matches the 2026-10-13 build. The published site
(`tools/make_site.sh`, counts 8–64, minified) builds in 33 s.

### perf3.js (tower scene)

| Page | Chaos fps (1 s windows) | Settled | Idle fps | Drag fps | Hold fps |
|---|---|---|---|---|---|
| 16 (8 + 8) | 48 49 50 62 62 62 | 6 s | 61 | 52 | 58 |
| 48 (24 boxes, 24 spheres) | 13 11 10 11 10 13 | 11 s | 61 | 12 | 12 |
| 48 (4 boxes, 44 spheres) | 18 16 17 22 32 48 | 6 s | 61 | 25 | 27 |
| 64 (32 + 32) | 9 8 7 7 7 7 | not within 26 s | 8 | 7 | 7 |
| 64 (4 boxes, 60 spheres) | 13 11 11 10 11 12 | 19.5 s | 61 | 19 | 20 |

The 64 mixed page is still awake when the idle, drag and hold windows run, so those three are pile-up numbers. (old:
16 bodies chaos 60–62 throughout; 48 mixed 12–17, settled 9.5 s; 64 sphere-heavy settled 17 s.)

### One physics step, frozen (`freeze3.js` + `bench.sh 3`, bigmed)

| Page | Step |
|---|---|
| 48 mixed, frozen at 2.5 s / 4 s / 8 s | 43.1 / 43.3 / 30.2 ms |
| 48 sphere-heavy (4 boxes), frozen at 3 s / 8 s | 21.3 / 8.8 ms |
| 32 mixed, frozen at 6 s | 5.7 ms |
| 16 mixed, frozen at 6 s (asleep) | 4.5 ms |

**Live, 48 bodies at 2.5 s** (`V=1 tr.js out/p48.html 2500 3000`): a 48.8 ms style pass (median), 2 passes per frame,
9 fps. Layout is 0.37 ms and paint 0.47 ms per frame.

**Idle, 32 bodies, all asleep** (`tr.js out/p32.html 20000 2000`): 2 passes per frame of about 1.8 ms each, 3.6 ms of
style per frame at 61 fps. With the pointer over the arena (`HOVER=1`): 3.3 ms per frame.

### Ablation of the frozen 48-body pile (frozen at 4 s, ≈43–46 ms step)

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

The unablated page measured 43.3 ms in the frozen-step run above and 46.3 ms here: the ±4% noise floor. Read the
implied costs to the nearest few ms.

Active gates in that pile (`gates.js out/p48.html 48 2500,1500,4000`, i.e. at 2.5 s, 4 s and 8 s), unchanged from the
old machine:

| Time | np | tcp | ov | uA |
|---|---|---|---|---|
| 2.5 s | 64 | 16 | 4 | 2 |
| 4 s | 63 | 15 | 4 | 2 |
| 8 s | 41 | 11 | 2 | 1 |

Declarations per gate family at 48 bodies (static count, brace-matched like `ablate.py`; a property of the build,
not the machine):

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
| 1,128 broadphase near tests `calc(sign(max(0, R − hypot(dx, dy, dz))))` | ≈ 3.8 ms per step, about 3.3 µs each (`mk_flags.py`: 5.58 vs 1.82 ms) |
| Pair rules with present owner name, style() false | ≈ 1.07 µs each (§2), × 3,360 ≈ 3.6 ms |
| Together | ≈ 7.4 ms, about 17% of the 43 ms frozen step. *(projected)* ≈ 13 ms at 64 bodies, ≈ 53 ms at 128 |

### Timestep vs settling (32 bodies, `sleepy.js … 32 25`, one at a time)

| RATE | Result |
|---|---|
| 90 (default) | all 32 asleep at 3.5 s |
| 60 | 27 of 32 asleep from 11.5 s; bodies 0–3 and 18 never sleep |
| 45 | 12–20 of 32 asleep throughout; 20 at 25 s |

### Settling and physics checks

- `sleepy.js out/p48.html 48 40`: all 48 asleep at 11 s, and they stay asleep.
- `smoke.sh 16` passes all three scenes, the scene switches and the grab test:

| Scene | Frames in 12 s | Floor penetration | Sphere overlap | vmax | Asleep |
|---|---|---|---|---|---|
| tower | 679 | 0.35 px | 0.09 px | 834 | 16/16 |
| rain | 669 | 0.30 px | 0.01 px | 812 | 16/16 |
| stack | 721 | 0.35 px | 0 px | 63 | 16/16 |

(old: the tower ran 372 frames in 12 s, with a 1.15 px floor penetration and a 3.06 px sphere overlap, close to its
4 px limit. At nearly twice the frame rate the tower's worst overlap is now small.)

---

### The sparse regime (field scene)

`SCENE=field` packs every body at rest on the floor (`FIELD_GAP` apart; `TRAY=2` doubles the floor for benchmarks), so the scene loads asleep. `tools/sparse.js page N c` drags the body nearest the tray centre in a circle for 3 s and reports the median style pass, fps and how many bodies woke.

Two runs each (2026-10-17):

| Page | Awake during the drag | Style pass | fps | [old] |
|---|---|---|---|---|
| 64, gap 6 (dense pile) | 9 | 53.6–55.8 ms | 8–9 | 13–25 awake, 45–55 ms, 8–10 fps |
| 64, gap 6, double tray | 17 | 44.3–44.7 ms | 10 | 15, 35–43 ms, 11–13 fps |
| 64, gap 30, double tray (one body alone) | 2 | 16.1–17.2 ms | 23–25 | 1–2, 15.7–16.7 ms, 24–26 fps |
| 96, gap 30, double tray | 4 | 33.7–34.3 ms | 12 | 4, 38–41 ms, 10–11 fps |
| 32, gap 6 | 7 | 12.9–13.0 ms | 27–28 | 31 (the whole pile woke), 14–18 ms, 22–28 fps |

How many bodies a drag wakes depends on how far the dragged body gets in 3 s, and so on the frame rate: the dense rows
woke fewer bodies here than on the old machine. The 32-body pile no longer wakes as a whole.

Frozen mid-drag (`BODY=k tools/freezegrab.js … 1500`), 64 bodies, `bench.sh 3`:

| Removed | dense pile (gap 6, body 40) | gap 30, double tray (body 59), 1 awake |
|---|---|---|
| nothing | 61.1 | 16.2 |
| all pair blocks | 36.9 | 12.2 |
| per-body awake blocks (`ac`) | 21.5 | — |
| sleeping-body blocks (`as`) | 61.3 | 15.8 |
| every gated block | 9.5 | 9.1 |

(old: 52.5 / 32.3 / 25.8 / 50.8 / 12.5 for the dense pile; 13.1 / 9.0 / 12.4 / 7.4 for gap 30. The old note "5.1 ms
with static registers: the freeze's wobble of all 840 registers is 7 ms" was not re-measured.)

In the dense pile the awake cluster has about 90 near and 40 touching pairs: about 24 ms of narrowphase and solves
here. In the one-body drag the 6,016 pair rules cost 4 ms (0.67 µs each), nearly all of them rejected by an absent
owner name.

### Spatial cells A/B (`CELLS=1`; see HISTORY.md)

| Page (field, gap 30, double tray, one body dragged) | Style pass, two runs |
|---|---|
| 64, all-pairs digest (default, `BOOLQ` on) | 16.3, 16.1 ms |
| 64, cells without `BOOLQ` | 22.1, 22.8 ms |
| 64, cells + `BOOLQ` | 22.3, 22.5 ms |
| 64, cells + `BOOLQ` + unnamed deep rules (`OWNLEV=1`) | 27.5, 26.9 ms |
| 96, digest + `BOOLQ` | 36.6, 34.5 ms |
| 96, cells + `BOOLQ` | 60.4, 59.5 ms |

Frozen one-body drag at 64: digest 16.2 ms, cells 22.8; without the sleepers' blocks 15.8 / 16.2 (the cells'
per-sleeper bookkeeping is about 6.6 ms). Frozen tower chaos at 48 with one baked state (`freeze3.js out/p48.html 4000
FT …`): 43.7 (p48), 46.1 (cells), 45.5 (cells + BOOLQ), 45.1 (+ OWNLEV=1): within about 5%, close to the noise
when everything is awake. The old "digest rebuilt" and "without the name-nested near-test rules" variants were not
rebuilt.

### 64 and 96 bodies, live (tower)

| Page | Style pass at 3 s | fps | Active gates at 3 s |
|---|---|---|---|
| 48 | 47.7 ms | 9.5 | np 62, tcp 15, ov 4 |
| 64 | 86–89 ms | 6 | np 117, tcp 27, ov 10 |
| 96 | 159 ms | 3.5 | nothing asleep for 24 s (`sleepy.js`) |

Frozen at 3 s, 64 bodies: 73.2 ms; without pair blocks 36.7 (pairs ≈ 36 ms); without `ac` blocks 20.7; without any
gated block 9.4. Owner names off (`OWNSET=`) changes nothing with everything awake (82.6 vs 86.9 ms). The world-AABB
broadphase would keep 108 of 118 sphere-near pairs (`tools/bpcount.js out/p64.html 64 3000`); 37 touch. The old
face- and internals-hiding measurements (8 and 12 ms per live pass at 64) were not re-measured.

### Firefox support (2026-10-17)

Chrome cost of the Firefox changes (ARCHITECTURE.md §6), frozen 48-body pile (`freeze3.js out/m48.html 4000`),
`ab.js -p bigmed 'node tools/tr.js {} 1500 1500'`, median ratio to the old build (IQR):

| Variant | Ratio |
|---|---|
| A-vs-A control (10 rounds) | 1.037 (1.002–1.162) |
| everything (`BOOLQ=0`, `1 * hypot`, Firefox-only blocks), 10 rounds | 1.057 (1.035–1.093) |
| `BOOLQ=0` only (8 rounds) | 1.033 (1.021–1.071) |
| `1 * hypot` only / Firefox-only blocks only (6 rounds) | 0.980 / 0.987 |
| (dead end) names from a wrapper #LN, gates inherited (8 rounds) | 1.065 (0.992–1.649) |
| (dead end) #LN + `BOOLQ=0` (10 rounds) | 1.112 (1.027–1.126) |

The control's own spread was +4% that day; the shipped variant is within it. 32 bodies frozen at 4 s: 1.019
(0.997–1.045), control 1.002. At the time, with these off (`BOOLQ=1 HYPOT1=0 FFQ=0`) the output was byte-identical to the old
generator's; the later rendering-only changes (shadow first, `tan(atan2())` scale, a hidden notice) weren't timed
(the shadow order changed 39 pixels of a Chrome screenshot).

Firefox 157 (Playwright's, `BROWSER=firefox`, scroll-driven animations pref on), same machine:

| | Chrome | Firefox |
|---|---|---|
| `perf3.js` 32 bodies: chaos fps (6 × 1 s) | 25 22 24 35 62 62 | 28 28 34 57 62 62 |
| idle / drag / hold fps | 61 / 31 / 26 | 61 / 29 / 31 |
| simulated seconds per second (free fall, rain 16) | 0.91 | 0.44–0.59 |
| `smoke.js` frames in 12 s, tower 16 | 640 | 552 |

Firefox runs one step per frame (Chrome two), so at similar frame rates its simulation runs at about half speed.

## 2. Style engine cost model (microbenchmarks)

Pages: `experiments/costs/mk*.py`, generated in a scratch directory, then `node tools/stylebench.js <pages> 500 1500`
over every page of one generator, three interleaved rounds; each number is the median of the three medians. Inputs
come from an animated `--t`. "Per unit" subtracts a baseline page and divides by the count; the baseline is the empty
page (`cq0.html`, 0.17 ms) unless the row says otherwise.

**Read this section with the frequency note at the top.** Most of these pages run at 60 fps with a light main
thread, so the core clocks down between frames. Single rounds sometimes came in at half the median (for example
`cqm10000` 2.6 against 5.1 ms, `nest1` 1.8 against 3.9 ms, `u_var1` 1.4 against 2.9 ms). Costs taken as differences
between two pages that both run at 60 fps are the most trustworthy. Old values (arm64 VM) are in brackets.

| Pattern (2,000 props on one element, `mk2.py`) | Style pass | Per prop |
|---|---|---|
| registered `<number>`, constant `5` | 2.71 ms | 1.27 µs [1.57] |
| registered `calc(5 * 2 + 1)` (no var) | 4.71 ms | 2.27 µs [1.96] |
| registered `calc(var(--t) * k)` | 5.38 ms | 2.61 µs [2.15] |
| unregistered `--x: 5` | 1.16 ms | 0.50 µs [0.49] |
| unregistered `calc(var(--t) * k)` (substitution only) | 2.92 ms | 1.38 µs [1.33] |
| registered, 1 var + 10 literal ops | 6.03 ms | 2.93 µs [3.15] |
| registered, 5 vars, about 10 ops | 5.86 ms | 2.85 µs [2.94] |
| chain `--b{i}: calc(var(--b{i−1}) + 1)` | 5.23 ms | 2.53 µs [2.54] |
| `if(style(--t: 5): 1; else: calc(…))` | 5.56 ms | 2.70 µs [2.62] |

| Extra token (1,000 props, `mk4.py`, vs `k_base` 3.77 ms) | Per token |
|---|---|
| each `+ j.5` literal (20 per prop) | +0.094 µs [0.12] |
| each `+ var(--u)` (registered, 20 per prop) | +0.134 µs [0.17] |
| each `* 1.0001` (20 per prop) | +0.098 µs [0.13] |
| each nested paren (20 per prop) | +0.087 µs [0.08] |
| each `max(var(--u), 1)` (10 per prop) | +0.27 µs [0.33] |
| each `+ var(--u)` into an unregistered prop (20 per prop) | +0.090 µs [0.10] |

The two machines disagree on the cheapest forms the same way Chromium 141 and 153 did: a constant into a registered
property measured cheaper here and expression tokens cheaper still. Don't read small per-prop differences from this table.

**Inheritance depth** (`mk.py`): 2,000 inherited registered props set at the top of a 50-deep chain, with each level adding 1: 5.50 ms. Non-inherited: 5.50 ms. Set on the root: 5.62 ms. Still no per-level copy cost.

**Container-query gating** (`mk_gating.py`, one element, an animated parent):

| Rules | Style pass | Over baseline |
|---|---|---|
| none (`cq0`, `n0`, `sq0`) | 0.17–0.19 ms | — |
| 10,000 `@container zzK {…}` with the name absent | 5.06 ms | 4.9 ms (0.49 µs per rule) |
| 50,000 with the name absent | 8.56 ms | 8.4 ms (0.17 µs per rule) |
| 10,000 / 50,000 with the outer name present and the inner absent | 5.13 / 9.70 ms | 5.0 / 9.5 ms |
| 10,000 / 50,000 with two absent names | 5.12 / 8.88 ms | 4.9 / 8.7 ms |
| 20,000 three-deep nests (present, present, absent) | 5.46 ms | 5.3 ms |
| 20,000 three-deep nests (absent, present, present) | 5.91 ms | 5.7 ms |
| 2,000 three-deep, all present (declaring the same prop) | 1.54 ms | 1.4 ms |
| 5,000 `@container pres style(--gK: 7)` (name present, false, container restyles each frame) | 5.54 ms | 5.4 ms ⇒ **1.07 µs per rule** [0.89] |
| the same 5,000 with the name absent | 1.11 ms | 0.9 ms ⇒ 0.18 µs per rule [0.14] |

**Rule matching at scale** (`experiments/costs/mk_part.py`, `part_depth.py`, `part_order.py`, `part_styleform.py`; 24k
rules on one element unless noted, baseline `base0` 0.21 ms subtracted):

| Form | µs per rule |
|---|---|
| absent name, 3 named ancestors of 3 names | 0.17–0.22, linear to 300k rules (24k 5.2 ms, 100k 17.1 ms, 300k 50.0 ms) [0.09–0.13; 2.3 / 11 / 38 ms] |
| absent name, D named ancestors of M names each | ≈ 0.2 + 0.6–0.9 ns × D × M (D=32, M=128: 2.7; D=100, M=32: 3.2; D=100, M=128: 7.7) [2.1; 2.0; 8.2] |
| present name, no `style()` | 0.21 [0.07–0.16] |
| present name + false `style(--g: 1)` | 0.80–0.86 (independent of depth and list length: found at the parent) [0.56–0.74] |
| present name + `style(--g)` (true iff value ≠ initial), false / true | 0.50 / 0.49 [0.40 / 0.41] |
| unregistered `style(--u: 1)` / `style(--u)` | 0.59 / 0.54 [0.51 / 0.43] |
| unnamed `style()` false / true | 0.78–0.81 / 0.71 [0.58 / 0.48] |
| range `style(--h > 9)` false / true; `8 < --h < 9`; bound `calc(var())` | 1.68 / 1.76; 2.28; 2.19 [1.57 / 1.66; 2.24; 1.95] |
| `style(--x: var(--y))` (true; 5,000 rules) | 1.07 [0.64] |
| `or` of 9 `style()` (5,000 rules) | 7.4 (0.82 per disjunct) [5.2] |
| nested queries | inner first, short-circuit (outer true + inner false 0.89; outer false + inner true 1.77) [0.63; 1.27] |
| `and` | left to right, short-circuit (false and true 0.93; true and false 1.47) [0.64; 1.19] |
| outer present name, inner absent + `style()` (K such rules per pair, 8,128 pairs) | 0.18–0.21 each for K = 4–9 [0.10] |
| unregistered `calc(var(--t) * k)` / 4-branch `if()` producing an ident / 12-branch (2,000 props) | 1.40 / 2.62 / 2.66 [1.25 / 2.0 / 2.6] |

Feature support in 153 (`part_feat.py`, a property of the browser build, not re-run here; `make engine-check` covers
the facts the engine depends on): range style queries with literal, `var()` and `calc()` bounds, and ident equality `style(--cell: var(--cell2))` all work. `style(--x)` on a registered property is true iff the computed value differs from its initial value (`--h: 7` with initial 7 is false, `calc(1 - 1)` is false); on an unregistered one iff it is declared at all (`--u: 0` is true).

**Register readback floor** (`mk_regs.py`: 60 levels, R register elements with two view timelines each, 2R
animations on one #LS-like element). R = 420: no timelines 4.7 ms; 7 moving registers 2.5–2.6 ms; all moving 2.9 ms
(and the frame rate drops to 23 fps: ticking 840 timelines costs outside style); #LS split into one element per body
3.1 ms. R = 840: no timelines 4.9–5.2; 7 moving 5.2–5.7; all moving 10.5–11.4 ms (5–7 fps); per body 7.2–7.3. [old:
R = 420 1.6 / 2.3 / 2.4 / 2.7; R = 840 3.0 / 5.2 / 10.] The no-timeline pages run at 61 fps and the moving ones well
below it, so the "no timelines" baseline is the page most inflated by frequency scaling. Per-body readback elements
still don't help.

**Inherited custom properties down a deep chain** (`mk_inherit2.py`): 6,000 inherited registered properties declared
at level 1 cost 7.0, 7.2 and 7.4 ms at 8, 66 and 130 levels deep (at the root: 12.3 ms). No depth × properties term.
An empty level costs about 11 µs per pass (66 levels 0.94 ms, 130 levels 1.53 ms). [old: 7.1 ms at every depth, 10 ms
at the root, about 15 µs per empty level.]

**Absent container names are no longer free.** In Chromium 141, 50,000 absent-name rules cost nothing measurable
(0.18–0.21 ms against a 0.19 ms base). In 153 they cost about 8 ms per pass, and the cost is not linear in the rule
count. Gating by owner name still pays: a present name with a false `style()` costs about 6× an absent one. The engine
has about 4,000 gated blocks at 48 bodies, so this overhead is small next to its step.

**Paused-animation evaluator** (`mk3.py`): 200 elements × `animation-delay: calc(var(--x) * -1s)` paused, 20 props
per keyframe set. 30.2 ms with one animation and 57.4 ms with two composited with add, against 6.2–7.2 ms for the
calc equivalent and 4.5 ms for no props. That's about 128 µs per element, against 9–13 µs for calc. [old: 87 against
12–15 µs.] Still a dead end.

## 3. Variable fonts as compute (`experiments/fonts/`)

Font builder: `vf.py` (fontTools). Axes run −16384…16384, so the CSS value equals the F2DOT14 coordinate.

**Correctness (`t1.py` + `t1.js`, re-run 2026-10-17).** `1ch` gives the HVAR advance of "0" and `1ic` the advance of U+6C34, both exact. `1ex` and `1cap` give MVAR `xhgt`/`cpht`, exact. A bilinear A·B region is exact (A=4096, B=12288 → 352 px). All of this resolves at style time with no layout.

**Cost (`t2.py`: one font, 2 axes, distinct coordinates per element per frame):**

| Page | 100 elements | 400 elements |
|---|---|---|
| calc baseline (same inputs) | 3.30 ms | 5.49 ms |
| font + `1ch` | 4.73 ms | 6.52 ms (16 µs per element; +2.6 µs over calc) |
| font + 4 outputs | 5.02 ms | 7.58 ms (+5.2 µs over calc) |
| fixed coordinates (cached instances) | 2.64 ms | 5.50 ms |
| font with no outputs | 2.28 ms + 2.4 ms layout per frame | 2.66 ms + 4.1 ms layout per frame |

[old, 400 elements: calc 5.42, `1ch` 6.89, 4 outputs 7.11, fixed 4.86, no outputs 2.75 + 3.9 layout.] The 100-element
pages sit near the light-page floor; the 400-element pages separate the variants.

**Width scaling (`t3.py NA R M tag`: the parent sets NA axes, M children each pick a different font family and read 4 outputs; each output sums R random 1–2-axis regions):**

| NA axes | R regions/output | M | Style per pass | Per child instance |
|---|---|---|---|---|
| 8 | 4 | 100 | 4.7 ms | 47 µs [35] |
| 64 | 4 | 100 | 5.4 ms | 54 µs [52] |
| 64 | 200 | 100 | 10.6 ms | 106 µs [82] |
| 256 | 200 | 100 | 39.8 ms | 398 µs [416] |
| 64 | 2,000 | 50 | 21.8 ms | 437 µs [330] |

*(derived)* About 0.07 µs per region term at 64 axes (rows 2 and 3: 5.2 ms over 100 × 196 × 4 extra terms; old 0.04).
Region records span every axis, so the cost grows with regions × axes.

## 4. Compositor interpolation (`experiments/compositor/`, `tools/compframes.js`)

Two interleaved runs each, 2026-10-17:

| Page | Style per pass | Main-thread frames/s | Compositor draws/s |
|---|---|---|---|
| synthetic, 40 3D boxes, 30,000 heavy props (`mk.py c_tr.html 30000 tr`), `transition: transform 300ms` | 219–265 ms | 3.7–4.3 | **20–29** |
| same without the transition (`… no`) | 92–95 ms | 10.3–10.7 | 10.3–10.7 |
| same, transition without `will-change` (`mk2.py … trnw`) | 220–222 ms | 4.7 | 27–28 |
| same, `will-change` only (`mk2.py … wc`) | 92–102 ms | 9.7–10.7 | 9.7–10.7 |
| real engine, 48 bodies, no transition | 52–54 ms | 7.3–8.0 | 7.3–8.0 |
| real engine, 48 bodies, `.bw,.bd{transition:transform 250ms linear}` | 144 ms | 3.3 | **53–54** |
| same, 700 ms | 138–150 ms | 3.0–3.3 | 60 |
| real engine, `.bw` only | 53 ms | 7.7 | 7.7 |
| frozen 48 (`FZ4000_p48`), without / with the transition | 22.6 / 22.5 ms | 20.3–20.7 | — |

On the real engine the compositor still draws at 53–60 fps. **But the transitions cost the main thread more than half
its frame rate** (7.3–8 → 3.0–3.3 fps). On the synthetic page the compositor no longer holds 60: with 220–265 ms
passes it draws 20–29 frames/s [old: 165 ms passes, 55–61 draws/s].

**Why** (measured 2026-10-13 on the old machine; the 2026-10-17 rows above agree in direction):

- **Each transition restart costs time in proportion to the number of registered properties on the page.** On the synthetic page, the same 10,000 heavy declarations cost 24.5 → 45 ms per pass with the transition when registered, and 10.4 → 11.3 ms when unregistered. The 48-body page has 24,896 `@property` rules; *(derived)* about 1.25 ms per transitioned body per pass, roughly 0.05 µs per registered property per restart.
- It scales with the number of transitioned bodies: 1 body 49.6 ms (no change), 8 bodies 59–63 ms, 48 bodies 108–113 ms, against 47–53 ms without.
- Passes per frame don't change (2.0 without, 1.9 with), and each pass still runs one `Document::recalcStyle`; that recalc just takes longer.
- `will-change: transform` alone costs nothing (re-checked 2026-10-17: the `wc` row matches `no`), and neither does an unrelated element with a compositor `@keyframes` animation. Neither restarts a transition.
- A frozen page shows no cost (re-checked 2026-10-17: 22.6 vs 22.5 ms): frozen poses barely move, so nothing restarts.
- **A transition on `.bw` never fires** (re-checked 2026-10-17: draws stay at the main-thread rate, 7.7/s). `.bw` gets its pose from its own animation, and changes caused by an element's own animations don't start transitions. Only `.bd`, which inherits the quaternion, transitions, so `.bw,.bd{transition…}` smooths rotation only.
- Registrations are page-global, so CSS can't shield the bodies from them. Avoiding the cost would mean fewer registered properties in the engine.
- This is not new in Chromium 153. The 141 synthetic pages showed the same ratio: 110 vs 62 ms per pass, 8.3 vs 15.7 main frames/s. In 141 the real engine's main-thread rate didn't change (2.7 fps with and without); that is unexplained.

Interpolating body poses this way was tried and dropped: transitions on `.bd` restart from the spawn pose, so bodies jump back and forth. See [HISTORY.md](HISTORY.md).

## 5. Process parallelism (`experiments/iframes/`)

`mkchild.py` writes a 12,000-element child, which no longer saturates a process, so these runs use a **48,000-element**
child (the same page with the count raised in a scratch copy; about 37–40 ms per pass here, 26 ms on the old machine).
Served over HTTP (`python3 -m http.server`), measured with `procs2.js`:

| Setup | Renderer processes doing style | Passes/s |
|---|---|---|
| 1 iframe, same origin | 1 | 26 [39] |
| 2 iframes, same origin | 1 | 26 total (≈13 each) [39 total] |
| 2 sandboxed iframes (`par2s`, `par2sh`, over HTTP) | 1 | 25 total [38] |
| 2 cross-site iframes (127.0.0.1 and 127.0.0.2, parent on localhost) | **2** | **26 and 26** [37 and 38] |

Only cross-site iframes get a process of their own, and then each runs at the single-iframe rate. (old: with the
12,000-element child, `--enable-features=IsolateSandboxedIframes` also left the sandboxed pair in one process; not
re-run.)

## 6. Misc

- `ident()` / `var(ident(…))`: unsupported in 153 (`experiments/ident/run.js` prints `--op=-99 --op3=-99`).
- avar2: Chrome 148+ only.
- A registered number survives `var()` with **6 significant digits**, which is why the digests pack 6 bodies per decimal word.
