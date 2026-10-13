# Architecture: how it works now

The page is `dist/js_in_css.xhtml`, built by `make page`. It is one XHTML file of about 9.6 MB that runs no
script. The user types JavaScript into an editor, presses Run, and the program runs in four stages. CSS reads the
text back, CSS compiles it to bytecode, and a font executes the bytecode while Chrome shapes text. Output appears
in an 8 × 16 console.

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
   (cache misses, write-backs, MUL/DIV/MOD/SHL13, PUTC)
   ▼
 console: 8 × 16 RAM cells shown with a counter-style font
```

Run and Edit form one checkbox (`#run`, the first element of `body`). Every stage reads its state through
sibling selectors (`#run:checked ~ …`). Edit unchecks the box, which clears the CPU's registers and puts RAM
back to zero.

---

## 1. Memory map and ISA

Addresses are words. A word is a 20-bit two's-complement integer.

| Range | Contents | Written by |
|---|---|---|
| 0 … 4095 | ROM: the runtime library (`compiler/lib_src.js`, compiled by `jsc.js`). It ends with a jump to 4608. | baked into the CPU font's GSUB |
| 4096 | `STRTAG` = 262144, the untag constant read by the lib | lib `__init`, copied from staging |
| 4097 … 4351 | globals and array literals (255 words) | lib `__init` copies the initial values; the program writes the rest |
| 4352 … 4607 | string literals, each `[tag word][bytes…][0]` | compiler overlays, read-only |
| 4608 … 5118 | code (511 words) | compiler overlays, read-only |
| 5119 | count of staged words | compiler `.fin` |
| 5120 … | staged initial globals and array data, with `STRTAG` at 5120 | compiler overlays |
| 5632 ↑ | stack (`sp0`) | program |
| 7040 … 7167 | console, 8 columns × 16 rows | PUTC service |

The RAM runs from 4096 to 7167 (`ramSize` 3072).

**Instruction word.** A word is `op × 8192 + imm`, with a 13-bit immediate. `LOADL` / `STOREL` / `INCL` /
`IDXL` read the immediate as signed (≥ 4096 means negative, relative to FP).

**Opcodes.** There are 45, listed in `compiler/cc_ref.py` and `machine/uarch.py`:

> NOP PUSHI LOADG STOREG LOADL STOREL LOADI STOREI ADD SUB MUL DIV MOD LT GT LE GE EQ NE AND OR NOT NEG JMP JZ
> JNZ CALL ENTER RET POP DUP PUTC HALT JMPI SHL13 INCG INCL IDX IDXL PRINT PRINTB PRINTSP PRINTBSP PRINTLN PRINTBLN

