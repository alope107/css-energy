# Benchmarks

Every performance measurement of the current code, with how to re-run it.

**Conventions**

- Everything here was measured on **2026-10-13** in **headless Chromium 153.0.8010.12** (Chrome for Testing, from the
  Playwright 1.63 image), launched by `tools/browser.js` with `CHROME=/usr/local/bin/chromium`, in the project
  devcontainer: **arm64, 8 vCPUs** (Docker Desktop, linuxkit kernel), no GPU. Desktop Chrome will differ; the user's
  machine has not been measured.
- *(derived)* marks a value computed from logged data.
- "Self-compile" means the self-hosted jsc (`archive/machine/image.json`) compiles FizzBuzz on the CPU, then runs it.
- Earlier versions of this file recorded measurements of pages, generators and fonts that no longer exist (the
  pure-CSS VM, cpu2, the fixed-program compile pages) and numbers from other chats. Those were removed on 2026-10-13
  because they can't be reproduced. [HISTORY.md](HISTORY.md) still tells that story, and the raw logs are in
  `archive/results/`. The earlier numbers came from a different sandbox and aren't comparable with these.

## Headline numbers

| What | Number | Section |
|---|---|---|
| Font CPU on the page | ~112 steps/s (8.93 ms per step, r = 0.979 across 84 programs) | §5 |
| FizzBuzz 1–15 on the page (1,329 steps) | compiled ~2.3 s after Run, HALT at ~13.8–14.4 s | §5 |
| CSS compiler alone (L3 harness, no readback) | median 325 ms per program; ≈ 166 ms + 6.0 ms per code word | §4 |
| One CPU frame of the page (trace) | 3 passes, 103 ms style+layout, 34 ms shaping, 128 ms frame | §6 |
| FizzBuzz in uharfbuzz alone (no browser) | 19.2 ms per shaping, 193 shapings (N16 S32) | §3 |
| Self-compile in uharfbuzz alone | 9.9 ms per shaping, 2,919 shapings, 5.1 steps per shaping (N16 S16) | §3 |
| Editor readback sweep | 1.18–1.21 s, 0 misses | §7 |

**Where the time goes**

- **Run time.** It is set by shapings, because each shaping is a layout pass and a frame holds at most 2. Traps
  (cache misses, write-backs, EXT ops, PUTC) end shapings early.
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
| The real page | `make l5` / `make l5-smoke`, or `EXP1=build/ui_exp/fizzbuzz.grid node machine/ui_seq.js build/js_in_css.xhtml` | `compiledMs` includes the readback sweep; `haltMs` is Run → HALT. `machine/ui_run.js page` also reports the first step. |
| Where a frame goes | `RUN=1 node machine/trace.js build/js_in_css.xhtml 6 && python3 machine/passprof.py trace.json` | Without `RUN=1` it traces the idle editor scan. Writes `trace.json` in the cwd. |
| Readback sweep | `python3 readback/rb_only2.py rb.xhtml && node readback/rbsweep.js rb.xhtml tests/fizz.js 3` | |

`machine/halttime.js`, `fullrun.js` and `bench2.js` never press Run; they were written for the old fixed-program
pages. `readback/rbtest.js` reads the old `--v` latches without pressing Run and reports `match false` on the
current readback page; use `rbsweep.js`.

---

## 1. Machine model (no browser)

`python3 tools/traps.py <files>` (uarch4, N16 S32), and the reference simulator's `steps` from `compiler/mkimage.py`.

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

The reference simulator counts FizzBuzz as 1330 steps; the font CPU's count is always one lower.

## 2. The CSS compiler's size

Source: `tools/vsz.py`, `tools/lp.py`, the `make page` build line, and `make l2` / `make l2-generic`.

