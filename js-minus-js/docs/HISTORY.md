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
- **13, the register machine (2026-10-21).** A proof of concept on a subset (`exp/regvm/`) ran compute-bound programs
  2.0–2.6× faster than the stack machine at the same compile time, so the whole language moved over: two-word
  three-address instructions, a stack of operand descriptors instead of a register allocator, the runtime library
  compiled by `cc_ref` itself, and instructions that do in CSS what the stack machine left to ROM routines: the dynamic
  operators, `a[i]` and `o.x` in place, NEW, a string's `+` written word by word (the cat class), traps that write their
  frame one word per execution. The full language first compiled 8–13% slower than main (median per program); inlining
  the DSL's single-use temps and materialising each code record's word brought it to 3% (BENCHMARKS §14). Run times:
  §14. The stack machine last exists at `212175a`.
- **14, the hybrid (2026-10-22).** Benchmarked against each other, the register machine won on compute and branch
  `rom-css` (the stack machine with the runtime's work on memory as instructions, a cache line per execution) on
  strings, arrays and objects. The hybrid took `rom-css`'s primitives onto the register machine, redone for three-address
  code (KIND, ALLOC, the MCPY and MCMP families, APUSH, a line-wide cat class), and found its two remaining costs on the
  way: the collector's per-collection walk of from-space (now a map kept as blocks are made, which also fixed a hang on a
  grown array's headerless block) and user code evicted from the data cache by the data it works on (now a code cache of
  its own: suite passes −28% in the model). With GETX / SETX probing objects in the machine, 25 programs ran 1.74× faster
  than the register machine and 1.53× than `rom-css` (geometric means); two light programs 3–4% slower than the register
  machine, since every register costs every pass (BENCHMARKS §15).
- **15, the network (2026-10-19 … 21, branch `css-fetch`, on the stack machine).** `fetch(url)` / `read()` through one `NET` instruction and
  a modem iframe that reloads itself (ARCHITECTURE §3.8). `<object>`s fire their request once only (ENGINE_NOTES 53); a
  quirks-mode child reads any same-origin body as CSS (50). The first return channel was responsive iframes (51): it
  needed a flag in 153 and its height never shrank (52). The user's fragment-scroll readback (56,
  `net/xhtml-tests/`) replaced it: no flag, 20 bits per answer. The gateway is a proxy: CSS can't build a URL, and CSS
  can't read an arbitrary body. On the font CPU a word took 0.5–0.8 s; on the CSS CPU about 0.25 s. Then 4 modems with
  2 bytes each: half the time for a body (BENCHMARKS §16), not the quarter the probe promised; two bugs on the way, a
  hidden box restoring stale answers (ENGINE_NOTES 59) and the request flickering to idle on settling passes.
- **16, held modem loads (2026-10-22, branch `net-modem`).** The modems stopped reloading all the time: the gateway
  holds each one's next load until it has the answers (ENGINE_NOTES 62), the old document sends the next request as
  soon as the page lays it out, and the answer is in the document, not a quirks-mode stylesheet. 1.6–2.0× per program
  (BENCHMARKS §16). Traces then showed what a modem document costs the page: two forced style passes of the CPU page
  each, at its parse's end and when `document.fonts` turns ready (ENGINE_NOTES 63), so each document now answers two
  parts, on its slot's x and y. On the way: a harness's `requestAnimationFrame` loop had been running the page 1.5×
  faster than a user sees it (64), and a server-wide cap on held loads starved `make l5-net`'s 6 browsers (the cap is
  per browser now, by cookie).
  `NET` moved to the register machine with the hybrid's merge (2026-10-23): `NET A, B` (ARCHITECTURE §3.8).
