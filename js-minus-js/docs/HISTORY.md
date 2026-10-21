# History: how the design got here, and what didn't work

Numbers for superseded code come from raw logs and earlier chats on other machines. The code was removed on
2026-10-15 (`git checkout 91d73bc -- js-minus-js/archive`), the logs on 2026-10-18 (`83d4fde`), the font CPU (timeline 2–11)
on 2026-10-20 (last at `181cbb7`). "Self-compile": the self-hosted `jsc.js` in ROM compiles FizzBuzz at run time, then runs it.
"Direct fizz": FizzBuzz compiled into ROM.

## Timeline

- **0, HarfBuzz spikes (2026-10-09).** One Lookup referenced K times in the LookupList runs K steps per shaping (a toy
  VM font reached 16,000; the sanitizer caps subtables at 16,384).
- **1, pure-CSS stack VM.** ROM as `if()` branches, RAM as remembered sizes. Self-compile 3,609 s, direct fizz 316 s.
- **2, font CPU.** State as a line of glyphs, S micro-cycles per shaping, CSS servicing traps; a ring cache replaced
  FIFO + evict buffer. Self-compile 1,287 s. Traps limit instructions per shaping; style and layout dominate shaping.
- **3, any zoom.** One font unit = one device pixel (`zoomfix.py`).
- **4, decode-tree RAM.** Style + layout 70 → ~20 ms per pass; direct fizz 87.5 → 22 s; self-compile 385 s.
- **5, 4-word cache lines, four RAM banks.** Self-compile 250 s; N16 S32 best.
- **6, compiler in CSS.** jsc in ROM spent ~365 s compiling FizzBuzz vs ~14 s running it. `cc_ref.py` and its DSL
  twin replaced it. FizzBuzz recalc by generator: 8,562 ms (whole step per character) → 3,104 (parser per token) →
  914–1,573 (variants per (mode, token), delayed tables, label anchors) → 318 (class-specialised lexers).
- **7, typed input.** Readback joined to the compiler; fixed style-query values ≥ 256, 13k registered temps,
  per-level animations, HTML nesting. Compiled ~5 s after Run; FizzBuzz halted ~27 s after Run.
- **8, correctness.** `var a = "hi"; console.log(a)` printed 4352 (strings were bare addresses). Built the five
  test levels (first run 37/53), tagged strings, static types and most of the language; `FALL` folding halved the
  CSS. Later (2026-10-17) block scope, `const`, `do … while`, `?:` and rule merging (BENCHMARKS §4c).
- **9, execution speed (2026-10-13).** The PRINT family, slim readback readers and a compositor layer for the editor:
  FizzBuzz 193 → 103 shapings, ~1.9× faster on the page.
- **10, 16K RAM (2026-10-13).** Dense RAM cost ~2.4 ms per pass per 1,000 untouched cells; sparse groups made cost
  follow the working set. 15-bit addresses, 1K ROM, `compiler/layout.json`.
- **11, objects and GC (2026-10-17).** Self-looping probes (3 micro-cycles per key vs ~20 as a jsc loop), ROM routines
  for the slow paths, Cheney GC (mark-sweep would touch the whole heap, ~770 shapings per collection). The first
  version needed 531 subtables per cycle; gated rule groups and `merge_digits` got 392. Fixed on the way: 16 copies of
  every self-update rule (HarfBuzz −6%), comparisons overflowing for operands 2^19 apart (`tests/suite/cmp_far.js`),
  the model's 20-bit address mask. FizzBuzz within 1% on the page.
- **12, the CSS CPU again (2026-10-19).** Chained shapings (branch `chain-shapings`) showed nested containers running
  several recalcs in one pass; a toy of instructions in style alone came out at 0.38 ms per instruction against the font
  CPU's ~8.6. The machine (`machine/gen_css.py`, `exp/csscpu/README.md`): a chain of instruction levels per pass, a
  2-way cache in custom properties, read ports at the chain's end, latches against livelock. Getting it fast was
  learning Blink's style costs: a container-query test ~2 µs per element (a rule per opcode and per cache word made
  idle levels 269 µs), an `if()` ~70 ns per entry it contains, size containers above a subtree restyling it once per
  container (7 times per fill). FizzBuzz on the page 10.5 → 3.9 s after Run; CPU-only pages 2.8–7.3× faster
  (BENCHMARKS §12). The font CPU's code was removed; it last exists at commit `181cbb7`.

## Dead ends and superseded approaches

