# Benchmarks

Every performance measurement that survives, with where it came from and how to re-run it.

**Conventions**

- All browser numbers are headless Chromium 153 on a Linux cloud sandbox (`--no-sandbox --disable-gpu`, software
  compositing). Desktop Chrome will differ; the user's machine has not been measured.
- *(derived)* marks a value computed from logged data. *(inferred)* marks a guess about which page or variant a
  log came from.
- Raw logs are in `archive/results/`.
- "Self-compile" means the self-hosted jsc compiles FizzBuzz at run time on the CPU, then runs it.
- "Direct fizz" means FizzBuzz compiled into ROM ahead of time.

## Headline numbers

| What | Number | Section |
|---|---|---|
| Font CPU on the page | ~51 steps/s (19.6 ms per step, r = 0.977 across 83 programs) | §7 |
| FizzBuzz 1–15 on the current page (1,329 steps) | compiled ~4.7–6.2 s after Run, HALT at ~32 s | §7, §A |
| CSS compiler alone (L3 harness, no readback) | median 664 ms per program; ≈ 322 ms + 13 ms per code word | §6c |
| Self-compile, best font CPU (cpu4, N16 S16) | 233 s to HALT | §1a |
| Self-compile, pure-CSS VM | 3,608 s | §5 |
| Self-compile, in uharfbuzz alone (no browser) | 34 ms per shaping, 5.1 steps per shaping (~150 steps/s) | §3a |
| One frame of the font-CPU page (trace) | 3 passes, 207 ms style+layout, 74 ms shaping, 221 ms frame | §2b |
| Compile chain, FizzBuzz, Chrome recalc | 8,562 ms (first generator) → 318 ms (ccpage4) | §6a |

**Where the time goes**

- **Run time.** It is set by shapings, because each shaping is a layout pass and a frame holds at most 2. Traps
  (cache misses, write-backs, EXT ops, PUTC) end shapings early.
- **Predicting it.** `tools/traps.py prog.js` gives a program's shapings from the model without a browser.
- **Compile time on the page.** It is mostly the readback sweep: 64 frames after Run, plus the chain (§7 vs §6c).

---

## A. Measurements from the correctness work (2026-10-10 evening)

The runtime representation was tuned against the machine model, and each change was then checked on the page.

### A1. FizzBuzz under the machine model, as the runtime library changed

Source: `tools/traps.py` (`uarch4` model, N16 S32), `tests/fizz.js`.

| Version | Code words | Steps | Shapings | MISS | EXT | PUTC | WFAIL |
|---|---|---|---|---|---|---|---|
| Before the fixes: bare string pointers, `print` / `puts` | 45 | 1260 | **187** | 54 | 56 | 58 | 0 |
| Tagged strings; caller emits separators; untag via `+262144` (SHL13) | 53 | 1219 | 206 | 68 | 63 | 58 | 5 |
| Untag constant read from cell 4352 (on the string line) | 53 | 1205 | 221 | **91** | 56 | 58 | 4 |
| Newline back in the callee (`…Ln` entries) | 45 | 1287 | 204 | 70 | 56 | 58 | 2 |
| Constant moved to cell 4096 (a hot line); runtime checks made cheap | 45 | 1399 | 196 | 53 | 56 | 58 | 3 |
| **Final**: `puts` checks only the sign; `putsLn` inlined | 45 | 1329 | **193** | 53 | 56 | 58 | 2 |

**What it showed**

- Shapings, not steps, track wall time.
- Code that grows past the 16-line cache costs more than any number of extra ROM instructions. ROM fetch never
  traps, but every word of user code is RAM.
- A constant of 2^18 or more costs an EXT trap (SHL13) each time it is built.

Other programs, final against before the fixes:

| Program | Before (code / steps / shapings) | Final (code / steps / shapings) |
|---|---|---|
| `primes.js` | 38 / 2227 / 291 | 38 / 2247 / 295 |
| `gcd.js` | 30 / 195 / 33 | 30 / 215 / 34 |
| `array_sort.js` | 65 / 766 / 91 | 65 / 786 / 92 |
| `tests/programs/t1.js` | 63 / 2216 / 241 | 63 / 2236 / 242 |
| `tests/programs/t2.js` | 126 / 1145 / 167 | 130 / 1206 / 174 |
| `tests/programs/t3.js` | 97 / 443 / 78 | 97 / 472 / 81 |
| `tests/programs/t4.js` | 90 / 724 / 133 | 90 / 744 / 135 |

### A2. FizzBuzz steps in the reference simulator, as the library changed

| Library | Steps |
|---|---|
| Original (`print(n)`, `puts(s)`) | 1261 |
| `print(n, e)` with an unconditional tag check | 1539 |
| Tag check behind `n < 0` | 1527 |
| Static string type → `puts` | 1374 |
| Number type → `printNum`; separators emitted by the caller | 1219 |
| + `addc` | 1220 |
| Final (robust checks, `…Ln` entries) | 1330 |

These are reference-simulator steps; the font CPU's count is one lower.

### A3. FizzBuzz on the real page, back to back in the same sandbox

The harness is `machine/ui_seq.js` (initial program, Run → HALT).

| Page | Compiled (ms after Run) | HALT (ms after Run) |
|---|---|---|
| Before the fixes, run 1 / run 2 | 5,063 / 4,890 | 29,873 / 30,820 |
| Intermediate (206 shapings, row 2 of A1), run 1 / run 2 | 5,285 / 5,223 | 33,515 / 32,872 |
| Final page, L5 run | 5,327 | 31,792 |
| Final page, clean-repo smoke run | 6,150 | 31,868 |

The page timings follow the model's shapings. Run to run, the noise is about ±1 s.

### A4. The CSS compiler's size through the session

Source: `tools/vsz.py`, `tools/lp.py`, `ccpage5.build` info.

| Stage | Parser variants | Temps, all variants | Label ports per level | CSS |
|---|---|---|---|---|
| Start of session | 225 | 56,157 | 25 | — |
| New language features, first build | 303 | 108,710 | 26 | 12.0 MB |
| Out-of-set punctuation folded (`P()` → 0) | 290 | — | 21 | 8.8 MB |
| + semicolon insertion (`T_NL`, `}` path) | 319 (before the no-op merge) | 91,035 | 35 | — |
| + reachable-block pruning (`FALL`) and no-op merge | 299 + 1 pass-through | 47,427 | 22 | 5.8 MB |
| + `addc`, final | 299 + 1 pass-through (319 before the merge) | 56,673 | 22 | 7.5 MB |

- The final page is 9.6 MB with about 3,800 `@property` rules; the previous page had 4,268.
- Generating the page takes about 30 s.

L3 compile time for FizzBuzz went 1,053 ms → 823 ms → 900 ms → 818 ms across those stages. L2 DSL evaluation
went from 357 to 292 temps per parser step with the specialised variants; the generic parser is 3,795 temps.
`tools/vsz.py` and `tools/lp.py` count variants before the no-op merge (319); the page has 299 plus one
pass-through rule.

---

## B. Measurements from related chats (other sandboxes; not reproducible from this repo)

These are taken from the chats' own summaries. Re-measure before relying on them.

