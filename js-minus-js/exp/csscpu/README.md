# A CPU in style alone

Since 2026-10-19 this is the page's CPU (`machine/gen_css.py`, `machine/csssim.py`, `docs/ARCHITECTURE.md` §3); the font
CPU was removed (last at commit `181cbb7`). This directory keeps how it was found and measured: the toy, the timing tools, Blink's style costs.

Can CSS style recalc beat the font CPU (HarfBuzz) at running js-minus-js bytecode? Two stages: a toy that times
instructions with nothing missing (`mkcpu.py`), then a CPU-only page that runs real programs to HALT
(`machine/gen_css.py`), timed against the font CPU's CPU-only page.

## The machine (`machine/gen_css.py`, oracle `machine/csssim.py`)

`python3 machine/gen_css.py image.json out.html` takes a `compiler/mkimage.py --ram` image, as the font CPU's
`gen_fvm4.py` did, and builds a page with no font and no script. FizzBuzz, gcd, primes, array_sort, str_table, bool_print, putc
and break_nested run to HALT with cc_ref's exact step counts and the expected console.

```
python3 compiler/mkimage.py --ram tests/suite/fizzbuzz.js build/csscpu/fizz.json
python3 machine/gen_css.py build/csscpu/fizz.json build/csscpu/fizz.html        # K=32 ISSUE=2
POLL=30 node exp/csscpu/halt.js build/csscpu/fizz.html build/csscpu/fizz.json     # load -> HALT, checks the console
python3 machine/csssim.py tests/suite/fizzbuzz.js 32                               # passes, checked against cc_ref
```

A layout pass (two per frame, the font CPU's frame gate):

- **`#cpu`** holds the registers as view timelines (as the font CPU did): pc, sp, fp, the output cursor, the cache
  (16 sets × 2 ways × 4 words: 128 words, 32 tags with dirty bits, 16 victim bits), the pending miss and the read
  ports' eight words. 262 registers.
- **`.fl`** fills the block the last pass missed into its set's victim way (a dirty victim goes out through the RAM
  write channels) and prefetches the next block if it is absent and its victim is clean.
- **K = 32 levels** of three nested `display: contents` elements. `.f` fetches (ROM from a static table, as the font
  has its ROM inside it; RAM through the cache) and decodes. `.x` executes: one `@container style(--cls: c)` rule for
  each of 7 instruction classes, `if()` on the opcode inside it. `.c` commits the registers, and a write as its whole
  cache set (16 rules). An instruction runs only if every word it touches is cached (and, for output, the pass's
  console write set is free); the first one that can't stops the chain and records its missing block.
