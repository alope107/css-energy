# Architecture

`make page` builds one XHTML file that runs no script. The user types JavaScript and presses Run; CSS reads the text
back, CSS compiles it to bytecode, and CSS executes it: a chain of instructions per layout pass. Output goes to an
8 × 16 console. (Until 2026-10-19 the CPU was a GSUB font; §3.7.)

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
 CSS CPU: registers in view timelines; each layout pass runs up to 32    machine/gen_css.py, csssim.py (model)
   instructions as nested elements (fetch > execute > commit) out of a   machine/memtree.py (RAM)
   2-way cache in custom properties; the first miss stops the chain and
   read ports at its end fetch the block for the next pass
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
| 0 … 6143 | ROM: the runtime library (`lib_src.js` compiled by jsc, ~3,650 words; its first words jump to `code_base`), hand-written routines (`rtlib.py`, ~520 words), the jump table at 6128 … (`vec_base`) | the page's static ROM table |
| 6144 | `data_base`: `STRTAG` = 262144, the untag constant (and the object key bias) | compiler `.fin` (an overlay) |
| 6145 … 6399 | globals (255 words) | the program |
| 6400 | `STR0`: the empty marker; then `"true"` and `"false"` (`SEED`) | compiler `.fin` |
| 6414 … 7167 | strings and property names, `[length][bytes…][0]` each (768 words with `SEED`) | compiler overlays (the length: the parser) |
| 7168 … 7678 | code (`code_base`, 511 words) | compiler overlays |
| 7679 | count of global words (the collector's roots) | compiler `.fin` |
| 7935 | `strend`: the string area's end | compiler `.fin` |
| 7936 … | `rt_base`: HP, GCLIM, GCSP, KEYCELL, RETCELL, the routines' cells (`layout.json` `rt_cells`) | instructions, ROM routines |
| 8192 … 16255 | stack (`sp0`) | program |
| 16256 … 22399 | heap (`heap_lo`): two semi-spaces of 3,072 words | NEW, ROM routines, GC |
| 22400 … 22527 | console: the last `cols × rows` words | PRINT / PUTC service |

RAM is 16,384 words from 6144; the compile chain names cell `k` = address − 6144 `--c<k>`. Everything the program
reads but never writes (code, strings, `data_base`'s constant) is an overlay, so nothing is copied at start.

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
labels `NL` = 64 (6-bit fields); `EMAX` = 12 code words per step; `NI` = 32 interned strings and names; `SDATA` = 256
words of globals, `str_size` = 768 of strings; the page: 24 × 64 characters, 400 tokens (`TMAX`).

**Parser structure.** 27 modes (`S_STMT`, `S_OPND`, …). Control-stack kinds: bodies (`C_IFB`, `C_LOOPB`, `C_SWITCH`,
…), pending headers and statements (`C_IFC`, `C_SWITCHC`, `C_FORINIT`, `C_ASSIGN`, `C_CASE`, …), braceless bodies (`kind + BRACELESS`, closed
by `complete_stmt`). Entries pack as `kind × 4096 + a × 64 + b` and `e × 4096 + c × 64 + d` (`e` = block-scope mark).

**Features.**

- `&&` / `||`: `a DUP JZ/JNZ L POP b`, `L` defined when the operator pops. The value's static type merges both
  operands' (as `?:` does): boolean if either is, so the PRINTB forms misprint only a 0 or 1 from the other side.
- `c ? a : b`: `c JZ L1 a JMP L2 L1: b L2:`. `?` pushes `M_TERN`; `:` swaps in `M_TELSE` (lowest precedence), which
  defines `L2` when popped. A ternary in an else branch reuses the outer `L2`, so the DSL checks for one `M_TELSE`
  once after `popops`' loop.
- `do … while`: `C_DOB` (continue, break, top labels); `S_DOWHILE` waits for `while`; the `)` emits `JNZ top`.
- Block scope: function-level names grow up from 0 (`nsym`), block-level `let` / `const` down from `NS - 1`
  (`nlet`); each control entry records `nlet` and closing a body restores it. `const` is a symbol bit.
- Semicolon insertion: a newline after a statement-ending token (identifier, number, string, `) ] } ++ --`) is pending
  (`pnl`) until the next significant character, which the lexer sees as the lookahead of the blank or comment end
  before it: `. [ ( ? : , ) ] * % < > & | = ; }` continue the statement or end it themselves (no token), anything else
  gets `T_NL`. `+` `-` (`++x` starts a statement) and `/` (comment or division) are decided on the character itself;
  after `return` (`lt` 2) the newline always gives `T_NL`. The parser treats `T_NL` as `;` only where a statement can
  end outside `( [`, calls and `for` headers. On the page the newline level's lookahead is the next line's first
  character, so a line's source element opens at the previous line's newline level.
- `switch`: the value is on the stack only while tested, so bodies, `break`, `continue` and `return` need no cleanup.
  `C_SWITCH` holds the pending test's label, the end label, `default`'s label and flags. Each `case v:` is `[JMP Bk]
  Tk: DUP v EQ JZ Tk+1 POP Bk:` (the `JMP` lets the previous body fall through); `}` is `[JMP end] Tlast: POP [JMP
  default] end:`. `break` targets the innermost loop or switch, `continue` the innermost loop. `S_SWCASE` makes the
  body start with `case`, `default` or `}`.
- `++` / `--` in expressions (variables): `x++` is `LOAD INC`, `++x` `INC LOAD` (`--` with `PUSHI 1 SUB` and a `DUP`);
  `pm` = 3 after one, so no `.` or `[` may follow.
- Strings in the string area: the lexer writes a literal's or a name's bytes (a word reserved before them) and the NUL;
  the parser writes the length word when it interns the string (the lexer has one data port per character). A string
  token's value is its address − `data_base` (1024: no room) + 2048 × its length (+ 2^18 for an identifier followed
  directly by `(`: a method call needs no interning). A literal is `PUSHS address`.
- `.length`: a string's and an array's length are both the word before the value's address, so `x.length` is
  `PUSHI 1 SUB LOADI`.
- Array literals: the elements on the stack, then `CALL mkarrN` (N ≤ 8, fixed-count routines) or `PUSHI n CALL mkarr`.
  `x[k]` reads `IDXA`, `x[k] = v` is `[x, k, v] STOREX`, `x[k] op= e` is `OVER OVER IDXA e op STOREX`.
- `+` and the comparisons: the plain instruction when the static types say numbers (for a comparison: either
  operand), else `DYN op` (bit 6 / 7 of its immediate: the left / right operand is a boolean, for `"x" + true`).
- Methods: `x.name(` for a name in `METHODS` (`cc_ref.py`) pushes `M_METH`; the `)` emits `CALL` of the ROM routine
  for that name and argument count (`ALLM`), the receiver and the arguments on the stack. `parseInt(` `Number(`
  `String(` push 0 as the receiver. A method's name not followed by `(` is a property (it was interned then).
- `console.log`'s `+` chains: a piece with a string on either side stays on the stack (`M_PRINT`'s value counts them);
  the argument's end prints them with `CALL pnK` (K ≤ 8 pieces; more are joined first), and a lower-precedence
  operator joins them with `CALL catnK` first. A boolean piece becomes `"true"` / `"false"` (`b2s`).
