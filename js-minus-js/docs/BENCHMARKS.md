# Benchmarks

Every performance measurement of the current code, with how to re-run it.

**Conventions**

- Everything here was measured on **2026-10-13** in **headless Chromium 153.0.8010.12** (Chrome for Testing, from the
  Playwright 1.63 image), launched by `tools/browser.js` with `CHROME=/usr/local/bin/chromium`, in the project
  devcontainer: **arm64, 8 vCPUs** (Docker Desktop, linuxkit kernel), no GPU. Desktop Chrome will differ; the user's
  machine has not been measured.
- **"Before"** is the page as of commit `6f1d92e` (printing by lib routines, PUTC per character); **"after"** is
  the `worktree-js-optimize` branch (the PRINT instruction family, slim readback readers, the editor pane on its
  own compositor layer). Both were measured in the same session, back to back, the before numbers from
  `dist/js_in_css.xhtml` of that commit.
- *(derived)* marks a value computed from logged data.
- "Self-compile" means the self-hosted jsc (`archive/machine/image.json`) compiles FizzBuzz on the CPU, then runs it.
- Earlier versions of this file recorded measurements of pages, generators and fonts that no longer exist (the
  pure-CSS VM, cpu2, the fixed-program compile pages) and numbers from other chats. Those were removed on 2026-10-13
  because they can't be reproduced. [HISTORY.md](HISTORY.md) still tells that story, and the raw logs are in
  `archive/results/`. The earlier numbers came from a different sandbox and aren't comparable with these.

## Headline numbers

| What | Before | After | Section |
|---|---|---|---|
| FizzBuzz 1–15 on the page | 1,329 steps, 193 shapings; compiled ~2.3 s after Run, HALT at 14.0–14.7 s (run ≈ 12 s) | 476 steps, 103 shapings; compiled ~2.35 s, HALT at 8.5–8.6 s (run ≈ 6.2 s) | §5 |
| FizzBuzz on the CPU alone (no editor, no compile chain) | HALT 8.8–10.1 s after load | 4.8–4.9 s | §5c |
| Suite shapings (model, 89 programs) | 5,967 (traps: 1,478 MISS, 1,083 EXT, 1,342 PUTC) | 4,147 (1,309 MISS, 1,104 EXT, ~230 PRINT) | §1 |
| Font CPU on the page, L5 fit | ~112 steps/s (8.93 ms per step, r = 0.979, 84 programs) | 85 steps/s (11.7 ms per step, r = 0.797, 87 programs; a step now does more) | §5 |
| One CPU frame of the page (mid-run trace) | 3 passes, 115 ms style+layout, 34 ms shaping, 143 ms frame | 3 passes, 100–102 ms style+layout, 34 ms shaping, 125–128 ms frame | §6 |
| CSS compiler alone (L3 harness, no readback) | median 325 ms per program; ≈ 166 ms + 6.0 ms per code word | median 318 ms per program; ≈ 158 ms + 6.4 ms per code word | §4 |
| FizzBuzz in uharfbuzz alone (no browser) | 19.2 ms per shaping, 193 shapings (N16 S32) | 19.0 ms per shaping, 103 shapings | §3 |
| Self-compile in uharfbuzz alone | 9.9 ms per shaping, 2,919 shapings, 5.1 steps per shaping (N16 S16) | (not re-run) | §3 |
| Editor readback sweep | 1.18–1.21 s, 0 misses | unchanged | §7 |

**Where the time goes**

- **Run time.** It is set by shapings, because each shaping is a layout pass and a frame holds at most 2. Traps
  (cache misses, write-backs, EXT ops, PRINT chunks, PUTC) end shapings early.
- **Per pass** (mid-run trace, after): about 17 ms of HarfBuzz shaping, 5 ms restyling `#cpu`, and layout with the
  readers' container-query restyles inside it; plus a third, settle pass without a shaping every frame (§6).
- **Predicting it.** `tools/traps.py prog.js` gives a program's shapings from the model without a browser.
- **Compile time on the page.** It is mostly the readback sweep after Run, plus the chain (§5 vs §4).

## How to measure

