# Architecture

`make page` builds one XHTML file that runs no script. The user types JavaScript and presses Run; CSS reads the text
back, CSS compiles it to bytecode, and a font executes it while Chrome shapes text. Output goes to an 8 × 16 console.

```
 editor (contenteditable)                                        readback/ui_rb.py
   │  font axis SCAN copies one column's character into a sentinel glyph's width;
   │  probes measure it; one latch cell per line × column holds the code
   ▼
 character chain: 24 × 65 + 1 nested levels, one per source character    compiler/ccpage5.py
   │  lexer step (cc_dsl.LexProg) per level; finished tokens → token registers (view timelines)
   ▼
 token chain: up to 400 nested levels, one per token                      compiler/ccpage5.py
   │  parser step (cc_dsl.Prog) per level, one specialised variant per (mode, token)
   │  emits code words as overlays named after their RAM cells (--c<index>)
   ▼
 font CPU: the machine state is a line of text; Blink shapes it with      machine/gen_fvm4.py, cpu4.py
   a GSUB font that runs 32 micro-cycles per shaping; CSS services traps   machine/memtree.py (RAM)
   (cache misses, write-backs, MUL/DIV/MOD/SHL13, PRINT, PUTC)
   ▼
 console: 8 × 16 RAM cells shown with a counter-style font
```

Run and Edit are one checkbox (`#run`, first in `body`), read through sibling selectors (`#run:checked ~ …`). Edit
clears the CPU's registers and zeroes RAM.

---

## 1. Memory map and ISA

Addresses are 15-bit words (4 hex digits, the top one masked to 3 bits); a word is a 20-bit two's-complement integer.
The map is `compiler/layout.json`, read by `cc_ref.LAYOUT`, `libbuild.js`, `uarch.py` and the page generator.

| Range | Contents | Written by |
|---|---|---|
| 0 … 1023 | ROM: runtime library (`lib_src.js`, 103 words, ends with a jump to `code_base`), object runtime (`rtlib.py`, 383 words), jump table at 1020 … 1023 (`vec_base`) | baked into the font |
| 1024 | `data_base`: `STRTAG` = 262144, the untag constant | `__init`, from staging |
| 1025 … 1279 | globals and array literals (255 words) | `__init`; the program |
| 1280 … 1535 | strings `[tag][bytes…][0]`, property names `[bytes…][0]` | compiler overlays |
| 1536 … 2046 | code (`code_base`, 511 words) | compiler overlays |
| 2047 | count of staged words | compiler `.fin` |
| 2048 … 2303 | staged globals and arrays (`init`), `STRTAG` at 2048 | compiler overlays |
| 2304 … 2322 | `rt_base`: HP, GCLIM, GCSP, KEYCELL, RETCELL, routine scratch | object instructions, ROM routines |
| 2560 … 11135 | stack (`sp0`) | program |
| 11136 … 17279 | heap (`heap_lo`): two semi-spaces of 3,072 words | object instructions, GC |
| 17280 … 17407 | console: the last `cols × rows` words | PRINT / PUTC service |

RAM is 16,384 words from 1024; the compile chain names cell `k` = address − 1024 `--c<k>`.

**RAM on the page** (`machine/memtree.py`): one leaf per word, a `content-visibility: hidden` element whose
remembered width is word + 2^20, with `anchor-name: --c<k>`. Four bank trees (address mod 4) of radix-4 decode nodes
route the write channels (`wa` / `wd`, one per issue) to the leaf. Reads are `anchor-size(--c<k> width, 2^20px)`
through a per-bank name mux; compiler overlays come later in tree order and win for the read-only areas.

**Sparse groups.** Leaves sit in groups of 256 (`memtree.GROUP`), `display: none` until a write reaches them (the
group latches `--live`: 0 s transition, 1,000,000 s delay). A hidden cell has no anchor, so a read falls back to 0,
which is what unwritten RAM holds. The console (and on CPU-only pages the static areas) is live from the start. The
reason: every rendered cell costs style, anchor and layout work every pass, touched or not (ENGINE_NOTES 40–42);
with groups per-pass cost follows the working set. Page size and load time still grow with RAM.

