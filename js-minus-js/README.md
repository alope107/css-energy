# JavaScript, compiled by a stylesheet and run by a font

`dist/js_in_css.xhtml` is one static XHTML page, and no script runs on it. You type a JavaScript program into its
editor and press Run. The program then goes through four stages:

1. **CSS reads the text back.** A variable-font axis copies characters into glyph widths, and CSS measures them.
2. **CSS compiles it.** One nested element per character lexes, and one per token parses and generates bytecode.
3. **A font runs it.** A GSUB "CPU" executes the bytecode while Chrome shapes a line of text.
4. **The output appears.** It shows in an 8 × 16 console.

It works in Chrome only, and has been tested only on headless Chromium 153.

**Status (2026-10-17).**

- All five test levels pass. That includes 114 programs checked against Node's output and 38 programs the
  compiler must reject.
- On the page, compiling takes about 1.7–5.8 s from Run (median 2.2 s), including the 1.2 s readback sweep. FizzBuzz 1–15 then runs
  in about 8.3 s and halts about 10.8 s after Run (headless Chromium 153 on the Ubuntu mini PC, 2026-10-17); it was
  18.3 s on the same machine before printing
  moved into the machine (one trap per output chunk instead of one per character).
- Objects and garbage collection (branch `js-objects`): FizzBuzz runs as fast as before (Run → HALT within 1%), and
  compiles about 4% slower; object programs run at the suite's usual 4–5 steps per shaping (BENCHMARKS.md §10).
- See [docs/BENCHMARKS.md](docs/BENCHMARKS.md) for the numbers and [docs/HISTORY.md](docs/HISTORY.md) for
  how the design got here.

## Quick start

```
npm install                       # playwright-core + @sparticuz/chromium (Chromium 153, Linux x64), for the test harnesses only
pip install -r requirements.txt   # fontTools, brotli (uharfbuzz optional)
make page                         # -> build/js_in_css.xhtml (about 25 s; reproducible)
make test                         # fast tests, no browser (about 5 s)
make test-browser                 # the CSS compiler in Chrome (about 1.5 min)
make test-ui-smoke                # the real page, typed like a user (about 1 min)
```

- To open the page, load `dist/js_in_css.xhtml` (or `build/js_in_css.xhtml`) in Chrome.
- Elsewhere than Linux x64, set `CHROME=/path/to/chrome` for the harnesses.

## Repository

```
compiler/   the compiler: cc_ref.py (reference) + cc_dsl.py/dsl.py (the same step as CSS) + ccpage5.py (the page's
            compile chain); the runtime library lib_src.js -> lib.json (libbuild.js runs jsc.js under Node)
machine/    the font CPU: uarch*.py (model), cpu4.py/cpugen.py/otl.py (GSUB), fvm_build.py (font),
            gen_fvm4.py (the page), memtree.py (RAM); browser harnesses (ui_seq.js, fullrun.js, trace.js, ...)
readback/   editor text readback: ui_rb.py, mkfont2.py (AsciiProbe font)
tests/      suite/ (114 programs + Node .out), suite_err/ (38 rejects), harnesses for levels L1-L5
tools/      browser.js (launcher), traps.py (cost of a program on the CPU), vsz.py / lp.py (variant sizes)
dist/       the built page
docs/       ARCHITECTURE.md, HISTORY.md, BENCHMARKS.md, ENGINE_NOTES.md
archive/    raw result logs; README.md indexes the removed superseded code (restore it from git)
AGENTS.md   instructions for coding agents (CLAUDE.md imports it)
```

## The language

- **Declarations**: `var`, `let`, `const`, including `var a = 1, b = 2;`.
  - `let` and `const` are block-scoped: one declared in a `{ }` block, an `if` / `else` / loop body or a `for (let ...)`
    header is gone when that ends, and shadows an outer name of the same name until then. `var` is function-scoped.
  - Assigning to a `const` (`=`, `op=`, `++`, `--`) is a compile error, and so is a `const` without `=`. The elements
    of a `const` array can still be assigned (`a[0] = 1`).
  - All of this is resolved at compile time: the code is the same as for `var`.
- **Functions**: top-level `function` declarations. They support parameters, locals, recursion, calls before
  the definition, and `return` with or without a value.
- **Control flow**: `if` / `else` / `else if`, `while`, `do … while`, `for (;;)` (any part may be empty), `break`,
  `continue`, `switch` with `case` / `default`.
  - `switch` compares with `===` (so strings by content, as they are interned), in order; a `case` value can be
    any expression, `default` can stand anywhere, and bodies fall through until `break`.
  Bodies may be a block or a single statement, and a dangling `else` binds as in JavaScript.