- The PRINT family pops a value and prints it; the page's CSS services it (§3.3). A tagged string pointer prints
  its bytes, 0 / 1 print as `false` / `true` with the B forms (the compiler knows the type is boolean), anything
  else prints in decimal. SP / LN add a space / a newline. One service writes up to 4 console cells (one write
  channel per bank), so a short value costs one trap; a string chunk also ends at its 4-word block or at a `\n`.
  Until the value is out, the CPU re-traps with the same value and the page's `--pst` register carries the
  position (a string's next byte, or the chunks done for a number).

- Constants of 8192 or more take `PUSHI hi; SHL13; PUSHI lo; ADD`. SHL13 is a trap (an EXT op), so avoid
  large constants in hot code.
- Calling convention: `CALL` pushes the return PC. `ENTER n` saves FP and reserves `n` locals. `RET n` drops `n`
  arguments and leaves the return value.
- Parameter `k` of `n` lives at `fp − 1 − n + k`.

**Values.**

- **Numbers** are 20-bit and wrap.
- **Strings** are tagged pointers: `address − 262144`. The value of a literal is the tag word stored in front of
  its bytes, loaded with `LOADG` (`PUSHI` can't hold a negative number).
- **Booleans** are 0 or 1 at run time.

**Static types.** The compiler tracks the static type of the last value it emitted (`lb`: 0 unknown,
1 boolean, 2 string, 3 number). Each `console.log` argument is one PRINT word: the B form when the type is
boolean (0 / 1 would otherwise print as numbers), the plain form for everything else, since the machine tells a
string from a number at run time. The last argument takes the LN form, the others the SP form.

- `addc` does `+` inside a `console.log` argument when the operand types aren't both known numbers. It either
  adds, or prints both pieces (PRINT) and returns DONE (the tag of 4352, never a valid string), which PRINT
  prints as nothing.
- Before 2026-10-13 printing was done by lib routines (`printNum`, `puts`, `printBool`, their `…Ln` forms) with
  one PUTC trap per character and a MOD / DIV trap per digit; see HISTORY.md.

The language itself, its limits and the error messages are in [the README](../README.md#the-language).

---

## 2. The compiler

It exists twice, and the two forms must agree exactly. The tests enforce this at level 2.

- **`compiler/cc_ref.py`** is the reference: a character-at-a-time pushdown transducer.
  - It takes one step per character, with fixed-size tables and stacks.
  - It has no recursion and no lookahead beyond the next character.
  - Each step may complete one token, which the parser handles at once: shunting-yard for expressions, a
    control stack for statements.
  - Words whose address isn't known yet carry a label id, resolved when the program is linked.
  - It also contains the bytecode simulator `run()`, which wraps to 20 bits like the machine.
- **`compiler/cc_dsl.py`** is the same step written in the integer expression DSL of `compiler/dsl.py`. A DSL
  program is predicated straight-line code (`with self.when(cond): …`) over integer temps in SSA form.
  - **Evaluated in Python**, it is level 2's model of the page.
  - **Compiled to CSS**, each temp becomes one custom-property declaration (`css2()` is the compact emitter;
    `dce()` drops dead temps).
  - `Prog` is the parser step, one token per call. `LexProg` is the lexer step, one character per call.

### Fixed limits

These are in `cc_ref.py` and shared by the DSL.

| Name | Value | Meaning |
|---|---|---|
| `OD` | 8 | operator stack depth |
| `CD` | 8 | control stack depth |
| `NS` | 32 | symbols |
| `NF` | 16 | functions |
| `NL` | 64 | labels (6-bit fields in control-stack entries) |
| `EMAX` | 12 | code words emitted per step |
| `SDATA` | 256 | size of the globals and string areas |
| page | 24 × 64 | editor lines × columns |
| page | 400 | tokens (`TMAX`) |

### Parser structure

- **Modes**: `S_STMT`, `S_OPND`, `S_OPER`, … 26 in all.
- **Control-stack kinds**:
  - bodies: `C_IFB`, `C_ELSEB`, `C_LOOPB`, `C_FUNCB`;
  - pending headers and statements: `C_IFC`, `C_WHILEC`, `C_FORINIT`, `C_FORCOND`, `C_FORSTEP`, `C_ASSIGN`,
    `C_EXPR`, `C_RETURN`, `C_IDXA`;
  - braceless bodies (`kind + BRACELESS`), closed by `complete_stmt` when their single statement ends.
- **Packing**: control-stack entries pack as `kind × 4096 + a × 64 + b` and `c × 64 + d`. Operator-stack entries
  pack as `code × 8192 + value`.

### How each feature is implemented

- **Short-circuit `&&` / `||`**: the compiler emits `a DUP JZ/JNZ L POP b` and defines `L` when the operator is
  popped. At most one `&&` and one `||` can pop together (precedence increases up the stack between markers), so
  the DSL defines both labels after the pops.
- **Semicolon insertion**: the lexer emits token `T_NL` (14) at a newline that follows a token that can end a
  statement (identifier, number, string, `)` `]` `++` `--`). The parser treats it as `;` only where a statement
  can end and no `( [` or call is open; elsewhere it ignores it. A `}` right after an unterminated statement ends
  it first (the `asic` / `f_asic` path).
- **`else if` chains**: an `if` that is the braceless body of an `else` reuses that `else`'s end label and
  wrapper. `pendLa + 64` flags the reuse. A chain therefore uses one control-stack entry and one label however
  long it is.
- **Static types**: a symbol's type is its last assignment in source order, kept in the symbol table. A
  function's type comes from its `return`s, kept in the function table. Both are 2-bit fields: `sk_j` holds
  `type × 65536 + kind × 16384 + addr + 8192`, and `fl_k` holds `label + 64 × type`.

### The CSS compiler page (`compiler/ccpage5.py`)

`build(lib, L, P, TMAX)` returns `(css, html, timelines, info)`.

**Character chain** (`#cc`, inside `#ccw`)

- **Levels**: one nested `display: contents` element per character slot: 24 lines × (64 columns + newline),
  plus one NUL, which makes 1561 levels.
- **Line sources**: one source element per line (`.ls`) animates the line's 64 codes into `--lc0 … --lc63` from
  the latch cells' view timelines (`--ch<line>_<col>`). Every line reuses those names, so each level inherits
  only its own line's codes.
- **Lexer dispatch**: each level computes `--ncl`, the class of the next character. The child's lexer is picked
  by `@container style(--ncl: K)` from 9 class-specialised `LexProg` variants (space, alpha, digit, `"`, `\`,
  `/`, other punctuation, newline, NUL).
- **Token registers**: a level that completes a token shows `.tr`, a scroller whose four subjects (code, value,
  hash1, hash2) are placed at those pixel offsets. Their view-timeline names are `--tk<t>c/v/h/g`, with the token
  index `t` chosen by an `if()` mux.
- **String bytes** become in-flow overlays `.ovs` named after their RAM cell.

**Token chain** (`#tcr`, nested inside the deepest character level)

- **Group sources**: one source element per 32 tokens (`.gs0` / `.gs1` by group parity) animates their four
  values.
- **Parser variants**:
  - Level `t + 1` runs the parser on token `t`. The variant is chosen by
    `@container style(--vh: mode) and style(--tcq: tokencode)` on its parent.
  - The page has 299 variants (`tools/vsz.py` counts 319, before the no-op variants are merged). Pure-error variants are dropped: a token no variant accepts sets `bad`, which
    shows as error 99.
  - Variants that change nothing collapse into one pass-through rule per token code.
  - With a known starting mode, `Prog` folds away the blocks that can't be reached (the `FALL` map). This halved
    the generated CSS.
- **State**: state alternates between parity copies (`--p-<name>-A/B`). Temps share a small pool of names
  (`qp<i>`), because every registered property costs time on every animated element.
- **Tables**: symbol and function tables are delayed writes. A step writes at most one entry per table through a
  write port (`o_y*`, `o_f*`). The next level applies it with a container query on the parent's port.
- **Code words**: up to 12 fixed overlays per level (`.ov.k<s>`, `position: fixed`, inside `contain: strict`).
  Each has `anchor-name: --c<index>` and width `word + 2^20`. A word that needs a label adds
  `anchor-size(--l<j> width)`.
- **Labels**: in-flow anchors `.lp<k>` (22 ports per level) named `--l<j>`, with the label's value as width.
- **Finish**: the last live level shows `.fin`:
  - the count word;
  - the staged `STRTAG`;
  - `--ccdone`, which is 1 when the compile finished without error;
  - `--ccinfo`, whose width is `done + 2·err + 1024·words` (the CPU page's status line reads it).

  Separately, `#tcr > .big` (`--cctoo`) is shown when there are more than 400 tokens.

**Reading RAM**: a RAM read takes the width of the last element in tree order with the anchor name `--c<index>`.
Compiler overlays come after the RAM leaves, so they override them. That only works because the program never
writes those cells: code, strings and staging are read-only at run time.

**Constraints**

- **Container query values must stay below 256.** Chrome's `@container style()` never matches a
  calc()-computed `<integer>` of 256 or more, which is why variant keys are small.
- **The page must be XHTML.** The chain is about 2,000 elements deep, and the HTML parser stops nesting at 512.

---

## 3. The font CPU (`machine/`)

### 3.1 Design

- **`uarch.py` / `uarch4.py`**: the value-level reference model and the CSS trap service. `Machine4` is what
  `tests/suite_machine.py` runs.
- **`cpu4.py`**: compiles that micro-architecture into GSUB through `cpugen.py` (stages A / RA / MAP) and
  `otl.py`, a hand-written GSUB assembler.
  - The assembler exists because one cycle's lookups are referenced S times from the LookupList (aliasing), and
    fontTools can't express that.
  - Every state glyph is a GDEF mark. Each lookup uses mark-filtering sets to see only the cells it needs, which
    keeps contexts short.
- **`fvm_build.py`**: writes the woff2 and the metadata the page needs (`build/f4cc_16.*`).

### 3.2 State and cache

- **State**: a string of about 1,274 glyph cells: core registers as hex digits, a control glyph, and 16 cache
  lines of 4 words.
- **Cycles**: one shaping runs S = 32 micro-cycles (`font-feature-settings: "cv01" var(--go)`).
- **Commit and traps**:
  - An instruction commits PC, SP, FP and its memory write only in its last micro-cycle, so a trap simply
    restarts it.
  - A trap sets the control glyph to `('T', kind)`, and the rest of the shaping does nothing.
  - Trap kinds: MISS (cache miss), WFAIL (dirty victim), EXT (MUL, DIV, MOD, SHL13, and the six PRINT ops),
    PUTC, HALT. A PRINT trap repeats until the service has written the whole value (RESV is raised then).
- **Cache**:
  - 16 lines of 4 words, organised as a ring with a victim pointer. No data ever moves between lines.
  - A MISS on an absent block writes back the victim's dirty words (one per bank) and fills the whole block.
  - Instruction fetch from ROM is a font lookup and never traps.

### 3.3 The page around it (`gen_fvm4.py`)

**Registers**

- Registers are view-timeline scrollers: a subject at `value` px inside a tall scroller, read through an
  animation on that timeline.
- View-timeline registers update every layout pass. Remembered sizes (the RAM leaves) update only once per frame.

**Each pass**

1. The state is rendered as a line of text, one counter per state digit, through a `@counter-style` that maps to
   the CPU glyphs.
2. HarfBuzz shapes it.
3. The widths of about 60 spans are the next state. They are read back two per reader: width and height, with
   `container-type: size`.

The page does at most 2 shapings per frame.

**Trap service (CSS)**

- RAM is four banks (address mod 4), each its own decode tree (`memtree.py`). A whole cache line is written back
  or filled in one service, through four bank read ports (768-way muxes) and up to four writes per issue.
- A RAM leaf is a `content-visibility: hidden` element whose remembered width is the word plus 2^20.
- Off-path tree nodes compute constants, so restyling stops one level below them. This took style plus layout
  per pass from 70 ms to about 20 ms.
- The service also computes EXT ops (MUL, DIV, MOD, SHL13) and writes PUTC output into the console.
- PRINT service: the trap's value (T1) is classified at run time (string pointer, boolean with the B forms, number);
  the four bank read ports are pointed at the string's block (`--mblk`), the chunk's characters are computed
  (`--pch0…3`), and each goes to the bank of its console cell (`(optr + i) mod 4`, so consecutive cells never
  share a bank). The register `--pst` carries the position between services; `--resvT` is raised when the value
  and its separator are out. `uarch.Machine.print_service` is the same state machine in Python.

**Precision and pixels**

- Words crossing `var()` are kept signed (|v| < 2^19). Chrome serializes a registered `<integer>` with 6
  significant digits, so 1048575 became 1048580.
- `zoomfix.py` finds the device-pixel ratio with resolution media queries. One font unit must equal one device
  pixel, because HarfBuzz positions are 16.16 fixed point and Chrome snaps glyphs to device pixels.

**Gating**

- `--go = font ok × compiler done (ccok) × run × …`. The CPU shows nothing until `--ccgo` is raised.
- Edit sets `--run` to 0. That multiplies every held register to 0, and RAM leaves are forced back to zero.

### 3.4 Runtime library

- The source is `compiler/lib_src.js`, written in jsc's dialect. `libbuild.js` compiles it with the self-hosted
  `jsc.js` under Node into `lib.json`: ROM words plus entry addresses. It holds only `addc` now (93 ROM words);
  printing is the PRINT instruction family (jsc's `prn(x)` builtin emits a PRINT).
- `__init` copies the staged globals into place, then the ROM's last word jumps to the user code at 4608.
- The lib is baked into the CPU font, so a lib change means `make page` (lib → image → font → page).

---

## 4. Editor readback (`readback/ui_rb.py`)

The readback design comes from a separate "CSS Text Readback" chat.

**Reading a character**

- The editor uses the AsciiProbe font (`mkfont2.py`). Its variable axis `SCAN = j + 1` activates, through GSUB
  FeatureVariations, a lookup set that copies column `j`'s character into a sentinel glyph's advance.
- One probe per line measures the sentinel (`anchor-size()` of a `::after` anchor).
- A row of latch cells per line holds the codes. Each latch writes through a 0 s transition and holds through a
  1,000,000 s delay. Each latch cell also carries a view-timeline register (`--ch<k>_<j>`) that the compiler reads.

**The scan**

- It is frame-locked: view-timeline registers keep the previous frame's clock and a counter, so the scan advances
  exactly one column per frame at any frame rate. A time-driven scan skips columns when frames are slow.
- It covers a fixed 64 columns. A range taken from the editor's width flickers, because the sentinel's width is
  the very code being read.

**Run**

- After Run, the editor goes read-only. The scan makes one more full sweep, then raises `--rbrd`. The compile
  chain shows only once `--ccgo` is 1, and `--ccgo` is driven from the `--rbrdT` timeline.
- A few frames later `--rbdet` freezes the scan registers.

---

## 5. Tests

`make test` runs the fast levels (about 5 s). `make test-browser` runs level 3, and `make test-ui-smoke` /
`make test-ui` run level 5.

| Level | Command | What runs | Checked against |
|---|---|---|---|
| oracle | `make expect` | each `tests/suite/*.js` under Node, with putc shimmed | writes `*.out` |
| L1 | `make l1` | `cc_ref` compile + 20-bit simulator | Node output |
| L2 | `make l2` | DSL evaluated in Python level by level: the page's specialised variants and class lexers (`SPEC=1`); `make l2-generic` uses the unspecialised parser | the reference: parser state, tables, every code word, label and data word |
| L3 | `make l3` | the generated CSS compiler in Chrome. One page (`build/suite_css.xhtml`); the harness writes each program into the latch cells | the reference, word for word; `tests/suite_err/*` must be rejected |
| L4 | `make l4` | `uarch4.Machine4` (cache, traps) runs every compiled image | Node output |
| L5 | `make l5` / `l5-smoke` | the real page. Type each program, Run, read the console | Node output laid out on the 8 × 16 grid |

**Suites**

- `tests/suite/` holds 89 programs, each with a Node-generated `.out`. They must fit the editor (24 × 64);
  `suite_ref.py` warns if one doesn't.
- `tests/suite_err/` holds 14 programs the compiler must reject.
- `tests/programs/` holds the older demo programs t1–t4 and e1–e2.

**Not covered**

- L5 includes only programs that finish within 1,500 steps (86 of 89 since the PRINT family; `tests/suite_ui.py`).
- The harnesses detect HALT through the page's `--isHALT` flag, not a trap-kind index (the index moves when
  opcodes are added: HALT is 109 now, 97 before the PRINT family).
- Error 99 on the page stands for a specific code from the reference: a token no variant accepts.

**Other tools**

- `tools/traps.py prog.js…`: per-program code words, steps, shapings and traps from the machine model. This is
  the fastest way to predict run time on the page.
- `tools/vsz.py`, `tools/lp.py`: parser-variant sizes and label-port counts. Label ports become elements on
  every token level, so watch this number.
- `machine/hbtest.py`: runs the real font in uharfbuzz against the model.
- `machine/trace.js` + `machine/passprof.py`: a Chrome trace, split into passes per frame, style+layout time and
  shaping time. Use `RUN=1` on the typed-input page so the trace covers Run, not the idle scan.

---

## 6. Build

```
make page   # compiler/lib.json (if lib_src.js changed) -> build/ccimg.json -> build/f4cc_16.woff2 -> build/js_in_css.xhtml
make dist   # copy it to dist/
```

- Builds are reproducible: the Makefile pins `PYTHONHASHSEED` and `SOURCE_DATE_EPOCH`.
- `make page` takes about 25 s, of which the font build is about 2 s.
- The image (`mkimage.py tests/fizz.js`) supplies the ROM and the editor's initial program.
- Page-generator environment variables (`gen_fvm4.py`):
  - `UI=1`: the typed-input page, which is the product.
  - `UIL` / `UIP` / `UIT`: lines, columns and tokens.
  - `SHORT=0`: readable property names, for debugging (short names are the default).
- Without `UI=1`, the generator builds the older fixed-program pages; see `archive/`.

**Toolchain**

- Python 3.13, fontTools 4.65 and brotli (uharfbuzz 0.56 is optional).
- Node 22, with playwright-core 1.64 for the harnesses.
- Chromium 153.0.8010.0 headless, from the npm package `@sparticuz/chromium` (Linux x64); `CHROME=/path`
  overrides it.
- The page needs at least CSS `if()` and `sibling-index()`. It has only been tested on that Chromium.
