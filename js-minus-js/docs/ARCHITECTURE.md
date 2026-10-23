# Architecture

`make page` builds one XHTML file that runs no script. The user types JavaScript (or picks a sample) and presses Run;
CSS reads the text back, CSS compiles it to register code, and CSS executes it: a chain of instructions per layout
pass. Output goes to a 9 × 16 console. (Until 2026-10-21 the machine was a stack machine, last at commit `212175a`;
until 2026-10-19 the CPU was a GSUB font, §3.8.)

```
 editors (contenteditable; #ed and the samples, one shown)              readback/ui_rb.py
   │  font axis SCAN copies one column's character into a sentinel glyph's width;
   │  probes measure it; one latch cell per line × column holds the code
   ▼
 character chain: 24 × 65 + 1 nested levels, one per source character    compiler/ccpage5.py
   │  lexer step (cc_dsl.LexProg) per level; finished tokens → token registers (view timelines)
   ▼
 token chain: up to 400 nested levels, one per token                      compiler/ccpage5.py
   │  parser step (cc_dsl.Prog) per level, one specialised variant per (mode, token)
   │  emits instructions as overlays named after their RAM cells (--c<index>)
   ▼
 CSS CPU: registers in view timelines; each layout pass runs up to 32    machine/gen_css.py, csssim.py (model)
   instructions as nested elements (fetch > execute > commit) out of a   machine/memtree.py (RAM)
   2-way cache in custom properties; the first miss stops the chain and
   read ports at its end fetch the block for the next pass
   ▼
 console: 9 × 16 RAM cells shown with a counter-style font
```

Run and Edit are one checkbox (`#run`, first in `body`), read through sibling selectors (`#run:checked ~ …`). Edit
clears the CPU's registers and zeroes RAM. The picker's radio buttons (`#pk<i>`) follow it.

---

## 1. Memory map and ISA

Addresses are 15-bit words; a word is a 20-bit two's-complement integer. The map is `compiler/layout.json`, read by
`cc_ref.LAYOUT`, `uarch.py`, `rtlib.py` and the page generator.

| Range | Contents | Written by |
|---|---|---|
| 0 … 6143 | ROM: the runtime library (`lib_src.js` compiled by `cc_ref` in rom mode, 4,460 words), then `pstub` (2) | the page's static ROM table |
| 6144 | `data_base`: `STRTAG` = 262144, the untag constant (and the object key bias) | compiler `.fin` (an overlay) |
| 6145 … 6399 | globals (255 words) | the program |
| 6400 | `STR0`: the empty marker; then `"true"` and `"false"` (`SEED`) | compiler `.fin` |
| 6414 … 7167 | strings and property names, `[length][bytes…][0]` each (768 words with `SEED`) | compiler overlays (the length: the parser) |
| 7168 … 8190 | code (`code_base`, 1,023 words: 511 instructions) | compiler overlays |
| 8191 | count of global words (the collector's roots) | compiler `.fin` |
| 8447 | `strend`: the string area's end | compiler `.fin` |
| 8448 … | `rt_base`: HP, GCLIM, …, G_FLO, G_FREE (`layout.json` `rt_cells`); NET's cells (NETSEQ, RLEFT, RBUF0 … RBUF7, padded into cache sets the stack and code don't use); the collector's map of block starts at 8496 (`map_base`: a bit per 8 heap words, 48 words for both semi-spaces) and its powers of two at 8544 (16) | instructions, ROM routines |
| 8704 … 16239 | stack (`sp0`) | program |
| 16240 … 22383 | heap (`heap_lo`): two semi-spaces of 3,072 words | NEW, the cat class, ROM routines, the collector |
| 22384 … 22527 | console: the last `cols × rows` = 144 words | output instructions |

