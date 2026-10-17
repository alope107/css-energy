# Benchmarks

Every performance measurement of the current code, with how to re-run it.

**Conventions**

- Everything here was measured on **2026-10-17** on the **Ubuntu mini PC**: Intel Core i5-12600H (4 P-cores with 2
  threads each and 8 E-cores, 16 threads), 30 GB RAM, host kernel Linux 7.0, no GPU, cpufreq governor `powersave` with
  energy preference `balance_performance`. The browser is **headless Chromium 153.0.8010.12** (Chrome for Testing),
  launched by `tools/browser.js` with `CHROME=/usr/local/bin/chromium` in the project devcontainer (profile
  `fontcpu`). That is the same Chromium build as the previous numbers. Nothing else was running. Desktop Chrome will
  differ.
- The previous version of this file was measured on 2026-10-13 on an **arm64 Docker Desktop VM with 8 vCPUs**. Old
  numbers that help read the new ones are given in brackets or as "(old: …)".
- **Pages.** "Before" is the page as of commit `6f1d92e` (printing by lib routines, PUTC per character), shipped in
  this repo as `dist/js_in_css.xhtml` of commit `9319bc0`. "3K" is the first optimised page (the PRINT instruction
  family, slim readback readers, the editor pane on its own compositor layer; 3K-word dense RAM): `dist/` of
  `a01eb0c`. "Current" is the shipped page (16K-word RAM with sparse rendering, 15-bit addresses): `dist/` of
  `50de8fc`, identical to what `make page` builds today. All three were re-measured back to back in the same session.
- *(derived)* marks a value computed from logged data.
- "Self-compile" means the self-hosted jsc (`tests/programs/jsc_self.json`) compiles FizzBuzz on the CPU, then runs it.
- Measurements of pages, generators and fonts that no longer exist were removed on 2026-10-13; [HISTORY.md](HISTORY.md)
  tells that story, and the raw logs are in `archive/results/`.

**Noise on this machine (A-vs-A, 2026-10-17).** `ab.js` with the same page as both variants, each run a fresh browser:

| Measure | Runs | Median (min–max) | Ratio B/A, median (IQR) |
|---|---|---|---|
| Real page, FizzBuzz Run → HALT (`ui_seq.js`, 4 rounds) | 8 | 10.79 s (10.75–10.85) | 1.007 (0.998–1.009) |
| CPU-only FizzBuzz, load → HALT (`halttime.js`, 6 rounds) | 12 | 6.33 s (6.25–7.27) | 0.993 (0.980–0.998) |

The page timings are steadier than on the old VM (±0.5% on the real page, against about ±2% there). The CPU-only page
had one outlier in 12 runs (7.27 s, +15%), so take a median of at least three runs. The Chromium harnesses here are
not much affected by the P-core/E-core split or by frequency scaling (css-physics `docs/BENCHMARKS.md` describes both),
because a running page keeps its core busy.

## Headline numbers

| What | Before | Current | [Old machine, current] | Section |
|---|---|---|---|---|
| FizzBuzz 1–15 on the page | 1,329 steps, 193 shapings; compiled 2.94–2.97 s after Run, HALT at 18.2–18.3 s (run ≈ 15.3 s) | 476 steps, 103 shapings; compiled 2.51–2.58 s, HALT at 10.75–10.90 s (run ≈ 8.3 s) | compiled 2.4–2.6 s, HALT 9.7–10.4 s | §5 |
| FizzBuzz on the CPU alone (no editor, no compile chain) | – | HALT 6.25–6.48 s after load | 5.4 s | §5c |
| Suite shapings (model, 89 programs) | 5,967 (traps: 1,478 MISS, 1,083 EXT, 1,342 PUTC) | 4,147 (1,309 MISS, 1,104 EXT, ~230 PRINT) | same (model) | §1 |
| Font CPU on the page, L5 fit | – | 63 steps/s (15.8 ms per step, r = 0.809, 87 programs) | 85 steps/s (3K page) | §5 |
| One CPU frame of the page (mid-run trace) | 3 passes, 115 ms style+layout, 45 ms shaping, 141 ms frame | 3 passes, 124 ms style+layout, 43 ms shaping, 148 ms frame | 108 / 35 / 137 ms | §6 |
| CSS compiler alone (L3 harness, no readback) | – | median 380 ms per program; ≈ 189 ms + 7.6 ms per code word | median 318 ms per program | §4 |
| FizzBuzz in uharfbuzz alone (no browser) | – | 20.6 ms per shaping, 103 shapings | 18.1 ms | §3 |
| Self-compile in uharfbuzz alone | – | 9.55 ms per shaping (N16 S16; the image no longer halts, see §3) | 9.9 ms | §3 |
| Editor readback sweep | – | 1.12–1.21 s, 0 misses | 1.18–1.21 s | §7 |

**The new machine against the old one** *(derived)*: HarfBuzz shaping is about 13% slower here (20.6 against 18.1 ms
per shaping), and the mid-run frame is about 8% slower (148 against 137 ms). FizzBuzz on the current page halts about
6% later (10.8 against 9.7–10.4 s), and on the CPU-only page about 17% later. The before page slowed more (HALT 18.3
against 14.0–14.7 s), so the speed-up from before to current reads larger here: 1.7× in HALT time and 1.8× in run time.

**Where the time goes**

