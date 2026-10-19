# Benchmarks

Measurements of the current code. How to measure: `.claude/skills/benchmark/SKILL.md`.

**Conventions.** Measured 2026-10-17 on the Ubuntu mini PC (Intel i5-12600H, no GPU), headless Chromium
153.0.8010.12 launched by `tools/browser.js` (profile `fontcpu`), nothing else running unless noted; desktop Chrome
will differ. A-vs-A noise (`../shared/js/ab.js`, fresh browser per run): the real page's FizzBuzz Run → HALT is
steady to ±0.5% (10.79 s median, 8 runs); a CPU-only page's load → HALT to ±2%, with an occasional +15% outlier
(6.33 s median, 12 runs), so take a median of at least three. Compare only runs made back to back on one machine.
"Before" is the page before the PRINT family (`dist/` of `9319bc0`). *(derived)* marks values computed from logs.

## Headline numbers

| What | Current | Section |
|---|---|---|
| FizzBuzz 1–15 on the page | 476 steps, 103 shapings; compiled 2.51–2.58 s after Run, HALT at 10.75–10.90 s (run ≈ 8.3 s). Before: 1,329 steps, 193 shapings, HALT 18.2–18.3 s | §5a |
| FizzBuzz on the CPU alone (no editor, no compile chain) | HALT 6.25–6.48 s after load | §5c |
| Suite shapings (model) | 4,147 (1,309 MISS, 1,104 EXT, ~230 PRINT); before: 5,967 | §1 |
| Font CPU on the page, L5 fit | 63 steps/s (15.8 ms per step) | §5b |
| One CPU frame (mid-run trace) | 3 passes: 124 ms style+layout, 43 ms shaping, 148 ms frame | §6 |
| CSS compiler alone (L3, no readback) | median 380 ms per program; ≈ 189 ms + 7.6 ms per code word | §4 |
| HarfBuzz alone (uharfbuzz) | FizzBuzz 20.6 ms per shaping (N16 S32) | §3 |
| Editor readback sweep | 1.12–1.21 s, 0 misses | §7 |
| Objects, FizzBuzz against the page before them | Run → HALT ×1.006, Run → compiled ×1.045, HarfBuzz ×1.015 per shaping | §10 |

