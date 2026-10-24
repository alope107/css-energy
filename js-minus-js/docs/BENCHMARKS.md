# Benchmarks

Measurements of the current code. How to measure: `.claude/skills/benchmark/SKILL.md`. §1–§11 measured the font CPU,
removed on 2026-10-20 (last at commit `181cbb7`); they stay as the baseline the CSS CPU (§12) is compared with.

**Suite programs changed on 2026-10-23** (busy work removed, the checks kept): `str_keys_gc`, `obj_gc` and
`gc_rawblock` collect at most twice and fill the heap with empty objects, `str_keys`, `fib` and `deep_recursion` run
shorter loops, and `obj_gc_small` (a subset of `obj_gc`) is gone. Times for those programs before that date aren't
comparable with later ones; ratios measured within one run still are.

**Conventions.** Measured 2026-10-17 on the Ubuntu mini PC (Intel i5-12600H, no GPU), headless Chromium
153.0.8010.12 launched by `tools/browser.js` (profile `fontcpu`), nothing else running unless noted; desktop Chrome
will differ. A-vs-A noise (`../shared/js/ab.js`, fresh browser per run): the real page's FizzBuzz Run → HALT is
steady to ±0.5% (10.79 s median, 8 runs); a CPU-only page's load → HALT to ±2%, with an occasional +15% outlier
(6.33 s median, 12 runs), so take a median of at least three. Compare only runs made back to back on one machine.
"Before" is the page before the PRINT family (`dist/` of `9319bc0`). *(derived)* marks values computed from logs.

## Headline numbers

| What | Current | Section |
|---|---|---|
| Compile speed (2026-10-24): padding levels passed through, token levels waiting for their tokens, the scan stopping at the first blank column | the page's Run → compiled 0.71× (FizzBuzz ~2.0 s, was ~2.9 s), the chain alone 0.86×, a REPL entry 0.70× (interleaved, unleased) | §21 |
| The hybrid: the runtime's primitives (branch `rom-css`) and a code cache on the register machine (2026-10-22) | 25 programs on CPU-only pages 1.74× faster than the register machine and 1.53× than the stack machine with the primitives (geometric means; total 334.5 s against 545.7 and 452.3); faster than both on 23, compute as fast as the register machine; suite steps −57%, passes −45% / −27% (model) | §15 |
| Register machine against the stack machine (2026-10-21) | samples on CPU-only pages 1.07–2.75× faster (compute 1.9–2.8×, FizzBuzz output-bound 1.07×), 3.0× fewer suite steps; compile time median ×1.03; FizzBuzz on the page compiled as fast, HALT 3.1 s (main 3.4 s) | §14 |
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
| font CPU (`181cbb7`) | 2,678–2,771 | 10,453–10,581 | ~7.8 s |
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

**Long programs**, load → HALT (one run each, one browser; CSS pages by `tests/csscpu_pages.js`, font pages by
`exp/csscpu/halt.js`):

| Program | Steps | CSS CPU | Font CPU | Speed-up |
|---|---|---|---|---|
| `fib.js` | 8,353 | 8.6 s | 81.7 s | 9.6× |
| `deep_recursion.js` | 8,445 | 56.1 s | 196.5 s | 3.5× |
| `obj_gc_small.js` | 12,432 | 40.1 s | 152.0 s | 3.8× |
| `obj_gc.js` | 40,443 | 287.2 s | not halted at 900 s (30,042 steps) | > 3.1× |

(`halt.js` compares the console with the raw output, so it reports fib's wrapped console as wrong on the font page;
its step count was exact.)

- Correctness: L5 164/164 and L5-input 14/14 on the CSS CPU page; C2 111/111 (every suite program under 1,500 steps,
  objects included) and the nine longer ones; C1 120/120.
- Misses dominate long runs: deep recursion and heap allocation evict dirty lines, so the prefetch (clean victims
  only) never helps and each pass fills one block (`deep_recursion`: 1,413 of 1,415 passes end on a miss). The font
  CPU, with a 16-line cache and a trap per miss, is slower still.


## 13. Strings and arrays (2026-10-20)

Heap strings and growable arrays (ARCHITECTURE §3.6): ROM 6,144 words (a jsc-compiled runtime and hand-written
routines), new instructions PUSHS, IDXA, STOREX, DYN, `JZ` / `JNZ` / `NOT` reading a string's length, `ENTER` zeroing
its locals. Main is `22295b9`, built in its own worktree; headless Chromium 153, mini PC, nothing else running, the
two pages alternately.

**Editor page, FizzBuzz** (`machine/ui_seq.js`, three rounds):

| Page | compiledMs | haltMs |
|---|---|---|
| main | 2,512–2,555 | 4,022–4,075 |
| strings and arrays | 2,437–2,467 | 3,607–3,625 |

*(derived)* HALT ~10% sooner: no startup copy (`__init` is gone: globals start at 0, `data_base`'s constant is an
overlay), no heap setup, 415 steps against 462.

**CPU-only pages** (`machine/halttime.js`, `POLL=30`, two runs each; run = first step → HALT):

| Program | Steps main / now | Run main | Run now |
|---|---|---|---|
| FizzBuzz | 462 / 415 | 678–683 ms | 610–620 ms |
| `gcd.js` | 122 / 91 | 104–111 ms | 42–46 ms |
| `primes.js` | 1,774 / 1,695 | 1,564 ms | 1,605–1,619 ms |
| `str_table.js` | 165 / 118 | 354–358 ms | 285–290 ms |
| `obj_basic.js` | 360 / 232 | 1,456 ms | 968–1,058 ms |
| `array_sort.js` | 647 / 545 | 659–695 ms | 794–813 ms |
| `str_concat.js` | 82 / 93 | 318–372 ms | 414–423 ms |

- `array_sort` is slower: its array is a heap block (header and elements: more blocks to fill than the old static
  array next to the globals), and `a[i]` is `LOADG a; i; IDXA` (the arr class) where the old static arrays had one IDX.
  DYN in a class of its own took it from ~960 to ~890 ms (A/B, three runs each).