- **Run time.** It is set by shapings, because each shaping is a layout pass and a frame holds at most 2. Traps
  (cache misses, write-backs, EXT ops, PRINT chunks, PUTC) end shapings early.
- **Per pass** (mid-run trace): about 21 ms of HarfBuzz shaping in each of the two shaping passes, plus restyling `#cpu` and layout with the
  readers' container-query restyles inside it; and a third settle pass without a shaping every frame (§6).
- **Predicting it.** `tools/traps.py prog.js` gives a program's shapings from the model without a browser.
- **Compile time on the page.** It is mostly the readback sweep after Run, plus the chain (§5 vs §4).

## How to measure

| Question | Command | Notes |
|---|---|---|
| Shapings for a program (model) | `python3 tools/traps.py prog.js…` | `uarch4` model, N16 S32. Instant. |
| Compiler size | `python3 tools/vsz.py`, `python3 tools/lp.py` | Variants before the page's no-op merge. |
| HarfBuzz alone | `CPUMOD=cpu4 python3 machine/hbtest.py image.json N S [maxshapings]` | Writes `cpu.ttf` in the cwd. The image must hold the program's code: `build/ccimg.json` doesn't (the page's CSS compiler supplies it), so it never halts. Use `tests/programs/jsc_self.json`, or build an image the way `tests/suite_machine.py` does. |
| CSS compiler in Chrome | `make l3`, or for every line: `node tests/suite_css.js build/suite_css.xhtml` | Run → done, without readback. |
| Typed-input chain alone | `python3 tests/ui_test.py tests/fizz.js out.xhtml && node tests/uitest.js out.xhtml` | Fake latch cells, no editor. |
| The real page | `make l5` / `make l5-smoke`, or `EXP1=build/ui_exp/fizzbuzz.grid node machine/ui_seq.js build/js_in_css.xhtml` | `compiledMs` includes the readback sweep; `haltMs` is Run → HALT (the page's `--isHALT`). `machine/ui_run.js page` also reports the first step. |
| The CPU alone | a RAM image with the program (as `tests/suite_machine.py` builds it; `expected` = the console grid), `python3 machine/gen_fvm4.py img.json build/f4cc_16 out.html`, `IMG=img.json node machine/halttime.js out.html` | No editor, no compile chain: the CPU starts at load. |
| Where a frame goes | `RUN=1 RUNWAIT=3500 node machine/trace.js build/js_in_css.xhtml 4 && python3 machine/passprof.py trace.json` | Without `RUN=1` it traces the idle editor scan. The window must sit inside the run (FizzBuzz halts ~10.8 s after Run). `WAIT` (ms after load, default 3000) for CPU-only pages. Writes `trace.json` in the cwd. |
| Readback sweep | `python3 readback/rb_only2.py rb.xhtml && node readback/rbsweep.js rb.xhtml tests/fizz.js 3` | |

`machine/halttime.js`, `fullrun.js` and `bench2.js` never press Run; they are for CPU-only (fixed-program) pages. `readback/rbtest.js page prog.js` types the file, sets Run, waits for `--rbready` and prints what the latches read, line
by line (`match true` when it equals the file); `rbsweep.js` repeats that and counts misses.

---

## 1. Machine model (no browser)

`python3 tools/traps.py <files>` (uarch4, N16 S32), and the reference simulator's `steps` from `compiler/mkimage.py`.
The model is deterministic: re-run on 2026-10-17, every count matches. Current (PRINT family; EXT is MUL / DIV / MOD /
SHL13, PRINT a console-output chunk, PUTC a `putc()` call):

| Program | Code words | Steps | Shapings | MISS | EXT | PRINT | PUTC | WFAIL |
|---|---|---|---|---|---|---|---|---|
| `tests/suite/fizzbuzz.js` | 45 | 476 | 103 | 26 | 39 | 23 | 0 | 1 |
| `tests/suite/primes.js` | 38 | 1783 | 240 | 12 | 160 | 10 | 0 | 2 |
| `tests/suite/gcd.js` | 30 | 123 | 24 | 10 | 5 | 2 | 0 | 0 |
| `tests/suite/array_sort.js` | 65 | 635 | 77 | 25 | 0 | 5 | 0 | 0 |
| `tests/programs/t1.js` | 63 | 2031 | 217 | 20 | 1 | 3 | 0 | 1 |
| `tests/programs/t2.js` | 130 | 583 | 102 | 46 | 18 | 11 | 0 | 2 |
| `tests/programs/t3.js` | 97 | 293 | 63 | 28 | 7 | 5 | 8 | 1 |
| `tests/programs/t4.js` | 90 | 567 | 119 | 56 | 1 | 3 | 13 | 16 |

Before (lib printing, PUTC per character):

| Program | Code words | Steps | Shapings | MISS | EXT | PUTC | WFAIL |
|---|---|---|---|---|---|---|---|
| `tests/suite/fizzbuzz.js` | 45 | 1329 | 193 | 53 | 56 | 58 | 2 |
| `tests/suite/primes.js` | 38 | 2247 | 295 | 14 | 188 | 26 | 1 |
| `tests/suite/gcd.js` | 30 | 215 | 34 | 10 | 10 | 5 | 0 |
| `tests/suite/array_sort.js` | 65 | 786 | 92 | 25 | 5 | 10 | 0 |
| `tests/programs/t1.js` | 63 | 2236 | 242 | 20 | 16 | 10 | 3 |
| `tests/programs/t2.js` | 130 | 1206 | 174 | 45 | 61 | 31 | 6 |
| `tests/programs/t3.js` | 97 | 472 | 81 | 30 | 14 | 21 | 1 |
| `tests/programs/t4.js` | 90 | 744 | 135 | 59 | 13 | 22 | 10 |

The reference simulator counts one step more than the font CPU (HALT). Suite-wide (89 programs + t1–t4, model):
46,458 → 26,682 steps and 5,967 → 4,147 shapings.

**Configurations that were modelled and not built** (suite shapings, current): N = 24 lines 3,888; N = 32 3,858;
S = 48 cycles 3,427; S = 64 3,161; N32 S64 2,848. The sanitizer caps S × 432 subtables at 16,384 (S ≤ 37), and
HarfBuzz time grows with cells × lookups × S. A code / data partition of the 16 lines: 4,368–4,713 (worse).

## 2. The CSS compiler's size

Source: `tools/vsz.py`, `tools/lp.py`, the `make page` build line, and `make test` (L2). Re-run 2026-10-17.

| Measure | Value |
|---|---|
| Parser variants | 323 before the no-op merge; 302 + 1 pass-through on the page, in 168 rules (identical variants of a mode share one, §4c) [319; 299 rules before the language features of §4c] |
| Temps, all variants | 62,756 [56,505 before §4c; 56,673 before the PRINT family] |
| Largest variant | 1,380 temps (`S_NAMES '}'`) [1,253] |
| Label ports per level | 21 [22] |
| Levels | 1,561 character levels, 401 token levels |
| Compile-chain CSS | 7.7 MB (7,666,557 bytes) [7,407,608; 7,515,752 before the PRINT family] |
| Page | 12.1 MB (12,107,435 bytes) [11,857,709; the 3K page 9,514,312, before 9,612,666] |
| `make page` | 28 s, reproducible [26 s] |
| L2 DSL evaluation (suite of 97 + 25 programs, 6,373 parser steps) | 336 temps per step with the specialised variants [291 per step on the 90 + 14 programs before §4c]; 3,795 with the generic parser (not re-run) |

## 3. HarfBuzz alone (uharfbuzz 0.56.3, no browser)

`machine/hbtest.py` shapes the real cpu4 font in HarfBuzz and checks every shaping against `uarch4`. The current font
build line reads `6803 glyphs, 1274 cells, 111 lookups/cycle, 432 subtables/cycle, 205 lib` (1K ROM). RAM images are
built as `tests/suite_machine.py` builds them (code and data in RAM).

| Workload | N, S | Shapings | Steps | Result | HarfBuzz time |
|---|---|---|---|---|---|
| FizzBuzz | 16, 32 | 103 | 476 | halted, output ok | 20.56 ms per shaping [18.1] |
| `bubble_sort_print` | 16, 32 | 167 | 901 | halted, output ok | 20.48 ms [17.9] |
| `array_sort` | 16, 32 | 77 | 635 | halted, output ok | 21.07 ms [18.3] |
| `str_table` | 16, 32 | 40 | 168 | halted, output ok | 20.37 ms [18.3] |
| Self-compile (`tests/programs/jsc_self.json`) | 16, 16 | 158,800+ | 636,754+ | every shaping matches the model, but it never halts | 9.55 ms per shaping [9.88] |

*(derived)* FizzBuzz: 4.6 steps per shaping, 2.1 s of HarfBuzz time. The self-compile image predates the 16K memory
map: it holds a 3K RAM and a 2,298-word ROM, so on the current CPU it runs without halting. Its per-shaping time is
still a fair measure of the N16 S16 font. Before the memory-map change it halted after 2,919 shapings and 14,985
steps (5.1 steps per shaping; old machine, 28.8 s of HarfBuzz time).

## 4. The CSS compiler in Chrome

### 4a. L3 suite, per program

`make l3` (`tests/suite_css.py` + `tests/suite_css.js`): one page; each program is written into the latch cells, Run
is pressed, and the harness times Run → the chain's done anchor and checks every word against `cc_ref`.

2026-10-17: **104/104 pass** (90 valid programs, 14 error programs; `load 180 ms`; the whole run 79 s).

- Valid programs: min 229 / median 380 / max 1,488 ms (`else_if_long`, 137 words). The fit is ms ≈ 189 + 7.6 ×
  words (r = 0.90) *(derived)*. [old machine: min 194 / median 318 / max 1,037; ≈ 158 + 6.4 × words.]
- Error programs: 187–522 ms, median 220 *(derived)*. Two report err 99 where the reference has a specific code
  (`bad_char` wants 48, `unterminated_str` wants 3); L3 counts any nonzero error as ok.
- Slowest valid programs: else_if_long 1488 ms/137 w, print_unknown 900/90, array_sort 817/65, asi_brace 753/72,
  bubble_sort_print 692/75, nested_loops 672/32, and_or_chain 652/86, asi_continuation 644/39. FizzBuzz: 580 ms, 45
  words [427].
- *(derived)* The compiler runs about 20% slower here than on the old machine.

### 4b. The typed-input chain driven by fake latch cells

`python3 tests/ui_test.py tests/fizz.js out.xhtml && node tests/uitest.js out.xhtml` (times Run → the chain's done
anchor), two runs:
`{"loadMs":177,"doneMs":642,"recalcMs":599,"layoutMs":9,"recalcs":2,"done":1,"err":0,"words":45,"ok":1}` and
`{"loadMs":177,"doneMs":600,"recalcMs":558,"layoutMs":8,…}` [old: done 486 ms, recalc 451 ms, load 140 ms].

### 4c. Language features: block scope, `const`, `do … while`, `?:` (branch `js-lang-basics`, 2026-10-17)

The goal was no run-time cost and as little compile-time cost as possible. Each step was measured on the L3 page
against the baseline L3 page (`234a0ca`), in interleaved rounds (baseline, new, baseline, new, …; `node
tests/suite_css.js page.xhtml`). The ratio is new / baseline for each of the 90 programs common to both, and the
table gives its median per round. Run to run, a program's ratio spreads by about ±7% (IQR), so read the medians
across rounds.

**Run time.** Compile time only, by construction:

- Every program the old compiler compiled correctly (95 of 97 suite programs + t1–t4) compiles to identical code and
  data words, so steps and shapings are unchanged. The other two (`let_block`, `let_shadow_fn`) printed wrong values
  before: `let` was `var`.
- `do … while` costs one `JNZ` per iteration where `while` costs a `JZ` and a `JMP`. A 40-iteration sum takes 432
  steps and 46 shapings, against 476 and 50 for the same loop as `while` (model, `tools/traps.py`).
- `c ? a : b` costs the same as `if / else`: a 30-iteration loop takes 586 steps and 73 shapings as a ternary, against 576 and 73 as
  `if / else` (27 against 29 code words).
- Real page, FizzBuzz (`machine/ui_seq.js`, 6 interleaved rounds against the baseline page): HALT ratio 1.000 (range
  0.92–1.05), compiled ratio 0.970 (0.89–1.03). The machine was noisier than in the A-vs-A table at the top: the
  baseline's HALT ranged 10.9–12.8 s.

**Compile time, step by step** (L3; sizes from `tools/vsz.py` and `tools/lp.py`):

| Build | Temps | Variants (rules on the page) | Max label ports | Largest variant | L3 ratio per round |
|---|---|---|---|---|---|
| Baseline | 56,505 | 319 (299) | 22 | 1,253 | 1 |
| + block-scoped `let` / `const`, `const` checks | 58,324 | 319 | 22 | 1,323 | 0.997, 0.978 |
| + `do … while` | 60,766 | 322 | 22 | 1,380 | 1.003, 1.003 |
| + `?:`, first version | 66,816 | 336 | 23 | 1,423 | 1.002, 1.041, 1.042, 1.038 |
| `?:` trimmed: one check after `popops`' loop, `close_block` shares one label port | 64,542 | 336 | 21 | 1,380 | 1.029, 1.048, 1.025 |
| `?` and `:` out of `PUNCT` (14 → 3 new variants) | 62,756 | 323 | 21 | 1,380 | 1.011, 1.000, 1.021 |
| + identical variants share one rule | 62,756 | 323 (168) | 21 | 1,380 | 0.977, 0.970, 0.950 |

- Block scope uses a two-region symbol table. The lookup's extra comparison per symbol adds 5% to the largest
  variant, with no measurable compile-time cost.
- `do … while`: a first version with a mode after the `)` for the optional `;` (`S_DOEND`) doubled the total
  temps (112,279) and raised the ports to 29, and it was replaced. With it, a do body that stopped the
  `complete_stmt` chain made the mode dynamic, so `S_ELSE`'s pure-error variants no longer folded to a constant
  error and weren't dropped (9 → 37 variants), until those tokens stopped closing do bodies.
- **Every rule costs time whether it applies or not.** Each token level checks every variant's container query.
  40 never-matching copies of variant rules added to the `?:` build (+13% rules) cost +4.3%, +2.0% and +1.6% (3
  rounds against the same page without them). That is why the ternary's 14 new variants cost more than their
  temps, and why merging the 115 duplicate variants (36% of them: mostly `S_LBRACE`, `S_INC`, `S_AFTERELSE`,
  `S_VARAFTER` on punctuation tokens) into shared rules made the compiler about 3% faster than the baseline.

L3 itself: **122/122 pass** in every round (97 valid programs, 25 error programs with the intended codes 64–67, 3, 4
and 47). L1 97/97, L2 ALL OK, L4 97/97, `make l5-smoke` 9/9.

---

## 5. Full page end-to-end (editor → CSS compiler → font CPU): L5 suite

### 5a. FizzBuzz alone (`machine/ui_seq.js`, initial program, nothing else running)

Two interleaved rounds per page, plus the A-vs-A runs of the current page (top of this file):

| Build | load | compiledMs | haltMs | run (haltMs − compiledMs) |
|---|---|---|---|---|
| Before (`9319bc0`) | 334 / 343 ms | 2,969 / 2,938 | 18,204 / 18,328 | 15,235 / 15,390 |
| 3K (`a01eb0c`) | 339 / 335 ms | 2,976 / 2,974 | 10,648 / 10,804 | 7,672 / 7,830 |
| Current (16K sparse) | 329–356 ms | 2,513–2,582 | 10,855–10,899 (A-vs-A: 10,746–10,851) | 8,290–8,350 |

*(derived)* Before → current: HALT 18.3 → 10.8 s (1.7×), run 15.3 → 8.3 s (1.8×). The 16K page compiles 0.4 s faster
than the 3K page but runs 0.6 s longer, so the two halt within 2% of each other. [old machine: before HALT 14.0–14.7 s,
3K 8.5–8.6 s, 16K 9.7–10.4 s.]

### 5c. The CPU alone (`machine/halttime.js` on CPU-only pages, from load to HALT)

CPU-only pages of the current machine (16K sparse RAM), `python3 machine/gen_fvm4.py img.json build/f4cc_16 out.html`
on a RAM image built as `tests/suite_machine.py` builds it. Two runs each:

| Program | Steps | HALT after load | [old, 16K sparse] |
|---|---|---|---|
| FizzBuzz | 476 | 6,401 / 6,267 ms (A-vs-A median 6,333) | 5,421 ms |
| `str_table.js` | 168 | 2,744 / 2,731 ms | 2,436 ms |
| `bool_print.js` | 48 | 1,088 / 1,088 ms | – |
| `bubble_sort_print.js` | 901 | 10,016 / 9,547 ms | 8,133 ms |
| `array_sort.js` | 635 | 4,336 / 4,531 ms | 3,747 ms |

Every page halted with the exact step count; the output matched (`bubble_sort_print` prints 8-character lines, which
wrap a blank row in the 8-column console, so its grid differs only from the harness's expected layout).

### 5b. The L5 suite

`make l5` (`machine/ui_seq.js` with `tests/suite_ui.py 1500`). It acts as a user: it waits for the scan, then for each
program it clicks Edit, retypes the editor, clicks Run, and polls every 100 ms. `compiledMs` is the time from the Run
click until the status shows compiled or error. `haltMs` is the time from the Run click until the page's `--isHALT`
is 1 or an error shows. Font = `f4cc_16` (N16 S32 B4). Viewport 1300×950. Current page (16K sparse RAM), 2026-10-17,
nothing else running; the whole run took 11.4 min.

Summary *(derived)*:
- `load ms 343`. 101 runs: the initial program plus 100 suite entries (87 run to HALT, 14 compile errors). **101 of 101 ok.**
- Compile (Run → compiled), valid programs: min 1,708 / median 2,199 / max 5,847 ms.
  The fit is compiledMs ≈ 1,562 + 26.0 × words (r = 0.90).
- Error detection: 1,662–2,502 ms, median 1,720.
- Execution (haltMs − compiledMs): min 563 / median 1,542 / max 22,765 ms. The fit is ≈ 188 + **15.77 ms per step**
  (r = 0.809), which is about **63 steps/s**. Per program the rate ranges from 22.3 to 140.7 steps/s, median 61.6.
- FizzBuzz (476 steps, 45 words): the initial run compiled at 2,600 ms and halted at 11,171 ms; the same program
  mid-suite took 2,776 / 13,224 ms (run 10.4 s against 8.6 s). On the old 3K page the two agreed (8,716 / 8,629 ms).
  *(inferred)* The sparse RAM keeps every group a program has written, so later programs run on a page with more
  live cells; a fresh page (§5a) is the fair comparison.
- The whole suite took Σ haltMs = 454 s.
- [old machine, on the 3K page (the 16K page's L5 timings weren't recorded there): compile median 1,750 ms, ≈ 1,356 +
  18.5 × words; 11.74 ms per step, 85 steps/s; Σ haltMs 353 s.] Part of the gap is the machine (§5a: the 3K page halts
  FizzBuzz 1.2× later here) and part is the 16K page's longer runs (§5a, §8).

Full table (generated from the `ui_seq.js` log; `steps/s` = steps / run time):

| program | words | steps | compiledMs | haltMs | run ms | steps/s | status |
|---|---|---|---|---|---|---|---|
| initial | 45 | 476 | 2600 | 11171 | 8571 | 55.5 | ok |
| user_report.js | 6 | 54 | 1777 | 2409 | 632 | 85.4 | ok |
| and_or_chain.js | 86 | 134 | 2764 | 6044 | 3280 | 40.9 | ok |
| and_or_value.js | 22 | 52 | 1866 | 3047 | 1181 | 44.0 | ok |
| array_basic.js | 17 | 129 | 2135 | 3527 | 1392 | 92.7 | ok |
| array_loop.js | 23 | 210 | 2124 | 3901 | 1777 | 118.2 | ok |
| array_neg.js | 13 | 181 | 1784 | 3070 | 1286 | 140.7 | ok |
| array_param.js | 31 | 184 | 2519 | 4447 | 1928 | 95.4 | ok |
| array_sort.js | 65 | 635 | 3071 | 9243 | 6172 | 102.9 | ok |
| array_write.js | 25 | 121 | 2117 | 3489 | 1372 | 88.2 | ok |
| asi_basic.js | 31 | 93 | 2773 | 4763 | 1990 | 46.7 | ok |
| asi_brace.js | 72 | 268 | 4049 | 8242 | 4193 | 63.9 | ok |
| asi_continuation.js | 39 | 167 | 3203 | 5990 | 2787 | 59.9 | ok |
| asi_control.js | 58 | 234 | 3790 | 7518 | 3728 | 62.8 | ok |
| asi_mixed.js | 39 | 134 | 2868 | 4759 | 1891 | 70.9 | ok |
| big.js | 27 | 59 | 2041 | 3917 | 1876 | 31.4 | ok |
| bool_fn.js | 25 | 69 | 2199 | 4009 | 1810 | 38.1 | ok |
| bool_literal.js | 18 | 79 | 2243 | 3478 | 1235 | 64.0 | ok |
| bool_print.js | 16 | 48 | 1828 | 2829 | 1001 | 48.0 | ok |
| bool_var.js | 24 | 88 | 2398 | 3936 | 1538 | 57.2 | ok |
| braceless_loops.js | 52 | 269 | 2467 | 5990 | 3523 | 76.4 | ok |
| break_nested.js | 36 | 341 | 2502 | 5921 | 3419 | 99.7 | ok |
| bubble_sort_print.js | 75 | 901 | 3276 | 17995 | 14719 | 61.2 | ok |
| comments.js | 6 | 54 | 2179 | 2742 | 563 | 95.9 | ok |
| comments_block.js | 13 | 61 | 2275 | 3282 | 1007 | 60.6 | ok |
| compare.js | 47 | 102 | 2794 | 4846 | 2052 | 49.7 | ok |
| compound.js | 18 | 66 | 2026 | 3000 | 974 | 67.8 | ok |
| compound_array.js | 48 | 196 | 2398 | 4692 | 2294 | 85.4 | ok |
| compound_ops.js | 33 | 143 | 2774 | 4888 | 2114 | 67.6 | ok |
| cond_logic.js | 65 | 796 | 2657 | 8986 | 6329 | 125.8 | ok |
| continue_for.js | 19 | 190 | 1925 | 4526 | 2601 | 73.0 | ok |
| continue_while.js | 25 | 224 | 2347 | 4863 | 2516 | 89.0 | ok |
| dangling_else.js | 30 | 81 | 2322 | 3467 | 1145 | 70.7 | ok |
| div_exact.js | 17 | 49 | 1985 | 3150 | 1165 | 42.1 | ok |
| else_chain.js | 38 | 138 | 2545 | 4449 | 1904 | 72.5 | ok |
| else_if_braceless.js | 38 | 138 | 2325 | 5280 | 2955 | 46.7 | ok |
| else_if_long.js | 137 | 565 | 5847 | 28612 | 22765 | 24.8 | ok |
| else_if_mixed.js | 33 | 70 | 2887 | 4903 | 2016 | 34.7 | ok |
| escapes_more.js | 13 | 45 | 2041 | 3701 | 1660 | 27.1 | ok |
| expr_stmt_call.js | 21 | 83 | 2087 | 3233 | 1146 | 72.4 | ok |
| fizzbuzz.js | 45 | 476 | 2776 | 13224 | 10448 | 45.6 | ok |
| for.js | 16 | 107 | 1801 | 3333 | 1532 | 69.8 | ok |
| for_dec.js | 17 | 97 | 1708 | 2959 | 1251 | 77.5 | ok |
| for_empty.js | 28 | 116 | 2183 | 3738 | 1555 | 74.6 | ok |
| func_basic.js | 23 | 68 | 2401 | 3585 | 1184 | 57.4 | ok |
| func_forward.js | 13 | 43 | 1768 | 2568 | 800 | 53.8 | ok |
| func_globals.js | 18 | 73 | 2168 | 3211 | 1043 | 70.0 | ok |
| func_locals.js | 24 | 65 | 2086 | 3260 | 1174 | 55.4 | ok |
| func_many_args.js | 20 | 50 | 1901 | 2867 | 966 | 51.8 | ok |
| func_noreturn.js | 12 | 50 | 1752 | 2535 | 783 | 63.9 | ok |
| func_shadow.js | 20 | 66 | 2060 | 3043 | 983 | 67.1 | ok |
| gcd.js | 30 | 123 | 2615 | 4897 | 2282 | 53.9 | ok |
| if_no_braces.js | 14 | 59 | 1863 | 2756 | 893 | 66.1 | ok |
| inc_dec.js | 12 | 60 | 1893 | 2686 | 793 | 75.7 | ok |
| is_prime.js | 49 | 503 | 2703 | 10336 | 7633 | 65.9 | ok |
| let_const.js | 23 | 118 | 2205 | 3721 | 1516 | 77.8 | ok |
| logic.js | 43 | 97 | 2442 | 4154 | 1712 | 56.7 | ok |
| mod.js | 18 | 50 | 1897 | 3253 | 1356 | 36.9 | ok |
| multi_args.js | 33 | 81 | 2304 | 5200 | 2896 | 28.0 | ok |
| neg.js | 19 | 67 | 2068 | 3289 | 1221 | 54.9 | ok |
| nested_calls_args.js | 26 | 59 | 2211 | 3753 | 1542 | 38.3 | ok |
| nested_fn_calls_bool.js | 32 | 84 | 2084 | 3391 | 1307 | 64.3 | ok |
| nested_loops.js | 32 | 242 | 2208 | 4671 | 2463 | 98.3 | ok |
| num_print.js | 14 | 46 | 1925 | 2963 | 1038 | 44.3 | ok |
| precedence.js | 35 | 67 | 2540 | 4322 | 1782 | 37.6 | ok |
| prefix_inc.js | 28 | 118 | 2180 | 3559 | 1379 | 85.6 | ok |
| print_unknown.js | 90 | 393 | 4108 | 13041 | 8933 | 44.0 | ok |
| putc.js | 13 | 45 | 1830 | 2824 | 994 | 45.3 | ok |
| return_early.js | 34 | 200 | 2592 | 5363 | 2771 | 72.2 | ok |
| short_circuit.js | 28 | 63 | 2323 | 3355 | 1032 | 61.0 | ok |
| short_circuit_side.js | 57 | 142 | 2663 | 5977 | 3314 | 42.8 | ok |
| single_quote.js | 12 | 60 | 1964 | 3505 | 1541 | 38.9 | ok |
| str_concat.js | 38 | 86 | 2775 | 6174 | 3399 | 25.3 | ok |
| str_escape.js | 13 | 45 | 2033 | 4052 | 2019 | 22.3 | ok |
| str_literal.js | 10 | 42 | 1886 | 3127 | 1241 | 33.8 | ok |
| str_mixed.js | 16 | 80 | 2115 | 3255 | 1140 | 70.2 | ok |
| str_param.js | 14 | 52 | 1880 | 3026 | 1146 | 45.4 | ok |
| str_return.js | 19 | 52 | 1926 | 3069 | 1143 | 45.5 | ok |
| str_table.js | 45 | 168 | 2729 | 6755 | 4026 | 41.7 | ok |
| str_var.js | 6 | 54 | 1747 | 2549 | 802 | 67.3 | ok |
| strict_eq.js | 17 | 65 | 1983 | 2961 | 978 | 66.5 | ok |
| strict_ops.js | 33 | 81 | 2048 | 4209 | 2161 | 37.5 | ok |
| unary_not.js | 9 | 41 | 1824 | 2559 | 735 | 55.8 | ok |
| var_multi.js | 51 | 197 | 2588 | 5754 | 3166 | 62.2 | ok |
| while.js | 15 | 115 | 1783 | 3272 | 1489 | 77.2 | ok |
| while_break.js | 15 | 86 | 1978 | 2921 | 943 | 91.2 | ok |
| while_true_return.js | 23 | 131 | 2410 | 4535 | 2125 | 61.6 | ok |
| assign_undef.js | 0 | 0 | 1662 | 1731 | 69 | – | error: undefined variable |
| bad_char.js | 0 | 0 | 1697 | 1771 | 74 | – | syntax error ( counter(cse) ) |
| break_outside.js | 0 | 0 | 1828 | 1915 | 87 | – | error: break outside a loop |
| extra_brace.js | 0 | 0 | 1742 | 1818 | 76 | – | error: unexpected } |
| fn_in_block.js | 0 | 0 | 1718 | 1787 | 69 | – | error: nested function |
| missing_brace.js | 5 | 0 | 1721 | 1792 | 71 | – | error: missing } |
| nested_function.js | 0 | 0 | 1712 | 1784 | 72 | – | error: nested function |
| return_outside.js | 0 | 0 | 1795 | 1871 | 76 | – | error: return outside a function |
| str_build.js | 0 | 0 | 1675 | 1745 | 70 | – | error: strings can only be joined in console.log |
| too_much_string.js | 0 | 0 | 2502 | 2592 | 90 | – | error: too much string data |
| unclosed_paren.js | 0 | 0 | 1704 | 1798 | 94 | – | syntax error ( counter(cse) ) |
| undef_fn.js | 13 | 0 | 1843 | 1922 | 79 | – | error: undefined function |
| undef_var.js | 0 | 0 | 1708 | 1783 | 75 | – | error: undefined variable |
| unterminated_str.js | 0 | 0 | 1917 | 1994 | 77 | – | syntax error ( counter(cse) ) |


---

## 6. Frame profile of the page

`RUN=1 RUNWAIT=3500 node machine/trace.js <page> 4`, then `python3 machine/passprof.py trace.json`. `passprof`
counts `LocalFrameView::UpdateStyleAndLayout` events over 1 ms and `InlineNode::ShapeTextIncludingFirstLine` events
over 2 ms between `Commit`s. The window (3.5–7.5 s after Run) sits inside every run.

| Trace (FizzBuzz, mid-run, 2026-10-17) | Frames | Passes per frame | Style+layout per frame | Shaping per frame | Frame |
|---|---|---|---|---|---|
| Before (`9319bc0`) | 26 | 3.00 | 115 ms | 45 ms | 141 ms |
| 3K (`a01eb0c`) | 26 | 3.00 | 115 ms | 46 ms | 142 ms |
| Current (16K sparse) | 25 | 3.00 | 124 ms | 43 ms | 148 ms |
| Idle editor scan (no Run) | 177 | 2.00 | 19 ms | 0 ms | 23 ms |
| CPU-only FizzBuzz, 16K (`WAIT=700`, 3 s) | 26 | 2.46 | 105 ms | 43 ms | 112 ms |

[old machine: before 115 / 34 / 143 ms; 3K 102 / 34 / 128 ms; 16K 108 / 35 / 137 ms; idle 16 / 0 / 20 ms; CPU-only
3K 93 / 36 / 97 ms.] Shaping takes about 30% longer per frame here than on the old machine; style and layout 0–15%.
The before and 3K pages now trace the same per frame. The 3K page's gain shows in run time instead (§5a: 476
steps instead of 1,329), and its paint change is outside `passprof`'s style+layout sum.