---

## 2. The compiler

It exists twice, and the two must agree exactly (L2).

- **`compiler/cc_ref.py`**, the reference: a character-at-a-time pushdown transducer (fixed-size tables, no recursion,
  no lookahead past the next character). A completed token is parsed at once: shunting-yard for expressions, a
  control stack for statements. Unresolved addresses carry a label id until link time. `run()` simulates the
  bytecode (wrapping to 20 bits).
- **`compiler/cc_dsl.py`**, the same step in the integer DSL of `compiler/dsl.py`: predicated straight-line code
  (`with self.when(cond): …`) over SSA temps. Evaluated in Python it is L2's model of the page; compiled to CSS each
  temp is one custom-property declaration. `Prog` parses one token per call, `LexProg` lexes one character.

**Fixed limits** (`cc_ref.py`): operator and control stacks `OD` = `CD` = 8; symbols `NS` = 32; functions `NF` = 16;
labels `NL` = 64 (6-bit fields); `EMAX` = 12 code words per step; `NI` = 16 interned strings and names; `SDATA` = 256
words of globals and of strings; the page: 24 × 64 characters, 400 tokens (`TMAX`).

**Parser structure.** 27 modes (`S_STMT`, `S_OPND`, …). Control-stack kinds: bodies (`C_IFB`, `C_LOOPB`, …),
pending headers and statements (`C_IFC`, `C_FORINIT`, `C_ASSIGN`, …), braceless bodies (`kind + BRACELESS`, closed
by `complete_stmt`). Entries pack as `kind × 4096 + a × 64 + b` and `e × 4096 + c × 64 + d` (`e` = block-scope mark).

**Features.**

- `&&` / `||`: `a DUP JZ/JNZ L POP b`, `L` defined when the operator pops.
- `c ? a : b`: `c JZ L1 a JMP L2 L1: b L2:`. `?` pushes `M_TERN`; `:` swaps in `M_TELSE` (lowest precedence), which
  defines `L2` when popped. A ternary in an else branch reuses the outer `L2`, so the DSL checks for one `M_TELSE`
  once after `popops`' loop.
- `do … while`: `C_DOB` (continue, break, top labels); `S_DOWHILE` waits for `while`; the `)` emits `JNZ top`.
- Block scope: function-level names grow up from 0 (`nsym`), block-level `let` / `const` down from `NS - 1`
  (`nlet`); each control entry records `nlet` and closing a body restores it. `const` is a symbol bit.
- Semicolon insertion: the lexer emits `T_NL` after a newline that follows a statement-ending token; the parser
  treats it as `;` only where a statement can end outside `( [` and calls.
- `else if`: the inner `if` reuses the `else`'s end label and wrapper (`pendLa + 64`): one control entry per chain.
- Static types (2-bit, in `sk_j` and `fl_k`): a symbol's last assignment in source order, a function's `return`s.

### The CSS compiler page (`compiler/ccpage5.py`)

**Character chain** (`#cc`): one nested `display: contents` level per character slot, 24 × (64 + newline) + 1 NUL
= 1,561. One source element per line (`.ls`) animates its codes into `--lc0 … --lc63` from the latch cells' view
timelines (`--ch<line>_<col>`); every line reuses the names, so a level inherits only its own line. `--ncl`, the next
character's class, picks one of 9 class-specialised `LexProg` variants. A level that completes a token shows `.tr`, a
scroller whose four subjects (code, value, hash1, hash2) are view timelines `--tk<t>c/v/h/g`. String bytes become
in-flow overlays `.ovs` named after their RAM cell.

**Token chain** (`#tcr`, inside the deepest character level):

- One source element per 32 tokens animates their four values.
- Level `t + 1` parses token `t` with the variant chosen by `@container style(--vh: mode) and style(--tcq: token)`.
  `tools/vsz.py` counts 346 variants; the page has 322 in 188 rules: pure-error variants are dropped (a token no
  variant accepts sets `bad`, error 99), no-op variants share a pass-through rule per token, and identical variants
  of one mode share one rule (`style(--tcq: a) or …`). Every rule costs time on every token level whether it applies
  or not (BENCHMARKS §4c). With a known starting mode, `Prog` folds away unreachable blocks (`FALL`).