| Question | Command | Notes |
|---|---|---|
| Shapings for a program (model) | `python3 tools/traps.py prog.js…` | `uarch4` model, N16 S32. Instant. |
| Compiler size | `python3 tools/vsz.py`, `python3 tools/lp.py` | Variants before the page's no-op merge. |
| HarfBuzz alone | `CPUMOD=cpu4 python3 machine/hbtest.py image.json N S [maxshapings]` | Writes `cpu.ttf` in the cwd. The image must hold the program's code: `build/ccimg.json` doesn't (the page's CSS compiler supplies it), so it never halts. Use `archive/machine/image.json`, or build an image the way `tests/suite_machine.py` does. |
| CSS compiler in Chrome | `make l3`, or for every line: `node tests/suite_css.js build/suite_css.xhtml` | Run → done, without readback. |
| Typed-input chain alone | `python3 tests/ui_test.py tests/fizz.js out.xhtml && node tests/uitest.js out.xhtml` | Fake latch cells, no editor. |
| The real page | `make l5` / `make l5-smoke`, or `EXP1=build/ui_exp/fizzbuzz.grid node machine/ui_seq.js build/js_in_css.xhtml` | `compiledMs` includes the readback sweep; `haltMs` is Run → HALT (the page's `--isHALT`). `machine/ui_run.js page` also reports the first step. |
| The CPU alone | a RAM image with the program (as `tests/suite_machine.py` builds it; `expected` = the console grid), `python3 machine/gen_fvm4.py img.json build/f4cc_16 out.html`, `IMG=img.json node machine/halttime.js out.html` | No editor, no compile chain: the CPU starts at load. |
| Where a frame goes | `RUN=1 RUNWAIT=3500 node machine/trace.js build/js_in_css.xhtml 4 && python3 machine/passprof.py trace.json` | Without `RUN=1` it traces the idle editor scan. The window must sit inside the run (FizzBuzz halts ~8.5 s after Run). `WAIT` (ms after load, default 3000) for CPU-only pages. Writes `trace.json` in the cwd. |
| Readback sweep | `python3 readback/rb_only2.py rb.xhtml && node readback/rbsweep.js rb.xhtml tests/fizz.js 3` | |

`machine/halttime.js`, `fullrun.js` and `bench2.js` never press Run; they are for CPU-only (fixed-program) pages. `readback/rbtest.js` reads the old `--v` latches without pressing Run and reports `match false` on the
current readback page; use `rbsweep.js`.

---

## 1. Machine model (no browser)

`python3 tools/traps.py <files>` (uarch4, N16 S32), and the reference simulator's `steps` from `compiler/mkimage.py`.
After (PRINT family; EXT is MUL / DIV / MOD / SHL13, PRINT a console-output chunk, PUTC a `putc()` call):

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

**Configurations that were modelled and not built** (suite shapings, after): N = 24 lines 3,888; N = 32 3,858;
S = 48 cycles 3,427; S = 64 3,161; N32 S64 2,848. The sanitizer caps S × 432 subtables at 16,384 (S ≤ 37), and
HarfBuzz time grows with cells × lookups × S. A code / data partition of the 16 lines: 4,368–4,713 (worse).

## 2. The CSS compiler's size

Source: `tools/vsz.py`, `tools/lp.py`, the `make page` build line, and `make l2` / `make l2-generic`.

| Measure | Value |
|---|---|
| Parser variants | 319 before the no-op merge; 299 + 1 pass-through on the page |
| Temps, all variants | 56,505 (56,673 before the PRINT family) |
| Label ports per level | 22 |
| Levels | 1,561 character levels, 401 token levels |
| Compile-chain CSS | 7.4 MB (7,407,608 bytes; 7,515,752 before) |
| Page | 9.5 MB (9,514,312 bytes; 9,612,666 before) |
| `make page` | 25 s, reproducible |
| L2 DSL evaluation (FizzBuzz suite, 4,931 parser steps) | 292 temps per step with the specialised variants; 3,795 with the generic parser |

## 3. HarfBuzz alone (uharfbuzz 0.56.3, no browser)

`machine/hbtest.py` shapes the real cpu4 font in HarfBuzz and checks every shaping against `uarch4`. The font build
line reads `9875 glyphs, 1274 cells, 111 lookups/cycle, 432 subtables/cycle, 217 lib` (before the PRINT family:
9749 glyphs, 199 lib).

| Workload | N, S | Shapings | Steps | Result | HarfBuzz time |
|---|---|---|---|---|---|
| FizzBuzz, after (RAM image built as in `tests/suite_machine.py`) | 16, 32 | 103 | 476 | halted, every shaping matches the model | 19.02 ms per shaping |
| FizzBuzz, before | 16, 32 | 193 | 1329 | halted, output ok | 19.15 ms per shaping |
| Self-compile (`archive/machine/image.json`, before) | 16, 16 | 2,919 | 14,985 | halted, output ok | 9.88 ms per shaping |

*(derived)* FizzBuzz after: 4.6 steps per shaping, 2.0 s of HarfBuzz time; before: 6.9 steps per shaping, 3.7 s. Self-compile: 5.1 steps per
shaping, 28.8 s of HarfBuzz time, ~520 steps/s. The self-compile's shaping and step counts are identical to the
2026-10-09 log `archive/results/machine/hb4_img.log`, which recorded 34.13 ms per shaping in the old sandbox; that
also shows the log's unrecorded S was 16.

## 4. The CSS compiler in Chrome

### 4a. L3 suite, per program

`make l3` (`tests/suite_css.py` + `tests/suite_css.js`): one page; each program is written into the latch cells, Run
is pressed, and the harness times Run → the chain's done anchor and checks every word against `cc_ref`.

- After (2026-10-13, this branch): **103/103 pass** (`load 184 ms`). Valid programs: min 194 / median 318 / max 1037 ms;
  the fit is ms ≈ 158 + 6.4 × words (r = 0.90) *(derived)*. Error programs: median 184 ms.
  FizzBuzz: 427 ms, 45 words. The compiler change (one PRINT word per `console.log` argument instead of
  CALL / POP / PUSHI / PUTC) left compile time where it was.
- Before (2026-10-13 morning): `load 145 ms`. **103/103 pass** (89 valid programs, 14 error programs). `make l3` took 1 min 13 s.
- Valid programs: min 190 / median 325 / max 1,072 ms (`else_if_long`, 140 words) *(derived)*. A linear fit gives
  ms ≈ 166 + 6.0 × words (r = 0.89) *(derived)*.
- Error programs: 170–477 ms, median 215 *(derived)*. Two report err 99 where the reference has a specific code
  (`bad_char` wants 48, `unterminated_str` wants 3); L3 counts any nonzero error as ok.
- Slowest valid programs: else_if_long 1072 ms/140 w, asi_control 835/58, print_unknown 793/115, array_sort 788/65,
  asi_brace 698/72, bubble_sort_print 622/78, asi_continuation 598/42, compare 587/47. FizzBuzz: 478 ms, 45 words.

### 4b. The typed-input chain driven by fake latch cells

`python3 tests/ui_test.py tests/fizz.js out.xhtml && node tests/uitest.js out.xhtml` (times Run → the chain's done
anchor):
`{"loadMs":140,"doneMs":486,"recalcMs":451,"layoutMs":8,"recalcs":2,"done":1,"err":0,"words":45,"ok":1}`

---

## 5. Full page end-to-end (editor → CSS compiler → font CPU): L5 suite

### 5a. FizzBuzz alone, before and after (`machine/ui_seq.js`, initial program, nothing else running)

| Build | compiledMs | haltMs | run (haltMs − compiledMs) |
|---|---|---|---|
| Before (`6f1d92e`), two runs | 2,519 / 2,201 | 14,659 / 13,987 | 12,140 / 11,786 |
| PRINT family | 2,448 / 2,468 | 9,539 / 9,775 | 7,091 / 7,307 |
| + slim readers | 2,753 / 2,655 | 9,698 / 9,335 | 6,945 / 6,680 |
| + `#app` on its own layer (after) | 2,373 / 2,336 | 8,600 / 8,477 | 6,227 / 6,141 |

Run-to-run noise is about ±0.2 s. *(derived)* execution 12.0 s → 6.2 s (1.9×); 476 steps in 6.2 s is 77 steps/s
of a program that used to need 1,329 steps, i.e. the same work in half the time.

### 5c. The CPU alone (`machine/halttime.js` on CPU-only pages, from load to HALT)

| Program | Before | After |
|---|---|---|
| FizzBuzz (`tests/fizz.js`) | 10,060 / 8,784 ms (1,329 steps) | 5,908 → 4,831 (slim readers) → 4,858 ms (476 steps) |
| `str_table.js` | – | 2,722 → 2,158 ms (168 steps) |
| `bool_print.js` | – | correct output, 48 steps |

### 5b. The L5 suite, after

`make l5` (`machine/ui_seq.js` with `tests/suite_ui.py 1500`). It acts as a user: it waits for the scan, then for each
program it clicks Edit, retypes the editor, clicks Run, and polls every 100 ms. `compiledMs` is the time from the Run
click until the status shows compiled or error. `haltMs` is the time from the Run click until the page's `--isHALT`
is 1 or an error shows. Font = `f4cc_16` (N16 S32 B4). Viewport 1300×950. Nothing else was running.

Summary *(derived)*:
- `load ms 303`. 101 runs: the initial program plus 100 suite entries (87 run to HALT, 14 compile errors). **101 of 101 ok.**
- Compile (Run → compiled), valid programs: min 1,598 / median 1,750 / max 4,817 ms.
  The fit is compiledMs ≈ 1,356 + 18.5 × words (r = 0.86).
- Error detection: 1,632–1,999 ms, median 1,657.
- Execution (haltMs − compiledMs): min 448 / median 1,128 / max 17,856 ms. The fit is ≈ 99 + **11.74 ms per step**
  (r = 0.797), which is about **85 steps/s**. Per program the rate ranges from 30.1 to 169.4 steps/s, median 86.3.
  (Steps are not comparable with the before numbers: a PRINT step does the work of a dozen old ones.)
- FizzBuzz (476 steps, 45 words): compiled 2,254 ms, HALT at 8,629 ms, run ≈ 6.4 s. The first
  ("initial") FizzBuzz run took 2,346 / 8,716 ms.
- The whole suite took Σ haltMs = 353 s (before: 401 s for 98 runs).

Full table (generated from the log with `l5table.py`):

| program | words | steps | compiledMs | haltMs | run ms | steps/s | status |
|---|---|---|---|---|---|---|---|
| initial | 45 | 476 | 2346 | 8716 | 6370 | 74.7 | ok |
| user_report.js | 6 | 54 | 1639 | 2193 | 554 | 97.5 | ok |
| and_or_chain.js | 86 | 134 | 2041 | 4363 | 2322 | 57.7 | ok |
| and_or_value.js | 22 | 52 | 1635 | 2483 | 848 | 61.3 | ok |
| array_basic.js | 17 | 129 | 1721 | 2807 | 1086 | 118.8 | ok |
| array_loop.js | 23 | 210 | 1721 | 2961 | 1240 | 169.4 | ok |
| array_neg.js | 13 | 173 | 1638 | 2676 | 1038 | 166.7 | ok |
| array_param.js | 31 | 184 | 1991 | 3398 | 1407 | 130.8 | ok |
| array_sort.js | 65 | 635 | 2458 | 7058 | 4600 | 138.0 | ok |
| array_write.js | 25 | 121 | 1683 | 2773 | 1090 | 111.0 | ok |
| asi_basic.js | 31 | 93 | 2173 | 3627 | 1454 | 64.0 | ok |
| asi_brace.js | 72 | 268 | 2957 | 6010 | 3053 | 87.8 | ok |
| asi_continuation.js | 39 | 167 | 2553 | 4541 | 1988 | 84.0 | ok |
| asi_control.js | 58 | 234 | 2834 | 5740 | 2906 | 80.5 | ok |
| asi_mixed.js | 39 | 134 | 2114 | 3534 | 1420 | 94.4 | ok |
| big.js | 27 | 59 | 1646 | 3051 | 1405 | 42.0 | ok |
| bool_fn.js | 25 | 69 | 1703 | 3059 | 1356 | 50.9 | ok |
| bool_literal.js | 18 | 79 | 1791 | 2645 | 854 | 92.5 | ok |
| bool_print.js | 16 | 48 | 1620 | 2356 | 736 | 65.2 | ok |
| bool_var.js | 24 | 88 | 1802 | 2917 | 1115 | 78.9 | ok |
| braceless_loops.js | 52 | 269 | 1894 | 4414 | 2520 | 106.7 | ok |
| break_nested.js | 36 | 341 | 1945 | 4423 | 2478 | 137.6 | ok |
| bubble_sort_print.js | 75 | 901 | 2438 | 12847 | 10409 | 86.6 | ok |
| comments.js | 6 | 54 | 1847 | 2306 | 459 | 117.6 | ok |
| comments_block.js | 13 | 61 | 1993 | 2654 | 661 | 92.3 | ok |
| compare.js | 47 | 102 | 2252 | 3735 | 1483 | 68.8 | ok |
| compound.js | 18 | 66 | 1861 | 2642 | 781 | 84.5 | ok |
| compound_array.js | 48 | 196 | 2073 | 3981 | 1908 | 102.7 | ok |
| compound_ops.js | 33 | 143 | 1854 | 3511 | 1657 | 86.3 | ok |
| cond_logic.js | 65 | 796 | 2468 | 7483 | 5015 | 158.7 | ok |
| continue_for.js | 19 | 190 | 1728 | 3682 | 1954 | 97.2 | ok |
| continue_while.js | 25 | 224 | 2069 | 4151 | 2082 | 107.6 | ok |
| dangling_else.js | 30 | 81 | 1915 | 2871 | 956 | 84.7 | ok |
| div_exact.js | 17 | 49 | 1639 | 2605 | 966 | 50.7 | ok |
| else_chain.js | 38 | 138 | 2236 | 4028 | 1792 | 77.0 | ok |
| else_if_braceless.js | 38 | 138 | 2180 | 4467 | 2287 | 60.3 | ok |
| else_if_long.js | 137 | 565 | 4817 | 22673 | 17856 | 31.6 | ok |
| else_if_mixed.js | 33 | 70 | 2414 | 4155 | 1741 | 40.2 | ok |
| escapes_more.js | 13 | 45 | 1716 | 2924 | 1208 | 37.3 | ok |
| expr_stmt_call.js | 21 | 83 | 1668 | 2511 | 843 | 98.5 | ok |
| fizzbuzz.js | 45 | 476 | 2254 | 8629 | 6375 | 74.7 | ok |
| for.js | 16 | 107 | 1617 | 2711 | 1094 | 97.8 | ok |
| for_dec.js | 17 | 97 | 1665 | 2542 | 877 | 110.6 | ok |
| for_empty.js | 28 | 116 | 1708 | 2836 | 1128 | 102.8 | ok |
| func_basic.js | 23 | 68 | 1817 | 2679 | 862 | 78.9 | ok |
| func_forward.js | 13 | 43 | 1677 | 2125 | 448 | 96.0 | ok |
| func_globals.js | 18 | 73 | 1757 | 2471 | 714 | 102.2 | ok |
| func_locals.js | 24 | 65 | 1712 | 2593 | 881 | 73.8 | ok |
| func_many_args.js | 20 | 50 | 1638 | 2305 | 667 | 75.0 | ok |
| func_noreturn.js | 12 | 50 | 1750 | 2264 | 514 | 97.3 | ok |
| func_shadow.js | 20 | 66 | 1739 | 2443 | 704 | 93.8 | ok |
| gcd.js | 30 | 123 | 1843 | 3324 | 1481 | 83.1 | ok |
| if_no_braces.js | 14 | 59 | 1669 | 2130 | 461 | 128.0 | ok |
| inc_dec.js | 12 | 60 | 1665 | 2129 | 464 | 129.3 | ok |
| is_prime.js | 49 | 503 | 1995 | 7439 | 5444 | 92.4 | ok |
| let_const.js | 23 | 118 | 1725 | 2751 | 1026 | 115.0 | ok |
| logic.js | 43 | 97 | 1847 | 2976 | 1129 | 85.9 | ok |
| mod.js | 18 | 50 | 1598 | 2480 | 882 | 56.7 | ok |
| multi_args.js | 33 | 81 | 1828 | 3794 | 1966 | 41.2 | ok |
| neg.js | 19 | 67 | 1672 | 2562 | 890 | 75.3 | ok |
| nested_calls_args.js | 26 | 59 | 1734 | 2563 | 829 | 71.2 | ok |
| nested_fn_calls_bool.js | 32 | 84 | 1722 | 2663 | 941 | 89.3 | ok |
| nested_loops.js | 32 | 242 | 1767 | 3689 | 1922 | 125.9 | ok |
| num_print.js | 14 | 46 | 1666 | 2309 | 643 | 71.5 | ok |
| precedence.js | 35 | 67 | 1751 | 3062 | 1311 | 51.1 | ok |
| prefix_inc.js | 28 | 118 | 1704 | 2848 | 1144 | 103.1 | ok |
| print_unknown.js | 90 | 371 | 3551 | 10658 | 7107 | 52.2 | ok |
| putc.js | 13 | 45 | 1689 | 2314 | 625 | 72.0 | ok |
| return_early.js | 34 | 200 | 1902 | 3792 | 1890 | 105.8 | ok |
| short_circuit.js | 28 | 63 | 1727 | 2407 | 680 | 92.6 | ok |
| short_circuit_side.js | 57 | 142 | 1996 | 4326 | 2330 | 60.9 | ok |
| single_quote.js | 12 | 60 | 1694 | 2590 | 896 | 67.0 | ok |
| str_concat.js | 38 | 86 | 1838 | 4084 | 2246 | 38.3 | ok |
| str_escape.js | 13 | 45 | 1612 | 3107 | 1495 | 30.1 | ok |
| str_literal.js | 10 | 42 | 1706 | 2569 | 863 | 48.7 | ok |
| str_mixed.js | 16 | 80 | 1675 | 2591 | 916 | 87.3 | ok |
| str_param.js | 14 | 52 | 1695 | 2377 | 682 | 76.2 | ok |
| str_return.js | 19 | 52 | 1666 | 2524 | 858 | 60.6 | ok |
| str_table.js | 45 | 168 | 1907 | 4572 | 2665 | 63.0 | ok |
| str_var.js | 6 | 54 | 1656 | 2111 | 455 | 118.7 | ok |
| strict_eq.js | 17 | 65 | 1603 | 2279 | 676 | 96.2 | ok |
| strict_ops.js | 33 | 81 | 1709 | 3112 | 1403 | 57.7 | ok |
| unary_not.js | 9 | 41 | 1640 | 2133 | 493 | 83.2 | ok |
| var_multi.js | 51 | 197 | 1907 | 4038 | 2131 | 92.4 | ok |
| while.js | 15 | 115 | 1694 | 2589 | 895 | 128.5 | ok |
| while_break.js | 15 | 86 | 1632 | 2270 | 638 | 134.8 | ok |
| while_true_return.js | 23 | 131 | 1916 | 3362 | 1446 | 90.6 | ok |
| assign_undef.js | 0 | 0 | 1607 | 1657 | 50 | – | error: undefined variable |
| bad_char.js | 0 | 0 | 1607 | 1657 | 50 | – | syntax error ( counter(cse) ) |
| break_outside.js | 0 | 0 | 1611 | 1664 | 53 | – | error: break outside a loop |
| extra_brace.js | 0 | 0 | 1582 | 1634 | 52 | – | error: unexpected } |
| fn_in_block.js | 0 | 0 | 1597 | 1652 | 55 | – | error: nested function |
| missing_brace.js | 5 | 0 | 1586 | 1636 | 50 | – | error: missing } |
| nested_function.js | 0 | 0 | 1608 | 1663 | 55 | – | error: nested function |
| return_outside.js | 0 | 0 | 1616 | 1670 | 54 | – | error: return outside a function |
| str_build.js | 0 | 0 | 1579 | 1634 | 55 | – | error: strings can only be joined in console.log |
| too_much_string.js | 0 | 0 | 1935 | 1999 | 64 | – | error: too much string data |
| unclosed_paren.js | 0 | 0 | 1581 | 1634 | 53 | – | syntax error ( counter(cse) ) |
| undef_fn.js | 13 | 0 | 1641 | 1697 | 56 | – | error: undefined function |
| undef_var.js | 0 | 0 | 1586 | 1632 | 46 | – | error: undefined variable |
| unterminated_str.js | 0 | 0 | 1805 | 1857 | 52 | – | syntax error ( counter(cse) ) |