**Where the time goes.** Run time is set by shapings: each is a layout pass, a frame holds at most 2, and traps
(misses, write-backs, EXT, PRINT, PUTC) end them early; `tools/traps.py` predicts shapings without a browser. Each
shaping pass costs ~21 ms of HarfBuzz plus restyling `#cpu` and layout (with the readers' restyles inside it), and
every frame adds a settle pass (§6). Compile time on the page is mostly the readback sweep plus the chain.

## 1. Machine model (no browser)

`python3 tools/traps.py <files>` (uarch4, N16 S32); deterministic. EXT is MUL / DIV / MOD / SHL13, PRINT a console
chunk, PUTC a `putc()` call.

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

The reference simulator counts one step more (HALT). Suite-wide (89 programs + t1–t4), before → current: 46,458 →
26,682 steps, 5,967 → 4,147 shapings.

Modelled, not built (suite shapings): N = 24 3,888; N = 32 3,858; S = 48 3,427; S = 64 3,161; N32 S64 2,848; a code /
data partition 4,368–4,713. S is capped by S × subtables ≤ 16,384; HarfBuzz time grows with cells × lookups × S.

## 2. The CSS compiler's size

`tools/vsz.py` and the `make page` build line. The first three rows include objects (§10); the rest were
measured just before them.

| Measure | Value |
|---|---|
| Parser variants | 346 before the no-op merge; 322 on the page, in 188 rules |
| Temps, all variants | 67,451 |
| Label ports per level | 21 |
| Largest variant | 1,380 temps (`S_NAMES '}'`) |
| Levels | 1,561 character levels, 401 token levels |
| Compile-chain CSS / page | 7.7 MB / 12.1 MB |
| `make page` | 28 s, reproducible |
| L2 DSL evaluation | 336 temps per parser step with the specialised variants |

## 3. HarfBuzz alone (uharfbuzz 0.56.3, no browser)

`machine/hbtest.py` shapes the real cpu4 font and checks every shaping against `uarch4`. Images from
`compiler/mkimage.py --ram prog.js img.json`.

| Workload | N, S | Shapings | Steps | HarfBuzz ms per shaping |
|---|---|---|---|---|
| FizzBuzz | 16, 32 | 103 | 476 | 20.56 |
| `bubble_sort_print` | 16, 32 | 167 | 901 | 20.48 |
| `array_sort` | 16, 32 | 77 | 635 | 21.07 |
| `str_table` | 16, 32 | 40 | 168 | 20.37 |

All halted with correct output. *(derived)* FizzBuzz:
4.6 steps per shaping, 2.1 s of HarfBuzz.

## 4. The CSS compiler in Chrome

### 4a. L3 suite

`make l3 SHARDS=1` (one browser; `make l3` runs 6 at once): one page; each program is written into the latch cells,
Run pressed, Run → done anchor timed, every word checked against `cc_ref`. 104/104 pass (90 valid, 14 error
programs). Valid: min 229 / median 380 / max 1,488 ms (`else_if_long`, 137 words); ms ≈ 189 + 7.6 × words (r = 0.90)
*(derived)*. FizzBuzz 580 ms. Errors: 187–522 ms.

### 4b. (removed)

The fake-latch chain harness duplicated L3 (§4a), which times the same chain per program; removed 2026-10-18.

### 4c. Language features: block scope, `const`, `do … while`, `?:` (2026-10-17)

L3 page against the baseline (`234a0ca`), interleaved rounds; ratio new / baseline, median over programs per round.
Run time is unchanged (identical code words for every old program; `do … while` saves a jump per iteration, `?:`
costs the same as `if / else`); real-page FizzBuzz: HALT ratio 1.000, compiled 0.970.

| Build | Temps | Variants (rules) | Max ports | Largest | L3 ratio per round |
|---|---|---|---|---|---|
| Baseline | 56,505 | 319 (299) | 22 | 1,253 | 1 |
| + block-scoped `let` / `const` | 58,324 | 319 | 22 | 1,323 | 0.997, 0.978 |
| + `do … while` | 60,766 | 322 | 22 | 1,380 | 1.003, 1.003 |
| + `?:`, first version | 66,816 | 336 | 23 | 1,423 | 1.002, 1.041, 1.042, 1.038 |
| `?:` trimmed | 64,542 | 336 | 21 | 1,380 | 1.029, 1.048, 1.025 |
| `?` and `:` out of `PUNCT` | 62,756 | 323 | 21 | 1,380 | 1.011, 1.000, 1.021 |
| + identical variants share one rule | 62,756 | 323 (168) | 21 | 1,380 | 0.977, 0.970, 0.950 |

**Every rule costs time whether it applies or not**: each token level tests every variant's container query. 40
never-matching rules (+13%) cost +4.3%, +2.0%, +1.6%. So new variants cost more than their temps, and merging the 115
duplicate variants into shared rules made the compiler ~3% faster than the baseline.

### 4d. `switch`, `++` / `--` in expressions, `a[i]++`, `.length` (branch `sugar`, 2026-10-18)

Compiler only. Size (`tools/vsz.py`): 67,451 → 69,965 temps, 346 → 355 variants (`S_SWCASE`, and `++` / `--` after an
operand, pure errors before), max label ports 21 → 21, largest variant (`S_NAMES '}'`) 1,523 → 1,545, `S_NAMES ')'`
1,256 → 1,211. A first version had 70,682 temps: each `emit` costs ~12 temps per variant (one selector per code slot),
so the switch shares code records, pushes and label ports with what was there (`if` / `while` / `switch` headers push
once, loop / function / switch closes share their first `JMP`, `RET` / `POP` and a port).

Compile time (L3, the 140 programs both pages compile, six runs pinned to CPUs 12–15, main / sugar / sugar / main /
main / sugar, an Android emulator on ~3 CPUs throughout): ratios 1.012, 1.001, 1.016 against main-vs-main 0.984,
so about +1%, at the noise floor.

Run time: old programs compile to the same code size and output; the 97 without array literals take the same steps.
An array literal's length word costs 16 steps once, when the ROM's startup copies it (`array_basic` 17 → 18 shapings,
`obj_array` with 3 arrays 83 → 96).

## 5. The page end to end

### 5a. FizzBuzz (`machine/ui_seq.js`, initial program)

| Build | compiledMs | haltMs | run |
|---|---|---|---|
| Before (`9319bc0`) | 2,938–2,969 | 18,204–18,328 | 15.2–15.4 s |
| Current | 2,513–2,582 | 10,746–10,899 | 8.3 s |

*(derived)* HALT 1.7× sooner, run 1.8× faster.

### 5b. The L5 suite

`make l5 SHARDS=1` (one browser): acts as a user (Edit, retype, Run, poll every 100 ms). 101 of 101 ok (87 run to
HALT, 14 errors); 11.4 min.

- Compile, valid programs: 1,708 / 2,199 / 5,847 ms (min / median / max); ≈ 1,562 + 26.0 × words (r = 0.90).
- Error detection: 1,662–2,502 ms, median 1,720.
- Execution: median 1,542 ms, max 22,765 (`else_if_long`); ≈ 188 + 15.77 ms per step (r = 0.809), about 63 steps/s
  (per program 22–141).
- FizzBuzz mid-suite ran 10.4 s against 8.6 s as the initial program: sparse RAM keeps every group earlier programs
  wrote live *(inferred)*. Use a fresh page (§5a) for comparisons.

### 5c. The CPU alone (`machine/halttime.js`, CPU-only pages, load → HALT)

| Program | Steps | HALT after load |
|---|---|---|
| FizzBuzz | 476 | 6,267–6,401 ms (A-vs-A median 6,333) |
| `str_table.js` | 168 | 2,731–2,744 ms |
| `bool_print.js` | 48 | 1,088 ms |
| `bubble_sort_print.js` | 901 | 9,547–10,016 ms |
| `array_sort.js` | 635 | 4,336–4,531 ms |

All halted with the model's exact step count and correct output.

## 6. Frame profile

`RUN=1 RUNWAIT=3500 node machine/trace.js <page> 4`, `python3 machine/passprof.py trace.json` (window 3.5–7.5 s after
Run, inside every run).

| Trace (FizzBuzz, mid-run) | Passes per frame | Style+layout per frame | Shaping per frame | Frame |
|---|---|---|---|---|
| Current page | 3.00 | 124 ms | 43 ms | 148 ms |
| Idle editor (no Run) | 2.00 | 19 ms | 0 ms | 23 ms |
| CPU-only page (`WAIT=700`, 3 s) | 2.46 | 105 ms | 43 ms | 112 ms |

An invalidation-tracking trace (2026-10-13) put 98% of style resolutions inside `Layout` (~1,300 per pass, under the
readers' size containers) against ~48 per `recalcStyle` (~5 ms, mostly `#cpu`'s ~900 custom properties). The third
pass is a settle pass without shaping (ENGINE_NOTES 34, 38).

## 7. Editor readback

`python3 readback/rb_only2.py rb.xhtml && node readback/rbsweep.js rb.xhtml tests/fizz.js 3`: sweeps of 1,115,
1,214 and 1,172 ms, 0 misses. One column per frame over 64 columns, ~18 ms per column *(derived)*.

### 7a. Scan only after Run (2026-10-17)

Running the scan only after Run (and all-div editor lines) left HALT unchanged and made compiling ~6% faster
(2,527 → 2,331 ms, `ab.js -r 6`). Idle while editing, main-thread busy time fell from ~1,000 to ~350 ms/s (style
~500 → ~57 ms/s, layouts 121–126 → 60 per s), and a selection's highlight no longer jumps (0 of the screencast frames
against 14–19 of ~105).