**[CSS harfbuzz performance optimization](https://claude.ai/chat/a0443640-884f-4ac4-a31a-6996723b78a2)**
(fvm.html, cpu2 era)

- About 6 instructions per frame.
- Per pass: about 39 ms style and 34 ms layout, against about 6 ms shaping.
- The clock ceiling is about 180 passes/s, against about 6 measured.
- 17.7 steps/s in the sandbox.

**[JS in CSS compiler architecture](https://claude.ai/chat/d3f41ebe-8d70-4fc1-b81c-85cdc71b9e66)**

- Self-hosted jsc: about 365 s to compile FizzBuzz and about 14 s to run it, about 14,000 compile steps.
- Nested-element unrolling: about 39 µs per level, correct to 500 levels.

**[CSS JavaScript interpreters speedup](https://claude.ai/chat/427a6452-26e2-4ff6-8289-3177eab3cabc)**

- 300–600 chained dependent lookups (nested grid, or `@function` per level) resolve in one rendering update.
- `sibling-index()` costs about 50% more than a literal index.
- RAM-style writes cost about 5 µs per cell whatever the layout.
- Text or counter readback lags about one frame. GSUB readback resolves within one update but becomes
  unreliable past about 100 chained links.
- A rebuilt memtree with `inherits: true` routing restyled the whole 7,168-element page: 167 ms per pass, against
  14 ms with `inherits: false`.
- The transition latch kept 200 of 200 burst writes; the remembered-size approach kept 0 of 200.
- Chained RAM reads take about 0.2 ms each, up to 64 levels. 8 parallel ports take 1.7 ms; 32 take 4.2 ms.
- avar2: a 784-axis MLP went from 419 ms to 6.6 ms after working around a Fontations scaling bug.

**[ASCII sum calculator CSS](https://claude.ai/chat/fbdb756b-6c90-4667-961a-b2652895dfe6)** (the original readback)

- 40–55 fps.
- A HarfBuzz fuzz of the readback font: 1,896 cases, 0 errors.
- Short text is re-read in about 1.4 s.

---

# Part 2. Historical record, by subsystem (compiled from the logs)

## §0. Reference inputs (needed to interpret step counts)

### Program images (`archive/machine/*.json`, metadata only)

| image | what | expected `steps` | ROM words | notes |
|---|---|---|---|---|
| `image.json` | self-hosted `jsc.js` compiler compiles a FizzBuzz (1..15) source, then runs it | 14986 | 2298 | the "full" / "self-compile" workload |
| `direct.json` | the same FizzBuzz compiled straight into ROM (`build.js --direct`) | 1229 | 121 | the "fizz" workload |
| `t/hi.json` | self-compile of `console.log("Hi"); console.log(42);` | 2951 | 2298 | |
| `ccimg.json` (10-10 22:24; now `build/ccimg.json`) | CSS-compiled FizzBuzz (lib ROM + chain overlays) | 1330 | 359 | current lib |
| `ccimg_pre.json`, `ccimg_v1.json`, `ccimg_t1..t4.json` (not kept) | earlier CSS-compiled FizzBuzz; tests t1–t4 | 1261; 2217 / 1146 / 444 / 725 | 106 | |

The font CPU's final `steps` readout is always one less than the image's `steps` (14985 vs 14986, 1228 vs 1229).

### Font CPU builds (metadata JSON next to each `.woff2`)

| meta file | N (lines) | S (cycles/shaping) | B (words/line) | subtables/cycle | glyphs | built |
|---|---|---|---|---|---|---|
| `fcpu.json` / `fdir.json` | 16 | 16 | 1 | 347 | 9188 | 10-09 14:50 / 17:39 |
| `fcpu32.json` / `fdir32.json` | 32 | 32 | 1 | 347 | 9188 | 10-09 14:59 / 17:39 |
| `f4cpu.json` / `f4dir.json` | 16 | 16 | 4 | 432 | 9749 | 10-09 23:53 / 23:50 |
| `f4cpu_8_16.json` | 8 | 16 | 4 | 432 | 9749 | 10-10 00:00 |
| `f4cpu_8_32.json` | 8 | 32 | 4 | 432 | 9749 | 10-10 00:00 |
| `f4cpu_12_24.json` | 12 | 24 | 4 | 432 | 9749 | 10-10 00:00 |
| `f4cpu_16_32.json` | 16 | 32 | 4 | 432 | 9749 | 10-10 00:00 |
| `f4dir_16_32.json` / `f4dir_16_48.json` | 16 | 32 / 48 | 4 | 432 | 9749 | 10-10 00:36 |
| `f4cc.json`, `f4cc_16.json` (shipped) | 16 | 32 | 4 | 432 | 9749 | 10-10 08:41 / 22:24 |
| `f4cc_20.json`, `f4cc_24.json` | 20 / 24 | 32 | 4 | 432 | 9749 | 10-10 08:51 |

The prefixes are `fcpu`/`f4cpu` = self-compile image, `fdir`/`f4dir` = direct image, and `f4cc` = CSS-compiled. N, S
and B are the font CPU's cache lines, micro-cycles per shaping, and words per line (`uarch.py` / `uarch4.py`).

---

## §1. Font CPU — end-to-end runs in Chromium (run to HALT)

**Harness:** `machine/fullrun.js page.html maxMinutes` (env `GC=1` forces GC each poll, `DT` = poll ms (default 10000),
`IMG` = image json for output check). It polls `--steps/--kind/--PC` on `#cpu`, logs progress plus the renderer's
RSS to stderr (`*.err`), and stops after 3 polls with no change. It then prints
`{"secs", "final", "match"}` and the 8×16 console grid to stdout (`*.log`).
**Caveat:** `secs` includes page load and the ~3 trailing no-change polls. The "halt seen" column below is the first
poll that showed the final step count; the halt happened between the previous poll and that one.
*(derived from .err)*

The command lines come from `archive/machine/runall*.sh`:
```
runall.sh  : GC=1 DT=5000 IMG=direct.json node fullrun.js {fvm_fizz,fvm_fizz32,vm_fizz}.html 20 > d_$f.log 2> d_$f.err
runall2.sh : GC=1 DT=2000 IMG=direct.json node fullrun.js fvm_fizz.html 3 / fvm_fizz32.html 3 / vm_fizz2.html 2.5   (r2_*)
             GC=1 IMG=image.json node fullrun.js fvm32.html 20 / vm2.html 25                                      (r2_*)
runall3.sh : for c in 8_32 12_24 16_32 8_16; GC=1 node fullrun.js f4_$c.html 15 > r4_$c.log                     (IMG default image.json)
runall4.sh : GC=1 DT=2000 IMG=direct.json node fullrun.js {b_f4fz48,b_f4fz32,b_fvmfz}.html 3                     (r5_*)
             GC=1 DT=5000 IMG=image.json  node fullrun.js {b_f4,b_fvm}.html 12                                    (r5_*)
```

### 1a. Font CPU (HarfBuzz) pages

| log (`archive/results/machine/`) | date | page / font *(inferred from names)* | workload | final steps | halt seen at (prev poll) | `secs` | steps/s *(derived, steps ÷ halt-seen)* | output | renderer RSS MB min/max |
|---|---|---|---|---|---|---|---|---|---|
| `fullrun_fvm` | 10-09 16:21 | fvm.html, N16 S16, B1, flat RAM (pre-memtree) | self-compile | 14985 | 1253 s (1242) | 1286.8 | ~12.0 | match | 300/416 |
| `t/hi.log` | 10-09 15:55 | t/hi.html (N16 S16) | self-compile "Hi" | 2950 | 231 s (219) | 264.6 | ~12.8 | **match:false** | 317/416 |
| `d_fvm_fizz` | 10-09 17:41 | fvm_fizz.html, fdir N16 S16 | direct fizz | 1228 | 69 s (63) | 87.5 | ~17.8 | match | 277/375 |
| `d_fvm_fizz32` | 10-09 17:42 | fvm_fizz32.html, fdir32 N32 S32 | direct fizz | 1228 | 51 s (45) | 69.9 | ~24.1 | match | 285/427 |
| `tr_fvm` | 10-09 22:41 | "tr" = tree RAM? (memtree.py; command not recorded) | self-compile | 14985 | 370 s (359) | 400.8 | ~40.5 | match | 191/239 |
| `r2_fvm_fizz` | 10-09 22:43 | fvm_fizz.html (tree RAM) | direct fizz | 1228 | 15 s (13) | 22.0 | ~82 | match | 162/170 |
| `r2_fvm_fizz32` | 10-09 22:43 | fvm_fizz32.html | direct fizz | 1228 | 16 s (14) | 23.2 | ~77 | match | 168/179 |
| `r2_fvm32` | 10-09 22:52 | fvm32.html, N32 S32 | self-compile | 14985 | 353 s (343) | 385.3 | ~42.5 | match | 189/211 |
| `r4_f4` | 10-09 23:58 | f4.html, cpu4 N16 S16 B4 *(no runall line, same naming)* | self-compile | 14985 | 278 s (268) | 311.3 | ~53.9 | match | 202/222 |
| `r4_8_32` | 10-10 00:05 | f4_8_32.html N8 S32 B4 | self-compile | 14985 | 253 s (242) | 284.9 | ~59.2 | match | 191/215 |
| `r4_12_24` | 10-10 00:10 | f4_12_24.html N12 S24 B4 | self-compile | 14985 | 256 s (246) | 289.2 | ~58.5 | match | 197/226 |
| `r4_16_32` | 10-10 00:14 | f4_16_32.html N16 S32 B4 | self-compile | 14985 | 248 s (237) | 280.9 | ~60.4 | match | 204/221 |
| `r4_8_16` | 10-10 00:19 | f4_8_16.html N8 S16 B4 | self-compile | 14985 | 265 s (254) | 296.7 | ~56.5 | match | 188/212 |
| `r5_b_f4fz48` | 10-10 00:36 | b_f4fz48.html (f4dir_16_48: N16 **S48**) | direct fizz | **0** | — | 10.7 | — | **match:false, never started** | 164/167 |
| `r5_b_f4fz32` | 10-10 00:37 | b_f4fz32.html (f4dir_16_32) | direct fizz | 1228 | 17 s (14) | 24.7 | ~72 | match | 180/192 |
| `r5_b_fvmfz` | 10-10 00:37 | b_fvmfz.html (fdir N16 S16 B1) | direct fizz | 1228 | 15 s (13) | 22.1 | ~82 | match | 164/172 |
| `r5_b_f4` | 10-10 00:41 | b_f4.html (cpu4 N16 S16) | self-compile | 14985 | 233 s (227) | 250.2 | ~64.3 | match | 198/218 |
| `r5_b_fvm` | 10-10 00:47 | b_fvm.html (cpu2 N16 S16) | self-compile | 14985 | 314 s (308) | 330.1 | ~47.7 | match | 176/192 |

What the `b_` prefix means is not recorded. The pages were generated 10-10 00:36, after `memtree.py` and `gen_vm.py`
(00:23) were edited. The `t_*` pages from 00:23–00:35 (`t_f4`, `t_f4k3`, `t_f4k4`, `t_f48`, `t_f4p`, `t_f4pd`,
`t_fvm`, `t_fz`, `t_anc`, `t_ab_noread`, `t_ab_noregs`) have no logs. One trace of `t_f4p` exists (§2).

Observations:
- The fizz runs got 4–5× faster between 17:41 and 22:43 (69 s → 15 s). The self-compile got 3.5× faster
  (fvm 1253 s → tr/r2 ~353–370 s). That window covers the decode-tree RAM (`memtree.py`, see §2).
- The 4-word-line CPU (cpu4) beat cpu2 at N16 S16 in the same r5 batch: 233 s vs 314 s for the self-compile.
- Among the r4 sweep (cpu4, self-compile), N16 S32 was fastest (248 s) and N8 S16 slowest (265 s). The spread is ~7%.
- The run with S=48 never executed a step.

### 1b. Throughput sample — `archive/spikes/scratch/b.log` (10-09 15:12)
Harness `machine/bench2.js page.html secs`: it waits 5 s, then samples `--steps`, `--nsh` (shapings) and a
rAF frame counter over the window. The page is a fvm.html build of that time (N16 S16, self-compile image).
```
{"page":"fvm.html","secs":80.3,"fps":3.04,"stepsPerSec":17.48,"shapingsPerSec":6.08,"stepsPerFrame":5.75,
 "a":{"t":6.15,"fr":19,"steps":83,"nsh":32},"z":{"t":86.467,"fr":263,"steps":1487,"nsh":520}}
```
*(derived)* That is 2.0 shapings per frame and 2.87 steps per shaping.

---

## §2. Font CPU — frame/pass profiling

### 2a. `memtree.py` docstring (10-09 23:52)
> "The tree keeps per-pass style work off the leaves. … Measured on the font CPU: style+layout per pass 70 ms -> ~20 ms."

This is the decode-tree RAM. Before it, each RAM cell had one rule per write channel (`gen_fvm.py --ram=flat`); the
tree is now the default.

### 2b. Chrome trace (10-10 00:35, 11.4 MB, not kept) — page `t_f4p.html` (a cpu4 page of that time)
It was recorded by `machine/trace.js page.html secs` (3 s settle, then a trace with default 6 s). `trace.js` prints the
top self-times, but that output was not saved. Re-analysed now with the on-disk scripts:

`python3 passprof.py trace.json` → output **(re-derived 2026-10-11 from the existing trace; nothing was re-run in the browser)**:
```
frames 26: passes/frame 3.00, style+layout ms/frame 207, shaping ms/frame 74, frame ms 221
```
(passprof counts `LocalFrameView::UpdateStyleAndLayout` events over 1 ms and `InlineNode::ShapeTextIncludingFirstLine`
events over 2 ms between `Commit`s.)

Event totals over the 6.29 s trace span *(derived)*:

| event | total ms | count |
|---|---|---|
| ProxyMain::BeginMainFrame | 5655 | 26 |
| LocalFrameView::UpdateStyleAndLayout | 5531 | 100 |
| Layout / performLayout | 4513 / 4473 | 135 |
| InlineNode::ShapeTextIncludingFirstLine | 2073 | 160 |
| EventHandler::handleMouseMoveEvent → LayoutView::HitTest | 1885 / 1884 | 26 |
| UpdateLayoutTree (style) | 1024 | 81 |

The ~1.9 s of mouse-move hit testing comes from the headless harness, not from the page.

Implication *(derived)*: about 3 passes per ~221 ms frame, which is ~4.5 frames/s. In this K = 3-pass configuration,
shaping is roughly ⅓ of style+layout time.

### 2c. Profiling and trace scripts with no saved output
- `archive/machine/prof.js page secs`: CDP Performance metrics (RecalcStyle/Layout/Script durations). No output saved.
- `machine/frames.js page nframes`: per-frame register trace. No output saved.
- `archive/machine/dbgpage.js`, `haltdump.js`, `snap.js`: debugging dumps, not benchmarks.
- `machine/halttime.js page [maxSec]`: navigation → HALT time, polled every 250 ms. No saved output.
- `archive/spikes/scratch/trace_run2.js`, `trace_run3.js`, `trace_runui.js`, `trace_idle*.js`, `trace_recalc.js`, `trace_go.js`,
  `perframe.js`: trace / main-thread phase aggregators for the UI page (10-10 17:21–18:36). No saved output.

---

## §3. HarfBuzz rule-cost microbenchmarks (uharfbuzz, offline)

### 3a. Recorded: `archive/results/machine/hb4_img.log` (10-09 23:37)
This is `hbtest.py` run with `CPUMOD=cpu4` (the build line shows the cpu4 stats). It shapes the self-compile `image.json`
in real HarfBuzz and checks every shaping against `uarch4`. The command line was not recorded; it was presumably
`CPUMOD=cpu4 python3 hbtest.py image.json 16 S > hb4_img.log` with S unknown.
```
built: 9709 glyphs, 1274 cells, 64 lookups/cycle, 429 subtables/cycle, 199 lib, GSUB 1.54 MB, 1.4s
  200 shapings ok, 1051 steps, hb 33.58 ms/shaping
  ...
  2800 shapings ok, 14477 steps, hb 34.18 ms/shaping
done: 2919 shapings, 14985 steps, halted=True, output ok=True, hb 34.13 ms/shaping
```
*(derived)* 5.13 steps/shaping and 99.6 s of pure HarfBuzz time for the whole self-compile, which is ~150 steps/s
of HarfBuzz alone.

### 3b. HarfBuzz benchmark scripts with no saved results
| script (`archive/results/machine/`) | date | what it measures | usage |
|---|---|---|---|
| `walkbench.py` | 10-09 14:20 | cost of a context walk: rule `A := B-value`, B at distance d ∈ {0,8,32,64}, mark-filtered vs not; prints ns per target and ns per try-step | `python3 walkbench.py` |
| `stagetime.py` | 10-09 14:18 | per-lookup (stage) time for one cycle on the initial state (cpu2), minus empty shape | `python3 stagetime.py N` |
| `stagetime2.py` | 10-09 14:27 | the same on realistic mid-run states sampled every 30 shapings | `python3 stagetime2.py N S [top]` |
| `stagetime3.py` | 10-09 23:41 | as above, min-of-5, `CPUMOD`/`IMG`/`NST` env | `CPUMOD=cpu4 python3 stagetime3.py N S [top]` |
| `hbbench.py` | 10-09 23:42 | full-shaping time (cv01), min of 7 over 25 sampled states | `python3 hbbench.py image.json N S` |
| `hbbench2.py` | 10-09 23:43 | the same per feature: cv01, cv02, ss01, ss04, ss08, none | `python3 hbbench2.py image.json N S` |
| `hbbench3.py` | 10-09 23:44 | S ∈ {2,4,16} × feature, builds `b2/b4/b16.ttf` | `python3 hbbench3.py image.json N` |
| `ablk.py` | 10-09 23:45 | per-lookup cost in the full pipeline: shaping time with lookup i dropped (2 cycles), `us/cycle` | `CPUMOD=cpu4 python3 ablk.py image.json 16 16 30` |
| `prof4.py` | 10-09 23:45 | per-lookup cost in context (prefix-difference method), median over states; "one cycle: N us" | `python3 prof4.py image.json N [top]` (env `NST`, `S`) |
| `floor.py` | 10-09 23:48 | per-application cost of 6 named lookups (each applied 100×) | `python3 floor.py` |
| `cmpf.py` | 10-09 23:45 | b2.ttf cv01 vs ablk.ttf cvtt/cv01 shaping ms and an output hash | `python3 cmpf.py` |
| `hbtest.py` | 10-09 23:47 | correctness and hb ms/shaping (see 3a) | `python3 hbtest.py image.json N S [maxshapings]` |

The `.ttf` outputs of these scripts are on disk (`bench.ttf`, `b2/b4/b16.ttf`, `ablk.ttf`, `prof4.ttf`, `floor.ttf`,
`st.ttf`, `t.ttf`, `wb.ttf`), which shows they ran, but no results were saved. Re-run them for numbers.

### 3c. Early HarfBuzz/CSS probes, `archive/spikes/hb/` (10-09 11:43–12:13), with no saved results
- `evA.js` measures shaping time vs string length (L = 1, 8, 64) for fonts on and off.
- `evB.js` and `evC.js` / `evC2.js` / `evC3.js` measure readback correctness and `per_unit_us` per style+layout readback for N units.
- `evP.js` measures how wide a width can be read back exactly, at scales 1 and 64.
- `evV.js` covers a variable-font readback.
- `evVM*.js` covers the toy GSUB VM (`vmfont.py`/`vmk.py`). `evVM2.js` reports `us_per_readback` for K ∈ {1, 100, 1000, 10000, 16000} aliased step lookups.
- `t2.py` is the "unambiguous budget probe" (how many lookups fire).

The pages (`A.html`, `B.html`, `C_font_*.html`, `C_mux_*.html`, `V_*.html`, `VM.html`, `VMchain.html`, `X.html`, `P.html`) are
still there, and `archive/spikes/hb/run_page.js page.html evalfile.js` runs them. No numbers were recorded.

---

## §4. Machine-model studies (Python/JS simulators, no browser), with no saved results

| script | date | what | usage |
|---|---|---|---|
| `archive/machine/sweep.py` | 10-09 14:57 | uarch.Machine for N ∈ {16,32} × S ∈ {16,24,32,48,64}: shapings, steps, steps/shaping, trap histogram | `python3 sweep.py` |
| `archive/machine/sim2.py` | 10-09 23:30 | instructions per shaping for cache variants: baseline, eager write-back ×1/×3, 4-word and 8-word lines; (N,S) ∈ {(16,16),(16,32),(32,32)} | `python3 sim2.py image.json [...]` |
| `archive/machine/sim3.py` | 10-09 23:30 | Block lines: N ∈ {8,12,16} × B ∈ {2,4} × S ∈ {16,24,32}, instr/shaping | `python3 sim3.py image.json` |
| `machine/uarch.py` (`__main__`) | 10-09 14:01 | prints `steps/shaping`, `cyc/step`, traps | — |
| `tools/traps.py` | 10-10 21:50 | per test program: code words, steps, shapings and trap kinds under uarch4 N=16 S=32, old vs new compiler/lib | `python3 traps.py files...` |
| `archive/spikes/scratch/tr2.js`, `archive/spikes/scratch/tr3.js`, `archive/spikes/scratch/tr_mod.js`, `archive/spikes/scratch/policy.js` | 10-09 12:58–13:15 | trap-distance model: how far a HarfBuzz-hosted core could run between traps (LRU cache of N cells; policies) | `node tr2.js image.json` |

The `steps` field in each image JSON (§0) is the only stored output of the reference simulator.

---

## §5. CSS VM without the font (pure CSS bytecode VM, `gen_vm.py`)

Same harness as §1 (`fullrun.js`). In these runs `kind` stays 0 and `pc` reads 0 (the readout is font-CPU-specific).
The step counter does not count the same thing as on the font CPU: for the same direct fizz it ends at 1547 or 5388,
and for the self-compile at 18823 or 49050. Treat these steps as **page-specific units**. All runs with
`match:true` produced the correct FizzBuzz output.

| log | date | page | workload | final steps | halt seen (prev) | `secs` | steps/s *(derived)* | output | RSS MB |
|---|---|---|---|---|---|---|---|---|---|
| `archive/results/machine/fullrun_vm.log` | 10-09 17:25 | vm.html (flat RAM, K=2) | self-compile | 18823 | 3608 s (3597) | 3608.8 | ~5.2 | match | 252/369 |
| `archive/results/machine/d_vm_fizz.log` | 10-09 17:47 | vm_fizz.html | direct fizz | 1454 when the browser died | — | — | ~4.8 | **crash**: `page.waitForTimeout: Target page, context or browser has been closed` at 302 s; .log empty | 237/338 |
| `archive/results/machine/d_vm_fizz2.log` | 10-09 17:52 | vm_fizz2.html | direct fizz | 1547 | 315 s (309) | 315.6 | ~4.9 | match | 235/335 |
| `archive/results/machine/r2_vm_fizz2.log` | 10-09 22:45 | vm_fizz2.html (tree RAM) | direct fizz | 5388 | 152 s (149) | 151.6 | ~35.4 | match | 153/160 |
| `archive/results/machine/r2_vm2.log` | 10-09 23:17 | vm2.html (tree RAM) | self-compile | 49050 | 1502 s (1492) | 1502.4 | ~32.7 | match | 169/190 |
| `archive/spikes/scratch/vmrun.log` | 10-09 15:28 | (CSS VM, page unknown) | ? | 342 at 72 s | — | — | ~4.75 | **crash** (browser closed) | 268/344 |

Notes:
- `gen_vm.py` docstring: "The machine executes K instructions per frame (one per layout pass, K write channels),
  because remembered sizes only update once per frame while timeline registers update every pass." The default is
  `--issue=2`, and the page text says "two bytecode instructions per frame".
- In the r2 runs (`r2_vm_fizz2` 152 s, `r2_vm2` 1502 s) the CSS VM was clearly slower in wall time than the font CPU at
  the same time (15 s and 353 s).
- `archive/machine/bench.js page secs [prop] [sel]` samples a step counter every 5 s plus a 2 s rAF fps. It has no saved output.

---

## §6. The compiler as CSS (compile chain) — load / recalc / layout costs

### 6a. Standalone compile-chain pages, FizzBuzz (`archive/results/compiler/*.json`, 10-10 07:45–08:36)
Harness: `archive/compiler/cctest.js page_test.html` (page from `cctest.py prefix`). It reports `loadMs` (navigation to load),
`recalcMs` and `layoutMs` (CDP `RecalcStyleDuration`/`LayoutDuration` totals) and reads back the overlays.
Check with `python3 cccheck.py src.js out.json`. Unless noted, the program is `tests/fizz.js`, which compiles to 45
code words and a data area holding "Fizz"/"Buzz".

| file | date | generator / variant *(inferred from name and time)* | loadMs | recalcMs | layoutMs | note |
|---|---|---|---|---|---|---|
| `cc_fizz_out.json` | 08:01 | `ccpage.py`: one level per char, whole step program on every level | 10339 | 8562 | 1682 | |
| `cc2_out.json` | 08:07 | `ccpage2.py`: lexer every level, parser only after a token via `@container` | 3290 | 3104 | 39 | |
| `cc3_out.json` | 08:13 | `ccpage3.py` first build | 1698 | 1573 | 36 | code words differ from all later runs (e.g. c513 = 24576 vs 28672) |
| `cc3_spec.json` | 08:14 | ccpage3, specialised parser variants | 3508 | 2369 | 44 | |
| `cc3_generic.json` | 08:14 | ccpage3 `generic` (one unspecialised parser) | 1715 | 1578 | 17 | |
| `cc3_m.json` | 08:20 | ccpage3, `SPEC_LEVEL=m` (per mode) | 1826 | 1170 | 60 | |
| `cc3_mt.json` | 08:20 | `SPEC_LEVEL=mt` (mode × token kind) | 1442 | 914 | 31 | |
| `cc3_mtv.json` | 08:20 | `SPEC_LEVEL=mtv` (× punctuation value) | 2916 | 1813 | 38 | |
| `cc3n_mt.json` | 08:21 | ccpage3 mt, `NEST=1`? | 2536 | 1981 | 34 | |
| `cc3n_mtv.json` | 08:21 | ccpage3 mtv, `NEST=1`? | 2644 | 1549 | 40 | |
| `cc4_mt.json` | 08:23 | `ccpage4.py` (per-char lexer rules, class-bucketed parser), mt | 1419 | 896 | 31 | |
| `cc4_mtv.json` | 08:23 | ccpage4 mtv | 1696 | 798 | 18 | |
| `cc4_t1.json` | 08:25 | ccpage4, tests/t1.js | 1954 | 1040 | 41 | err=0, 63 words |
| `cc4_e1.json` / `cc4_e2.json` | 08:24 | ccpage4, error tests | 1037 / 1031 | 155 / 125 | 4 / 3 | err=99 |
| `cc5_mt.json` / `cc5_mtv.json` | 08:28 | revision "5" (ccpage3/4 edited 08:28), mt / mtv | 1231 / 1390 | 709 / 477 | 32 / 19 | err=0, 45 words |
| `cc6.json` | 08:36 | revision "6" | 667 | 318 | 37 | err=0, 45 words |

The next set is `archive/compiler/runall.sh` (ccpage4 + cctest.js on every test), writing `archive/results/compiler/cc_*.json` at 10-10 08:44–08:46:

| file | loadMs | recalcMs | layoutMs | err / words |
|---|---|---|---|---|
| `archive/results/compiler/cc_fizz.json` | 662 | 338 | 36 | err=0, 45 |
| `archive/results/compiler/cc_t1.json` | 904 | 518 | 62 | err=0, 63 |
| `archive/results/compiler/cc_t2.json` | 1081 | 695 | 100 | err=0, 126 |
| `archive/results/compiler/cc_t3.json` | 969 | 585 | 94 | err=0, 97 |
| `archive/results/compiler/cc_t4.json` | 967 | 603 | 74 | err=0, 90 |
| `archive/results/compiler/cc_e1.json` | 379 | 68 | 5 | err=3 |
| `archive/results/compiler/cc_e2.json` | 369 | 94 | 4 | err=4 |

Trend: fizz compile went from recalc 8562 ms (ccpage) to 318–338 ms (ccpage4 final), about 25× less.

### 6b. Typed-input compiler (ccpage5) driven by fake latch cells
- `archive/results/compiler/ui_fizz.json` (10-10 19:10) came from `ui_test.py fizz.js out.xhtml` + `node uitest.js out.xhtml`. `uitest.js` times
  from Run to the chain's done anchor.
  `{"loadMs":253,"doneMs":857,"recalcMs":776,"layoutMs":20,"recalcs":2,"done":1,"err":0,"words":45,"ok":1}`
- A comment in `ccpage5.py:86` gives a measured cost: "(an animation on each level made every timeline update
  restyle the chain: ~3 ms per level)". This is why the per-character codes are animated once per line on a source
  element.
- `ccpage5.py:117`: "every registered property costs something on each animated element, so keep their number small"
  (qualitative).

### 6c. L3 suite — CSS compiler in Chrome, per program (`archive/results/suite/l3_results.log`, 10-10 22:48)
Harness: `make l3` (`tests/suite_css.py` + `tests/suite_css.js`). It is one page; each
program is written into the latch cells, then the run times Run → done anchor (rAF-polled) and checks the words
against `cc_ref`.
- `load 301 ms`. Result: **103/104 pass, FAILED: too_many_globals**, which timed out at 60003 ms with no words. It wanted
  err 25 (too many globals).
- 89 valid programs: compile time min 365 / median 664 / max 2441 ms (`else_if_long`, 140 words) *(derived)*.
  A linear fit gives ms ≈ 322 + 13.3 × words (r = 0.93) *(derived)*.
- 14 error programs: 295–666 ms, median 398 *(derived)*. Three of them report err 99 where the reference has a specific
  code (`bad_char` wants 48, `too_much_string` wants 48, `unterminated_str` wants 3) but are counted as ok.
- Slowest valid programs: else_if_long 2441 ms/140 w, print_unknown 1713/115, bubble_sort_print 1540/78,
  asi_control 1366/58, asi_brace 1326/72, compare 1241/47, var_multi 1235/60, cond_logic 1218/65, array_sort 1181/65,
  and_or_chain 1138/86, fizzbuzz 1119/45.
- The full per-program table is in the source log (104 lines).

### 6d. Container-query / registered-property cost probes, with no saved results
- `archive/readback/cqbench.py mode N R` writes `cq_<mode>.html`: N nested `.lv` and R `@container style()` rules. The modes are
  `reg` (registered `--k`), `unreg` (unregistered, via `if()`), `none` (class selectors) and `name` (named containers).
  `archive/readback/cqrun.js files...` prints `recalc <ms>`. The `cq_*.html` files are not on disk and no output was saved.
- `archive/readback/anbench.py mode D NA` measures animation creation vs inheritance cost. It builds a chain of D
  `display:contents` levels reading `var(--a<i>)`, with modes `inside` / `outside` / `nested` / `nested0`. The pages
  `an_inside.xhtml`, `an_outside.xhtml`, `an_nested.xhtml` and `an_nested0.xhtml` are on disk (10-10 17:35). They are
  meant to be traced with `archive/spikes/scratch/trace_go.js page [ms]` (toggles `#go`). No numbers were saved.
- `archive/compiler/proto.py D P` + `proto.js` (10-10 07:45) are the first prototype: D nested levels × P registered integer
  props. `proto.js` prints `load ms` and `recalcStyle ms`. `proto.json` holds only the expected values, and no
  timing was saved.
- `tools/lp.py`, `tools/vsz.py` (10-10 20:58–21:50) are size statistics of the parser variants (temps, ports,
  variants per mode), not timings. Nothing was saved.
- `archive/spikes/scratch/t.js`, `t2.js` (10-10 08:19) are container-query correctness probes, not benchmarks.

---

## §7. Full page end-to-end (editor → CSS compiler → font CPU): L5 suite

`archive/results/suite/l5_results.log` (10-10 22:43).
Harness: `make l5` (`machine/ui_seq.js` with `tests/suite_ui.py 1500`). It acts as a user: it waits
for the scan, then for each program it clicks Edit, retypes the editor, clicks Run, and polls every 100 ms.
`compiledMs` is the time from the Run click until the status shows compiled or error. `haltMs` is the time from the
Run click until `--kind` = 97 (HALT) or an error. Font = `f4cc_16` (N16 S32 B4). Viewport 1300×950.

Summary *(derived)*:
- `load ms 610`. 98 runs: the initial program plus 97 suite entries (83 run to HALT, 14 compile errors). **All 98 ok.**
- Compile (Run → compiled), valid programs: min 2305 / median 3408 / max 6943 ms (asi_brace, 72 words).
  The fit is compiledMs ≈ 2474 + 39.0 × words (r = 0.78).
- Error detection: 1957–3752 ms, median 2137.
- Execution (haltMs − compiledMs): min 1533 / median 4063 / max 27315 ms. The fit is ≈ −263 + **19.6 ms per step**
  (r = 0.977), which is about **51 steps/s**. Per program the rate ranges from 31.4 to 88.5 steps/s, median 54.3.
- FizzBuzz (1329 steps, 45 words): compiled 4694 ms, HALT at 32009 ms, run ≈ 27.3 s ≈ 48.7 steps/s. The first
  ("initial") FizzBuzz run took 5327 / 31792 ms.
- The whole suite took Σ haltMs = 812.9 s.

Full table (generated from the log):

| program | words | steps | compiledMs | haltMs | run ms (halt-compiled) | steps/s | status |
|---|---|---|---|---|---|---|---|
| initial | 45 | 1329 | 5327 | 31792 | 26465 | 50.2 | ok |
| user_report.js | 6 | 105 | 2305 | 3899 | 1594 | 65.9 | ok |
| and_or_chain.js | 86 | 347 | 4784 | 12661 | 7877 | 44.1 | ok |
| and_or_value.js | 22 | 145 | 2812 | 5266 | 2454 | 59.1 | ok |
| array_basic.js | 17 | 306 | 3423 | 8125 | 4702 | 65.1 | ok |
| array_loop.js | 23 | 273 | 3114 | 6955 | 3841 | 71.1 | ok |
| array_neg.js | 13 | 229 | 2497 | 5084 | 2587 | 88.5 | ok |
| array_param.js | 31 | 247 | 4411 | 8455 | 4044 | 61.1 | ok |
| array_sort.js | 65 | 786 | 5043 | 17325 | 12282 | 64.0 | ok |
| array_write.js | 25 | 241 | 3377 | 7370 | 3993 | 60.4 | ok |
| asi_basic.js | 31 | 331 | 4396 | 9988 | 5592 | 59.2 | ok |
| asi_brace.js | 72 | 418 | 6943 | 16390 | 9447 | 44.2 | ok |
| asi_continuation.js | 42 | 388 | 5003 | 12424 | 7421 | 52.3 | ok |
| asi_control.js | 58 | 379 | 5848 | 13619 | 7771 | 48.8 | ok |
| asi_mixed.js | 39 | 235 | 4249 | 8426 | 4177 | 56.3 | ok |
| big.js | 27 | 758 | 3016 | 18269 | 15253 | 49.7 | ok |
| bool_fn.js | 25 | 290 | 4392 | 10677 | 6285 | 46.1 | ok |
| bool_literal.js | 18 | 145 | 4162 | 7051 | 2889 | 50.2 | ok |
| bool_print.js | 16 | 147 | 3510 | 6731 | 3221 | 45.6 | ok |
| bool_var.js | 24 | 216 | 4122 | 8811 | 4689 | 46.1 | ok |
| braceless_loops.js | 52 | 563 | 4194 | 14224 | 10030 | 56.1 | ok |
| break_nested.js | 36 | 347 | 4146 | 10502 | 6356 | 54.6 | ok |
| comments.js | 6 | 89 | 2957 | 4490 | 1533 | 58.1 | ok |
| comments_block.js | 13 | 125 | 3558 | 5866 | 2308 | 54.2 | ok |
| compare.js | 47 | 195 | 4402 | 8499 | 4097 | 47.6 | ok |
| compound.js | 18 | 129 | 3010 | 5614 | 2604 | 49.5 | ok |
| compound_array.js | 54 | 303 | 3831 | 10309 | 6478 | 46.8 | ok |
| compound_ops.js | 33 | 351 | 3985 | 10157 | 6172 | 56.9 | ok |
| cond_logic.js | 65 | 876 | 4342 | 16552 | 12210 | 71.7 | ok |
| continue_for.js | 19 | 341 | 3315 | 9317 | 6002 | 56.8 | ok |
| continue_while.js | 25 | 287 | 4021 | 9183 | 5162 | 55.6 | ok |
| dangling_else.js | 30 | 145 | 3978 | 6508 | 2530 | 57.3 | ok |
| div_exact.js | 17 | 219 | 2919 | 7334 | 4415 | 49.6 | ok |
| else_chain.js | 38 | 484 | 3720 | 12847 | 9127 | 53.0 | ok |
| else_if_braceless.js | 38 | 408 | 3882 | 12464 | 8582 | 47.5 | ok |
| else_if_mixed.js | 33 | 286 | 4848 | 10275 | 5427 | 52.7 | ok |
| escapes_more.js | 13 | 303 | 3316 | 8014 | 4698 | 64.5 | ok |
| expr_stmt_call.js | 21 | 118 | 3262 | 5523 | 2261 | 52.2 | ok |
| fizzbuzz.js | 45 | 1329 | 4694 | 32009 | 27315 | 48.7 | ok |
| for.js | 16 | 229 | 2431 | 6682 | 4251 | 53.9 | ok |
| for_dec.js | 17 | 190 | 2543 | 5594 | 3051 | 62.3 | ok |
| for_empty.js | 28 | 180 | 3596 | 6733 | 3137 | 57.4 | ok |
| func_basic.js | 23 | 160 | 3001 | 5730 | 2729 | 58.6 | ok |
| func_forward.js | 13 | 106 | 3193 | 5672 | 2479 | 42.8 | ok |
| func_globals.js | 18 | 108 | 3191 | 5123 | 1932 | 55.9 | ok |
| func_locals.js | 24 | 178 | 3180 | 6459 | 3279 | 54.3 | ok |
| func_many_args.js | 20 | 113 | 2957 | 5370 | 2413 | 46.8 | ok |
| func_noreturn.js | 12 | 114 | 2548 | 4706 | 2158 | 52.8 | ok |
| func_shadow.js | 20 | 158 | 3007 | 5845 | 2838 | 55.7 | ok |
| gcd.js | 30 | 215 | 3895 | 8556 | 4661 | 46.1 | ok |
| if_no_braces.js | 14 | 94 | 2786 | 4562 | 1776 | 52.9 | ok |
| inc_dec.js | 12 | 95 | 2756 | 4369 | 1613 | 58.9 | ok |
| is_prime.js | 52 | 1201 | 4748 | 31474 | 26726 | 44.9 | ok |
| let_const.js | 23 | 239 | 3812 | 7975 | 4163 | 57.4 | ok |
| logic.js | 43 | 161 | 4084 | 7119 | 3035 | 53.0 | ok |
| mod.js | 18 | 164 | 2872 | 5943 | 3071 | 53.4 | ok |
| multi_args.js | 51 | 445 | 3431 | 12501 | 9070 | 49.1 | ok |
| neg.js | 19 | 230 | 2951 | 6787 | 3836 | 60.0 | ok |
| nested_calls_args.js | 26 | 122 | 3091 | 5671 | 2580 | 47.3 | ok |
| nested_fn_calls_bool.js | 32 | 152 | 3756 | 7254 | 3498 | 43.5 | ok |
| nested_loops.js | 32 | 419 | 3342 | 10491 | 7149 | 58.6 | ok |
| num_print.js | 14 | 195 | 2611 | 5829 | 3218 | 60.6 | ok |
| precedence.js | 35 | 245 | 3408 | 8688 | 5280 | 46.4 | ok |
| prefix_inc.js | 28 | 240 | 3407 | 7356 | 3949 | 60.8 | ok |
| putc.js | 13 | 51 | 2507 | 4131 | 1624 | 31.4 | ok |
| return_early.js | 34 | 264 | 3954 | 9848 | 5894 | 44.8 | ok |
| short_circuit.js | 28 | 98 | 3989 | 5919 | 1930 | 50.8 | ok |
| short_circuit_side.js | 60 | 604 | 4231 | 15170 | 10939 | 55.2 | ok |
| single_quote.js | 12 | 285 | 3059 | 7350 | 4291 | 66.4 | ok |
| str_concat.js | 45 | 533 | 3933 | 13807 | 9874 | 54.0 | ok |
| str_escape.js | 13 | 483 | 3170 | 10933 | 7763 | 62.2 | ok |
| str_literal.js | 10 | 243 | 2729 | 6518 | 3789 | 64.1 | ok |
| str_mixed.js | 16 | 181 | 3761 | 6498 | 2737 | 66.1 | ok |
| str_param.js | 14 | 282 | 2875 | 6938 | 4063 | 69.4 | ok |
| str_return.js | 19 | 160 | 3072 | 5901 | 2829 | 56.6 | ok |
| str_table.js | 48 | 514 | 4964 | 14898 | 9934 | 51.7 | ok |
| str_var.js | 6 | 105 | 2483 | 4077 | 1594 | 65.9 | ok |
| strict_eq.js | 17 | 129 | 2866 | 5160 | 2294 | 56.2 | ok |
| strict_ops.js | 42 | 301 | 3010 | 9750 | 6740 | 44.7 | ok |
| unary_not.js | 9 | 109 | 2630 | 4956 | 2326 | 46.9 | ok |
| var_multi.js | 60 | 570 | 4190 | 16108 | 11918 | 47.8 | ok |
| while.js | 15 | 266 | 2742 | 7037 | 4295 | 61.9 | ok |
| while_break.js | 15 | 121 | 2682 | 4370 | 1688 | 71.7 | ok |
| while_true_return.js | 23 | 166 | 4204 | 8264 | 4060 | 40.9 | ok |
| assign_undef.js | 0 | 0 | 2141 | 2259 | 118 | – | error: undefined variable |
| bad_char.js | 0 | 0 | 2180 | 2306 | 126 | – | syntax error ( counter(cse) ) |
| break_outside.js | 0 | 0 | 2187 | 2303 | 116 | – | error: break outside a loop |
| extra_brace.js | 0 | 0 | 2116 | 2233 | 117 | – | error: unexpected } |
| fn_in_block.js | 0 | 0 | 2036 | 2204 | 168 | – | error: nested function |
| missing_brace.js | 5 | 0 | 2236 | 2354 | 118 | – | error: missing } |
| nested_function.js | 0 | 0 | 2126 | 2346 | 220 | – | error: nested function |
| return_outside.js | 0 | 0 | 2032 | 2153 | 121 | – | error: return outside a function |
| str_build.js | 0 | 0 | 2132 | 2270 | 138 | – | error: strings can only be joined in console.log |
| too_much_string.js | 0 | 0 | 3752 | 3880 | 128 | – | syntax error ( counter(cse) ) |
| unclosed_paren.js | 0 | 0 | 2101 | 2268 | 167 | – | syntax error ( counter(cse) ) |
| undef_fn.js | 13 | 0 | 2552 | 2677 | 125 | – | error: undefined function |
| undef_var.js | 0 | 0 | 1957 | 2076 | 119 | – | error: undefined variable |
| unterminated_str.js | 0 | 0 | 2363 | 2475 | 112 | – | syntax error ( counter(cse) ) |

---

## §8. Editor text readback (scan)

- `readback/rbsweep.js page.xhtml src.js [reps]` types a file, sets Run, waits for `--rbready`, and prints
  `rep N sweep ms X misses Y`. The pages come from `archive/readback/rb_only2.py out.xhtml [sweeps dwell]`. No output was saved.
- `readback/rbtest.js page src [waitMs]` is a readback correctness check (`match true/false`). No output was saved.
- `archive/readback/tl1.js` … `tl9.js` (10-10 17:11–18:32) are behaviour probes of view-timeline registers under
  pause/move/detach (`start`, `paused`, `paused+moved`, `paused+detached`). They print values, not timings. The
  `tl*.html` pages were not kept, and no output was saved.
- `archive/spikes/scratch/scanlog.js`, `scanlog2.js`, `rbread.js`, `caplog.js`, `chkdet.js`, `frz.js` (10-10 18:35–19:03) are scan
  debugging tools with no saved output.
- `ui_rb.py` docstring (design note, not a number): the scan is frame-locked and "advances exactly one column per
  frame at any frame rate (a time-driven scan skips columns when frames are slow)". The range is fixed at P = 64
  columns, so one full sweep is ≥ 64 frames.
- The only end-to-end numbers that include readback are the L5 `compiledMs` figures (§7). They contain the extra
  scan sweep after Run, the character chain and the token chain.

---

## §9. Ablations

- `archive/machine/ablate.py page.html outdir` (10-09 19:44) writes `(scratch, not kept) ab_full.html`, `ab_noW.html` (write-channel
  container rules removed), `ab_noMux.html` (RAM read mux → constant), `ab_noCells.html` (RAM cells removed),
  `ab_noState.html` (`#state` line removed) and `ab_noCon.html` (console cells removed). The source was a 2.2 MB flat-RAM
  fvm page. **No timing results are saved** for any of them. They are meant to be run with `bench2.js` / `prof.js`.
- `gen_fvm4.py` / `g4a.py` env `ABL=noregs|noread` produce `archive/machine/t_ab_noregs.html` and `t_ab_noread.html`
  (10-10 00:31). **No results saved.**
- `(scratch, not kept) t_f4_nocon.html` (10-10 00:27) and `(scratch, not kept) fvm_nohb.html` (10-09 14:54) are further ablation pages with no results.
- `ablk.py` (lookup-drop ablation in HarfBuzz, §3b) has no saved results.
- `(scratch, not kept) g0.5/0.9/1/1.1/512.html`, `dz.html`, `dz.png`, `gw.js`, `dpr.js`, `dprchk.js`, `zoomfix.py` are device-pixel-ratio
  / zoom correctness experiments, not performance.

---

## §10. Benchmark-like scripts with NO recorded results (re-run list)

| script | measures | run as |
|---|---|---|
| `archive/machine/bench.js` | steps/s plus fps for a CSS VM page | `node bench.js page.html 60 [--steps] [#cpu]` |
| `machine/bench2.js` | steps/s, shapings/s, fps, steps/frame (only b.log survives, §1b) | `node bench2.js page.html 60` |
| `archive/machine/prof.js` | style vs layout time via CDP metrics | `node prof.js page.html 20` |
| `machine/trace.js` + `passprof.py` | Chrome trace → passes/frame, style+layout/shaping ms per frame | `RUN=1 node machine/trace.js build/js_in_css.xhtml 6 && python3 machine/passprof.py trace.json` |
| `machine/halttime.js` | load, first-step and HALT ms | `IMG=… node halttime.js page.html 300` |
| `machine/frames.js` | per-frame register trace | `node frames.js page.html 12 [extra,props]` |
| `machine/ui_run.js` | typed page: time to compiled, first step and HALT | `node ui_run.js page.xhtml [prog2 exp2]` |
| `archive/machine/walkbench.py`, `stagetime*.py`, `hbbench*.py`, `ablk.py`, `prof4.py`, `floor.py`, `cmpf.py` | HarfBuzz lookup costs (§3b) | see §3b |
| `archive/machine/sweep.py`, `sim2.py`, `sim3.py` | model steps/shaping vs N, S, B (§4) | see §4 |
| `archive/readback/cqbench.py` + `cqrun.js` | container-query recalc cost | `python3 cqbench.py reg 2000 200 && node cqrun.js cq_reg.html` |
| `archive/readback/anbench.py` | animation vs inheritance cost | `python3 anbench.py nested 1560 64`, then trace `#go` |
| `readback/rbsweep.js` | scan sweep ms and read misses | `node rbsweep.js page.xhtml src.js 3` |
| `archive/compiler/proto.py` + `proto.js` | nested registered-property chain recalc | `python3 proto.py D P && node proto.js` |
| `tests/uitest.js` | Run → done, recalc/layout for ccpage5 (only `archive/results/compiler/ui_fizz.json` survives) | `node uitest.js out.xhtml` |
| `archive/spikes/hb/ev*.js` (with `archive/spikes/hb/run_page.js`) | early shaping, readback and toy-VM costs | `node run.js page.html evX.js` |
| `archive/spikes/scratch/trace_*.js`, `archive/spikes/scratch/perframe.js` | UI-page phase traces | `node trace_run2.js page ui` |
| `tools/traps.py`, `archive/spikes/scratch/tr2.js`, `archive/spikes/scratch/policy.js` | trap statistics (model) | see §4 |

---

## §11. Caveats

- `fullrun.js` `secs` overstates run time by up to 3 polls plus load. Use the "halt seen" column. Halt resolution is
  the poll interval: 2 s, 5 s or 10 s.
- The CSS-VM step counts (§5) are not comparable across pages or with the font CPU.
- Many pages were regenerated after their logs were written. For example, `fvm_fizz.html` on disk is from 10-10 09:28,
  but its logs are from 10-09. The page a log measured may no longer exist in that form.
- Variant names for `cc3n_*`, `cc5_*`, `cc6`, the `b_*` pages, `tr_fvm` and the S of `hb4_img.log` are inferred and were
  not recorded.
- The headless runs use `--disable-gpu` with software compositing, so desktop Chrome timings will differ.
