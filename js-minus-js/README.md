# JavaScript, compiled and run by a stylesheet

`dist/js_in_css.xhtml` is one static XHTML page, and no script runs on it. You type a JavaScript program into its
editor and press Run. The program then goes through four stages:

1. **CSS reads the text back.** A variable-font axis copies characters into glyph widths, and CSS measures them.
2. **CSS compiles it.** One nested element per character lexes, and one per token parses and generates bytecode.
3. **CSS runs it.** Each layout pass executes up to 32 instructions as a chain of nested elements, out of a cache of
   RAM held in custom properties. (Until 2026-10-19 a GSUB "CPU" font ran it while Chrome shaped text; its code last
   exists at commit `181cbb7`.)
4. **The output appears.** It shows in an 8 × 16 console.

It works in Chrome only, and has been tested only on headless Chromium 153.

**Status (2026-10-19).**

- Every test level passes: 120 programs checked against Node's output and 46 the compiler must reject, plus
  differential tests that check thousands of generated, reformatted and mutated programs against Node (`make fuzz`).
  The CPU's checks: C1 (its model, every program) and C2 (a CPU-only page per program, 111 under 1,500 steps).
- On the page, FizzBuzz 1–15 compiles in about 2.4 s from Run (including the 1.2 s readback sweep), runs in about
  1.5 s, and halts about 3.9 s after Run; the font CPU took 10.5 s. On CPU-only pages the CSS CPU is 2.8–7.3× faster
  than the font CPU (FizzBuzz 1.0 s against 5.7 s from load).
- Numbers: [docs/BENCHMARKS.md](docs/BENCHMARKS.md). How it works: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start

```
npm install                       # playwright-core + @sparticuz/chromium (Linux x64), for the harnesses only
pip install -r requirements.txt   # fontTools, brotli (the readback font)
make page                         # -> build/js_in_css.xhtml (about 40 s; reproducible)
make test                         # fast tests, no browser (about 10 s)
make fuzz                         # differential tests against Node, no browser (about 1.5 min)
make l3                           # the CSS compiler in Chrome (about 40 s)
make c2                           # the CSS CPU on CPU-only pages (about 30 s)
make l5-smoke                     # the real page, typed like a user (about 30 s)
```

Open `dist/js_in_css.xhtml` (or `build/js_in_css.xhtml`) in Chrome. Elsewhere than Linux x64, set
`CHROME=/path/to/chrome` for the harnesses. Toolchain: Python 3.12+, fontTools 4.65+ (the readback font), Node 22+;
the page needs CSS `if()`, `sibling-index()`, anchor positioning and view timelines.

## The language

- **Declarations**: `var`, `let`, `const`, including `var a = 1, b = 2;`. `let` / `const` are block-scoped (a `{ }`
  block, an `if` / `else` / loop body, a `for (let ...)` header) and shadow outer names; `var` is function-scoped.
  Assigning to a `const` (`=`, `op=`, `++`, `--`) or declaring one without `=` is a compile error; its array elements
  can still be assigned. All of this is compile time only.
- **Functions**: top-level `function` declarations with parameters, locals, recursion, calls before the definition,
  and `return` with or without a value. A call passes exactly as many arguments as the function has parameters.
- **Control flow**: `if` / `else` / `else if`, `while`, `do … while`, `for (;;)` (any part may be empty), `switch`
  with `case` / `default`, `break`, `continue`. Bodies may be a block or a single statement; a dangling `else` binds
  as in JavaScript. `switch` compares with `===` in order; a `case` value can be any expression, `default` can stand
  anywhere, and bodies fall through until `break`.
- **Values**: integers, `true` / `false`, `null`, strings in `"..."` or `'...'` with escapes `\n \t \r \\ \" \'`,
  number array literals (`[1, -2, 3]`) with `.length`, and objects.
- **Objects**:
  - Literals `{a: 1, "b c": 2, 3: x, d: {e: 4}}`: identifier, string or number keys, values of any type nested to any
    depth, `{}`, a trailing comma.
  - Reads and writes by name or value: `o.a`, `o.d.e`, `o["b c"]`, `o[3]`, `o[k]`, `a[i].x`, `f().y`. `o.a`, `o["a"]`
    and `o[k]` with `k = "a"` are the same property; `o[1]` is not `o["1"]`.
  - Assignment statements: `o.x = e`, `o.x op= e`, `o.x++`, `o[k] = e`, `o.a.b[i] += 1`. A new key grows the object
    without limit.
  - Objects are references (`q = p` shares, `p === q` compares identity); they can be passed, returned and stored in
    arrays and objects.
  - `x[k]` works on arrays wherever they come from (a parameter, a property).
  - A copying garbage collector reclaims memory when the heap is full.
- **Operators**: `+ - * / %`, `< > <= >= == != === !==`, `!`, unary `-`; `&&` / `||` short-circuit and return an
  operand (`0 || 7` is `7`); `c ? a : b`, nested either way.
- **Assignment**: `=`, `+= -= *= /= %=` and `++ --` (also on `a[i]`) as statements; `x++ x-- ++x --x` also inside
  expressions (`a[i++]`, `while (n--)`).