| # | Tried | What happened | Replaced by |
|---|---|---|---|
| 1 | Pure-CSS VM as the CPU (2026-10-09) | 3–4× slower (3,609 vs 1,287 s; 1,502 vs 385 s): one instruction per pass | font CPU; then the CSS CPU (timeline 12) |
| 2 | One `@container` rule per RAM cell per write channel | 70 ms style + layout per pass | decode tree, ~20 ms |
| 3 | FIFO cache + evict buffer, data moving between lines | long contexts, slow in HarfBuzz | ring with a victim pointer |
| 4 | One-word cache lines | more traps | 4-word lines (385 → 250 s) |
| 5 | fontTools' feature compiler | can't alias lookups | hand-written `otl.py` |
| 6 | More than 16,384 aliased subtables | sanitizer rejects | ≤ 16,000 per font |
| 7 | S = 48 micro-cycles | never ran (S × subtables over the cap) | S = 32 |
| 8 | Unsigned 20-bit words in registered properties | 1048575 → 1048580 through `var()` | signed words |
| 9 | jsc compiling at run time on the CPU | ~365 s compiling vs ~14 s running | compiler in CSS |
| 10 | Whole compiler step per character | 8.5 s recalc | lexer/parser split |
| 11 | One generic parser per token level | 3.1 s recalc | container-query variants |
| 12 | Specialising on every punctuation value (46 MB CSS) | slower (1,813 vs 914 ms) | class-bucketed lexers |
| 13 | Variant ids ≥ 256 in style queries | never match | small fields |
| 14 | Symbol and function tables as parser state | every level copies them | delayed writes via ports |
| 15 | Animating each character level | ~3 ms per level | one source per line |
| 16 | 13k registered temps | animations very slow | pooled names (~2.6k) |
| 17 | HTML documents | nesting stops at 512 | XHTML |
| 18 | Pausing or freezing the chain's animations after the read | play-state from the base style; paused-created animations miss the timeline | sources keep running; `display: if()` |
| 19 | Time-driven editor scan | skipped columns | frame-locked scan |
| 20 | Scan range from the editor's width | flickers | fixed 64 columns |
| 21 | Inherited per-frame driver state | restyles every cell | non-inherited state |
| 22 | Two end-of-input levels | redundant | one NUL slot |
| 23 | Line sources paused after the read | unreliable capture | sources keep running |
| 24 | Strings as bare pointers | printed as numbers (4352) | tagged pointers |
| 25 | Tag offset 2^19 | untag overflowed 20 bits | 2^18 |
| 26 | Untag constant built with SHL13 | an EXT trap per string print | constant in a RAM cell |
| 27 | The constant in the string area's first cell | +23 misses on FizzBuzz | a cell on a hot line |
| 28 | Separator as an argument, or emitted by the caller | +9% steps, or code overflowing the cache | `…Ln` entry points |
| 29 | A fresh wrapper per `else if` | 8 branches overflowed the control stack | reuse the `else`'s wrapper and label |
| 30 | Label ports per possible deflab site | 26–35 ports per level | collected labels, pruned blocks (22) |
| 31 | Printing in the lib (PUTC per char, MOD/DIV per digit) | 114 of FizzBuzz's 193 shapings | PRINT family |
| 32 | Readers with value, scroller, spacer and pad per size container | ~1,300 restyles inside layout per pass | one scroller, positioned subjects |
| 33 | 3 or 4 issues per frame | wrong output | 2 issues |
| 34 | Code / data cache partition (model) | suite shapings +5% | one ring |
| 35 | Read-decoded anchors (read block down the trees) | whole trees restyled: 90 ms per recalc at 16K | sparse RAM groups |
| 36 | 13-bit addresses, ROM 0 … 4095 for a 93-word lib | RAM capped at 4K words | 15-bit, 1K ROM |
| 37 | Object instructions with 3-way selectors everywhere | 531 subtables per cycle; export dropped | gated rule groups, merged digits |
| 38 | `x[k]` dispatch in microcode (KEYV, PUTX), DUP2 | +1.2 ms per shaping for all programs | ROM dispatch via JNEG; OVER OVER |
| 39 | NEW zero-filling its chunk | 12 micro-cycles, two lines per object | NEW zeroes nothing; ENDK |
| 40 | Every identifier writing its bytes to the string area | FizzBuzz compiled ~7% slower | only after `.`, `{` or `,` |

## Open leads (untried)

- **Fewer traps.** Suite traps are mostly misses (1,309) and arithmetic EXT (1,104; 160 in `primes.js`): MOD / DIV,
  SHL13 and small-constant multiply in the font; dirty lines above SP treated as clean; an eviction buffer; next-line
  prefetch; top of stack in registers; two characters per word; read misses serviced within one layout pass (a toy
  chained 8 shapings in one layout).
- **Allocation loops** (`obj_gc.js`: 18 shapings per iteration, 14 misses evicting the loop's code): LRU, or writes to
  fresh heap lines that bypass the cache.
- **RAM group size 16 or 64** instead of 256: measured, not adopted. Both halted ~6% sooner in two rounds (BENCHMARKS §8);
  re-check with `ab.js` and the L5 suite before switching.
- **More shapings per frame**: chain dependent shapings in one lifecycle update with container-query
  layout → style → layout loops ([JS-in-CSS multicore](https://claude.ai/chat/91b25db5-fef0-4893-9055-42e5003ad7e5)).
  N16 S64 (needs fewer subtables per cycle).
- **Per-program CPU fonts**: hot blocks compiled to GSUB, or superinstructions from traces.
- **Compile time** (the sweep is ~1.2 s): several columns per frame; parallel lexing by prefix scan over the DFA.
- **Other compute surfaces** ([CSS JavaScript interpreters speedup](https://claude.ai/chat/427a6452-26e2-4ff6-8289-3177eab3cabc)):
  `@function` / nested-grid lookup chains (300–600 dependent lookups per update); avar2 (ENGINE_NOTES 33). css-physics
  measured both as compute (its `docs/HISTORY.md`): `@function` 2–3× slower than the same math inline (Chrome 141); each
  new set of axis values a new font instance, 47–106 µs (its BENCHMARKS §3).
- **Language**: a wider console; built strings; printing objects, `undefined`, `in` / `delete`, prototypes; booleans
  as parameters; specific error codes on the page.