- State alternates between parity copies (`--p-<name>-A/B`); temps share a small pool of names (`qp<i>`).
- Tables (symbols, functions, interned strings) are delayed writes: at most one entry per table per step through a
  port (`o_y*`, `o_f*`), applied by the next level with a container query.
- Code words: up to 12 fixed overlays per level (`.ov.k<s>`, inside `contain: strict`), `anchor-name: --c<index>`,
  width `word + 2^20` (plus `anchor-size(--l<j> width)` for a label). They override the RAM leaves (ENGINE_NOTES
  21), which works only because code, strings and staging are never written at run time.
- Labels: in-flow anchors `.lp<k>` (21 ports per level) named `--l<j>`, width = the label's value.
- The last live level shows `.fin`: the count word, the staged `STRTAG`, `--ccdone` and `--ccinfo` (width
  `done + 2·err + 1024·words`, for the status line). `#tcr > .big` (`--cctoo`) shows past 400 tokens.

---

## 3. The font CPU (`machine/`)

### 3.1 Design

- `uarch.py` / `uarch4.py`: the value-level model and the trap service; `Machine4` is what L4 runs.
- `cpu4.py` compiles it into GSUB through `cpugen.py` (stages A / RA / MAP) and `otl.py`, a hand-written assembler,
  because one cycle's lookups are referenced S times from the LookupList, which fontTools can't express. Every state
  glyph is a GDEF mark; mark-filtering sets let each lookup see only the cells it needs.
- `fvm_build.py` writes the woff2 and the page's metadata (`build/f4cc_16.*`).

### 3.2 State and cache

- State: about 1,274 glyph cells (core registers as hex digits, a control glyph, 16 cache lines of 4 words). One
  shaping runs S = 32 micro-cycles (`font-feature-settings: "cv01" var(--go)`).
- An instruction commits PC, SP, FP and its memory write only in its last micro-cycle, so a trap simply restarts it.
  A trap sets the control glyph to `('T', kind)`; the rest of the shaping does nothing. Kinds: MISS, WFAIL (dirty
  victim), EXT (MUL, DIV, MOD, SHL13, the six PRINT ops), PUTC, HALT. A PRINT trap repeats until the whole value is
  written (RESV).
- Cache: a ring of 16 lines with a victim pointer; data never moves between lines. A MISS writes back the victim's
  dirty words (one per bank) and fills the whole block. ROM fetch is a font lookup and never traps.

### 3.3 The page around it (`gen_fvm4.py`)

- Registers are view-timeline scrollers (a subject at `value` px); they update every pass, RAM only once per frame.
- Each pass renders the state as text (one counter per digit, through a `@counter-style` mapping to CPU glyphs),
  HarfBuzz shapes it, and 76 readers (size containers, mostly two values each) read about 140 span widths as the
  next state. At most 2 shapings per frame (ENGINE_NOTES 37).
- Trap service: four banks, so a whole line is written back or filled in one service (four read ports, up to four
  writes per issue). A read port is a two-level `if()` choosing the anchor name among the bank's 4,096 cells (at most
  128 `style()` tests), one `anchor-size()`, and a size container that makes it a property. Off-path tree nodes
  compute constants (ENGINE_NOTES 22, 41). The service also computes EXT ops and PUTC.
- PRINT service: T1 is classified at run time (string pointer, boolean for the B forms, number); the read ports point
  at the string's block (`--mblk`); characters (`--pch0…3`) go to their console cells' banks (`(optr + i) mod 4`).
  `--pst` carries the position between services. `uarch.Machine.print_service` is the same state machine.
- `zoomfix.py` makes one font unit one device pixel (ENGINE_NOTES 29).
- Gating: `--go = font ok × compiler done (ccok) × run × …`; nothing runs until `--ccgo`. Edit sets `--run` to 0,
  zeroing every held register and RAM leaf.