## 8. RAM group size

`MEMGROUP=n UI=1 python3 machine/gen_fvm4.py build/ccimg.json build/f4cc_16 out.xhtml`, real page, FizzBuzz, two
interleaved rounds:

| Cells per group | compiledMs | haltMs |
|---|---|---|
| 16 | 2,491 / 2,498 | 10,251 / 10,220 |
| 64 | 2,433 / 2,423 | 10,206 / 10,295 |
| 256 (shipped) | 2,561 / 2,582 | 10,899 / 10,875 |

**16 and 64 halt about 6% sooner than 256**, well beyond the noise. 256 was chosen on a loaded machine. A lead:
re-check with `ab.js` and the L5 suite before switching.

## 9. Caveats

Headless, no GPU: desktop Chrome will differ. The harness's mouse moves show up in traces as hit testing.

## 10. Objects (2026-10-17)

Measured while another session ran benchmarks: page runs pinned to E-cores (`taskset -c 12-15`; slower, steady; read
the ratios), HarfBuzz runs to one P-core in CPU time. "Before" is the page before objects (`8349991`).

| Measure | Before | After | Ratio (median, IQR) |
|---|---|---|---|
| FizzBuzz, uharfbuzz ms per shaping | 21.4–21.6 | 21.7–21.9 | ≈ 1.015 |
| Subtables per cycle (cap 512 at S = 32) / control values | 432 / 120 | 392 / 148 | |
| FizzBuzz Run → HALT (`ab.js`, 6 rounds) | 19.96 s | 20.16 s | 1.006 (1.003–1.019) |
| FizzBuzz Run → compiled | 4,523 ms | 4,642 ms | 1.045 (1.024–1.066) |
| Parser variants / on the page / rules | 323 / 302 / 168 | 346 / 322 / 188 | |
| Parser temps | 62,756 | 67,451 | 1.075 |