RAM is 16,384 words from 6144; the compile chain names cell `k` = address − 6144 `--c<k>`. Everything the program
reads but never writes (code, strings, `data_base`'s constant) is an overlay, so nothing is copied at start.

**RAM on the page** (`machine/memtree.py`): one leaf per word, a `content-visibility: hidden` element whose
remembered width is word + 2^20, with `anchor-name: --c<k>`. Four bank trees (address mod 4) of radix-4 decode nodes
route the write channels (`wa` / `wd`, one per issue) to the leaf. Reads are `anchor-size(--c<k> width, 2^20px)`
through a per-bank name mux; compiler overlays come later in tree order and win for the read-only areas.

**Sparse groups.** Leaves sit in groups of 256 (`memtree.GROUP`), `display: none` until a write reaches them (the
group latches `--live`: 0 s transition, 1,000,000 s delay). A hidden cell has no anchor, so a read falls back to 0,
which is what unwritten RAM holds. The console (and on CPU-only pages the static areas) is live from the start.

### The instructions

Two words at an even address (both in one cache block, so one fetch): word0 = op × 8192 + A, word1 = (B − 512) × 1024
+ C (LOADK, PRINTK and CALL use word1 whole). A, B and C are operands: 0 … 255 a global (`data_base + o`), 256 … 767
a frame slot (`fp + o − 256`), 768 … 1023 the constant `o − 896` (−128 … 127). Instructions in a function address their
temps past the function's locals; the linker adds the frame label (its count of locals) to those fields. `cc_ref.OPN`
lists them in class order (the CSS CPU's class is a range of opcodes).

| Class | Ops | What they do |
|---|---|---|
| alu | ADD SUB MUL DIV MOD LT GT LE GE EQ NE | A = B op C (20-bit wrap; `/` truncates; x / 0 = x % 0 = 0) |
| mov | MOV NEG LOADK GETFP KIND | A = B, −B, word1, fp; KIND A, B, k: A = kind test k of B (`cc_ref.KINDS`: the kind's code, string, array, object, array or object, a string not the program's own, its decimal length, any reference, a heap string) |
| jump | JMP, JLT … JNE, HALT | to A (if B op C) |
| test | JZ JNZ | to A if B is false / true: 0 and the empty string are false (a string's length word is read) |
| call | CALL RET NOT TENTER | CALL A, off: the return word (off × 8192 + return address) at fp + off, fp += off. RET B: B over the return word (the caller's slot for the value), fp −= off. TENTER A: CALL A with off = TRAPOFF and the return address pst + 2 (PRINT's trap) |
| mem | LDI STI | A = mem[B + C]; mem[A + B] = C (raw memory: the runtime library's `peek`, `poke`, `p[i]`) |
| dyn | DADD DADDL DADDR, DLT … DNE | numbers here; `+` with a string goes on to the cat class (L / R: that side is a boolean); with an array or object, and `==` / `!=` of two strings, the library |
| arr | GETX SETX | A = B[C], A[B] = C: an array inside its length here; an object whose key is a number or the program's own string goes to the obj class's probe (pst: its first pair); anything else the library (an array grows, a string's character, a key built at run time) |
| obj | GETP SETP NEW | A = B.key, A.key = B (C: the key's string-area offset), probing one pair per execution; SETP adds a pair in place (a full chunk: the library); NEW: a chunk |
| out | PRINT PRINTK PUTC | up to 4 console cells per execution (§3.2); PRINT of an array or object jumps to `pstub` |
| alloc | ALLOC | A = a new block of n words (B) of kind k (C: `cc_ref.ALLOCK`: a string of n bytes, its header, length and NUL written, A its value; an array of capacity n, its first line written; n raw words; an object chunk), marked in the collector's map (but raw ones) (§3.5) |
| apush | APUSH | the ROM's `push` routine's first instruction: B.push(C) and return (no array, or a full one: on to the routine) |
| mcpy | MCPY MUPPER MLOWER MFILL NPUT | C words from B to A (A ≤ B if they overlap; mapping letters' case); B into C words at A; B's digits at A: a line per execution |
| mcmp | MCMP MFEQ MFREF MWALK | A = the first i < A where B[i] ≠ C[i] / = C / refers into the from-space at C, else A: a line per execution; MWALK: the offset from B of the first `[len][bytes][0]` string of length A, or of the first at or past C, a string per execution |
| net | NET | A = the network gateway's answer to the word B, every part's bytes in RBUF0 … (§3.8) |
| cat | (a DADD with pst ≥ 1024) | a string's `+`, a line per execution (§3.6) |

**Traps.** A trapping instruction calls a ROM routine (`cc_ref.TRAPS`) as CALL would. A destination trap (the dynamic
operators, GETX, NEW) puts the routine's frame at its destination A, always a temp, so the value lands there; SETX and
SETP put it at fp + TRAPOFF (60, above any live temp: `TBMAX` keeps a frame's live words below it). The CSS CPU writes
one word per execution, so a trap is several executions (pc stays, `--pst` counts, only the last counts as a step): the
arguments last first (a destination trap's C may be the word after its frame's), then the return word, fp, pc. Once
started (pst > 0) it finishes whatever its operands then hold. PRINT of an array or an object writes nothing (the out
class has no memory write): it jumps to `pstub` with its own address in pst; `pstub`'s TENTER makes the frame and calls
`ptrap`, which decodes the PRINT's operand from the instruction itself. NEW's and ALLOC's traps (the heap full: `gcnew`,
`galloc`) return to the instruction, which executes again; a string's `+` that finds the heap full calls `gccat` (`cc_ref.CATTRAPS`),
which collects and joins.

**Values** (`cc_ref.isstr` / `isarr` / `isobj`). A string is its first byte's address − `STRTAG`, an array its ptr word's
address + `ARRTAG` (2^18), an object its chunk's address − `OBJTAG` (491,520). The tags are multiples of 2^15, so the
15-bit address registers untag a value for free: `LDI x, #-1` is a string's or an array's length. Numbers in
−255744 … −239761 are strings to the machine, in −475280 … −469137 objects and in 278384 … 284527 arrays.

---

## 2. The compiler

It exists twice, and the two must agree exactly (L2).

- **`compiler/cc_ref.py`**, the reference: a character-at-a-time pushdown transducer (fixed-size tables, no recursion,
  no lookahead past the next character). A completed token is parsed at once: shunting-yard for expressions, a
  control stack for statements. Unresolved addresses carry a label id until link time. `run()` simulates the code
  (wrapping to 20 bits). Its rom mode (`Compiler(..., rom=True)`) compiles the runtime library: raw memory, the
  intrinsics `peek` `poke` `__fp` `prn` `halt`, no dynamic operators, larger tables.
- **`compiler/cc_dsl.py`**, the same step in the integer DSL of `compiler/dsl.py`: predicated straight-line code
  (`with self.when(cond): …`) over SSA temps. Evaluated in Python it is L2's model of the page (each step compiled to
  one Python function, `dsl.pysrc`; `DSLEVAL=both` checks it against the tree evaluator `dsl.ev`); compiled to CSS each
  temp is one custom-property declaration. `Prog` parses one token per call, `LexProg` lexes one character.
  `dsl.Ctx.inline` puts a temp used once into its user's expression (a ternary's else operand counts twice: `css2`
  writes `ite(c, a, b)` as `b + c × (a − b)`), which takes a fifth of the declarations off a token level.

**Fixed limits** (`cc_ref.py`): operator and control stacks `OD` = `CD` = 8; operand descriptors `ODN` = 10 (with the
collapsed arguments, `TBMAX` = 24); symbols `NS` = 32; functions `NF` = 16; labels `NL` = 64 (6-bit fields);
`EMAX` = 7 instructions per step; `PIECES` = 4 printed pieces; `NI` = 32 interned strings and names; `SDATA` = 256
words of globals, `str_size` = 768 of strings, 1,023 of code; the page: 24 × 64 characters, 400 tokens (`TMAX`).

**Parser structure.** 27 modes (`S_STMT`, `S_OPND`, …). Control-stack kinds: bodies (`C_IFB`, `C_LOOPB`, `C_SWITCH`,
…), pending headers and statements (`C_IFC`, `C_SWITCHC`, `C_FORINIT`, `C_ASSIGN`, `C_PSET`, `C_CASE`, …), braceless
bodies (`kind + BRACELESS`, closed by `complete_stmt`). Entries pack as `kind × 4096 + a × 64 + b` and
`e × 4096 + c × 64 + d` (`e` = block-scope mark).

**Register allocation.** No register allocator: the operand stack of the stack machine became a stack of operand
descriptors (`od`, `nd` of them). An entry is `tb × 16384 + type × 4096 + descriptor`: an operand (a variable or a small
constant: no instruction yet), `TMP` (the value is in this entry's temp, `T(i)` = the frame slot past the locals),
`KBIG` (a constant LOADK must load: only on top, its value in `pk`) or `CND` (a pending comparison, B and C in `pk`:
only on top, for a branch to fuse). So `x = a + b * c` is `MUL T1, b, c` then `ADD x, a, T1`:

- An operator pops its operands' descriptors and emits one instruction into the left operand's temp, or, popped last
  in an assignment, straight into the target (`dest`). A comparison popped last before a branch stays pending and
  becomes the branch (`JLT` …); `!` likewise (`JZ` / `JNZ`).
- `popops` pops at most `popcap(minprec)` operators (`8 − minprec + UNARYRUN`): between markers the binary operators'
  precedences increase upwards, unary ones stack only on top (more than `UNARYRUN` = 4 of them: error 22).
- A variable on the stack is read when its instruction executes, so anything that could change it first copies it to
  its temp (`snapshot`): globals before a call, the variable before `x++` in an expression, every variable at the start
  of `&&` / `||` / `?:` (a copy made inside one would be made on one path only).
- Call arguments and array elements leave the descriptor stack once in their temps (`arg_end`: `tb`, the temps' base,
  moves past them until the call), so nesting is bounded by `TBMAX`, not `ODN`; an entry records the `tb` it was pushed
  at (its temp is `T(its tb + i)`, which a snapshot under a call needs).
- Static types (2 bits: 0 unknown, 1 boolean, 2 string, 3 number; in `sk_j`, `fl_k` and each entry) choose the plain
  instruction or the dynamic one: `+` is dynamic unless both sides are numbers or booleans, a comparison unless either
  is a number or a boolean.

**Features.**

- `&&` / `||`: `a → T(i); JZ/JNZ L, T(i); b → T(i); L:`. `c ? a : b`: `c Jfalse L1; a → T(i); JMP L2; L1: b → T(i);
  L2:`; `?` pushes `M_TERN`, `:` swaps in `M_TELSE` (lowest precedence), which defines `L2` when popped; an else branch's
  ternary reuses the outer `L2`. The value's static type merges both sides'.
- Calls: `CALL f, off` with the frame at the call's slot `T(d)`: the return word there, the arguments in `T(d + 1)` ….
  A function's parameters are `fp + 1 + k`, its locals after them, its temps after the locals (the frame label). A
  call passes exactly as many arguments as the definition has parameters (error 76).
- Methods: `x.name(` copies the receiver above its slot as the first argument; the `)` emits `CALL` of the ROM routine
  for that name and argument count (`ALLM`). `parseInt(` `Number(` `String(` pass an unused receiver. A method's name not
  followed by `(` is a property (it was interned then).
- Properties: `o.x` reads `GETP T, o, key`; `o.x = e` and `o.x op= e` are `C_PSET` statements ending in `SETP`; `x[k]`
  is `GETX` / `SETX`; `++` / `--` on either reads, adds and writes.
- Array literals: the elements in consecutive temps, then `CALL mkarrN` (N ≤ 8); past the eighth, `mkarr8` and one
  `SETX arr, #k, e` each (its trap appends). Object literals: `NEW`, then each pair as `SETP` (a number key: `SETX`).
- `switch`: the value in `T(0)` while the tests run; each `case v:` is `[JMP Bk] Tk: JNE Tk+1, T(0), v; Bk:` (`DEQ` +
  `JZ` when either may be a string); `}` is `[JMP end] Tlast: [JMP default] end:`. `S_SWCASE` makes the body start with
  `case`, `default` or `}`.
- `console.log`'s `+` chains: a piece with a string on either side stays on the stack, up to `PIECES` (more: the last
  two join); the argument's end prints each (flag 8: a piece, an array prints as its string). A lower-precedence
  operator joins the pieces first with `DADD`s.
- `.length`: a string's and an array's length are the word before the value's address, `LDI T, x, #-1`.
- Semicolon insertion, block scope, `do … while`, `else if` (one control entry per chain), strings in the string area
  and interning are as in the stack machine (HISTORY).

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
  `tools/vsz.py` counts 338 variants and 79,100 temps. Every rule costs time on every token level whether it applies or
  not (BENCHMARKS §4c). With a known starting mode, `Prog` folds away unreachable blocks (`FALL`).
- State alternates between parity copies (`--p-<name>-A/B`); temps share a small pool of names (`qp<i>`).
- Tables (symbols, functions, interned strings) are delayed writes: at most one entry per table per step through a
  port (`o_y*`, `o_f*`), applied by the next level with a container query.
- Instructions: up to 7 per level, two overlays each (`.ov.k<s>`, `.ov.j<s>`: word0 and word1), `anchor-name:
  --c<index>`, width `word + 2^20` plus a label's value (`anchor-size(--l<j> width)`: a jump target, or the frame label
  times its multiplier for a temp in a function). Each code record's word0 is one temp (`ew0`), which the 7 slots mux.
- Labels: in-flow anchors `.lp<k>` (22 ports per level) named `--l<j>`, width = the label's value.
- The last live level shows `.fin`: the globals' count word, `STRTAG` at `data_base`, the `SEED` strings, the string
  area's end at `strend`, `--ccdone` and `--ccinfo` (width `done + 2·err + 1024·words`, for the status line).

---

## 3. The CSS CPU (`machine/gen_css.py`)

Measurements and the style-engine costs behind the design: `exp/csscpu/README.md`.

### 3.1 A pass

- **Registers** (`#cpu`): view-timeline scrollers, a subject at `value` px; 358 of them: pc, fp, the console cursor,
  `--pst`, steps, halt, the pending miss, the data cache (32 tags with dirty bits, 16 victim bits, 128 words), the code
  cache (16 tags, 64 words), the read ports' eight words, the latches, the RAM and console write channels. Two passes
  per frame.
- **Fill** (`.fl`): the block the last pass missed goes into its set's victim way, from the port registers; a dirty
  victim's words go out through the RAM write channels. The next block is prefetched into its own set if it is absent
  there and the victim is clean. A miss of the fetch (`--pic`) fills the code cache instead, and prefetches the next line
  there if it is absent and code.
- **Chain**: 32 levels of three nested `display: contents` elements, styled once per pass:
  - `.f` fetches both words: ROM from a static table (one rule per 1,024-word tier), user code through the code cache;
    decodes op, A, B, C and the class (`cls_of`: the opcode's range; the cat class for a DADD with pst ≥ 1024, the obj
    class for a GETX / SETX with pst ≥ 1024).
  - `.x` executes: one `@container style(--cls: c)` rule per class (§1), `if()` on `--op` inside it. A class reads only
    what its instructions read (x: B, y: C, z / h: a third word or pair, e: a fourth, k / j: HP and GCLIM, p and l: a
    line, r: the collector map's word, w: the written word's set), since a rule evaluates every declaration in it.
  - `.c` commits: registers on success; on a stall, `--stop` and the missing block; output, bank by bank; a write as
    its whole cache set (16 rules on the set). SETP's new pair writes two words of one block (`--w2`); the primitives
    and the cat class up to a line (`write_line`: words u … u + k − 1).
- **Stalls**: an instruction runs only if every word it touches is cached (and, for output, its first cell's console
  bank is free this pass). The first that can't stops the chain. It keeps the operands it did read (**latches**:
  f/g, x, y, z/h, p, e, k/j) for its re-execution as the next pass's first instruction, so it needs only its written
  line resident at the end. A read is latched only if the reads its address came from were good (a class's `deps`).
  Two reads aren't latched: the map's word (r), which the same execution writes, so a miss there fills the written line,
  and MCMP's second line (l), the last read in order, which the last fill leaves resident.
- **Export** (`.ex`): the registers' subjects at the chain's end; the pass's writes into the channels; and eight
  **read ports** that read the missing block and the next during this pass's layout, for the next pass's fill.
- A miss on the block the same pass writes back would read its leaf before the write lands, so that fill waits a pass
  (`--stale`).

### 3.2 Memory and output

- Data cache: 16 sets × 2 ways × 4 words, set `(b + b / 16 + b / 256) mod 16` of block `b`, FIFO victims, write-allocate.
  `--T<line>` = 2 × (block + 1) + dirty, 0 for empty.
- Code cache: user code (`code_base` … `init`) is fetched through 16 direct-mapped lines of its own (line `b mod 16`,
  `--IT<i>` = block + 1, `--IW<i>_<word>`; `ICACHE=32,1` builds 32, for loops of more than 32 instructions). Only fetches fill it, and a fill prefetches the next
  line, so a loop's code stays resident while its data streams through the data cache: in the model, suite passes
  −28% (code misses 6,881 → 1,539; BENCHMARKS §15). Every register costs every pass, so 32 lines (caesar 24% faster) made
  23 of the 25 timed programs 2–12% slower (BENCHMARKS §15). Code isn't written at run time; the data cache still serves
  reads of code as data (`ptrap` decoding a PRINT).
- RAM: `memtree.py`'s leaves and decode trees, four banks. The read ports' leaf names are muxes; the most-read blocks
  (globals, strings, code) have their own mux, evaluated only when a block is missing.
- Console: its own four small trees and channels in a `contain: strict` box. A pass writes at most one cell per bank
  (cell address mod 4). `--cw` is the mask of the banks this pass has written: an output instruction runs if the bank of
  its first cell is free, and its chunk (up to 4 cells: a string's bytes to its block's end, a number's or boolean's
  characters) is cut at the run of free banks; the rest goes out on the next execution (`--pst`: a string's next byte,
  a number's characters so far). With 9 columns each row starts one bank later, so short lines share a pass.
- Instructions read 0 below RAM and drop their writes there.

### 3.3 Model and checks

- `machine/csssim.py` runs the same design pass by pass (both caches, prefetch, stall rules, latches, micro-steps,
  output banks); C1 checks it on every suite program against Node and cc_ref's steps. `machine/cssref.py` gives it machine
  states.
- `gen_css.py` refuses a page in which a registered `<integer>` value is more than one term (Chrome takes it as
  invalid and uses 0), a property is registered twice, or a class declares a property that isn't registered.

### 3.4 The page around it

- `UI=1` adds the editors, the readback scan, the compile chain and Run / Edit (`uipage.py`). Gating:
  `--go = compiled (ccok) × run × …`; nothing runs until `--ccgo`. Edit sets `--run` to 0, zeroing every register and
  RAM leaf; the compile chain's overlays hold code and strings, and read ports read them as RAM.
- The picker: eleven editors (`#ed`, the page's own program, then `samples/*.js`), one shown (`#pk<i>:checked ~ #app
  .ed<i>`); each keeps its edits. It is disabled while running (the scan reads the editor that shows).

### 3.5 Runtime library

`compiler/rtlib.py` builds the ROM: it fills in `lib_src.js`'s constants (upper-case names between double
underscores: the layout, the cells), compiles it with `cc_ref` in rom mode, and appends `pstub`. `lib.json` holds the
ROM and `entries` (every routine's address: the compiler calls the methods and `mkarrN`, the traps call `TRAPS`'
routines). It is a static table in the page (in tiers of 1,024 words), so a change means `make page`.

- The dialect: functions, locals, `while` / `for` / `if`, no short-circuit `&&` / `||` or `break`, `peek` / `poke` /
  `p[i]` on raw memory, `putc`, `prn` (PRINT), `halt`, `__fp()` (this frame's fp), and the primitives' intrinsics
  (`cc_ref.INTR`, below). No globals or string literals (they would land in the program's data area). A routine's frame
  holds tagged values, which the collector updates; a raw address must not be kept across an allocation.
- `lib_src.js`: the collector and its stubs (`gcnew`, `galloc`, `gccat`), strings (`newstr`, `tostr`, `cat`, `scmp`), the
  dynamic operators' routines, arrays (`newarr`, `grow`, `push`, `pop`, `join`), `getx` / `setx` / `setp`, `mkarrN`, the
  methods, printing arrays and objects (`pval`, `ptrap`), run-time string keys (`okey`).

**The runtime's primitives** (from branch `rom-css`, on the stack machine, redone for the register machine). The ROM's
work on memory is instructions that take a cache line per execution, `--pst` holding their progress, where a loop of
register code takes an instruction per word; and type tests are one instruction (KIND) where they were calls. One step
in `cc_ref.run()`; executions in `csssim.py`; a class each in `gen_css.py` (KIND inside mov). Intrinsics (rom mode):

| Intrinsic | Instructions | Executions |
|---|---|---|
| `__kind(v, K)` | KIND T, v, #K | 1 |
| `__alloc(n, A)` | ALLOC T, n, #A | HP (or the trap), the header's line, a string's NUL past it, the map's bit, T |
| `__mcpy` / `__mupper` / `__mlower` (d, s, n), `__mfill(d, v, n)`, `__nput(p, v)` | MCPY … d, s, n | a line of d per execution (to the end of the run, of d's line, of s's line) |
| `__mcmp(p, q, n)` / `__mfeq(p, v, n)` / `__mfref(p, flo, n)` | MOV T, n; MCMP … T, p, q | a line of p (and of q) per execution, T at the end |
| `__mwalk(p, e, n)` | MOV T, n; MWALK T, p, e | a string per execution |
| `__apush(x, v)` | APUSH 0, x, v | the element, the length, the result over the return word (and return) |

The ROM's `newstr` is one ALLOC; `join` sums its pieces' lengths and copies them into one string (MCPY, NPUT); `repeat`
doubles its copy; `slice`, `concat`, `grow`, `shift` and the collector's copies are MCPY; `find` searches with MFEQ and
compares with MCMP; `mkarrN` copies its arguments off its frame with one MCPY; `push` is APUSH, then the slow path.

### 3.6 Strings, arrays and objects, and the collector

**Heap blocks.** 8-aligned, a multiple of 8 words. A string is `[hdr][len][bytes…][0]`, an array
`[hdr][cap][len][ptr][elements…]` (ptr points at the elements, inline until the array outgrows `cap`, then at a raw
block of its own, which has no header and isn't in the collector's map); `hdr` = −2 − words − kind (kind 0 string, 1
array).

**Objects.** An 8-word chunk `[k0 v0 k1 v1 k2 v2 L pad]`. A key is a string's address in the string area (a value +
2^18), a number `n` is `n + 2^18`; 0 ends the keys (NEW zeroes `k0`; SETP's new pair writes the 0 after it first); `L`
is 0 or a link to an overflow chunk (negative). GETP / SETP probe one pair per execution (`--pst`: the pair's address),
and so do GETX / SETX when the key is a number or the program's own string (SETX hands a full chunk back to the arr
class, `--pst` 512, whose trap calls `setx`). Strings and names are interned by content hash, so a key is a
compile-time constant and `o[s]` finds `o.x` when `s` is `"x"`. A key built at run time (a heap string, or one of
`SEED`'s) traps to `getx` / `setx`, whose `okey` replaces it by the object's key with its characters if it has one, else,
when it is being stored, by the program's string with them if there is one (MWALK finds the strings of its length,
MCMP compares): a key is the literal whenever one exists, so it finds the same property as a literal key.

**A string's `+` in CSS (the cat class).** A DADD whose operands are a string and a string, number or boolean (no array
or object) hands over to the cat class (pst 2048). Then, pst 2048 + k: HP += the block's words (the heap full: `gccat`
through a trap, which collects and joins), the header and the length, the characters a line per execution (from X or
from Y, to the end of the source, of the written line and of a string's line; a number's digits and `true` / `false`
computed; the NUL with the last chunk if it fits), the NUL, the map's bit, then A. Each execution re-derives the block
from HP and the operands' lengths, so nothing but pst carries state, and A is written last (it may be B). The layout is
`newstr`'s, so the collector and the routines see the same heap either way.

**The collector** (`lib_src.js` `gc`): Cheney copying between the semi-spaces, conservative on the stack. The roots: the
globals (up to the count at `init − 1`) and every word of the stack from `sp0` up to its own frame except the return
words (found by walking the frames: off = the word / 8192). A frame keeps stale words (a register machine's temps aren't
cleared), so a stack word is forwarded only if it starts a block in the **map** at `map_base` (a bit per 8 heap words,
16 to a word, both semi-spaces). The map is kept as blocks are made: ALLOC (strings, arrays, chunks), NEW and the cat
class set their block's bit, the collector's copies set theirs in to-space, and a collection clears to-space's half first;
a stale word keeps a dead block alive at worst. (Until 2026-10-22 the bitmap was built at each collection by walking
from-space by its headers, a miss per block, 14–31% of the GC programs' passes; and a grown array's raw block, which
has no header, could misguide the walk into a loop: `tests/suite/gc_rawblock.js`.) MFREF finds the next word that refers
into from-space a line at a time, so roots and elements that are numbers cost nothing; copies are MCPY. The scan follows
an object's keys and values up to its first free pair (and its link if all three are used) and an array's elements up to
its length. HP and GCLIM are offsets from `heap_lo`; GCLIM is the current space's offset, so zeroed RAM is space A and
needs no setup.

### 3.7 The stack machine (replaced 2026-10-21; last at `212175a`)

One-word instructions on an evaluation stack (PUSHI, LOADG, …, the DYN, IDXA and SCANI families), the runtime library
compiled by the self-hosted `jsc.js` plus hand-written assembly behind a jump table. The register machine runs the same
programs in 2.2–4.8× fewer steps (BENCHMARKS §14).

### 3.9 The font CPU (removed; last at commit `181cbb7`)

A GSUB CPU ran 32 micro-cycles per shaping while Chrome shaped the machine state as a line of text, and CSS serviced
its traps. It was 2.8–7.3× slower than the CSS CPU (BENCHMARKS §12); ENGINE_NOTES 25–33 are what it relied on.

### 3.8 The network: `NET` and the modems

`fetch(url)` and `read()` are ROM routines (`lib_src.js`, called like `parseInt`: cc_ref `GLOBALS`) made of one
instruction, `NET` (opcode 58). Its word is `2 p + s`: `s` a sequence bit the lib alternates (the runtime cell
`NETSEQ`), so consecutive words always differ; `p = 4 arg + op` (`net/device.py`): op 0, two URL bytes (`arg = b0 + 256
b1`); op 1, GET (the status + 1, 0 if it failed); op 2, READ. P = 4 modem parts (`layout.json` `net_parts`) answer
each word at once: part j's answer to a READ is the body's bytes 2j and 2j + 1, packed as `b0 + 256 b1 + 65536 n`. `NET`
unpacks the answers into the bytes `RBUF0 … RBUF7` (−1 where there is none: `cc_ref.netw`) and puts part 0's answer
over the word. `read()` takes the next byte from there (`RLEFT` counts what's left), so a READ brings 8 bytes.
`cc_ref.run()`, `cssref.py` and `csssim.py` answer at once from `net/device.py`, which serves `tests/net/`; in csssim a
`NET` ends its pass the first time and runs first in the next, as on the page.

On the page the CPU can't make requests, so it talks to a gateway (`net/server.js`, which has the protocol) through two
modem iframes, each answering two parts:

- **The class `net`** (`NET A, B`) reads the word B and stalls without a miss until every part's answer to it has come
  (ENGINE_NOTES 56). While it waits it leaves `--req = 1 + word` at the chain's end, the register `rreq` (held on
  passes that don't run the chain). Then it runs 2 P + 1 times (`--pst`): the 8 bytes into `RBUF0 …`, then part 0's
  answer into A, which completes it; the word stays the request until then. The ROM reaches it as `__net(word)`. `rnt0`
  holds the clock (`--t`, 600 a second) when this request began; 20 s without an answer give −1.
- **The request**: the modems, `<iframe loading="lazy" src="/net/m0.html?part=i&n=4#t">`, are `NW + rreq` px tall
  (`NW` = 2^20 + 100; a word is below 2^19), each in an `NW × NW` box that clips it (`.nclip`), so the slot around it
  scrolls 2^20 px on both axes whatever the request. The boxes show from the run's first waiting `NET` on (the register
  `rlive`); before that nothing loads.
- **The modems' documents**: the gateway serves one per word to each modem, alternating `m0.html#t` and `m1.html#t` (a
  refresh to the same URL doesn't reload). A document refreshes as soon as it has loaded, and the gateway holds that
  navigation until the modem has new answers; the old document stays and keeps working (ENGINE_NOTES 62). Modem 0's
  documents send the request: they read `100vh − NW` and send five hex digits of it plus a check digit as
  `background-image: if(style(--x: …): url(d/<doc>/<i>/<x>); …)`, `x = 16 tag + digit`. A document fetches a URL once
  (ENGINE_NOTES 61), so `tag` is 1 + the word's seq bit, which every new word flips, and 0 (nothing sent) for an idle
  request and for the word the document came with. A resize restyles the document in the frame that lays out the new
  height, so the request is at the gateway a few ms later.
- **The answer**: modem i's document puts `#t` (100 × 100 px) at x, y = the answers `R = valid + 2 seq + 4 (answer)` of
  parts 2i and 2i + 1, below 10^6 (the page reads them through `var()`, which keeps 6 digits), and its load scrolls to
  `#t`. The scroll reaches `.nslot.np<i>`, the page's 100 × 100 `overflow: hidden` box around the clip box, so its
  `scrollLeft` and `scrollTop` are the two Rs; the scroll timelines `--nans<2i>` (x) and `--nans<2i+1>` (y) read them.
  An answer counts when it is valid and its seq is the word's bit 0; a modem's later documents for the same word carry
  none (R = 0), so an answer never comes back for a later word. Fragment scrolls cross only same-origin documents, so
  the modems are in the page's process, and each of their documents costs the page two forced style updates
  (ENGINE_NOTES 63): two answers per document halve them.
- **Outside `#clk`**: the slots and the iframes sit before `#clkw`, since Edit hides `#clk`. A box that goes `display:
  none` keeps its scroll offset and gets it back when it shows (ENGINE_NOTES 59): the last run's answers came back
  with it and could pass for the first word's. Out there the slots always show and only their clip boxes hide; they
  read `rreq` and `rlive` through animations of their own (their timelines and `--nans<j>` are scoped at `body`), which
  go inactive on Edit: the clip boxes hide, and the slots scroll back to 0.
- **The gateway** gives the page's modems a group: as it serves a page it writes a group id into their URLs, each
  modem's first request is redirected to its own session `/net/s/<id>/m0.html` (the fragment carries over), and its
  URLs are relative to that, so two pages can't mix their words. It acts on a request once all six digits have come for
  one tag with a matching check digit, computes the answers once per word, and resolves relative URLs against the page
  (the first request's referrer). A held navigation holds a connection, and Chrome opens 6 per host: past 4 held in one
  browser (a cookie tells browsers apart), the gateway answers the others at once and they poll, refreshing every
  second; a navigation held 20 s is answered with no answers.
- **The runtime cells** of the read path (`RLEFT`, `RBUF0 …`) sit at `rt_base + 32 … 47`, whose blocks fall in cache
  sets 11–14: at first they shared sets 9 and 10 with the stack's and the code's hot blocks, and every byte evicted one
  of the three (`layout.json` pads `rt_cells` to put them there).

A word brings 2 URL bytes or 8 body bytes. A URL word takes about 4 page frames (0.2–0.5 s): the request leaves in the
frame that lays it out, the new documents scroll in the next, where the CPU reads them; the rest are the lib's and the
register `rreq`'s. A READ takes about 10, most of them the CPU's work on its 8 bytes (BENCHMARKS §16).

---

## 4. Editor readback (`readback/ui_rb.py`)

- The editors use the AsciiProbe font (`mkfont2.py`): axis `SCAN = j + 1` activates, through FeatureVariations,
  lookups that copy column `j`'s character into a sentinel's advance. One probe per line measures it (`anchor-size()`
  of a `::after` anchor). Latch cells (0 s transition writes, 1,000,000 s delay holds) keep the codes, each with a
  view-timeline register `--ch<k>_<j>` the compiler reads.
- The scan is frame-locked (one column per frame at any frame rate) over a fixed 64 columns.
- It runs only after Run: while editing, `SCAN` is 0 and the registers are frozen (`--rbfrz`). After Run the editors
  are read-only, one sweep raises `--rbrd`, and `--ccgo` (from the `--rbrdT` timeline) shows the compile chain.
- Lines: line 0 is text directly in the editor, line `k` its `k`-th `div`, each with a sentinel. Nested divs show
  inline, `<br>` is hidden, `white-space: nowrap` with `&nbsp;`, and no CSS rule may match the line divs (ENGINE_NOTES
  44–49). Hidden editors are `display: none`, so the anchors are the shown one's; the per-line checks (`:has`) are
  per editor, under its radio button, on the editors' section with child combinators (on `#app` each searched its
  ~10,000 elements: BENCHMARKS §14). `make l5-input` checks that the scan reads what the editor shows; `tests/picker.js`
  the picker. An editor's initial text starts at its line 1, so a sample has at most 23 lines.

---

## 5. Tests

| Level | Command | What runs | Checked against |
|---|---|---|---|
| oracle | `make expect` | each `tests/suite/*.js` under Node, putc shimmed | writes `*.out` |
| L1 | `make l1` | `cc_ref` compile + 20-bit simulator, strict: fp back at its start at HALT | Node output |
| L2 | `make l2` | the DSL in Python level by level, with the page's specialised variants (`SPEC=1`; `make l2-generic` unspecialised) | the reference: parser state, tables, every word and label |
| L3 | `make l3`, `make fuzz-l3` | the generated CSS compiler in Chrome (`build/suite_css.xhtml`, programs written into the latch cells) | the reference, word for word; `suite_err` must be rejected (any nonzero error) |
| C1 | `make c1` | `csssim.py`, the CSS CPU pass by pass, runs every compiled image | Node output, cc_ref's steps |
| C2 | `make c2` | a CPU-only page per program under 1,500 steps (`tests/csscpu_pages.py`) runs to HALT in Chrome | Node output on the grid, cc_ref's steps |
| L5 | `make l5` / `l5-smoke` | the real page: type, Run, read the console | Node output on the 9 × 16 grid |
| L5 net | `make l5-net` | the `net_*` programs on the real page, served over HTTP with the gateway (`net/server.js`) | Node output, with `net/shim.js`'s fetch / read |

- `make test` = oracle, L1, quick fuzz, L2, C1. `tests/suite/` has 135 programs, `tests/suite_err/` 47;
  `samples/` the picker's ten; `tests/programs/` the demos t1–t4.
- **Differential tests** (`tests/fuzz/fuzz.py`; `make test` runs a quick fixed-seed set, `make fuzz` the full one,
  `make fuzz-l3` 300 of them through L3 in Chrome). Node is the oracle; each program goes through L1, L1 on the
  page's padded text when it fits the editor, and optionally L2 (`--l2`) and C1 (`--c1`). Sources: `fmt` (every suite
  program in 11 layouts), `gen` (random programs from `progen.py`, inside the documented language), `mut` (suite
  programs with token edits). Failures are shrunk into `build/fuzz/`; `tests/fuzz/show.py` replays one.
- L5 runs only programs under 1,500 steps (`tests/suite_ui.py`). Harnesses detect HALT by the page's `--isHALT` flag.
- Caches in `build/`, keyed by a hash of every input (sources, ROM entry points, settings), so they are never stale:
  `dslcache/` the parser variants compiled for L2 (`cc_dsl.compiled`; building one takes ~70 ms, loading it ~0.1 ms),
  `ccpage5/` the compile chain (`ccpage5.build`, shared by the product page and the L3 page). `DSLCACHE=0` and
  `CCCACHE=0` build without them.

---

## 6. Build

```
make page   # compiler/lib.json (if lib_src.js or cc_ref.py changed) -> build/ccimg.json -> build/js_in_css.xhtml
make dist   # copy it to dist/
```

- Reproducible (the Makefile pins `PYTHONHASHSEED` and `SOURCE_DATE_EPOCH`). The image (`mkimage.py tests/fizz.js`)
  supplies the ROM and the editor's initial program; `samples/*.js` the picker's.
- The compile chain's ~1,000 parser variants are built on every CPU (`JOBS`), and the chain is reused while the
  compiler doesn't change (`build/ccpage5/`, §5): a page takes ~7 s, or under a second after a machine-only change.
- `gen_css.py`: `UI=1` builds the product page; `UIL` / `UIP` / `UIT` set lines, columns, tokens; `SHORT=0` keeps
  the compiler's readable property names; `K` the levels per pass (32); `INLINE=0` (cc_dsl) keeps every temp.
  Without `UI=1` it builds a CPU-only page for a RAM image holding the program (HTML: name it `.html`).