---

## 6. Frame profile of the page

`RUN=1 RUNWAIT=3500 node machine/trace.js <page> 4`, then `python3 machine/passprof.py trace.json`. `passprof`
counts `LocalFrameView::UpdateStyleAndLayout` events over 1 ms and `InlineNode::ShapeTextIncludingFirstLine` events
over 2 ms between `Commit`s. The window (3.5–7.5 s after Run) sits inside every run; the earlier 8–14 s window
was fine for the 14 s "before" run but covers idle frames after HALT for the 8.5 s "after" run (shaping 17 ms per
frame there instead of 34), so those traces were discarded.

| Trace (FizzBuzz, mid-run) | Frames | Passes per frame | Style+layout per frame | Shaping per frame | Frame |
|---|---|---|---|---|---|
| Before (`dist/js_in_css.xhtml` of `6f1d92e`) | 27 | 3.00 | 115 ms | 34 ms | 143 ms |
| PRINT family + slim readers | 31 | 3.00 | 100 ms | 34 ms | 125 ms |
| + `#app` on its own layer (after) | 30 | 3.00 | 102 ms | 34 ms | 128 ms |
| Before, 8–14 s window (2026-10-13 morning) | 47 | 3.00 | 101–103 ms | 34 ms | 125–128 ms |
| Idle editor scan (no Run) | 296 | 2.00 | 16 ms | 0 ms | 20 ms |