- **17, the learnxinyminutes language (2026-10-23, branch `lxym`).** Everything in the learnxinyminutes JavaScript
  tutorial, one phase at a time, each through every test level: specials and `typeof`; doubles in an FPU of `calc()`
  (IEEE in Chrome, bit for bit) with JavaScript's shortest printing; bitwise operators; expression statements,
  implicit globals, labels, for of / in; functions as values, function expressions, nested functions and closures
  (an env cell per frame, closed on return by a label that turns RET into a trap); arrows; hoisting; `this`, method
  calls, `call` / `apply` / `bind`; prototypes as a link where an object's keys end, which the machine's probes follow;
  `new`; timers; `Math`; wrappers and `String.prototype`. The ROM grew to 12,288 words. Two new mechanisms carried
  most of it: a library call can find its operands in the instruction that trapped (as `jcmp` already did), and keys
  no probe takes (`x[hidden]`) send rare properties (`__proto__`, `prototype`, `Math.PI`) to the library without new
  instructions. Compile time +3–4% (arrows' rules and ports), run time +2.4% passes over the suite (the `this` slot,
  `callv`'s new cases), then −2.6% with CALLV entering closures itself (BENCHMARKS §17).
  Two page bugs surfaced on the way. The editor page started every program with its globals at 0 (Edit zeroes RAM),
  where hoisting and the function cache need `undefined`: a declared function used as a value (`new F`, `var g = f`)
  was a number there, and only the editor page showed it (C2 builds its pages from images); Edit now sets the global
  cells to `undefined`. And C2 pages stalled under load (arrows at step 786, once at `a02921a`; three pages per run once
  closures made `mkfn`, which reads code words through the data cache, common): six browsers on one page stalled half of
  them, always at the same LDI, with nothing pending and the same block in both ways of its set. The data fill had no
  check that its block was absent (the prefetch has one); a pending miss seen again after its fill, as when a register
  lands a frame late under load, filled the other way too. With the check, 30 of 30 such runs halt.
  Against main, measured last (BENCHMARKS §17): CPU-only pages 1.20× slower (geometric mean of 16 programs: more passes
  where frames grew or strings compare, and each pass costs more, the instruction classes carrying doubles, specials
  and calls), compiles 1.18× slower (median of 186 programs: 21% more temps per token). Three cuts on the way: a
  `console.log` chain past its pieces keeps the rest on its last piece when that is a string (`hanoi` had become three
  heap strings per line: 63 → 35 passes, main 33); the runtime takes its common cases first (two numbers or two
  strings skip `prim`, a name skips `canint`: steps −6.6%); and the picker's radio buttons moved next to their editors,
  so one set of readback rules serves all thirteen (`.pkr:checked + .ed`; per editor they had cost ~10% of a compile).
  Two tests from the start, `fn_in_block` and `nested_function`, became programs: the branch compiles them.
- **18, the REPL (2026-10-24, branch `repl`, from `lxym`).** A chip that turns the editor into a Node-style session:
  Enter runs it, and each entry's output and value show under it (ARCHITECTURE §3.10, README REPL). No script presses
  Run, so the page sees the editor's line count change (`:has`) and restarts the scan; CSS keeps no machine state
  between runs, so each Enter replays the whole session. The compiler got a REPL mode (entries end where a top-level
  statement starts a line: an echo of the entry's value, and a mark of where the output stands), the console a larger
  grid for the REPL and the marks, and the display latches what the last finished run showed. Then (the same day) a
  page of its own, which keeps the machine's state: Enter still reads and compiles the whole session, but the run
  starts at the first entry after the lines the last run read (the compiler's `rdone`, its start `--ccstart`), on the
  RAM that run left. That took three things the replay didn't need: the CPU writes its cache back once halted (a line
  a pass; a new run's CPU starts with an empty cache), the console's cursor starts at the last end mark, and the
  compiler is one pass, so lines already run compile to the same addresses. A session with fewer lines, or whose Enter
  came while a run was going (part of an entry's writes may be in RAM), runs from its start on cleared RAM. Two traps
  on the way: lxym's editor names rows by where their sentinels show, and moving the lines down for the output with
  `position: relative` moved the names too (ENGINE_NOTES 81: a transform doesn't); and in the frame Enter drops the
  compiler, the scan's 'run from line 0' flag still held the last sweep's value, which cleared a kept console.
  A CSS CPU bug surfaced on the way. The echo's cell moved every global a word, and the bank sample printed `wd ??`:
  `ops[i]` read a word of the wrong array. On the page an instruction makes all its reads at once and keeps (latches)
  the ones that hit for its re-execution, a read only if the reads its address came from hit too; but GETX's element
  `e` (address from `z`, the array's header, whose address is from `x`) checked `z`'s miss, not `x`'s. With `x` missing,
  `z` and `e` were read at garbage addresses that hit, and `e` was kept. csssim reads in order and stops at the first
  miss, so it never did. A read is good now only if every read its address came from was, transitively
  (`tests/suite/latch_chain.js` fails without it).
- **2026-10-24 — A fill stage in the chain; RAM trees not inherited** (`exp/ram/README.md`, BENCHMARKS 21). A catalog
  of ~40 ways to build RAM, probed, led to two changes. In the first, a RAM whose cost doesn't grow with its size,
  only the non-inherited trees (`RAMNI`, now the default) were kept. They cut the RAM's restyles ~3× (arr_gc ~790 → ~260
  elements per layout) but saved no time. The rest of it (unnamed leaves read through paths, the miss address through
  layout: `RAMDEC`) lost on the page, 0.95–1.29. The second, misses filled inside the pass, won. A data miss above
  level 16 is filled there through two nested size containers (the missing block's four leaves' widths and heights)
  and re-executed with its latches. The model gave 0.78 of the passes (geomean of 180 programs). On CPU-only pages it
  was 0.84 of the time (deep_recursion 0.62, closure_gc 0.80), and on the editor page deep_recursion 0.71 and
  closure_gc 0.81; short programs pay ~1–3% in compile. Two and three stages saved more passes but cost each pass more
  (the register subjects restyle in every stage's containers), so they lost on the GC programs and the compile.

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
| 35 | Read-decoded anchors (read block down the trees) | whole trees restyled: 90 ms per recalc at 16K (2026-10-24: likely an unmasked address; masked, with explicit `inherit`, only the paths restyle: `exp/ram`, ENGINE_NOTES 82) | sparse RAM groups |
| 36 | 13-bit addresses, ROM 0 … 4095 for a 93-word lib | RAM capped at 4K words | 15-bit, 1K ROM |
| 37 | Object instructions with 3-way selectors everywhere | 531 subtables per cycle; export dropped | gated rule groups, merged digits |
| 38 | `x[k]` dispatch in microcode (KEYV, PUTX), DUP2 | +1.2 ms per shaping for all programs | ROM dispatch via JNEG; OVER OVER |
| 39 | NEW zero-filling its chunk | 12 micro-cycles, two lines per object | NEW zeroes nothing; ENDK |
| 40 | Every identifier writing its bytes to the string area | FizzBuzz compiled ~7% slower | only after `.`, `{` or `,` |
| 41 | A trap's frame written by one instruction | the CPU writes one word (one cache set) per execution | the frame word by word, `--pst` counting |
| 42 | PRINT writing a trap frame for an array or object | a memory write in the out class would cost every PRINT | `pstub` (TENTER), `ptrap` decodes the PRINT |
| 43 | SETX / SETP frames at a fixed fp + 48 | a function's live temps could reach it | TRAPOFF 60; `TBMAX` bounds the live frame |
| 44 | Call arguments as operand descriptors | `[1, [2, [3, [4, [5]]]]]` overflowed the 10 descriptors | arguments leave the stack in their temps (`tb`) |
| 45 | `tb` only as the current base | a snapshot under a call copied a global over a collapsed argument (fuzz) | each descriptor keeps the `tb` it was pushed at |
| 46 | The 511-word code area, 6 instructions per token | 22% / 7% of generated programs rejected (main: 14% / 0%) | 1,023 words, `EMAX` 7, `PIECES` 4 |
| 47 | Inlining every single-use DSL temp | a ternary's else operand appears twice in css2's text: nested ones doubled, 344 KB declarations, out of memory | uses weighted by occurrences in the text |
| 48 | The operand stack's top in its own DSL variable | no smaller: pushes still write a slot, pops then read one | slots only |
| 49 | One-hot index flags shared between the slot selects | −1.5% CSS text, +7% declarations | inline selects |
| 50 | `pow2` by a loop in the collector's bitmap | 22% of the suite's steps (`mapbuild` 14% more) | a 16-word table of powers of two |
| 51 | One output instruction per pass, 8 columns | every line starts in bank 0: one short line per pass | a mask of the banks written, 9 columns |
| 52 | The runtime's `join` and `repeat` calling `cat` | the ROM copy loop and allocation per piece (stars: 5,205 steps) | `__dadd`, the cat class (1,082) |
| 53 | The picker's per-line checks as `:has()` on `#app`, per editor | 264 searches of ~10,000 elements: compile +1.7 s | `:has(> .frame > …)` on the editors' section |
| 54 | The collector's bitmap built at each collection by walking from-space by its headers | a miss per block: 21–31% of the GC programs' passes; a grown array's raw block has no header, and a negative first element looped the walk (`gc_rawblock.js` never halted) | the map kept as blocks are made (ALLOC, NEW, the cat class, the copies) |
| 55 | User code fetched through the data cache | 23% of the suite's passes ended on code misses: a loop's code (two words an instruction) evicted by its data | a 16-line code cache of its own (8 lines thrash: `obj_gc` 9,350 passes against 4,015) |
| 56 | HP and GCLIM as registers instead of memory cells (model) | 2–4% fewer passes in the GC programs, for an access path the ROM's collector would need | not done |
| 57 | A line written whole into a clean victim without a fill (model) | ~0%: allocation writes rarely cover a line, and their victims are dirty | not done |
| 58 | SETX's full chunk trapping from the obj class, as SETP's does | its trap's steps (pst 1 … 3) would route it back to the arr class | the chunk handed back (pst 512), the arr class's trap from its first step |
| 59 | A 32-line code cache | caesar 24% and bank 13% faster, the other 23 timed programs 0–12% slower: every register costs every pass (~20 µs; 80 dummy registers alone +2.3% on FizzBuzz) | 16 lines (`ICACHE=32,1` builds 32) |
| 60 | Code kept in the data cache by its replacement (evict the data way when the victim is code; model) | data starved: caesar 454 passes against 314, `obj_gc` 8,111 against 6,397 | a separate code cache |
| 61 | The code cache's register subjects outside the chain (in `.fl`, where they change) | no faster (1,046 against 1,040 ms on FizzBuzz): the cost isn't the subjects' depth | not done |
| 62 | `<object>`s as the request primitive, toggled by `display` | each fetches once; showing it again reuses its frame (ENGINE_NOTES 53) | a self-reloading modem iframe |
| 63 | An SVG `<object>`'s natural size as the return channel | set by the `width` / `height` attributes, not CSS; SVG is XML (no quirks) | responsive iframes, then fragment scroll |
| 64 | Responsive iframes as the return channel | a flag in 153; the height never shrinks (mod-4096 answers, 12 bits); every load relays the page out | fragment scroll (ENGINE_NOTES 56) |
| 65 | The modem cross-site, in its own process (font CPU) | ~40 loads/s but the page dropped to 5–6 frames/s | in process (fragment scroll needs it anyway) |
| 66 | Acting on a request seen in two consecutive loads | one more load per word | one clean load (each digit once) |
| 67 | 4 modems' answers unpacked by the lib | ~250 steps per READ; its cells evicted the stack and code (sets 9, 10) | NET writes the bytes; cells in sets 11–14 |
| 68 | The modems' boxes inside `#clk`, shown by a transition latch | Edit hid them, Run restored stale answers; the latch didn't hold | outside `#clk`, the register `rlive` |
| 69 | Modems that reload all the time (0 s refresh), the request read at the next load | each word waited for a load to finish and another to start; the reloads cost the page a third of its frames | loads the gateway holds until there is an answer; the request read live (ENGINE_NOTES 62) |
| 70 | The answer as a quirks-mode stylesheet (`rx`, `application/json`) per load | one more request per load; the gateway writes the documents anyway | the answer in the document (`#t`'s position) |
| 71 | 4 modems, one answer each | each document costs the page two forced style passes (ENGINE_NOTES 63): 8 per word | 2 modems, two answers each (x and y) |
| 72 | A render-blocking stylesheet arriving after the parse, to skip `FinishedParsing`'s forced update | still forced, at 0 and 15 ms | — |
| 73 | `const` assignment as a run-time TypeError through a getter-like slot | +91 temps in the hottest variants | compile error 64, as before |
| 74 | An arrow's expression body closed by S_OPER's own closer variants | the close's code in every `)` `;` `,` level of every program | modes of their own (S_OPERC / S_NAMEEC) whose other variants share S_OPER's rules (ccpage5 merges identical CSS across modes) |
| 75 | The global object as a static chunk outside the heap | `isobj` is a heap-range test: GETP / SETP saw no object | a heap object made on first use, kept in global 1 |
| 76 | The lexer's `this` / `new` test on one combined hash (h1 × 65519 + h2) | exact in Python (L2 passed), but a registered integer keeps 6 significant digits (ENGINE_NOTES 2): the page took `this` for a name | each half compared |
| 77 | GETP's string trap with its arguments in its frame at A | the frame (and the routine's locals) overwrite the slot above A, a method call's `this` | no arguments (the key decoded from the instruction) and one unused parameter (the locals start a slot higher) |
| 78 | Inner functions' calls through the library's `callv` every time | closure_gc +5% passes, func_expr +15% after `this` added cases to `callv` | open lead: a CALLV fast path for them |
| 79 | A 40 × 32 console for every program | FizzBuzz +24% on the page: the console box lays out every reader on each write | the grid's size a property: 9 × 16 for a program, 40 × 32 for the REPL |
| 80 | The console's RAM as 1,312 words (the REPL's grid and its marks) | its trees decoded in radix 82 × 4: every console write restyled 82 group nodes per bank, FizzBuzz's CPU-only page +17.6% | 1,536 words, radix 6 × 4 × 4 × 4 |
| 81 | The REPL's latches gated by an animated property in the transition's delay | no transition ever started (ENGINE_NOTES 79): Enter blanked the transcript | the gate as a container style query |
| 82 | A newline token's line as a property of each line's compile levels (`--lnum`, inline or on the line source) | the levels of different lines no longer shared Chrome's matched properties cache: FizzBuzz compiled 29% slower | the line added where the token is written (`.trl<k>`), only on the REPL |
| 83 | The REPL's line count from 24 `#app:has()` rules | `#app` restyles every frame of the scan: a program's compile +1% | `.pane:has()` into a register |
| 84 | The REPL as a chip in the program page's picker, replaying the session on each Enter | programs compiled ~6% slower for the REPL's page parts; an entry cost the whole session's run (13 s at 19 lines) | a page of its own that keeps the machine's state (ARCHITECTURE §3.10) |
| 85 | The REPL's output room opened by moving the lines with `position: relative` | the rows' names (their sentinels' view progress) moved with the lines: the probes read the wrong rows (ENGINE_NOTES 81) | `transform: translateY()` |
| 86 | Read paths down the RAM trees, the miss address through layout, unnamed leaves (`RAMDEC`) | the size container around the RAM is resolved in layout, and the tree under it restyled there each pass: 0.95–1.29 on CPU-only pages (arr_gc layout 9.8 → 16.7 ms) | the named leaves and the read ports' mux |
| 87 | Two or three fill stages (`STAGE=11,22`, `8,16,24`) | fewer passes, but each stage costs every pass: the GC programs 0.85–0.95 against one stage's 0.80–0.82, the compile 1.05× | one stage at level 16 |

## Open leads (untried)

- **Two strings' equality in the machine.** `==`, `===` and `switch` on two strings always trap (`jcmp` or `deq`, then
  `leqr` / `deqr`: ~37 steps, `primes` +30% passes against main). Same address is equal and different lengths unequal:
  a stage after the dyn class that reads both length words (as the cat class does) would decide most of them.
- **Compile time against main** (+18%, BENCHMARKS §17): `popops` chooses a dynamic operator in each of its ten
  iterations (`dop`, `bty`, `picmp`: ~80 temps an operator token), and `(` after an operand carries value and method
  calls in every variant. Choosing the operator once at push time, or variants for the common binary operators (a
  smaller `popcap`), would cut the temps; §14 found new variants cost more than their temps, so measure both.
- **A pass of the CPU** costs ~15% more than main's (`collatz`: the same passes in the model, 1.155× on the page): 63
  more registered properties and 53% more `if()`. Which classes' declarations every pass pays for is
  unmeasured.
- **Per-iteration `let`.** `for (let i ...)` has one `i`: closures made in the loop see its last value (README
  Limits). An env cell is per frame, and a top-level function's variables are globals, so a binding per iteration
  needs a block's own env chained to the frame's; the one-pass compiler doesn't know at the loop's head whether the
  body will capture `i`. Copying the frame into a fresh cell at each iteration's end would be wrong for the other
  variables the closures share.
- **Smaller frames.** A user function's frame is `[ret][this][params][env][locals][temps]`, two words more than
  before `this` and closures (`deep_recursion` 560 → 963 passes against main, its stack misses). The env slot could
  exist only in a function that makes a closure, as the last local (its RETC operand and `mkclo`'s word1 relative to
  the frame label): in the model `deep_recursion` 963 → 760, `fib` −4%, the rest under 1%; it needs a parser state
  bit (does this function make closures). The `this` slot can't go without every caller knowing the callee.
- **Making a function value** costs ~87 steps (`mkfn`: an ALLOC, 8 pokes, `mark`) and a closure ~230 (`newenv`, `mkfn`,
  two `mark`s): an ALLOC kind for function and env blocks (the header and the map bit written by the machine, as for
  object chunks) would make most of it one instruction.
- **Labels.** 64 per program (6-bit fields, and each level's label multiplexers grow with the count); a function takes
  3–4 (the close label for RETC whether or not it makes a closure). The generator's programs hit error 20 a third of
  the time.
- **Names from variables.** Node prints `var f = function () {}` as `[Function: f]`; the machine names functions only
  from declarations and object keys (the variable's name bytes aren't in the string area).
- **Callbacks from the library.** `map`, `forEach`, `sort` with a function: the library can't call user code except by
  returning into it (as `callv` does); the timers' loop is user code that asks the library for the next callback, a
  pattern that would also do for these.

- **What a register costs.** ~20 µs a pass each, changing or not (BENCHMARKS §15: 80 unused registers +2.3% on FizzBuzz),
  about four times the style cost measured for a subject alone: the 358 registers are ~2 ms of a light pass, and a
  cheaper register would pay for a 32-line code cache (caesar 24% faster) on everything else.
- **An intermittent early HALT** (the register machine's tree, 110 of 2,273 steps, on 2026-10-21; the hybrid's
  obj_keys, 218 of 313, once in ~370 runs): with a fresh browser per run, never twice. Likely the duplicate cache line
  that stalled C2 pages (timeline 17): a lookup that matches both ways of a set reads a wrong word. Not seen since that
  fix, but it was rare before it too.

- **Fewer traps.** Suite traps are mostly misses (1,309) and arithmetic EXT (1,104; 160 in `primes.js`): MOD / DIV,
  SHL13 and small-constant multiply in the font; dirty lines above SP treated as clean; an eviction buffer; next-line
  prefetch; top of stack in registers; two characters per word; read misses serviced within one layout pass (a toy
  chained 8 shapings in one layout).
- **Allocation loops** (`obj_gc.js`: 18 shapings per iteration, 14 misses evicting the loop's code): LRU, or writes to
  fresh heap lines that bypass the cache.
- **A cheaper fill stage** (`exp/ram/README.md`): the one stage (2026-10-24) costs every pass, since the register
  subjects restyle again in its two containers. One container holding all four words, or the registers kept outside
  the stage, would make two stages pay (the model: 0.71 of the passes against one stage's 0.78).
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
- **Language**: a wider console; `in` / `delete`, `instanceof`, classes, template literals, `try` / `catch`, default
  and rest parameters, destructuring; specific error codes on the page.
- **More in CSS**: string comparison (`DEQ` / `DLT` on two strings go to `scmp` in ROM, which compares with MCMP); a
  console write set of two cells per bank (output-bound programs fill the four cells of every pass).
- **Compile time**: the register compiler writes 53K characters of CSS per token level against the stack machine's
  41K (BENCHMARKS §14), mostly the operand-descriptor slots (selects and conditional updates over 10 slots) and the 7
  instruction slots' muxes; fewer descriptor slots, or slots indexed by a one-hot register, would cut both.
- **Network, cheaper words**: what a word still costs is the CPU's frames (the lib between words, ~60 steps per byte
  in `read()` and the program's loop), one frame of register lag on the request (`rreq` follows `--req` a frame later;
  the iframes' height could read the chain's end through `anchor-size()`, if a settling pass doesn't flicker it), and
  two forced style passes per modem document (ENGINE_NOTES 63). A modem with no document per word: while a document is
  loading, every layout re-scrolls to its fragment (`Document::ApplyScrollRestorationLogic` → `InvokeFragmentAnchor`;
  `needs_invoke_` stays until the load completes), so a document kept loading could take its answers as CSS images
  whose natural size moves `#t`. Untried; it needs a fresh URL per word for both the request and the answer (a
  document fetches a URL once, ENGINE_NOTES 61) and a pending request per document, and Chrome's 6 connections per host
  are few.
- **Network, more**: POST, request headers and response headers (more words); a gateway on the deployed site (a Worker
  with state per page); a two-click path with no gateway at all, through a form GET to a `data:` document (ENGINE_NOTES
  57: it can read CORS-enabled JSON as CSS and report through responsive iframes).