- **`.ex`**, at the chain's end, holds the registers' subjects, routes the pass's writes into the RAM and console
  channels, and holds eight read ports (readers, as the font CPU's page had). They read the missing block and the next one
  from the ROM and RAM leaves (`memtree.py`) during the same pass's layout and keep the words in registers for the next
  pass's fill.

The console has its own trees and channels inside a `contain: strict` box, so output doesn't restyle the RAM trees. A
channel keeps its cell until it takes another, rather than being cleared every pass (a channel change restyles its
whole tree). A miss on the block the same pass writes back would read its leaf before the write lands, so that fill
waits a pass (`machine/csssim.py` models it; FizzBuzz hits it once).

A stalled instruction keeps the operands it did read (latches: the fetched word, the stack words, the indirect reads,
a string's block) for its re-execution as the next pass's first instruction; a read is kept only if the reads its
address depends on were good. So an instruction always completes (each pass adds at least one operand) and needs only
its written line resident at the end. Without them `str_escape.js` never finished: its PRINT's code, stack top and
string were three blocks in one 2-way set, each fill evicting another. JNEG (emitted by the compiler for arrays) is
in the jump class.

`machine/csssim.py` is the design pass by pass: same cache, prefetch, stall rules, latches, PRINT chunking (uarch's print
service). It predicts the passes (FizzBuzz 36 at K = 32; the page latches every good read where sim keeps those before
the first miss, so the page can take fewer).

Checks (`make test` runs C1; `make c2`):
- **C1** (`tests/csscpu_sim.py`): csssim.py runs every suite program's image (the padded editor source, as the page compiles it)
  against Node's output and cc_ref's step count.
- **C2** (`tests/csscpu_pages.py` builds, `tests/csscpu_pages.js` runs): a page per program under 1,500 steps (111),
  each run to HALT in Chrome, console against Node's, steps against cc_ref's.
- `machine/gen_css.py` refuses to write a page in which a registered integer's value is more than one term (`--m: (a) * b`
  instead of `calc((a) * b)`): Chrome takes such a value as invalid and uses the initial value, 0, silently.

## Results (2026-10-19, headless Chromium 153, mini PC)

Load → HALT, `halt.js` with `POLL=30` for both pages, run alternately, two runs each. The font CPU pages are
`gen_fvm4.py` (commit `181cbb7`) without `UI=1` on the same images (its step count is one lower: it counts differently).

| Program | Steps | CSS CPU | Font CPU | Speed-up |
|---|---|---|---|---|
| FizzBuzz | 462 | 985–1,033 ms | 5,714–5,753 ms | 5.7× |
| `gcd.js` | 122 | 420–436 ms | 1,677–1,691 ms | 3.9× |
| `primes.js` | 1,774 | 1,732–1,779 ms | 12,787–13,022 ms | 7.3× |
| `array_sort.js` | 647 | 1,004–1,049 ms | 4,689–4,788 ms | 4.6× |
| `str_table.js` | 165 | 656–695 ms | 2,682–2,779 ms | 4.0× |
| `bool_print.js` | 46 | 392–400 ms | 1,097–1,127 ms | 2.8× |

The first step comes ~0.33 s after navigation (the font page: ~0.52 s); FizzBuzz then takes ~0.65 s, 36 passes in
~20 frames of ~33 ms. Short programs are mostly load.

How it got there (FizzBuzz, load → HALT): first correct page 2.5 s; class dispatch and set commit, ROM table and
prefetch 1.6 s; ports' muxes evaluated only on the ports and only when filling 1.5 s; console trees and holding
channels 1.26 s; ports moved below the chain 1.0 s. K = 20 / 48 and 3 or 4 issues per frame were slower.

## What things cost in Blink (measured here)

Per element, every chain level distinct (identical levels hit the matched-properties cache and time as free):

- **A container-query rule tested costs ~1–3 µs, matched or not.** The first chain had a rule per opcode (~50) and
  per cache word (128): a stalled level cost 269 µs, 16 µs without those rules. Classes and set commits: 47 µs.
- **A declaration costs ~1.3 µs**; an executing level has ~60 and costs ~340 µs (`chainbench.js`).
- **An `if()` costs ~70 ns for every entry it contains, taken or not, nested ones included, plus ~0.45 µs per
  condition tested** (1,024 entries: 75 µs with the first branch taken, 525 µs with the last; as 32 × 32 nested,
  75 µs and 100 µs). So a large table belongs in a rule that only matches when needed: the ROM table inside the fetch
  cost 40 µs on every RAM fetch; the 4,352-way read-port muxes cost ~5.5 ms a pass on `#cpu`.
- **Size containers above a subtree that inherits what they read restyle it once per container whose size
  changes.** With the eight read ports nested above the chain, one fill pass restyled the chain and the register
  subjects 7 times inside a single Layout (33 ms).
- A register subject costs ~4.5 µs of style a pass; the register animations little (128 fewer: ~0.3 ms).
- Not in Chromium 153: `ident()` (an anchor name from a number would replace the muxes) and `inherit()`.

`chainbench.js` (with `machine/gen_css.py BENCH=1`, `STALL=1`, `DUP=name`) times the chain alone from a real pass's start
state; `DUP` copies a declaration under a new name to price it without changing results. (A pass in ROM needs `--rom`
on the bench root, which `BENCH=1` sets since 2026-10-21: ROM code costs ~470 µs a level against ~378 µs for FizzBuzz.) `passcost.js` and
`stylecount.js` (`PER=1`) give per-pass costs and what restyled, `dbg.js` the registers each frame.

## The toy (`mkcpu.py`)

L instructions, nothing missing (the cache preloaded with the lines the run touches), timed per full recalc by
`bench.js` (each trial changes the immediate of `PUSHI 3` in `loop.js`'s loop, so every later state changes):

| Cache lookup | Every op reads its operands | Only the ops that use them |
|---|---|---|
| fully associative: 16 tag compares, 16-term sums | 0.72 ms | 0.57 ms |
| direct-mapped, `if()` select | 0.54 ms | 0.42 ms; 0.38 ms with lazy stack reads |

The font CPU costs ~8.6 ms per instruction on the page (BENCHMARKS §11 on branch `chain-shapings`).

**Measuring pitfall.** Blink stops restyling where computed values stop changing. A first harness varied the loop
counter, which the program overwrites in its first instructions, so only a few levels were recomputed and some pages
timed at 8 µs per instruction. A trial must change every later state, and the harness must check that it did.

## Where time goes now

The chain's executing levels (~340 µs each) and per-pass fixed costs (~6 ms). Programs that miss on most passes
(deep recursion, heap allocation: every victim dirty, so no prefetch) run one block per pass; a second write set per
pass, prefetching into dirty victims, or allocating a push's block above `sp` without reading it would help them.