- **Values**: integers, `true` / `false`, `null`, strings in `"..."` or `'...'` with escapes `\n \t \r \\ \" \'`,
  number array literals (`[1, -2, 3]`) with `.length`, and objects.
- **Objects**:
  - Literals `{a: 1, "b c": 2, 3: x, d: {e: 4}}`, with identifier, string or number keys; values of any type, nested to
    any depth; `{}`; a trailing comma.
  - Reads and writes by name or by any value: `o.a`, `o.d.e`, `o["b c"]`, `o[3]`, `o[k]` (k a string or a number),
    `a[i].x`, `f().y`. `o.a`, `o["a"]` and `o[k]` with `k = "a"` are the same property, and `o[1]` is not `o["1"]`.
  - Assignment as a statement: `o.x = e`, `o.x op= e`, `o.x++`, `o[k] = e`, `o.a.b[i] += 1`. A new key is added
    to the object, which grows without limit.
  - Objects are references: `q = p` shares one object, `p === q` compares identity. They can be passed to and
    returned from functions and stored in arrays and other objects (lists, trees).
  - `x[k]` works on arrays too, wherever the array comes from (a parameter, a property). A variable assigned an array
    literal is indexed directly, as before.
  - Memory is reclaimed by a copying garbage collector when the heap is full.
- **Operators**:
  - `+ - * / %`, comparisons `< > <= >= == != === !==`, `!` and unary `-`.
  - `&&` and `||` short-circuit and return an operand's value, as in JavaScript (`0 || 7` is `7`).
  - `c ? a : b`, nested either way (`x < 0 ? -1 : x > 0 ? 1 : 0`).
- **Assignment**: `=`, `+= -= *= /= %=` and `++ --` (also on `a[i]`) as statements; `x++ x-- ++x --x` also inside
  expressions (`a[i++]`, `while (n--)`).
- **Output**: `console.log(a, b, ...)` and `putc(code)`.
- **Comments**: `//` and `/* */`.
- **Strings are interned**: equal string literals are one value, so `===` compares them by content.
- **Semicolons**: optional where JavaScript inserts them. A newline after a complete statement ends it, unless
  the statement is still inside `( [` or a call. A `}` also ends one (`{ x++ }`).

### How values print

- A string is a tagged pointer: its address minus 2^18. `console.log` can tell it from a number at run time.
- Printing is one machine instruction per argument (the PRINT family), serviced by the page's CSS: up to 4
  console cells per shaping, so a short number or string costs one shaping instead of one per character.
- The compiler also tracks each value's type statically, so that booleans print as `true` / `false`. The tracked
  types are boolean, string, number and unknown, and they come from:
  - comparisons and `!`;
  - literals and arithmetic;
  - a variable's last assignment;
  - a function's returns.
- `console.log(1 < 2)` prints `true`. So does a variable or a function the compiler knows holds a boolean.
- The machine checks the value at run time, so a wrong static guess still prints a number or a string correctly
  (only 0 / 1 depend on the static type: boolean or number).
- `+` at the top level of a `console.log` argument joins strings: `"n = " + n`, `s + "!"`, `1 + n + "x"`.
  Strings can't be built anywhere else: `var s = "a" + "b"` is a compile error.

### How objects work

- An object is an 8-word chunk in the heap: three key/value pairs and a link to an overflow chunk, so one with more
  than three keys is a chain of chunks. Its value is a tagged pointer (its address minus 491,520, so the machine's
  15-bit address registers untag it for free).
- `o.x` is two machine instructions: `SCANI x` probes one key per execution (and runs again until it finds the key, the
  keys end, or it follows a link), and `LDF 1` loads the value next to the key. `o.x = e` is `SCANI x`, then `e`,
  then `PUTV x`. The key is a compile-time constant: the string's interned address.
- `o[k]` and `x[k] = v` call routines in the ROM that tell an array (an address) from an object (a negative value).
- `{a: 1, b: 2}` is `NEW`, the pairs stored in place (`SETF`), and `ENDK` to end the keys. Allocation is a pointer
  bump.
- When the heap (two semi-spaces of 3,072 words, 384 chunks each) is full, `NEW` calls the collector in the ROM: a
  copying (Cheney) collector whose roots are the globals, arrays and the whole stack. It costs time in proportion
  to the live objects, not to the garbage.
- The machine and its instructions: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §3.5.

### Limits