- **Output**: `console.log(a, b, ...)` and `putc(code)`.
- **Comments**: `//` and `/* */`.
- **Strings are interned**: equal literals are one value, so `===` compares them by content.
- **Semicolons**: optional where JavaScript inserts them. A newline after a complete statement ends it unless it is
  inside `( [`, a call or a `for (…)` header, or the next line continues it (starts with `.` `[` `(` `?` `:` `,` or a
  binary operator; `++x` on a new line is a new statement). After `return` a newline always ends the statement. A `}`
  also ends one (`{ x++ }`).

### How values print

- A string is a tagged pointer (its address minus 2^18), so `console.log` tells it from a number at run time. Each
  argument is one PRINT instruction, which writes up to 4 console cells per execution and repeats until it is done.
- The compiler tracks types statically (boolean, string, number, unknown; from comparisons and `!`, literals and
  arithmetic, a variable's last assignment, a function's returns) so that booleans print as `true` / `false`:
  `console.log(1 < 2)` prints `true`. Only 0 / 1 depend on the static type; strings and numbers are told apart at
  run time.
- `+` at the top level of a `console.log` argument joins strings (`"n = " + n`, `1 + n + "x"`). Strings can't be
  built anywhere else: `var s = "a" + "b"` is a compile error.

### How objects work

An object is an 8-word heap chunk (three key/value pairs and an overflow link). `o.x` is two instructions whose key is
the string's interned address; allocation is a pointer bump; a copying collector in ROM runs when the heap is full and
costs time per live object. Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §3.5.

### Limits

- **Program size**: 24 lines of 64 columns, 400 tokens, 511 code words; 256 words of string data (including one tag
  word per string, and the name's length + 1 for every `.name` in the program) and 255 words of globals and arrays
  (an array literal takes one more, for its length); 64 labels (a `switch` takes 2, plus 2 per `case` and 1 for a
  `default`), 32 variables in scope, 16 functions; 16 distinct strings and property names (one interning table); blocks and expressions nest 8 deep (a long
  `else if` chain counts as one level).
- **Memory**: RAM is 16K words (`compiler/layout.json`); the stack has about 14,700 words, so recursion can go a few
  thousand calls deep. About 384 object chunks (3 pairs each) can be live at once; more halts with `out of memory`.
- **Numbers**: 20-bit integers (−524288 … 524287) that wrap; `/` truncates. −257792 … −257537 don't print as numbers
  (string tags). −480384 … −474241 look like object pointers to the GC, which would move them. Number keys must lie
  in −262143 … 262143.
- **Booleans** print as `1` / `0` when passed as a parameter or returned by a function called before its definition.
  A value of `c ? a : b`, `a && b` or `a || b` mixing a boolean and a number prints as a boolean if it is `0` or `1`.
- **`console.log`** prints each argument (and each piece of a `+` join) as soon as it is computed, where JavaScript
  computes them all first: `console.log("a", f())` prints what `f` prints after `a `. It is a statement, not a value,
  and takes no trailing comma.
- **Strings and numbers**: comparing a string with a number (`"s" < 5`, `"5" == 5`) compares the pointer, and so does
  `+` / `+=` on a string the compiler can't see is one (a parameter, a property).
- **Arrays**: `.length` is the literal's length (writing past the end doesn't change it); on an object or a string it
  reads a meaningless number. `++` / `--` inside an expression work on variables only.
- **Scoping**: redeclaring a `let` / `const` in the same scope isn't an error (the later wins), and use before
  declaration in an inner block (`let x = x + 1`) isn't caught.
- **`do … while`**: `if (a) do s; while (c); else …` is rejected (drop that `;`); `do s;; while (c)` is accepted.
- **Objects**: a missing property and `null` read as 0 and print `0`; `console.log(o)` prints the pointer; duplicate
  keys in a literal keep the first value; no properties on arrays or other non-objects; no prototypes, methods,
  `delete`, `in`, `for … in`, `Object.keys`; a property assignment is a statement, not an expression.
- **Not supported**: `undefined`, nested functions or closures, string comparison by content, expression statements
  starting with a literal or `(`.
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
| 30, 38–39 | malformed `console.log`, or used as a value | 61 | a statement emits too much code at once |
| 32–37 | malformed `if` / `while` / `for` / `function` header | 62 | program too long (more than 511 words) |
| 40 | missing `}` at end of input | 63 | strings can only be joined in `console.log` |
| 64 | assignment to a `const` | 65 | `const` without `=` |
| 66 | `while` expected after a `do` body | 67 | `:` without `?` |
| 68 | too many strings and property names (16) | 69 | property name expected after `.` |
| 70 | a property assignment must be a statement | 71 | object literal: key expected |
| 72 | `:` expected after an object key or `default` | 73 | `case` / `default` outside a `switch` |
| 74 | a `switch` body must start with `case` / `default` | 75 | a second `default` |
| 76 | a call passes a different number of arguments than another call or the definition | | |
| 99 | page only: no parser variant accepts this token here | | |

The page reports 99 where the reference compiler gives a more specific syntax-error code.
