# JavaScript, compiled by a stylesheet and run by a font

`dist/js_in_css.xhtml` is one static XHTML page, and no script runs on it. You type a JavaScript program into its
editor and press Run. The program then goes through four stages:

1. **CSS reads the text back.** A variable-font axis copies characters into glyph widths, and CSS measures them.
2. **CSS compiles it.** One nested element per character lexes, and one per token parses and generates bytecode.
3. **A font runs it.** A GSUB "CPU" executes the bytecode while Chrome shapes a line of text.
4. **The output appears.** It shows in an 8 × 16 console.

It works in Chrome only, and has been tested only on headless Chromium 153.

**Status (2026-10-11).**

- All five test levels pass. That includes 89 programs checked against Node's output and 14 programs the
  compiler must reject.
- On the page, compiling takes about 2–7 s from Run, including the readback sweep. The CPU runs about 50
  bytecode steps per second, so FizzBuzz 1–15 finishes in about 32 s.
- See [docs/BENCHMARKS.md](docs/BENCHMARKS.md) for the numbers and [docs/HISTORY.md](docs/HISTORY.md) for
  how the design got here.

## Quick start

```
npm install                       # playwright-core + @sparticuz/chromium (Chromium 153, Linux x64), for the test harnesses only
pip install -r requirements.txt   # fontTools, brotli (uharfbuzz optional)
make page                         # -> build/js_in_css.xhtml (about 45 s; reproducible)
make test                         # fast tests, no browser (about 10 s)
make test-browser                 # the CSS compiler in Chrome (about 3 min)
make test-ui-smoke                # the real page, typed like a user (about 2 min)
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
tests/      suite/ (89 programs + Node .out), suite_err/ (14 rejects), harnesses for levels L1-L5
tools/      browser.js (launcher), traps.py (cost of a program on the CPU), vsz.py / lp.py (variant sizes)
dist/       the built page
docs/       ARCHITECTURE.md, HISTORY.md, BENCHMARKS.md, ENGINE_NOTES.md
archive/    superseded generators, spikes, and raw result logs (paths inside are stale; reference only)
AGENTS.md   instructions for coding agents (CLAUDE.md imports it)
```

## The language

- **Declarations**: `var`, `let`, `const`, including `var a = 1, b = 2;`. `let` and `const` behave like `var`.
- **Functions**: top-level `function` declarations. They support parameters, locals, recursion, calls before
  the definition, and `return` with or without a value.
- **Control flow**: `if` / `else` / `else if`, `while`, `for (;;)` (any part may be empty), `break`, `continue`.
  Bodies may be a block or a single statement, and a dangling `else` binds as in JavaScript.
- **Values**: integers, `true` / `false`, strings in `"..."` or `'...'` with escapes `\n \t \r \\ \" \'`, and
  number array literals (`[1, -2, 3]`).
- **Operators**:
  - `+ - * / %`, comparisons `< > <= >= == != === !==`, `!` and unary `-`.
  - `&&` and `||` short-circuit and return an operand's value, as in JavaScript (`0 || 7` is `7`).
- **Assignment**: `=`, `+= -= *= /= %=` (also on `a[i]`), and `x++ x-- ++x --x` as statements.
- **Output**: `console.log(a, b, ...)` and `putc(code)`.
- **Comments**: `//` and `/* */`.
- **Semicolons**: optional where JavaScript inserts them. A newline after a complete statement ends it, unless
  the statement is still inside `( [` or a call. A `}` also ends one (`{ x++ }`).

### How values print

- A string is a tagged pointer: its address minus 2^18. `console.log` can tell it from a number at run time.
- The compiler also tracks each value's type statically and calls a matching print routine. The tracked types
  are boolean, string, number and unknown, and they come from:
  - comparisons and `!`;
  - literals and arithmetic;
  - a variable's last assignment;
  - a function's returns.
- `console.log(1 < 2)` prints `true`. So does a variable or a function the compiler knows holds a boolean.
- Each print routine also checks the value at run time where that's cheap, so a wrong static guess still
  prints a number or a string correctly.
- `+` at the top level of a `console.log` argument joins strings: `"n = " + n`, `s + "!"`, `1 + n + "x"`.
  Strings can't be built anywhere else: `var s = "a" + "b"` is a compile error.

### Limits

- **Program size**:
  - 24 lines of 64 columns, 400 tokens, 511 code words.
  - 256 words of string data, including one tag word per string, and 255 words of globals and arrays.
  - 64 labels, 32 variables in scope, 16 functions.
  - Blocks nest 8 deep. Expressions nest 8 operators or parentheses deep.
  - A long `else if` chain counts as one level of nesting.
- **Numbers**:
  - Integers are 20-bit (−524288 … 524287) and wrap.
  - `/` truncates: `7 / 2` is `3`.
  - Numbers from −257792 to −257537 don't print as numbers, because that range holds string tags.
- **Booleans**:
  - A boolean passed as a parameter prints as `1` / `0`.
  - So does a boolean returned by a function called before its definition.
- **Not supported**:
  - objects, `.length`, `undefined` / `null`;
  - nested functions or closures, the ternary operator, `do` / `switch`;
  - `++` inside an expression;
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
| 99 | page only: no parser variant accepts this token here | | |

The page reports 99 where the reference compiler gives a more specific syntax-error code.

## Project rules

- **No script on the pages.** Harness scripts are fine.
- **Chrome only** is fine.
- **Speed over size.** Speed means both compile speed and execution speed; payload size doesn't matter.
- **Compile at run time, in CSS.** Building the compiled program into the page at build time doesn't count.