The new instructions cost ~7% per shaping; fixing the generator's 16 copies of every self-update rule paid most of it
back (alone: 19.6 → 18.4 ms). Compile time grew with 20 more rules, the intern table (16 container rules per token
level) and 6 more state variables per level.

Model (`tools/traps.py`), steps / shapings / misses: obj_basic 365 / 77 / 47; obj_nested 434 / 136 / 102; obj_keys
929 / 163 / 73; obj_func 537 / 107 / 68; obj_list 462 / 88 / 49; obj_tree 2,085 / 444 / 289; obj_grow 1,598 / 241 /
99; obj_gc_small 12,432 / 2,068 / 935; obj_gc 40,443 / 16,607 / 12,848.

- Object code runs 4–5 steps per shaping like the rest, except tight allocation loops: `obj_gc` takes 18 shapings
  per iteration, 14 of them misses (fresh heap lines evict the loop's code). The GC is 2% of `obj_gc`'s shapings.
- On the page (L5, loaded machine; FizzBuzz 12.6 s in the same run), Run → HALT: obj_basic 13.8 s, obj_list 15.0 s,
  obj_func 18.0 s, obj_nested 24.1 s, obj_keys 24.4 s; `obj_gc_small` (500 objects through the 384-chunk heap) 216 s,
  output and step count exact.

## 12. The CSS CPU (2026-10-19)

`machine/gen_css.py`; the build-up, ablations and Blink's style costs are in `exp/csscpu/README.md`. Headless
Chromium 153, mini PC.

**Editor page, FizzBuzz** (`machine/ui_seq.js`, one browser, the two pages alternately, three rounds each):

| Page | compiledMs | haltMs | run |
|---|---|---|---|
| font CPU (`make page-font`) | 2,678–2,771 | 10,453–10,581 | ~7.8 s |
| CSS CPU (`make page`) | 2,431–2,492 | 3,876–3,951 | ~1.45 s |

*(derived)* HALT 2.7× sooner, run ~5.4× faster.

**CPU-only pages**, load → HALT (`exp/csscpu/halt.js`, `POLL=30` for both, run alternately, two runs each):

| Program | Steps | CSS CPU | Font CPU | Speed-up |
|---|---|---|---|---|
| FizzBuzz | 462 | 985–1,033 ms | 5,714–5,753 ms | 5.7× |
| `gcd.js` | 122 | 420–436 ms | 1,677–1,691 ms | 3.9× |
| `primes.js` | 1,774 | 1,732–1,779 ms | 12,787–13,022 ms | 7.3× |
| `array_sort.js` | 647 | 1,004–1,049 ms | 4,689–4,788 ms | 4.6× |
| `str_table.js` | 165 | 656–695 ms | 2,682–2,779 ms | 4.0× |
| `bool_print.js` | 46 | 392–400 ms | 1,097–1,127 ms | 2.8× |

**Long programs** (one run each, one browser): LONGROWS

- Correctness: L5 164/164 and L5-input 14/14 on the CSS CPU page; C2 111/111 (every suite program under 1,500 steps,
  objects included) and the nine longer ones; C1 120/120.
- Misses dominate long runs: deep recursion and heap allocation evict dirty lines, so the prefetch (clean victims
  only) never helps and each pass fills one block (`deep_recursion`: 1,413 of 1,415 passes end on a miss). The font
  CPU, with a 16-line cache and a trap per miss, is slower still.