- `console.log` leaves no value (its PRINT words pop every argument): it ends its statement itself, without the
  expression statement's `POP` (`print_end`), and can't be used as a value.
- Argument counts: `fl_k` = label + 64 × type + 256 × (argument count + 1, 0 until the first call or the definition).
  `M_CALL`'s value is the function index + 16 × type + 64 × commas; its `)` checks or records the count, and
  `end_params` checks the calls made before the definition (error 76).
- The string area starts one word past `data_base + SDATA`, which is the lib's empty DONE marker PRINT stops at.
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
- The last live level shows `.fin`: the globals' count word, `STRTAG` at `data_base`, the `SEED` strings, the string
  area's end at `strend`, `--ccdone` and `--ccinfo` (width `done + 2·err + 1024·words`, for the status line). `#tcr > .big` (`--cctoo`) shows past 400 tokens.

---

## 3. The CSS CPU (`machine/gen_css.py`)

Measurements and the style-engine costs behind the design: `exp/csscpu/README.md`.

### 3.1 A pass

- **Registers** (`#cpu`): view-timeline scrollers, a subject at `value` px (the font CPU's mechanism); 273 of them: pc,
  sp, fp, the console cursor, `--pst`, steps, halt, the pending miss, the cache (32 tags with dirty bits, 16 victim
  bits, 128 words), the read ports' eight words, the latches, the RAM and console write channels. Two passes per frame
  (the frame gate: `--go`, `--k`, `--par`; a third settles).
- **Fill** (`.fl`): the block the last pass missed goes into its set's victim way, from the port registers; a dirty
  victim's words go out through the RAM write channels. The next block is prefetched into its own set if it is absent
  there and the victim is clean.
- **Chain**: 32 levels of three nested `display: contents` elements, styled once per pass:
  - `.f` fetches: ROM from a static table (its own container-query rule, since an `if()` costs its whole text wherever
    it is evaluated), RAM through the cache; decodes the opcode and its class.
  - `.x` executes: one `@container style(--cls: c)` rule per class (push, load, bin, jump, test, store, index, arr,
    dyn, the runtime's kind, alloc, apush, mcpy, mcmp, cat, enter (§3.5), out), `if()` on `--op` inside it for
    addresses, results and next registers. A container-query test costs ~2 µs per element,
    matched or not, an `if()` branch ~0.3 µs: a rule per opcode made even idle levels cost 269 µs, classes 47 µs.
  - `.c` commits: registers on success; on a stall, `--stop` and the missing block; output; a write as its whole
    cache set (16 rules on the set; 128 rules on the word cost too much to test).
- **Stalls**: an instruction runs only if every word it touches is cached (output also needs the pass's console write
  set). The first that can't stops the chain. It keeps the operands it did read (**latches**) for its re-execution as
  the next pass's first instruction, so it needs only its written line resident at the end: three blocks in one 2-way
  set (code, stack top, a string) otherwise evicted each other forever. A read is latched only if the reads its
  address came from were good (a class's `deps`, exactly).
- **Export** (`.ex`): the registers' subjects at the chain's end; the pass's writes into the channels (a channel keeps
  its cell until it takes another: a channel change restyles its whole tree); and eight **read ports** (readers: a
  fixed element whose width is `anchor-size()` of the leaf a two-level `if()` names, a scroller inside whose subject
  sits at `100cqi`) that read the missing block and the next during this pass's layout, for the next pass's fill.
  Nothing above the chain is a size container: ports nested above it restyled the chain once per port per fill.
- A miss on the block the same pass writes back would read its leaf before the write lands (channels take effect a
  pass later), so that fill waits a pass (`--stale`).

### 3.2 Memory and output

- Cache: 16 sets × 2 ways × 4 words, set `(b + b / 16 + b / 256) mod 16` of block `b`, FIFO victims, write-allocate.
  `--T<line>` = 2 × (block + 1) + dirty, 0 for empty.
- RAM: `memtree.py`'s leaves and decode trees, four banks (one block's four words in one pass). The read ports' leaf
  names are muxes over 4,352 blocks; the 512 most-read blocks (globals, strings, code, the stack's bottom) have their
  own mux, evaluated on the port, and only when a block is missing.
- Console: its own four small trees and channels in a `contain: strict` box, so output doesn't restyle RAM; readers
  as before. PRINT and PUTC write up to 4 cells per execution and repeat with `--pst` until done (uarch's print
  service).
- Object instructions read 0 below RAM and drop their writes there (`cc_ref.run`). NEW and ENDK write two words, one
  per execution (`--pst` 0, then 1).

### 3.3 Model and checks

- `machine/csssim.py` runs the same design pass by pass (cache, prefetch, stall rules, latches, PRINT chunks); C1
  checks it on every suite program against Node and cc_ref's steps. `machine/cssref.py` is the ISA as a stepper.
- `gen_css.py` refuses a page in which a registered `<integer>` value is more than one term (Chrome takes it as
  invalid and uses 0) or a property is registered twice (memtree's, the compiler's and the scan's names are global).

### 3.4 The page around it

- `UI=1` adds the editor, the readback scan, the compile chain and Run / Edit (`uipage.py`, shared with the font
  page). Gating: `--go = compiled (ccok) × run × …`; nothing runs until `--ccgo`. Edit sets `--run` to 0, zeroing
  every register and RAM leaf; the compile chain's overlays (named after their RAM cells) hold code, strings and
  staging, and read ports read them as RAM.

### 3.5 Runtime library

`compiler/rtlib.py` builds the ROM: it writes `lib_src.js`'s constants (upper-case names between double underscores:
the layout, the cells, opcodes) for `libbuild.js`, which compiles `lib_src.js` with the self-hosted `jsc.js` under Node,
then appends hand-written routines and the jump table. `lib.json` holds the ROM and `entries` (every routine's
address, for the compiler). It is a static table in the page (in tiers of 1,024 words, each a rule of its own: an
`if()` costs per entry it holds), so a change means `make page`.

- jsc's dialect: functions, locals, `while` / `for` / `if`, `peek` / `poke`, `putc`, `prn` (PRINT), `__fp()` (the
  caller's frame pointer, for the collector's roots), `__op(word, args…)` (one raw instruction). No globals or string
  literals: jsc would put them in the data area, which is the program's. A routine's frame holds tagged values, which
  the collector updates; a raw address must not be kept across an allocation.
- `lib_src.js`: the collector, strings (`newstr`, `tostr`, `cat`, `scmp`, `dynop`), arrays (`newarr`, `grow`, `aset`,
  `push`'s slow path, `pop`), the methods, printing arrays and objects (`pval`), run-time string keys (`okey`).
- `rtlib.py`: the GC stubs (`gc` for NEW, `galloc` for ALLOC, `gcat` for CAT), APPEND, GETX / SETX (the object paths;
  the rest goes to `lib_src.js`), the DYN stubs (`dcat0`: `+` without a boolean, straight to CAT; `dcat`; `dyn`), the
  PRINT trap stub, `push` (one APUSH word), `pnK`, `b2s`, `mkarrN`.

**The runtime's primitives** (opcodes 58 … 63, `uarch.RTOPS`). The ROM's work on memory is instructions that take a cache
line per execution, `--pst` holding their progress, rather than jsc loops that take a word per ~10 instructions (each
jsc instruction is a chain level, ~0.45 ms in Chrome; ENTER zeroing a local was one execution per local). One step in
`cc_ref.run()`; in `csssim.py` and `gen_css.py` a class each (`kind`, `alloc`, `mcpy`, `mcmp`, `apush`, `cat`, and
`enter`, which left `push`). jsc reaches them as `__op(__NAME__, operands…)` (`rtlib.consts()` names the immediates).

| Op | Stack | What it does | Executions |
|---|---|---|---|
| `KIND k` | [x] → [r] | k = 0: 0 number, 1 string, 2 array, 3 object; 1 … 3: x is that kind; 4 a heap string; 5 a string that isn't the program's own; 6 x's length in decimal; 7 an array or object; 8 the address of the stack word x below this one | 1 |
| `ALLOC k` | [n] → [b] | a block of ceil8(n) words at HP, its header −2 − words − k (an array, k = 1: its whole first line, capacity n − 4, length 0, the element pointer); full: GCSP, RETCELL, to `galloc` | 3: the header line, HP, the result |
| `MCPY k` | [d, s, n] → [d] | n words from s to d (d ≤ s if they overlap); k = 1 / 2 letters to upper / lower case; k = 3 [p, v] → [p]: v's decimal digits at p | a line of d per execution (to the end of d's line, of s's line, of the run) |
| `MCMP k` | [p, q, n] → [i] | the first i < n where p[i] ≠ q[i]; k = 1 where p[i] refers into the from-space at q, k = 2 where p[i] = q; else n. k = 3 [p, e, n] → [o]: through `[len][bytes][0]` strings from p, the first of length n is at p + o | a line of each per execution; k = 3 a string per execution |
| `APUSH` | [x, v, ret] → [n] | `x.push(v)`, then to ret: the ROM's `push` entry is this one word; no array, or a full one, goes on to `lib_src.js` `push` through the jump table | 3: the element, the length, the result |
| `CAT` | [a, b] → [s] | a new string, a's characters then b's (strings or numbers: a number's digits are written in place); full: to `gcat` | the header and length, HP, a line of characters per execution (the NUL with the last if it fits), the result |
| `ENTER n` | | the frame: the saved fp, the locals zeroed | a line of the frame per execution |

- Words to and from memory: `write_line` (`gen_css.py`) writes words u … u + k − 1 of one block, so the commit is still
  one cache set; `line_read` reads a block's four words (`p`, latched as PRINT's is, and `y`, which MCMP alone reads and
  which is not latched: it is the one read that can miss last, and the last fill is always resident).
- Every instruction counts one step when it completes, as in `cc_ref`. The miss rules are the other instructions':
  every word an execution touches must be cached, and the latches keep its operands across a stall.

### 3.6 Strings, arrays and objects, and the garbage collector

**Heap blocks.** 8-aligned, a multiple of 8 words. A string is `[hdr][len][bytes…][0]` (its value: the first byte's
address − `STRTAG`, like a literal's); an array `[hdr][cap][len][ptr][elements…]` (its value: the ptr word's address +
`ARRTAG` = 2^18; ptr points at the elements, inline until the array outgrows `cap`, then at a data block of its own);
`hdr` = −2 − words − kind (kind 0 string, 1 array). The tags are multiples of 2^15, so the 15-bit address registers
untag a value for free (`LOADI` of `x − 1` is the length of a string or an array).

**Instructions** (`cc_ref.run()`, `csssim.py`, `gen_css.py`'s push, arr, dyn, test and out classes). A trap pushes the return
address and jumps to a ROM routine, as CALL does:

| Op | Stack | What it does |
|---|---|---|
| `PUSHS a` | [] → [s] | push the string value of address `a` (a literal) |
| `IDXA` | [x, k] → [x[k]] | an array: its element (0 past the length); anything else traps to GETX |
| `STOREX` | [x, k, v] → [] | an array, `k` inside its length: the store; anything else traps to SETX (an array grows) |
| `DYN op` | [a, b] → [a op b] | ADD, EQ, NE, LT, GT, LE, GE on numbers; traps to `dyn` for `==` / `!=` of two strings, and for the others with a string, array or object |
| `JZ` / `JNZ` / `NOT` | | 0 and the empty string are false (a string's length word is read) |
| PRINT family | | an array or object traps to `print` (Node's one-line form; without a separator, a `+` piece: its string) |



**Objects.**

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

**Object instructions** (opcodes 45 … 53, in `cc_ref.run()`, `csssim.py` and `gen_css.py`'s index, store and load classes):

| Op | Stack | What it does |
|---|---|---|
| `SCANI k` | [o] → [c] | compare the key at the cursor with `k`: found or 0, stop (cursor stays on that word); negative, follow the link; else step 2 words. Re-executes until it stops |
| `SCAN` | [o] → [c] | the same, key in KEYCELL (the ROM routines' dynamic keys) |
| `LDF i` | [p] → [mem[p+i]] | `o.x` is `SCANI x; LDF 1` |
| `PUTV k` | [c, v] → [] | key at `c`: `mem[c+1] = v`; else call the ROM's append routine with `[c, v]` (return address in `mem[c+1]`) |
| `NEW` | [] → [o] | a chunk at HP; if the heap is full, call the GC (GCSP = SP, RETCELL = this NEW), which returns to it. Two executions: the word, then HP |
| `SETF i` | [o, v] → [o] | `mem[o+i] = v` (a literal's pairs) |
| `ENDK i` | [o] → [o] | `mem[o+i] = mem[o+i+1] = 0`: the keys end there. Two executions |
| `OVER` | [a, b] → [a, b, a] | |
| `JNEG l` | [a, b] → [a, b] | jump if `a` is negative (an object; an array is an address) |

- Restart safety: a first execution's write must leave the second's inputs unchanged (NEW writes HP last).
- ROM calls go through the jump table (`layout.json` `vectors`: gc, append, setx, getx, dyn, print). The assembly
  routines keep state in the `rt_base` cells, not frames (they nest: APPEND allocates, NEW collects).
- `o[k]` is IDXA / STOREX trapping to GETX / SETX; a key that is a heap string is first replaced by the object's key
  with its characters, if it has one (`okey`); a key the object doesn't have, stored, becomes the program's string with
  those characters if there is one (a walk of the string area up to `strend`, MCMP 3), so a key is the literal whenever
  one exists and it finds the same property as a literal key.

**The collector** (`lib_src.js` `gc`): Cheney copying between the semi-spaces. The roots: the globals (up to the count
at `init − 1`), the routines' value cells (S_V, S_K), and the stack from `sp0` to GCSP (the SP of the NEW, ALLOC or CAT
that found the heap full). A value is forwarded by its tag range: an object (a root may point *into* its chunk: a SCANI
cursor), a string, an array (copied with its elements inline, whatever its data block was); anything else that only
looks like one (a number in a tag range, a stale frame word) is left alone (alignment and the header are checked).
`fwdrange` finds the words that refer into from-space a line at a time (MCMP 1), so a root or an element that is a
number costs nothing; copies are MCPY. The scan follows an object's keys (a heap string key moves too) and values up
to its first free pair, and its link if all three are used, and an array's elements up to its length. HP and GCLIM
are offsets from `heap_lo`; GCLIM is the current space's offset, so zeroed RAM is space A and needs no setup. Cost is
per live block, nothing per dead one.

### 3.7 The font CPU (removed; last at commit `181cbb7`)

A GSUB CPU ran 32 micro-cycles per shaping while Chrome shaped the machine state as a line of text, and CSS serviced
its traps (misses, write-backs, MUL / DIV / MOD / SHL13, output): `uarch.py` / `uarch4.py` modelled it, `cpu4.py`,
`cpugen.py`, `otl.py` and `fvm_build.py` wrote the font, `gen_fvm4.py` its page, L4 checked the model and
`machine/hbtest.py` the font in uharfbuzz. It was 2.8–7.3× slower than the CSS CPU (BENCHMARKS §12); ENGINE_NOTES
25–33 are what it relied on.

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
| L1 | `make l1` | `cc_ref` compile + 20-bit simulator, strict: the stack must never go below its start and be back at HALT | Node output |
| L2 | `make l2` | the DSL in Python level by level, with the page's specialised variants (`SPEC=1`; `make l2-generic` unspecialised) | the reference: parser state, tables, every word and label |
| L3 | `make l3`, `make fuzz-l3` | the generated CSS compiler in Chrome (`build/suite_css.xhtml`, programs written into the latch cells) | the reference, word for word; `suite_err` must be rejected (any nonzero error) |
| C1 | `make c1` | `csssim.py`, the CSS CPU pass by pass, runs every compiled image | Node output, cc_ref's steps |
| C2 | `make c2` | a CPU-only page per program under 1,500 steps (`tests/csscpu_pages.py`) runs to HALT in Chrome | Node output on the grid, cc_ref's steps |
| L5 | `make l5` / `l5-smoke` | the real page: type, Run, read the console | Node output on the 8 × 16 grid |

- `make test` = oracle, L1, quick fuzz, L2, C1. `tests/suite/` has 120 programs (each must fit the editor, or
  `suite_ref.py` fails it), `tests/suite_err/` 46; `tests/programs/` has the demos t1–t4.
- **Differential tests** (`tests/fuzz/fuzz.py`; `make test` runs a quick fixed-seed set, `make fuzz` the full one,
  `make fuzz-l3` 300 of them through L3 in Chrome). Node is the oracle; each program goes through L1, L1 on the
  page's padded text when it fits the editor, and optionally L2 (`--l2`, on every program, rejected ones too) and C1
  (`--c1`). Sources: `fmt`, every suite program in 11 layouts that must print the same (no semicolons, comments
  between all tokens, tabs, CRLF, one line, one token per line, …); `gen`, random programs from `progen.py`, typed
  across the whole language and rendered twice from one tree, for us and for Node with the machine's integer
  semantics spelled out (20-bit wrap, truncating division, x / 0 = x % 0 = 0), staying inside the documented
  language so any difference is a bug; `mut`, suite programs with token edits, where Node's syntax errors must be
  rejected and L2 must agree (output differences are listed, not failures: a mutant can leave the language unseen).
  The oracle flags printed values our machine can't produce (objects, arrays, `null`, `undefined`, non-integers).
  Failures are shrunk into `build/fuzz/`; `tests/fuzz/show.py` replays one, `fuzz.py gen --k N` regenerates one.
- L5 runs only programs under 1,500 steps (`tests/suite_ui.py`). Harnesses detect HALT by the page's `--isHALT`
  flag, not a trap-kind index (that moves when opcodes are added).

---

## 6. Build

```
make page   # compiler/lib.json (if lib_src.js changed) -> build/ccimg.json -> build/js_in_css.xhtml
make dist   # copy it to dist/
```

- Reproducible (the Makefile pins `PYTHONHASHSEED` and `SOURCE_DATE_EPOCH`). The image (`mkimage.py tests/fizz.js`)
  supplies the ROM and the editor's initial program.
- `gen_css.py`: `UI=1` builds the product page; `UIL` / `UIP` / `UIT` set lines, columns, tokens; `SHORT=0` keeps
  the compiler's readable property names; `K` the levels per pass (32); `MEMGROUP=n` the RAM group size. Without
  `UI=1` it builds a CPU-only page for a RAM image holding the program (HTML: name it `.html`).