**Inside a pass** (old machine, 2026-10-13: invalidation-tracking trace of the before page, 2 s, 15 frames).
`StyleResolver::ResolveStyle` instants: 100,307, of which 97,931 inside `Layout` and 2,242 inside
`Document::recalcStyle`, i.e. about 1,300 per layout from the readers' container queries (`div.rb.rb2`, `div.sp`,
their children) and about 48 per recalc (`#cpu` and its ancestors; `recalcStyle` still takes 5.5 ms, almost all of
it `#cpu`'s ~900 custom properties). Layout invalidations per 15 frames: `.rb.rb2` 3,008 "Style changed" + 1,920
"Anchor positioning", `.sp` 2,063, the ~200 state-line spans 186–403 each ("Text changed" / "Style changed"). Per
frame: pass 1 ≈ 40 ms (17 ms shaping), pass 2 ≈ 38 ms (17 ms shaping), pass 3 ≈ 22–25 ms (no shaping): the settle
pass. These counts depend on the page, not the machine.

**The CPU-only page and the third pass** (old machine): a time-driven infinite animation added nothing (2.48 passes);
1,536 extra active view-timeline animations *removed* the third pass (2.00 passes). Why the full page always settles
and the CPU-only page mostly doesn't is not understood.

*(derived)* About 6.8 CPU frames per second on the full page; shaping is a third of style+layout time.

## 7. Editor text readback (scan)

`python3 readback/rb_only2.py rb.xhtml` (the standalone editor + frame-locked scan), then
`node readback/rbsweep.js rb.xhtml tests/fizz.js 3`: types the file, sets Run, waits for `--rbready`, and counts
unread or wrong cells.

| Rep | Sweep | Misses |
|---|---|---|
| 0 | 1,115 ms | 0 |
| 1 | 1,214 ms | 0 |
| 2 | 1,172 ms | 0 |

The scan advances one column per frame over P = 64 columns, so one sweep is ≥ 64 frames; *(derived)* ~18 ms per
column. [old: 1,178 / 1,178 / 1,206 ms.]

## 8. RAM size

**Group size of the sparse RAM** (`MEMGROUP=n UI=1 python3 machine/gen_fvm4.py build/ccimg.json build/f4cc_16 out.xhtml`;
real page, initial FizzBuzz, two interleaved rounds, 2026-10-17):

| Cells per group | compiledMs | haltMs |
|---|---|---|
| 16 | 2,491 / 2,498 | 10,251 / 10,220 |
| 64 | 2,433 / 2,423 | 10,206 / 10,295 |
| 256 (shipped) | 2,561 / 2,582 | 10,899 / 10,875 |

**On this machine 16 and 64 halt about 6% sooner than the shipped 256**, well beyond the ±0.5% A-vs-A noise. The old
measurement that chose 256 (real-page FizzBuzz 9.8 / 10.7 s with 256, 10.5 / 11.9 s with 64, 10.3 / 11.5 s with 16)
ran with another session loading the machine. This is a lead, not yet a change: re-check with `ab.js` and the L5
suite before switching.

**Dense against sparse** (old machine, 2026-10-13, branch `worktree-ram-expand`). The dense rendering (every cell
rendered and anchored) no longer exists in the generator, so this table can't be re-measured. CPU-only FizzBuzz
pages, HALT measured from load; frames from a 3 s trace starting 0.7 s after load:

| RAM words | page bytes (dense / sparse) | load, dense | HALT, dense | frame, dense | load, sparse | HALT, sparse | frame, sparse |
|---|---|---|---|---|---|---|---|
| 3,072 | 1.09 MB / 1.09 MB | 194–221 ms | 4,771–5,046 ms | 85 ms | 160 ms | 4,997 ms | 93 ms |
| 4,096 | 1.27 MB | 207–225 ms | 5,025–5,188 ms | 89 ms | – | – | – |
| 8,192 | 1.99 MB | 363 ms | 6,111–6,284 ms | 124 ms | – | – | – |
| 16,384 | 3.44 MB / 3.44 MB | 667–702 ms | 8,415–8,459 ms | 166 ms | 183 ms | 5,421 ms | 106 ms |
| 32,768 | 6.35 MB / 6.35 MB | 1,391 ms | 13,757–14,415 ms | 272 ms | 228 ms | 5,814 ms | 101 ms |

*(derived)* Dense: about 2.4 ms per pass per 1,000 cells, for cells the program never touches. The same pages with the
unused cells' `anchor-name` removed: 16K 114 ms, 32K 137 ms frames (HALT 6.2 / 8.6 s), so anchors are two thirds of it;
with the decode-tree nodes as blocks another ~5% (16K 106 ms, 32K 131 ms). Sparse: flat to within noise. The current
16K sparse CPU-only page on the mini PC: load 268–278 ms, HALT 6.27–6.40 s, frame 112 ms (§5c, §6).

Dead end, measured on the old machine: pushing the read block down the decode trees so that only four cells carry anchors made every
pass restyle the whole trees (16K: 38,000 `ResolveStyle` per pass, 90 ms per recalc; 3K HALT 9.6 s, 16K 15.9 s).

The real page with 16K sparse RAM against 3K dense is in §5a (HALT 10.9 against 10.6–10.8 s) and §6 (148 against
142 ms per frame). Page 11.9 MB (9.5 MB).

## 9. Caveats

- The headless runs have no GPU, so desktop Chrome timings will differ.
- The harness's own mouse moves show up in traces as hit testing (§6).
- Run comparisons back to back on one machine. The old-machine numbers in brackets come from an arm64 VM; earlier logs
  in `archive/results/` come from yet another sandbox.