- `str_concat`: `console.log("n = " + n)` prints its pieces through a ROM routine (`pnK`) instead of a PRINT each, so
  that `"a" + b == c` inside `console.log` is right.
- Load (navigation → first step) is the same as main's: the ROM has no leaf elements (a data read below RAM gives 0).
  With leaves for its ~6,000 words, each frame cost ~8 ms more: the editor's readback (one column a frame) compiled
  ~0.5 s later and FizzBuzz halted at ~4.3 s.
- The ROM fetch table is split into tiers of 1,024 words (a rule each): `str_concat` with the runtime's ~4,000 words in
  one table ran 1,174–1,212 ms, in tiers 1,024–1,052 ms (before the other changes above).

**Long string and array programs** (C2 pages, three browsers at once, so not timings to compare): `str_build` 7,586
steps 18.6 s, `str_methods` 13,633 steps 27.0 s, `arr_methods` 38,653 steps 83.2 s, `arr_nested` 15,937 steps 37.5 s.
String building and the methods run in ROM (jsc's code, ~1.5 ms a step).

**Compiler size** (`tools/vsz.py`): 338 variants, 70,478 temps (main: 355, 71,815); on the page 317 variants in 185
rules. `popops` emitting one word per operator (not one per case) took it from 104,872 temps.

## 14. The register machine (2026-10-21)

The stack machine (main, `212175a`, built in its own worktree) against the register machine (ARCHITECTURE §1–§3);
headless Chromium 153, the mini PC, the two pages alternately, nothing else running unless noted.

**Steps and passes** (`cc_ref`, each machine's `csssim.py`, K = 32; the 135 suite programs):

| | Stack machine | Register machine |
|---|---|---|
| steps | 829,910 | 277,403 |
| passes | 44,678 | 31,301 |
| passes ending on a miss / full (K) / output | 24,841 / 19,014 / 688 | 28,168 / 2,753 / 245 |

The register machine runs 3.0× fewer steps (a three-address instruction does what took two to four stack
instructions; strings, arrays and objects have instructions of their own) in 30% fewer passes, and now most passes end
on a cache miss. Over the ten samples the misses fall on code 588, heap 533, stack 381, strings 129, globals 71, the
runtime's cells 55: user code shares the 128-word cache with the data.

**CPU-only pages** (`machine/halttime.js`, `POLL=30`, three interleaved rounds; run = first step → HALT, median;
rounds within ±3%). The samples' pages; "no cat" is the register page built with `NOCAT=1` (a string's `+` traps to
the ROM's `cat`, as before the cat class; the runtime's `join` and `repeat` too):

| Sample | Steps stack / register | Stack machine | Register machine | Speed-up | No cat |
|---|---|---|---|---|---|
| primes | 31,636 / 6,585 | 54.8 s | 19.9 s | 2.75× | 30.4 s |
| sort | 10,398 / 1,728 | 17.3 s | 6.7 s | 2.57× | 12.3 s |
| stars | 11,347 / 1,082 | 18.4 s | 7.6 s | 2.41× | 11.5 s |
| fib | 56,772 / 23,252 | 50.3 s | 23.0 s | 2.18× | |
| caesar | 9,818 / 2,056 | 21.5 s | 10.3 s | 2.10× | 13.4 s |
| collatz | 8,088 / 3,673 | 7.2 s | 3.8 s | 1.91× | 3.8 s |
| tree | 10,665 / 2,273 | 22.1 s | 14.3 s | 1.55× | 18.8 s |
| bank | 3,633 / 1,060 | 7.8 s | 5.4 s | 1.43× | 5.7 s |
| hanoi | 627 / 273 | 1.29 s | 1.15 s | 1.12× | 1.59 s |
| fizzbuzz | 791 / 324 | 1.03 s | 0.96 s | 1.07× | |

- Compute (fib, collatz, primes' sieve) gains 1.9–2.8×; string building gains another 1.3–1.8× from the cat class.
- FizzBuzz is output-bound: a pass writes at most one console cell per RAM bank (4 cells), and 24 of its 40 passes
  end there. Packing several output instructions into a pass's free banks (9 columns, so rows start one bank apart)
  took it from 51 to 40 passes in the model (the suite's 1–15 from 29 to 22). Eight console banks would take it to ~33
  (model) for 32 more registers, which every pass of every program pays for: not done.
- The collector's powers of two from a table instead of a loop: suite steps 600,813 → 467,215 (−22%, before the
  cat class), mostly in the GC tests.

**Compile time** (`tests/suite_css.js`, the L3 page, each program compiled after a different one, as on the real page;
main's page and ours alternately, one browser; per-program ratio register / stack):

| Version | Median ratio (IQR) | Total over 135 programs |
|---|---|---|
| full language, first (96,580 temps), rounds 1–2 | 1.080 (1.000–1.166), 1.133 (1.065–1.230) | 96.0 vs 106.1 s, 95.4 vs 111.2 s |
| `popcap`, 4-iteration `print_call` (93,130 temps) | 1.134 (1.049–1.232) | 93.1 vs 108.0 s |
| single-use temps inlined, one word temp per record (79,100 temps) | 1.029 (0.979–1.098) | 93.5 vs 98.2 s |

- A compile is two frames, ~90% style recalc (a trace of `arr_methods`: 1,976 of 2,166 ms). Recompiling the same
  program again hides most of the difference (Blink's caches: 1,723 vs 1,556 ms), so compare cold compiles.
- What predicts it is the CSS text a token level evaluates more than its declaration count: weighted by how often
  the suite's tokens hit each variant, the stack compiler evaluates 349 temps and 40.7K characters per token, the first
  register compiler 451 and 73.4K, the current one 394 and 53.0K. A fit over the suite (first register version):
  stack ms ≈ 199 + 4.6 × tokens + 0.7 × words, register ≈ 201 + 4.4 × tokens + 2.4 × words.
- The biggest cuts: the 7 instruction slots' word mux had each record's `op × 8192 + A` written out in every slot
  (31% of a `)` level's text: now one temp per record); inlining single-use temps (`dsl.Ctx.inline`, −15% temps).
  Tried and dropped: the operand stack's top in its own variable (no smaller), shared one-hot slot flags (−1.5% text,
  +7% declarations).

**Compiler size** (`tools/vsz.py`): 338 variants, 79,100 temps (stack machine 338, 70,489); on the page 317 variants
in 185 rules; the suite_css page 12.9 MB (10.3).

**The editor page, FizzBuzz 1–15** (`machine/ui_seq.js`, the initial program; main's page and ours alternately, three
rounds):

| Page | compiledMs | haltMs |
|---|---|---|
| stack machine (main) | 2,275–2,342 | 3,330–3,412 |
| register machine | 2,282–2,361 | 3,092–3,153 |

- Compiled as fast, HALT ~7% sooner: the run after compiling is ~0.80 s against ~1.06 s (148 steps against 415).
- The sample picker first made the compile ~1.7 s slower (4,081–4,430 ms): the per-line checks became one `:has()`
  per editor and line on `#app`, each a search of its ~10,000 elements. On the editors' section with child combinators
  (`.pane:not(:has(> .frame > .ed<i> > div:nth-of-type(k))) ~ .probes …`) they cost less than main's 24 on `#app`
  (without the picker, compiled 2,426–2,475 ms, HALT 3,240–3,357).

## 15. The hybrid: the runtime's primitives and a code cache on the register machine (2026-10-22)

Branch `hybrid`: the register machine (`regvm`, `ae19432`) with branch `rom-css`'s runtime primitives (`b19708f`, on the
stack machine) redone for three-address code, the collector's map of block starts kept as blocks are made, GETX / SETX
probing objects in the machine, and a code cache (ARCHITECTURE §3.2, §3.5, §3.6). Against `regvm` and `rom-css`, each
built in its own worktree. Headless Chromium 153, the mini PC; every timing in a bench lease (`shared/py/bench.py`,
P-cores, foreign load 0.0%).

**Model** (`cc_ref` steps, `csssim.py` passes, K = 32; the 145 suite programs and samples all three run):

| | Register machine | Stack machine + primitives | Hybrid |
|---|---|---|---|
| steps | 319,709 | 310,954 | 137,579 |
| passes | 34,165 | 25,722 | 18,664 |

- Where the hybrid's passes end (146 programs, 21,633 passes): heap misses 10,332, stack 3,636, full (K) 1,964, the
  runtime's cells and the map 1,666, code 1,539, globals 1,111, strings 885. Without the code cache (30,360 passes) code
  misses were 6,881 (23%): a loop's code, two words an instruction, evicted by its data from the 128-word data cache.
- The primitives alone (no code cache) took the 145 programs' passes to 25,796 (−24% against the register machine; the GC
  programs still 1.3–1.4× the stack machine's, `mapbuild` gone but the loops' code evicted); the code cache to 18,664.
- Tried in the model (HISTORY 56–61): HP and GCLIM as registers −2–4% in the GC programs; whole-line writes without a fill
  ~0%; keeping code in the data cache by its replacement +45% (data starved); 16 data lines instead of 32 +50%.

**CPU-only pages**, load → HALT (`machine/halttime.js`, POLL=30; run = first step → HALT), three interleaved rounds, the
order rotating (median; ratio IQRs within ±2%):

| Program | Register machine | Stack + primitives | Hybrid | Hybrid / register | Hybrid / stack |
|---|---|---|---|---|---|
| fizzbuzz (sample) | 0.96 s | 1.07 s | 0.99 s | 1.030 | 0.926 |
| hanoi | 1.11 s | 1.25 s | 0.91 s | 0.819 | 0.719 |
| bank | 5.41 s | 4.76 s | 2.79 s | 0.518 | 0.589 |
| collatz | 3.74 s | 7.41 s | 3.72 s | 0.994 | 0.501 |
| caesar | 10.30 s | 10.96 s | 6.64 s | 0.645 | 0.610 |
| fib | 23.25 s | 51.83 s | 22.67 s | 0.976 | 0.437 |
| tree | 14.64 s | 11.30 s | 9.74 s | 0.665 | 0.863 |
| stars | 7.74 s | 3.44 s | 2.03 s | 0.264 | 0.590 |
| sort | 6.75 s | 5.12 s | 3.78 s | 0.560 | 0.733 |
| primes | 19.26 s | 20.23 s | 10.43 s | 0.547 | 0.515 |
| deep_recursion | 49.83 s | 57.82 s | 49.37 s | 0.992 | 0.854 |
| str_build | 3.08 s | 5.08 s | 3.21 s | 1.040 | 0.630 |
| str_cmp | 4.42 s | 3.85 s | 2.90 s | 0.657 | 0.753 |
| str_methods | 11.63 s | 9.43 s | 7.29 s | 0.630 | 0.773 |
| str_index | 9.28 s | 9.34 s | 5.40 s | 0.582 | 0.580 |
| str_keys | 83.75 s | 46.15 s | 38.58 s | 0.460 | 0.835 |
| arr_grow | 10.77 s | 6.66 s | 5.46 s | 0.490 | 0.819 |
| arr_nested | 10.58 s | 8.30 s | 4.83 s | 0.459 | 0.585 |
| arr_methods | 20.76 s | 11.66 s | 10.54 s | 0.508 | 0.909 |
| arr_print | 12.94 s | 13.41 s | 9.72 s | 0.751 | 0.724 |
| obj_count | 8.48 s | 3.71 s | 1.11 s | 0.131 | 0.300 |
| arr_gc | 147.77 s | 105.38 s | 87.69 s | 0.594 | 0.832 |
| obj_gc_small | 67.61 s | 44.28 s | 40.40 s | 0.598 | 0.912 |
| obj_keys | 4.89 s | 3.62 s | 2.14 s | 0.438 | 0.591 |
| obj_grow | 6.79 s | 6.21 s | 2.15 s | 0.316 | 0.348 |
| **total, geometric mean** | 545.7 s | 452.3 s | 334.5 s | **0.574** | **0.652** |

- Faster than the stack machine with the primitives on all 25 and than the register machine on 20; compute as fast as the
  register machine (fib 0.976, collatz 0.994, deep_recursion 0.992). Slower than it on two light, output- or miss-bound
  programs (fizzbuzz +3%, str_build +4%) with fewer passes (38 against 40, 93 against 100): a pass costs more (below).
- The largest gains are where the runtime's loops were: run-time object keys (obj_count 0.13: GETX / SETX probe in the
  machine), array literals and `push` (obj_grow, arr_nested, arr_grow), `repeat` and `join` (stars 0.26, a string built
  once), the collector (arr_gc, obj_gc_small 0.59–0.60 against the register machine's `mapbuild`).

**Per-pass cost.** Every register costs every pass, whether it changes or not: FizzBuzz (the sample), run ms, five
interleaved rounds — register machine 961; the same page with 176 more registered properties 962 (registered properties
cost nothing here); hybrid 993 with a 16-line code cache, 1,018 with 80 unused registers more, 1,050 with a 32-line code
cache (another 80 registers and a wider lookup). Moving the code cache's register subjects from the chain's end into
`.fl` (where they change) made no difference (1,046 against 1,040).

**Code cache size**, one interleaved round of the 25: 16 lines 334.8 s, 32 lines 343.5 s (geometric mean 32 / 16 1.023):
32 lines made caesar 24% and bank 13% faster (their loops are longer than 32 instructions) and 23 others 0–12% slower.
Default 16 (`ICACHE=32,1` builds 32).

**The editor page, FizzBuzz 1–15** (`machine/ui_seq.js`, three rounds, the three pages in rotation):

| Page | compiledMs | haltMs |
|---|---|---|
| register machine | 2,269–2,329 | 3,111–3,184 |
| stack machine + primitives | 2,306–2,371 | 3,389–3,516 |
| hybrid | 2,278–2,314 | 3,182–3,277 |

The program is 148 steps in 22 passes on both register pages (model); the hybrid's run after compiling is ~0.1 s longer,
the per-pass cost above. (With a 32-line code cache: 3,296–3,358.)

**Compile time** (`tests/suite_css.js`, the L3 page, one browser, one run each): per program, hybrid / register machine
median 1.007 (IQR 0.961–1.061), totals 115.5 against 114.7 s over the 182 programs all three run; the stack machine's
compiler 106.9 s (its pages compile ~7% faster, as in §14). The compiler is the register machine's: only the opcode
numbers moved (KIND joined the mov class).

**Costs.** The CPU-only page 4.42 MB (register machine 4.14, stack + primitives 4.40), the editor page 17.4 MB (17.1,
14.7); 357 registers (276, 274) and 844 registered properties (657, 684); the ROM 4,284 words (4,784, 6,139).

**Correctness.** L1 136/136, C1 136/136, L2 ALL OK, `make fuzz` ALL OK, L3 183/183, L5 smoke ok, and all 146 programs
(the suite and the samples) as CPU-only pages in Chrome with Node's console and cc_ref's steps. A new suite program,
`gc_rawblock.js`, never halted on the register machine (its collector's walk, HISTORY 54). One early HALT in ~370 timed
runs of the hybrid (obj_keys, 218 of 313 steps), not reproduced in 140 more; the register machine had one in 66 on
2026-10-21 (tree, 110 of 2,273): the same intermittent fault, inherited, not found yet.

## 16. The network (2026-10-21, branch `css-fetch`, measured on the stack machine)

`fetch` / `read` through the fragment-scroll modem (ARCHITECTURE §3.8), headless Chromium 153, no flags; page and gateway
(`net/server.js`) on one machine. The machine was shared with other sessions' browser jobs: absolute times swing ~2×
between runs, so the comparisons below are interleaved.

| Measure | Value |
|---|---|
| A word beside a trivial page (`net/probe/probe3.js`: the harness as the CPU) | median 20–23 ms; the first after idle ~1 s (the idle reload) |
| 600 random bytes through it | 609 words, 14.9 s, byte for byte |
| `net_fetch.js` on the page, compiled → HALT (`net/probe/pagenet.js`, 5 runs) | 9.5–10.9 s; 29 words |
| A word on the page, median gap between the gateway's requests (5 runs) | 283–330 ms (the font CPU's modem: 0.5–0.8 s); page 25–29 frames/s, modem 5.4–6.2 loads/s |
| `fetch` with no gateway (`file:`): Run → `-1` | 23 s (the 20 s timeout, then `fetch` gives up) |

Parallel modems (`net/probe/probe7.js`; the page's CPU drives its own modem through a `read()` loop, the harness drives
the extra ones the same way):

| Modems | Words/s per modem | Words/s in all | Page frames/s |
|---|---|---|---|
| 1 | 4.33–4.41 | 4.33–4.41 | 34.6–35.4 |
| 2 | 3.99–4.16 | 7.98–8.24 | 32.0–32.9 |
| 4 | 3.57 | 14.29 | 28.3 |

A word costs about 8 page frames whichever modem carries it, so throughput is bytes per word × modems.

**Built in (2026-10-21): 4 modems, 2 bytes each.** A word brings 2 URL bytes or 8 body bytes. Interleaved against the
single-byte, single-modem page (`e9198b2`), 3 rounds each, `net/probe/pagenet.js`, compiled → HALT:

| Program | 1 byte, 1 modem | 2 bytes, 4 modems | Words | Median word | Page frames/s |
|---|---|---|---|---|---|
| `net_long.js` (62 bytes, summed) | 22.6–22.9 s | 11.2–11.4 s (2.0×) | 85 → 20 | 247–252 → 372–390 ms | 32 → 22 |
| `net_fetch.js` (17 bytes, printed) | 8.4–9.9 s | 4.9–5.1 s (1.7×) | 29 → 9 | 241–263 → 312–342 ms | 28–34 → 26–27 |

Not the 6.6× the parallel probe suggested: the 4 modems' reloads (16–18 a second in all) cost the page a third of its
frames, so a word takes ~9 frames instead of ~8, and the CPU then works through 8 bytes. On the way: the lib's
unpacking loop (~250 steps per READ) moved into `NET` itself, which writes the bytes; and the read path's runtime cells
moved out of cache sets 9 and 10, where they evicted the stack and the code on every byte (`net_long` in csssim: 524 →
91 passes). Steps per byte, `net_long`: 51 (one byte per word) → 59.

What it costs programs that don't use the network (FizzBuzz; `ab.js`, fresh browser per run; `main` at `212175a`):

| Measure | A vs A | `main` vs this branch |
|---|---|---|
| CPU-only page, load → HALT (`halttime.js`, POLL=30) | 0.996 (0.984–1.005), 8 rounds | 1.110 (0.986–1.142), 12 rounds; then 0.976 (0.945–1.094), 16 rounds |
| Editor page, Run → HALT (`ui_seq.js`) | 1.032 (1.026–1.094), 4 rounds | 1.065 (0.924–1.136), 8 rounds |
| Editor page, Run → compiled | | 1.014 (0.850–1.082), 6 rounds |
| Parser variants; temps (`tools/vsz.py`) | | 338 → 338; 70,478 → 70,499 |

No difference shows above this machine's noise; the second CPU-only run had another session's benchmark beside it.
To settle a few percent, re-measure on a quiet machine.

**Held loads, two answers per document (2026-10-22, branch `net-modem`).** Times in this section until here came from
`net/probe/pagenet.js`, which ran a `requestAnimationFrame` loop in the page to count frames, and that runs the page
~1.5× faster than without one (ENGINE_NOTES 64); the ratios hold (both sides had it), the absolute times are low. The
page has no script, so these are without one: compiled → HALT, interleaved, 4 rounds, each run in a `bench.py` lease
(the P-cores), a fresh browser per run (`net/probe/runs.js`: Run, poll the status every 100 ms; `SERVER=` the older gateways).

| Program | `main` (`abcc857`): modems reload all the time | Held loads, 4 modems | Held, 2 modems × 2 answers |
|---|---|---|---|
| `net_fetch.js` (9 words) | 6.8–8.6 s | 4.1–5.4 s | 3.4–4.8 s |
| `net_long.js` (20 words) | 18.1–25.1 s | 11.0–13.6 s | 9.1–12.5 s |
| First word after Run | 1.4–1.5 s | 0.33–0.44 s | 0.32–0.46 s |
| A URL word (gaps between the gateway's requests) | 0.36–0.75 s | 0.19–0.52 s | 0.17–0.49 s |
| A READ word (8 bytes; the program sums them) | 1.0–2.5 s | 0.69–0.99 s | 0.61–0.93 s |

Held loads: the gateway holds each modem's next load until it has the modem's answers, so a modem loads once per word
and the request goes out as soon as the page lays it out (the old document is still there to send it); the answer is
in the document (no `rx` stylesheet). 1.6–2.0× per program. A word now costs about 4 page frames (URL words; ~10 for a
READ, most of them the CPU's): the request leaves in the frame that lays it out, the gateway answers within ~3 ms,
the new documents load and scroll in the next frame, and the CPU reads the answers in that frame (the other frames are
the lib's and the register `rreq`'s). What the modems still cost is their documents: two forced style passes of the
page each (ENGINE_NOTES 63), ~100 ms of the main thread per word with 4 of them. Two answers per document (x and y)
halve that; on a page built with `net_parts` 2 (one answer per document, 2 documents) URL words took ~285 ms against
~345 ms with 4 documents (3 rounds). Built as 2 modems × 2 answers it is ahead in 6 of the 8 pairs above (a whole
round ran 25% faster than the next on this machine), and in all 8 of 4 more rounds with the order swapped
(`net_fetch` 3.4–4.8 s against 3.8–5.4 s, `net_long` 9.1–12.4 s against 10.3–13.7 s; ratios 0.87–0.94): a median
0.89, ~11% less time.


## 17. The learnxinyminutes language (2026-10-24, branch `lxym`)

Branch `lxym` (HISTORY 17): JavaScript's values (doubles in an FPU of `calc()`, `true` / `false` / `null` /
`undefined` / `NaN` as values), functions as values, closures, arrows, `this`, prototypes, `new`, timers, `Math`,
wrappers. Against main (`0f31b87`), each built in its own worktree; headless Chromium 153, the mini PC. The editor
page's FizzBuzz timings ran in a bench lease; everything after them **interleaved and unleased** (the queue was switched
off on 2026-10-24), with other sessions' work beside it.

**Model** (`cc_ref` steps, `csssim.py` passes, K = 32; the 150 suite programs and samples both run, at `a6a745c`):

| | main | lxym |
|---|---|---|
| steps | 110,746 | 121,269 (+9.5%) |
| passes | 13,739 | 15,513 (+12.9%) |

- Per program the geometric mean is 1.087: 75 within ±2%, 11 faster, 64 slower.
- Three programs do more because their numbers are now JavaScript's: `big` 9 → 99 passes and `cmp_far` 24 → 135
  (numbers past 20 bits, which main wrapped, are doubles), `num_dot` 17 → 57. A double's literal is parsed once at run
  time (~160 steps for `3.14`), and printing a double takes ~260. Without the three: +11.2%.
- `deep_recursion` 560 → 963: a frame is `[ret][this][params][env][temps]`, two words more than main's, and its frames
  miss the cache. The env slot only where a closure is made would give 760 (HISTORY, leads).
- The collector's tests (`arr_gc` +353, `obj_gc` +161, `str_keys_gc` +125, `gc_rawblock` +92) miss more: the ROM grew
  2,048 words, which moved every RAM address and so the cache sets the stack, the globals and the heap share. Without
  them and `deep_recursion`: +6.6%.
- `==` and `switch` on two strings trap to `jcmp` (it reads the jump's operator and target from the instruction, then
  `leqr` / `deqr`): `primes` 284 → 369 passes (17 comparisons at ~37 steps against main's `deq` at ~11), `bank` 76 → 92,
  `str_cmp` 74 → 114.
- Within the branch: CALLV entering closures itself, 171 programs 44,809 → 43,645 passes (closures −17.8%); a
  `console.log` chain past its pieces keeping the rest on a string piece, `hanoi` 63 → 35 (main 33: the head had
  become three heap strings per line); the runtime's common cases first (two numbers or two strings skip `prim`, a
  name as a key skips `canint`, one range test for the hidden keys), steps −6.6% and passes −1.9% over all programs
  (`num_loop` 1,075 → 849 passes, `str_keys` 8,231 → 6,481 steps, a loop over doubles 1,452 → 588 steps).

**CPU-only pages**, load → HALT (`machine/halttime.js`, POLL=30; run = first step → HALT), five interleaved rounds,
medians (ms) and the median per-round ratio, at `a6a745c`:

| Program | main | lxym | steps | ratio |
|---|---|---|---|---|
| `fizzbuzz` | 875 | 969 | 324 / 324 | 1.104 |
| `hanoi` | 772 | 894 | 273 / 273 | 1.143 |
| `bank` | 2,505 | 3,620 | 381 / 574 | 1.449 |
| `collatz` | 3,683 | 4,206 | 3,673 / 3,673 | 1.155 |
| `caesar` | 7,230 | 7,126 | 959 / 938 | 0.969 |
| `stars` | 1,898 | 2,031 | 566 / 566 | 1.069 |
| `sort` | 3,227 | 3,820 | 1,220 / 1,361 | 1.187 |
| `primes` | 11,464 | 16,436 | 2,121 / 2,776 | 1.431 |
| `tree` | 9,739 | 10,602 | 1,573 / 1,637 | 1.086 |
| `deep_recursion` | 27,227 | 48,176 | 2,007 / 2,007 | 1.771 |
| `str_cmp` | 2,993 | 4,298 | 668 / 849 | 1.464 |
| `str_build` | 3,158 | 3,605 | 135 / 123 | 1.138 |
| `obj_count` | 1,261 | 1,434 | 389 / 417 | 1.137 |
| `obj_grow` | 2,471 | 2,192 | 701 / 769 | 0.967 |
| `arr_methods` | 9,905 | 11,331 | 3,007 / 3,657 | 1.143 |
| `str_methods` | 6,888 | 8,146 | 1,816 / 2,172 | 1.187 |

- Geometric mean 1.197. Beyond the model's passes, each pass costs more: `collatz` has the same steps and passes in
  the model and runs 1.155×. The CPU page has 1,200 registered properties (main 1,137), 168 instruction classes (157)
  and 6,331 `if()` (4,148): doubles, the specials, bitwise operators and calls live in the classes every pass
  evaluates.

**The editor page, FizzBuzz 1–15** (`machine/ui_seq.js`, `../shared/js/ab.js`, six rounds, in a lease, at `a6a745c`):

| | main | lxym | ratio (IQR) |
|---|---|---|---|
| compiled (from Run) | 2,448 ms | 2,979 ms | 1.214 (1.159–1.301) |
| HALT (from Run) | 3,277 ms | 3,946 ms | 1.204 (1.200–1.205) |

- The run after compiling: 829 → 967 ms (148 steps both).
- The sample picker: twelve samples cost +9.9% of a compile (the page without a picker against with, ten rounds;
  0.909, IQR 0.904–0.928), the two new ones +6.5% (ten rounds, 1.019–1.081). Each editor had 25 `:has()` rules for
  the readback's per-line checks under its radio button; with each radio right before its editor in `.frame`, one set
  serves them all (`.pkr:checked + .ed`): 0.935 (0.918–0.939) of the compile, twelve rounds (`0908314`). So FizzBuzz
  compiles in ~2.8 s against main's 2.4 (+14%).
- The final page (`0908314`) against main, eight interleaved rounds each, unleased on a busy machine (runs up to 10 s):
  compiled 1.147 (IQR 1.105–1.348), HALT 1.151 (1.096–1.207).
- After merging main (`3d9f039`, with §18: rows named by where they show, so the per-line checks are gone from both
  pages and two per editor are left for the one set), against that main, eight interleaved rounds each, unleased on a
  quiet machine: compiled 2,256 → 2,614 ms (1.168, IQR 1.152–1.216), HALT 3,238 → 3,781 ms (1.164, 1.156–1.193).

**Compile time** (`tests/suite_css.js`, the L3 page, the 186 programs both compile, one browser, main / lxym / lxym /
main): median per-program ratio 1.178 (IQR 1.115–1.252), total 119.0 → 146.2 s. The parser evaluates 454 temps per
token on FizzBuzz against main's 374 (+21%, L2's count): the variants its tokens hit grew, an operator after a name or an
operand by 250–590 temps (`popops`' ten iterations each choose a dynamic operator now, `(` after an operand calls values
and methods, arrows and `this` add operand-stack snapshots).

**Costs.** The editor page 24.9 MB (main 17.4), 4,569 registered properties (3,828); the ROM 10,798 words (4,462); the
compiler 152,295 temps in 492 variants, 24 label ports (79,100, 338, 22).

## 18. Pasting into the editor (2026-10-23, branch `editor-paste`)

Pasting over many lines froze the page (ENGINE_NOTES 76). The probes' contents now lay out only from Run on. Paste
times, `main`'s page against this one, interleaved (`shared/js/ab.js`) in a bench lease:

| Paste | `main` | `display: none` probes while editing | `content-visibility: hidden` (kept) |
|---|---|---|---|
| 200 plain lines over 200 | 2,451 ms | 660 ms | — |
| 200 formatted lines over 200 (VS Code's HTML) | 3,251–3,509 ms | 675–730 ms | 1,212 ms |
| 2 formatted lines over FizzBuzz | 80 ms | 40 ms | — |
| Compile, FizzBuzz (`compiledMs`, ratio to `main`, median and IQR) | 1.00 | 1.02–1.04 (IQR up to 1.07; A-vs-A 1.018, 0.96–1.06) | 0.96 (0.92–1.07) |

`display: none` was faster to paste into but built ~6,000 probe boxes at Run, a few percent of the compile; the
content-visibility version keeps them and showed no compile cost above the noise.

**Rows named by where they show (ENGINE_NOTES 77).** The sentinels' names now come from a view-timeline animation, so
the positional selectors and the `:has()` rules per line are gone, and lines nested by Chrome or by a paste read as
they show. Against the content-visibility page above, interleaved in a bench lease (FizzBuzz; pastes as above):

| | before | rows named by position |
|---|---|---|
| 200 formatted lines over 200 | 1,125 ms | 211 ms (0.19×) |
| 200 plain lines over 200 | 1,174 ms | 222 ms (0.19×) |
| 8 formatted lines into FizzBuzz | 81 ms | 33 ms (0.38×) |
| Compile, FizzBuzz (`compiledMs` ratio, median and IQR; A-vs-A 0.997, 0.985–1.016) | 1.00 | 0.945 (0.924–0.974) |

The first version left every probe's 64 cells laid out, absent rows' too, and the compile took 1.37× as long (IQR
1.35–1.38): the old `:has()` rules had hidden the probes of absent lines. A probe's width now comes from its
sentinel's height (constant through the scan), and `@container (width: 0px)` drops its cells. Pausing the rows'
animations at Run, or dropping their `:has()` leaf filter, changed nothing (1.41×, 1.41×).

**Leading sentinels, shown `<br>`s, the unread-rows note (2026-10-24, branch `editor-quirks`).** Against `main`,
interleaved, unleased (other agents' runs alongside): compile of FizzBuzz 0.981 (IQR 0.923–1.062; A-vs-A 0.995), 200
formatted lines over 200 1.000 (0.926–1.067): no cost above the noise.

## 19. The page's CSS in linked stylesheets (2026-10-24, branch `css-split`)

The 13.8 MB inline `<style>` became 15 linked sheets in `js_in_css/` (ARCHITECTURE §6), and the parser variants moved
into one section per family of modes. The rules are the same (5,764, each section's in its order but the variants').
Against `main`'s inline page, three variants (A, A again, the split page), 9 rounds interleaved with `ab.js`,
unleased (other agents' runs alongside, load average ~12), FizzBuzz on the editor page (`ui_seq.js`):

| ratio to A (median, range) | A again | split page |
|---|---|---|
| load (`p.goto` to `load`; A 714 ms) | 1.020 (0.80–1.15) | 0.654 (0.55–0.75): 481 ms |
| compile (`compiledMs`; A 2,443 ms) | 0.987 (0.88–1.13) | 1.000 (0.91–1.08) |
| Run → HALT (`haltMs`; A 3,506 ms) | 0.991 (0.89–1.09) | 0.991 (0.91–1.04) |

Compile and run cost the same. The page loads in two thirds of the time, every round. Not explained: the XML parser
no longer holds 13.8 MB of CDATA, and the sheets load in parallel, but no trace separates those.

On `lxym` (merged 2026-10-24, 1d2ad55): 16 sheets (lxym's arrow functions made `parser-functions`), the largest
`parser-names.css` at 9.2 MB, the page 4.3 MB; the same 6,520 rules as lxym's inline page. Against that page, the
same three variants, 21 rounds (9 + 12) interleaved, unleased (load average 2–9):

| ratio to A (median, IQR) | A again | split page |
|---|---|---|
| load (A 987 ms) | 0.998 (0.97–1.03) | 0.709 (0.67–0.72): 703 ms |
| compile (A 2,724 ms) | 1.004 (0.98–1.07) | 1.009 (0.98–1.05) |
| Run → HALT (A 3,840 ms) | 0.998 (0.98–1.07) | 1.005 (0.98–1.05) |


## 20. The REPL (2026-10-24, branch `repl`)

All pinned to the E-cores (`taskset -c 8-15`: ~1.9× slower than the P-cores but steady; the machine had 5–20 other
agents' load), interleaved with `../shared/js/ab.js`, ratios per round against `lxym` (`a6a745c`). A against A: IQR
0.985–1.015.

**What it costs a program** (FizzBuzz; the REPL chip not picked):

| Change | CPU-only page, Run → HALT | Real page, Run → compiled |
|---|---|---|
| The console 40 × 32 for every program (first try, P-cores, loaded) | | Run → HALT 1.24 (1.08–1.28) |
| The console's RAM as 1,312 words: trees in radix 82 × 4 | 1.176 (1.159–1.180) | |
| 1,536 words, radix 6 × 4 × 4 × 4, groups of 16 | 1.028–1.033 | |
| … the out class's `--pmk` / `--pmo` not inherited | 1.021–1.030 | |
| … the program's grid in trees of its own (144 cells), the REPL's in trees nothing shows | 1.001 (runMs) without the hidden trees, 1.017 (1.001–1.026) with them | |
| The CPU's latch fix (`tests/suite/latch_chain.js`) | 1.027 against 1.028: none | |
| The compiler's REPL mode, the line as `--lnum` on each line's levels | | L3 page: FizzBuzz 1,346 → 1,735 ms (+29%), others +2–7% |
| … a newline counter in the lexer's state | | L3: +4% |
| … the line where the token is written (`.trl<k>` on each level's `.tr`) | | L3: +2.2%, −1.0% (two rounds) |
| All of it (`NOREPL=1`: the page without the REPL's own parts) | | 1.005–1.008 |
| The page with the REPL | | 1.056–1.061 (FizzBuzz ~4.88 → 5.16 s); Run → HALT 1.046 |
| **The REPL on a page of its own** (the program page without its parts; the compiler's `rst`, `rdone`; against `8306b38`) | | **1.013 (1.003–1.023)**, 10 rounds (A against A: 1.001, 0.970–1.018); FizzBuzz ~4.7 s |

A per-line value on the compile chain's levels (inherited, registered or not) makes the levels of different lines
differ, and Chrome stops sharing their style (the matched properties cache): FizzBuzz, with many short lines, paid most.
The REPL's own page parts (its CSS section ~2%, the rest in pieces of 0.2–1%: the `:has()` count that was on `#app`,
~200 registered properties, timeline names, an editor's probe rules) cost a program ~5% of its compile; a page without
them (`NOREPL=1`) costs 0.5%. So the REPL moved to a page of its own (`repl.xhtml`): what is left on the program page is
the compiler's REPL mode, 2,216 more temps (154,511 against lxym's 152,295, +1.5%), ~1% of a compile.

**What an entry costs** (P-cores, unpinned, load ~5): Enter → the output shown, the whole session read, compiled and run
again. 8 lines (284 steps): the scan done 2.2 s, compiled 2.5 s, shown 3.9 s. 19 lines (`tests/repl/statements.js`, 1,544
steps): 3.9, 4.7, 12.9 s. Pinned to the E-cores, line by line through that session: 3.2 s for the first, 9.8 s at 5,
20 s at 10, 36 s at 15, 57.5 s at 19. The run grows with the session (each Enter replays it all) and the scan with the
editor's text (it reshapes every line every frame).

**With the state kept** (the REPL's page; each Enter runs only its entry): `tests/repl/statements.js` line by line
(`WAIT=1 node tests/repl_ui.js`), pinned to the E-cores: 4.8 s for the first, 6.8 s at 5, 11.6 s at 10, 13.0 s at 15,
15.5 s at 19 (the replay: 3.2, 9.8, 20, 36, 57.5). The 19th entry, two runs: the scan restarts 1.35 s after Enter, ends
at 12.2–12.7 s, the compile at 13.8–14.5 s, the output shows at 16.5–17.3 s (37 steps). So the scan is the cost now: 64
columns a frame each, every frame reshaping every line, though the lines already run keep their latched characters.

## 21. Compile speed (2026-10-24, branch `compile-speed`)

Against `main` (`c3f6900`, built in its own worktree), headless Chromium 153, the mini PC, **interleaved and unleased**
(`../shared/js/ab.js`, fresh browser per run; other sessions' browsers ran alongside, load 2–11).

**Where a compile went** (FizzBuzz on `main`'s page, a trace from Run, unpinned): the scan 64 frames of ~25 ms (mostly
layout) to ~1.9 s; then the compile chain in two style passes: the lexer's, 851 ms (810 of it style), and the parser's,
434 ms (394). On the L3 page the same chain: pass 1, 8,913 elements, ~400 ms; pass 2, 3,785 elements, ~320 ms.

| Change | What it does | Measured |
|---|---|---|
| Padding levels pass the lexer state through (`ccpage5` `CL_PAD`) | ~1,350 of FizzBuzz's 1,561 character levels: 15 copies instead of the space lexer's 63 declarations | L3 total (11 programs) 0.933 (IQR 0.906–0.939) |
| … and token levels wait for their tokens (`--has: 0` → `display: none`) | the lexer's pass no longer runs ~110 token levels' base rules on zeros: pass 1 400 → 261 ms (5,195 elements) | L3 total 0.843 (0.828–0.845); page Run → compiled 0.919 (0.888–0.932) |
| … and the scan stops at the first column blank in every row (`ui_rb.py` `EARLY`), columns past it read as spaces (`--rbe`) | FizzBuzz ~48 frames instead of 64 | see below |
| … and the latch cells show no counter text | a scan frame 24.7 → 22.3 ms (layout 13.9 → 11.5) | (in the totals below) |

**All of it against `main`**:

| Measure | `main` | `compile-speed` | ratio (median, IQR) |
|---|---|---|---|
| The page, Run → compiled, FizzBuzz then `and_or_chain` typed after it (sum; `ui_seq.js`, 8 rounds) | 5,585 ms | 3,989 ms | 0.712 (0.694–0.718) |
| L3, the compile chain alone, 11 programs (sum; `suite_css.js`, 6 rounds) | 15.5 s | 13.0 s | 0.857 (0.840–0.867) |
| The REPL page, `tests/repl/basics.js`'s first entry, Enter → its output shown (`WAIT=1 repl_ui.js`, 4 rounds) | 3,178 ms | 2,213 ms | 0.701 (0.681–0.828) |

Single runs on a quiet machine: FizzBuzz compiles ~2.0 s after Run against ~2.9 s (the scan ~1.5 s against ~1.9 s, the
chain ~0.4 + 0.3 s against ~0.6 + 0.35 s). The pages grew 0.2 MB (each character level's three codes masked by `--rbe`).

**Costs found on the way** (L3 traces and ablations, FizzBuzz unless named):

- A character level costs ~170 µs even as pure padding: with its rules stripped to `display: contents` ~75 µs, and without
  the line sources' animations ~10 µs. A synthetic chain of 1,561 nested `display: contents` levels styles in ~3 µs a level
  (17 µs cold), with 4,000 registered properties, 16 parity calcs a level or 3,000 inherited properties set above it
  (+15 µs a level, cold): the nesting costs nothing. Creating the 1,536 line-source animations is ~40 ms of the lexer's
  pass (kept alive across runs: 255 → 215 ms); all on one element they make every paint 170–280 ms (ENGINE_NOTES 83).
- A token level costs ~1.1 ms of plumbing (the variants' bodies stripped: pass 2 300 → 120 ms) and ~1.6 ms of its variant.
  Of the plumbing: the table writes' 160 container rules ~50 ms of the pass (−16% without them), the overlay and
  label-port children ~25 ms (−8%).
- The real page's lexer pass costs about twice L3's for the same elements (542 against ~260 ms): unexplained; not the
  inherited properties set above the chain, not the page's 36% more registered properties (4,628 against 3,392).
- Selector matching is negligible (selector stats: ~1 ms a pass).
- The scan: a frame restyles ~640 elements (the active group's cells, their registers, the probes) in 3–5 ms; its
  layout is most of the frame. Two columns a frame (one sentinel up to 9,215 px wide) halved the frames but ran 2.4
  passes a frame against 1.5 and each layout cost 18.7 against 13.1 ms: Run → compiled 0.874 against 0.798 for one
  column, both against `main`, pinned to CPUs 12–15 (ENGINE_NOTES 84). A reset of every latch cell at the sweep's start
  cost a 210 ms layout (ENGINE_NOTES 86).