- **Program size**:
  - 24 lines of 64 columns, 400 tokens, 511 code words.
  - 256 words of string data, including one tag word per string, and 255 words of globals and arrays.
  - RAM is 16K words (`compiler/layout.json`); the stack has about 14,700 words, so recursion can go a few thousand
    calls deep. Before 2026-10-13 RAM was 3K words and the stack 1,408.
  - 64 labels, 32 variables in scope, 16 functions. A `switch` takes 2 labels, plus 2 per `case` and 1 for a
    `default`.
  - Each array literal takes one word of the 255 for its length, besides its elements.
  - 16 distinct strings and property names (string literals and keys share one interning table). A property name
    is stored in the string area too.
  - Objects: about 384 chunks live at once (a chunk holds 3 pairs). A program that keeps more halts with
    `out of memory`.
  - Blocks nest 8 deep. Expressions nest 8 operators or parentheses deep.
  - A long `else if` chain counts as one level of nesting.
- **Numbers**:
  - Integers are 20-bit (−524288 … 524287) and wrap.
  - `/` truncates: `7 / 2` is `3`.
  - Numbers from −257792 to −257537 don't print as numbers, because that range holds string tags.
  - Numbers from −480384 to −474241 are object pointers to the garbage collector, which would move them. Number keys
    must lie between −262143 and 262143.
- **Booleans**:
  - A boolean passed as a parameter prints as `1` / `0`.
  - So does a boolean returned by a function called before its definition.
  - So does a boolean from `c ? a : b` whose other branch is not a boolean (`c ? false : 7`).
- **Arrays**: `.length` is the literal's length; writing past the end (`x[k] = v`) does not change it. On an
  object or a string, `.length` reads a meaningless number (it is not a property read).
- **`++` / `--`**: inside an expression only on a variable (`a[i]++` and `o.x++` are statements only).
- **Scoping**: redeclaring a `let` / `const` in the same scope is not an error (the later one wins), and using one
  before its declaration in an inner block (`let x = x + 1`) is not caught.
- **`do … while`**: `if (a) do s; while (c); else …` is rejected (write it without that `;`), and
  `do s;; while (c)` is accepted.
- **Objects**:
  - A missing property reads as 0 (JavaScript: `undefined`), and `null` is 0, so both print as `0`.
  - `console.log(o)` prints a number (the pointer), not the object.
  - Duplicate keys in one literal keep the first value. Properties of arrays and of other non-objects are not
    supported.
  - No prototypes, methods, `delete`, `in`, `for … in`, `Object.keys`.
  - An assignment to a property is a statement, not an expression (`a = o.x = 1` is an error).
- **Not supported**:
  - `undefined`;
  - nested functions or closures;
  - string comparison by content.
- **Console**: 8 columns × 16 rows. Long lines wrap, and output past 16 rows wraps to the top.

### Error codes

The status line shows a message for the common errors and `syntax error (n)` for the rest.

| Code | Meaning | Code | Meaning |
|---|---|---|---|
| 3 | expected an operand | 41 | function inside a function or block |
| 4–7 | undefined variable | 42–43 | array literal: numbers only / `,` or `]` |
| 8 | a statement can't start with this token | 44–46 | unexpected `,` `]` `)` |
| 9–10 | name expected after `var` / `++` | 47 | unbalanced `(` |
| 20 | too many labels (64) | 48 | unexpected token after an operand |
| 21 | blocks nested too deeply (8) | 49 | `=` expected after `a[i]` |
| 22 | expression too deep (8) | 50–53 | statement or `for` header ended in the wrong place |
| 23 | too many functions (16) | 54–55 | unexpected `}` |
| 24 | too many variables (32) | 56 | `break` / `continue` outside a loop |
| 25 | too many globals / array elements | 57 | `return` outside a function |
| 26 | too much string data | 60 | undefined function |
| 30, 38–39 | malformed `console.log` | 61 | a statement emits too much code at once |
| 32–37 | malformed `if` / `while` / `for` / `function` header | 62 | program too long (more than 511 words) |
| 40 | missing `}` at end of input | 63 | strings can only be joined in `console.log` |
| 64 | assignment to a `const` | 65 | `const` without `=` |
| 66 | `while` expected after a `do` body | 67 | `:` without `?` |
| 68 | too many strings and property names (16) | 69 | property name expected after `.` |
| 70 | a property assignment must be a statement | 71 | object literal: key expected |
| 72 | `:` expected after an object key or `default` | 73 | `case` / `default` outside a `switch` |
| 74 | a `switch` body must start with `case` / `default` | 75 | a second `default` |
| 99 | page only: no parser variant accepts this token here | | |

The page reports 99 where the reference compiler gives a more specific syntax-error code.

## Project rules

- **No script on the pages.** Harness scripts are fine.
- **Chrome only** is fine.
- **Speed over size.** Speed means both compile speed and execution speed; payload size doesn't matter.
- **Compile at run time, in CSS.** Building the compiled program into the page at build time doesn't count.