| Measure | Value |
|---|---|
| Parser variants | 319 before the no-op merge; 299 + 1 pass-through on the page |
| Temps, all variants | 56,673 |
| Label ports per level | 22 |
| Levels | 1,561 character levels, 401 token levels |
| Compile-chain CSS | 7.5 MB (7,515,752 bytes) |
| Page | 9.6 MB (9,612,666 bytes), 3,791 `@property` rules |
| `make page` | 25 s, byte-identical to `dist/js_in_css.xhtml` |
| L2 DSL evaluation (FizzBuzz suite, 4,931 parser steps) | 292 temps per step with the specialised variants; 3,795 with the generic parser |

## 3. HarfBuzz alone (uharfbuzz 0.56.3, no browser)

`machine/hbtest.py` shapes the real cpu4 font in HarfBuzz and checks every shaping against `uarch4`. The font build
line reads `9749 glyphs, 1274 cells, 111 lookups/cycle, 432 subtables/cycle, 199 lib`.

| Workload | N, S | Shapings | Steps | Result | HarfBuzz time |
|---|---|---|---|---|---|
| FizzBuzz (`tests/suite/fizzbuzz.js`, RAM image built as in `tests/suite_machine.py`) | 16, 32 | 193 | 1329 | halted, output ok | 19.15 ms per shaping |
| Self-compile (`archive/machine/image.json`) | 16, 16 | 2,919 | 14,985 | halted, output ok | 9.88 ms per shaping |

*(derived)* FizzBuzz: 6.9 steps per shaping, 3.7 s of HarfBuzz time, ~360 steps/s. Self-compile: 5.1 steps per
shaping, 28.8 s of HarfBuzz time, ~520 steps/s. The self-compile's shaping and step counts are identical to the
2026-10-09 log `archive/results/machine/hb4_img.log`, which recorded 34.13 ms per shaping in the old sandbox; that
also shows the log's unrecorded S was 16.

## 4. The CSS compiler in Chrome

### 4a. L3 suite, per program

`make l3` (`tests/suite_css.py` + `tests/suite_css.js`): one page; each program is written into the latch cells, Run
is pressed, and the harness times Run → the chain's done anchor and checks every word against `cc_ref`.

- `load 145 ms`. **103/103 pass** (89 valid programs, 14 error programs). `make l3` took 1 min 13 s.
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

`make l5` (`machine/ui_seq.js` with `tests/suite_ui.py 1500`). It acts as a user: it waits for the scan, then for each
program it clicks Edit, retypes the editor, clicks Run, and polls every 100 ms. `compiledMs` is the time from the Run
click until the status shows compiled or error. `haltMs` is the time from the Run click until `--kind` = 97 (HALT) or
an error. Font = `f4cc_16` (N16 S32 B4). Viewport 1300×950. The run took 9 min 43 s; `hbtest.py` and page builds were
running on other cores for its first few minutes.

Summary *(derived)*:
- `load ms 301`. 98 runs: the initial program plus 97 suite entries (84 run to HALT, 14 compile errors). **All 98 ok.**
- Compile (Run → compiled), valid programs: min 1,570 / median 1,794 / max 3,402 ms (asi_brace, 72 words).
  The fit is compiledMs ≈ 1,521 + 13.0 × words (r = 0.67).
- Error detection: 1,541–1,998 ms, median 1,576.
- Execution (haltMs − compiledMs): min 645 / median 1,842 / max 13,105 ms. The fit is ≈ −101 + **8.93 ms per step**
  (r = 0.979), which is about **112 steps/s**. Per program the rate ranges from 75.6 to 172.3 steps/s, median 114.9.
- FizzBuzz (1,329 steps, 45 words): compiled 2,608 ms, HALT at 15,713 ms, run ≈ 13.1 s ≈ 101 steps/s. The first
  ("initial") FizzBuzz run took 2,250 / 13,829 ms.
- The whole suite took Σ haltMs = 401 s.

**FizzBuzz alone, nothing else running** (`machine/ui_seq.js`, initial program, three runs back to back): compiled
2,366 / 2,283 / 2,285 ms, HALT 14,400 / 13,969 / 13,997 ms. `machine/ui_run.js`: compiled 2,289 ms, first step
2,519 ms, HALT 13,779 ms. Run-to-run noise is about ±0.3 s on ~14 s.