The paint change shows in run time (§5: 9.3–9.7 → 8.5–8.6 s) rather than here: `passprof` sums style and layout,
and paint recording is outside both.

**Inside a pass** (invalidation-tracking trace of the before page, 2 s, 15 frames). `StyleResolver::ResolveStyle`
instants: 100,307, of which 97,931 inside `Layout` and 2,242 inside `Document::recalcStyle`, i.e. about 1,300 per
layout from the readers' container queries (`div.rb.rb2`, `div.sp`, their children) and about 48 per recalc
(`#cpu` and its ancestors; `recalcStyle` still takes 5.5 ms, almost all of it `#cpu`'s ~900 custom properties).
Layout invalidations per 15 frames: `.rb.rb2` 3,008 "Style changed" + 1,920 "Anchor positioning", `.sp` 2,063,
the ~200 state-line spans 186–403 each ("Text changed" / "Style changed"). Per frame: pass 1 ≈ 40 ms (17 ms
shaping), pass 2 ≈ 38 ms (17 ms shaping), pass 3 ≈ 22–25 ms (no shaping): the settle pass.

**The same CPU without the editor and compile chain** (CPU-only FizzBuzz page, `machine/gen_fvm4.py` without
`UI=1`, trace 0.7–3.7 s after load, after): 2.46 passes per frame, 93 ms style+layout, 36 ms shaping, 97 ms frame;
over the whole run it halts 4.8 s after load (before: 8.8–10.1 s, 2.25 passes per frame, 66 ms frames in a late
window). Experiments on that page (each a 3 s trace): a time-driven infinite animation added nothing (2.48 passes,
103 ms); 1,536 extra active view-timeline animations (the latch registers' worth) *removed* the third pass
(2.00 passes, 93 ms). Why the full page always settles and the CPU-only page mostly doesn't is not understood.

*(derived)* About 7.8 CPU frames per second on the full page; shaping is a third of style+layout time; the settle
pass is about 18% of a frame.

## 7. Editor text readback (scan)

`python3 readback/rb_only2.py rb.xhtml` (the standalone editor + frame-locked scan), then
`node readback/rbsweep.js rb.xhtml tests/fizz.js 3`: types the file, sets Run, waits for `--rbready`, and counts
unread or wrong cells.

| Rep | Sweep | Misses |
|---|---|---|
| 0 | 1,178 ms | 0 |
| 1 | 1,178 ms | 0 |
| 2 | 1,206 ms | 0 |

The scan advances one column per frame over P = 64 columns, so one sweep is ≥ 64 frames; *(derived)* ~18 ms per column.

## 8. Caveats

- The headless runs have no GPU, so desktop Chrome timings will differ.
- The harness's own mouse moves show up in traces as hit testing (§6).
- Run comparisons back to back on one machine; these numbers came from a different sandbox than the earlier logs in
  `archive/results/`.