### 3.4 Runtime library

`compiler/lib_src.js`, in jsc's dialect, compiled by `libbuild.js` (the self-hosted `jsc.js` under Node) into
`lib.json`. It holds `__init` (copies the staged globals, then the ROM's last word jumps to `code_base`) and `addc`;
printing is the PRINT family (jsc's `prn(x)`). It is baked into the font, so a change means `make page`.

### 3.5 Objects and the garbage collector

**Representation.**

- An object is an 8-word chunk `[k0 v0 k1 v1 k2 v2 L pad]`; its value is the address minus `OBJTAG` = 491,520, a
  multiple of 32,768, so the 15-bit address registers untag it for free (`LDF`, `SETF`, `STOREI` and the probes take
  it as an address).
- A key is stored as value + 2^18 (`KBIAS` = `STRTAG`): a string key becomes its address in the string area (an
  immediate), a number `n` becomes `n + 2^18`. 0 marks a free pair and ends the keys. `L` is 0 or a link to an
  overflow chunk (negative, so the sign tells a link from a key).
- Words after the first free pair are never written (`NEW` zeroes nothing), so a one-pair object touches one line.
- Strings and names are interned by content hash in a 16-entry delayed parser table (`ih1_k ih2_k iv_k`), so a key
  is a compile-time constant and `o[s]` finds `o.x` when `s` is `"x"`. The lexer writes each identifier's bytes at
  `sdp` and commits them only after `.` (not after `console`) or before `:`.

**Instructions** (opcodes 45 … 53, microcode in `uarch.py`, mirrored in `cc_ref.run()`):

| Op | Stack | Micro-cycles | What it does |
|---|---|---|---|
| `SCANI k` | [o] → [c] | 3 per probe | compare the key at the cursor with `k`: found or 0, stop (cursor stays on that word); negative, follow the link; else step 2 words. Re-executes until it stops |
| `SCAN` | [o] → [c] | 4 per probe | the same, key in KEYCELL (the ROM routines' dynamic keys) |
| `LDF i` | [p] → [mem[p+i]] | 3 | `o.x` is `SCANI x; LDF 1` |
| `PUTV k` | [c, v] → [] | 4 | key at `c`: `mem[c+1] = v`; else call the ROM's append routine with `[c, v]` (return address in `mem[c+1]`) |
| `NEW` | [] → [o] | 4 | a chunk at HP; if the heap is full, call the GC (GCSP = SP, RETCELL = this NEW), which returns to it |
| `SETF i` | [o, v] → [o] | 3 | `mem[o+i] = v` (a literal's pairs) |
| `ENDK i` | [o] → [o] | 3 | `mem[o+i] = mem[o+i+1] = 0`: the keys end there |
| `OVER` | [a, b] → [a, b, a] | 2 | |
| `JNEG l` | [a, b] → [a, b] | 2 | jump if `a` is negative (an object; an array is an address) |

- Selectors: a 3-valued gate glyph `ZSEL` (from the control glyph and flags `ZT1 ZT2 ZD SD ST2`) picks address, data
  and commit; the per-digit gate `ZJ` copies it.
- Restart safety: every write before the last micro-cycle must leave the inputs unchanged; NEW writes HP last.
- ROM calls go through the jump table: GC (1020), APPEND (1021), SETX (1022), GETX (1023). Routines keep state in the
  `rt_base` cells, not frames (they nest: APPEND allocates, NEW collects).
- `x[k]`: a name statically typed number (an array literal) uses IDX; anything else calls GETX / SETX, which test the
  sign with JNEG. `o[k] op= e` is `[o, k] OVER OVER GETX e op SETX`.

**The collector** (`rtlib.py`, hand-written): Cheney copying between the semi-spaces. Roots are the globals and arrays
(up to the staged count at `init − 1`), the routines' scratch cells, and the stack from `sp0` to GCSP. A root may
point *into* a chunk (a SCANI cursor waits on the stack while `e` in `o.x = e` allocates), so its offset is found with
MOD 8; heap words only point at chunk starts. Copying sets `k0` to −1 and `k1` to the copy; the scan follows values up
to the first free pair, and the link if all three are used. Cost is a few shapings per live chunk, none per dead one.
HP and GCLIM start at 0, so the first NEW sets up the heap.

**Font budget**: 148 control values; 392 subtables per cycle of the 512 allowed at S = 32, thanks to
`cpu4.merge_digits` (an expression's digits in one subtable). Costs: BENCHMARKS §10.

---

## 4. Editor readback (`readback/ui_rb.py`)

- The editor uses the AsciiProbe font (`mkfont2.py`): axis `SCAN = j + 1` activates, through FeatureVariations,
  lookups that copy column `j`'s character into a sentinel's advance. One probe per line measures it (`anchor-size()`
  of a `::after` anchor). Latch cells (0 s transition writes, 1,000,000 s delay holds) keep the codes, each with a
  view-timeline register `--ch<k>_<j>` the compiler reads.
- The scan is frame-locked (one column per frame at any frame rate) over a fixed 64 columns.
- It runs only after Run: while editing, `SCAN` is 0 and the registers are frozen (`--rbfrz`), since scanning
  reshapes the editor and made selections jump. After Run the editor is read-only, one sweep raises `--rbrd`, and
  `--ccgo` (from the `--rbrdT` timeline) shows the compile chain; `--rbdet` then freezes the scan.
- Lines: line 0 is text directly in `#ed` (only after the editor was emptied), line `k` the `k`-th `#ed > div`, each
  with a sentinel; so the initial program is all divs from line 1. Nested divs show inline, `<br>` is hidden,
  `white-space: nowrap` with `&nbsp;`, and no CSS rule may match the line divs (reasons: ENGINE_NOTES 44–49).
  `make l5-input` checks that the scan reads what the editor shows.

---

## 5. Tests

| Level | Command | What runs | Checked against |
|---|---|---|---|
| oracle | `make expect` | each `tests/suite/*.js` under Node, putc shimmed | writes `*.out` |
| L1 | `make l1` | `cc_ref` compile + 20-bit simulator | Node output |
| L2 | `make l2` | the DSL in Python level by level, with the page's specialised variants (`SPEC=1`; `make l2-generic` unspecialised) | the reference: parser state, tables, every word and label |
| L3 | `make l3` | the generated CSS compiler in Chrome (`build/suite_css.xhtml`, programs written into the latch cells) | the reference, word for word; `suite_err` must be rejected (any nonzero error) |
| L4 | `make l4` | `uarch4.Machine4` runs every compiled image | Node output |
| L5 | `make l5` / `l5-smoke` | the real page: type, Run, read the console | Node output on the 8 × 16 grid |

- `make test` = oracle, L1, L2, L4. `tests/suite/` has 109 programs, `tests/suite_err/` 31; `tests/programs/` has
  the demos t1–t4.
- L5 runs only programs under 1,500 steps (`tests/suite_ui.py`). Harnesses detect HALT by the page's `--isHALT`
  flag, not a trap-kind index (that moves when opcodes are added).
- `machine/hbtest.py` runs the real font in uharfbuzz against the model: the only check that the font agrees (L4
  runs the model against itself).

---

## 6. Build

```
make page   # compiler/lib.json (if lib_src.js changed) -> build/ccimg.json -> build/f4cc_16.woff2 -> build/js_in_css.xhtml
make dist   # copy it to dist/
```

- Reproducible (the Makefile pins `PYTHONHASHSEED` and `SOURCE_DATE_EPOCH`). The image (`mkimage.py tests/fizz.js`)
  supplies the ROM and the editor's initial program.
- `gen_fvm4.py`: `UI=1` builds the product page; `UIL` / `UIP` / `UIT` set lines, columns, tokens; `SHORT=0` keeps
  readable property names; `MEMGROUP=n` sets the RAM group size. Without `UI=1` it builds a CPU-only page for a RAM
  image holding the program (HTML: name it `.html`).