Full table (generated from the log):

| program | words | steps | compiledMs | haltMs | run ms | steps/s | status |
|---|---|---|---|---|---|---|---|
| initial | 45 | 1329 | 2250 | 13829 | 11579 | 114.8 | ok |
| user_report.js | 6 | 105 | 1635 | 2285 | 650 | 161.5 | ok |
| and_or_chain.js | 86 | 347 | 2171 | 5547 | 3376 | 102.8 | ok |
| and_or_value.js | 22 | 145 | 1624 | 2760 | 1136 | 127.6 | ok |
| array_basic.js | 17 | 306 | 1717 | 3892 | 2175 | 140.7 | ok |
| array_loop.js | 23 | 273 | 1768 | 3444 | 1676 | 162.9 | ok |
| array_neg.js | 13 | 229 | 1631 | 2960 | 1329 | 172.3 | ok |
| array_param.js | 31 | 247 | 2056 | 4084 | 2028 | 121.8 | ok |
| array_sort.js | 65 | 786 | 2623 | 8990 | 6367 | 123.4 | ok |
| array_write.js | 25 | 241 | 1803 | 3899 | 2096 | 115.0 | ok |
| asi_basic.js | 31 | 331 | 2325 | 5638 | 3313 | 99.9 | ok |
| asi_brace.js | 72 | 418 | 3402 | 8129 | 4727 | 88.4 | ok |
| asi_continuation.js | 42 | 388 | 2772 | 7102 | 4330 | 89.6 | ok |
| asi_control.js | 58 | 379 | 3139 | 7171 | 4032 | 94.0 | ok |
| asi_mixed.js | 39 | 235 | 2228 | 4532 | 2304 | 102.0 | ok |
| big.js | 27 | 758 | 1811 | 8595 | 6784 | 111.7 | ok |
| bool_fn.js | 25 | 290 | 1824 | 4459 | 2635 | 110.1 | ok |
| bool_literal.js | 18 | 145 | 1782 | 3067 | 1285 | 112.8 | ok |
| bool_print.js | 16 | 147 | 1624 | 3054 | 1430 | 102.8 | ok |
| bool_var.js | 24 | 216 | 2045 | 4223 | 2178 | 99.2 | ok |
| braceless_loops.js | 52 | 563 | 2005 | 6494 | 4489 | 125.4 | ok |
| break_nested.js | 36 | 347 | 1862 | 4498 | 2636 | 131.6 | ok |
| comments.js | 6 | 89 | 1817 | 2550 | 733 | 121.4 | ok |
| comments_block.js | 13 | 125 | 1803 | 2767 | 964 | 129.7 | ok |
| compare.js | 47 | 195 | 2160 | 4265 | 2105 | 92.6 | ok |
| compound.js | 18 | 129 | 2135 | 3285 | 1150 | 112.2 | ok |
| compound_array.js | 54 | 303 | 1857 | 4728 | 2871 | 105.5 | ok |
| compound_ops.js | 33 | 351 | 1922 | 4737 | 2815 | 124.7 | ok |
| cond_logic.js | 65 | 876 | 1990 | 7613 | 5623 | 155.8 | ok |
| continue_for.js | 19 | 341 | 1706 | 4364 | 2658 | 128.3 | ok |
| continue_while.js | 25 | 287 | 1872 | 4201 | 2329 | 123.2 | ok |
| dangling_else.js | 30 | 145 | 1887 | 3094 | 1207 | 120.1 | ok |
| div_exact.js | 17 | 219 | 1786 | 3783 | 1997 | 109.7 | ok |
| else_chain.js | 38 | 484 | 2133 | 6540 | 4407 | 109.8 | ok |
| else_if_braceless.js | 38 | 408 | 2032 | 5952 | 3920 | 104.1 | ok |
| else_if_mixed.js | 33 | 286 | 2544 | 5298 | 2754 | 103.8 | ok |
| escapes_more.js | 13 | 303 | 1756 | 4208 | 2452 | 123.6 | ok |
| expr_stmt_call.js | 21 | 118 | 1803 | 2762 | 959 | 123.0 | ok |
| fizzbuzz.js | 45 | 1329 | 2608 | 15713 | 13105 | 101.4 | ok |
| for.js | 16 | 229 | 1731 | 3562 | 1831 | 125.1 | ok |
| for_dec.js | 17 | 190 | 1616 | 3017 | 1401 | 135.6 | ok |
| for_empty.js | 28 | 180 | 1923 | 3424 | 1501 | 119.9 | ok |
| func_basic.js | 23 | 160 | 1845 | 3335 | 1490 | 107.4 | ok |
| func_forward.js | 13 | 106 | 1619 | 2757 | 1138 | 93.1 | ok |
| func_globals.js | 18 | 108 | 1662 | 2669 | 1007 | 107.2 | ok |
| func_locals.js | 24 | 178 | 1865 | 3548 | 1683 | 105.8 | ok |
| func_many_args.js | 20 | 113 | 1770 | 2868 | 1098 | 102.9 | ok |
| func_noreturn.js | 12 | 114 | 1748 | 2719 | 971 | 117.4 | ok |
| func_shadow.js | 20 | 158 | 1764 | 3182 | 1418 | 111.4 | ok |
| gcd.js | 30 | 215 | 2010 | 4247 | 2237 | 96.1 | ok |
| if_no_braces.js | 14 | 94 | 1647 | 2565 | 918 | 102.4 | ok |
| inc_dec.js | 12 | 95 | 1784 | 2450 | 666 | 142.6 | ok |
| is_prime.js | 52 | 1201 | 2178 | 13840 | 11662 | 103.0 | ok |
| let_const.js | 23 | 239 | 1740 | 3491 | 1751 | 136.5 | ok |
| logic.js | 43 | 161 | 1894 | 3408 | 1514 | 106.3 | ok |
| mod.js | 18 | 164 | 1590 | 3151 | 1561 | 105.1 | ok |
| multi_args.js | 51 | 445 | 1776 | 5760 | 3984 | 111.7 | ok |
| neg.js | 19 | 230 | 1649 | 3247 | 1598 | 143.9 | ok |
| nested_calls_args.js | 26 | 122 | 1699 | 2820 | 1121 | 108.8 | ok |
| nested_fn_calls_bool.js | 32 | 152 | 1728 | 3345 | 1617 | 94.0 | ok |
| nested_loops.js | 32 | 419 | 1801 | 4746 | 2945 | 142.3 | ok |
| num_print.js | 14 | 195 | 1669 | 3179 | 1510 | 129.1 | ok |
| precedence.js | 35 | 245 | 1718 | 4085 | 2367 | 103.5 | ok |
| prefix_inc.js | 28 | 240 | 1783 | 3587 | 1804 | 133.0 | ok |
| putc.js | 13 | 51 | 1689 | 2364 | 675 | 75.6 | ok |
| return_early.js | 34 | 264 | 1868 | 4211 | 2343 | 112.7 | ok |
| short_circuit.js | 28 | 98 | 1809 | 2693 | 884 | 110.9 | ok |
| short_circuit_side.js | 60 | 604 | 1871 | 6599 | 4728 | 127.7 | ok |
| single_quote.js | 12 | 285 | 1632 | 3558 | 1926 | 148.0 | ok |
| str_concat.js | 45 | 533 | 1920 | 5996 | 4076 | 130.8 | ok |
| str_escape.js | 13 | 483 | 1758 | 5071 | 3313 | 145.8 | ok |
| str_literal.js | 10 | 243 | 1731 | 3270 | 1539 | 157.9 | ok |
| str_mixed.js | 16 | 181 | 1673 | 2905 | 1232 | 146.9 | ok |
| str_param.js | 14 | 282 | 1701 | 3380 | 1679 | 168.0 | ok |
| str_return.js | 19 | 160 | 1643 | 2899 | 1256 | 127.4 | ok |
| str_table.js | 48 | 514 | 2154 | 6624 | 4470 | 115.0 | ok |
| str_var.js | 6 | 105 | 1633 | 2278 | 645 | 162.8 | ok |
| strict_eq.js | 17 | 129 | 1600 | 2667 | 1067 | 120.9 | ok |
| strict_ops.js | 42 | 301 | 1668 | 4599 | 2931 | 102.7 | ok |
| unary_not.js | 9 | 109 | 1721 | 2699 | 978 | 111.5 | ok |
| var_multi.js | 60 | 570 | 2003 | 7011 | 5008 | 113.8 | ok |
| while.js | 15 | 266 | 1570 | 3423 | 1853 | 143.6 | ok |
| while_break.js | 15 | 121 | 1590 | 2466 | 876 | 138.1 | ok |
| while_true_return.js | 23 | 166 | 1783 | 3532 | 1749 | 94.9 | ok |
| assign_undef.js | 0 | 0 | 1580 | 1634 | 54 | – | error: undefined variable |
| bad_char.js | 0 | 0 | 1594 | 1648 | 54 | – | syntax error ( counter(cse) ) |
| break_outside.js | 0 | 0 | 1610 | 1674 | 64 | – | error: break outside a loop |
| extra_brace.js | 0 | 0 | 1560 | 1632 | 72 | – | error: unexpected } |
| fn_in_block.js | 0 | 0 | 1569 | 1621 | 52 | – | error: nested function |
| missing_brace.js | 5 | 0 | 1541 | 1603 | 62 | – | error: missing } |
| nested_function.js | 0 | 0 | 1554 | 1609 | 55 | – | error: nested function |
| return_outside.js | 0 | 0 | 1562 | 1600 | 38 | – | error: return outside a function |
| str_build.js | 0 | 0 | 1572 | 1628 | 56 | – | error: strings can only be joined in console.log |
| too_much_string.js | 0 | 0 | 1998 | 2065 | 67 | – | error: too much string data |
| unclosed_paren.js | 0 | 0 | 1580 | 1638 | 58 | – | syntax error ( counter(cse) ) |
| undef_fn.js | 13 | 0 | 1647 | 1702 | 55 | – | error: undefined function |
| undef_var.js | 0 | 0 | 1556 | 1612 | 56 | – | error: undefined variable |
| unterminated_str.js | 0 | 0 | 1756 | 1809 | 53 | – | syntax error ( counter(cse) ) |

---

## 6. Frame profile of the page

`RUN=1 node machine/trace.js build/js_in_css.xhtml 6`, then `python3 machine/passprof.py trace.json`. `passprof`
counts `LocalFrameView::UpdateStyleAndLayout` events over 1 ms and `InlineNode::ShapeTextIncludingFirstLine` events
over 2 ms between `Commit`s.

| Trace | Frames | Passes per frame | Style+layout per frame | Shaping per frame | Frame |
|---|---|---|---|---|---|
| CPU running (`RUN=1`: Run pressed, 8 s wait, 6 s trace) | 47 | 3.00 | 103 ms | 34 ms | 128 ms |
| Idle editor scan (no Run) | 296 | 2.00 | 16 ms | 0 ms | 20 ms |

Top self times in the CPU trace: `performLayout` 1,899 ms, `ShapeTextIncludingFirstLine` 1,524 ms,
`Document::recalcStyle` 811 ms, `AnimationTimeline::serviceAnimations` 417 ms. About 2.0 s of the 6 s trace is the
harness's mouse-move hit testing (`EventHandler::handleMouseMoveEvent`), not the page.

*(derived)* About 7.8 CPU frames/s; shaping is about a third of style+layout time.

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
