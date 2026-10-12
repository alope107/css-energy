# Typed JavaScript, compiled by CSS, run by a font

`fontcpu/js_in_css.xhtml` is the page. It needs Chrome, and no script runs on it. Type a program, press Run,
and read the output in the console on the left. Edit clears the machine.

The page is XHTML because the compile chain is about 2,000 elements deep, and the HTML parser stops nesting
at 512.

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
  - literals;
  - arithmetic;
  - a variable's last assignment;
  - a function's returns.
- Booleans exist only statically. `console.log(1 < 2)` prints `true`. So does a variable or function the
  compiler knows holds one.
- Each print routine also checks the value at run time where that is free (for example, `printNum` looks for a
  string only among negative values), so a wrong static guess still prints a number or a string correctly.
- `+` at the top level of a `console.log` argument joins strings: `"n = " + n`, `s + "!"`, `1 + n + "x"`.
  - With operands of unknown type (parameters, for example), the runtime's `addc` either adds them or prints
    both pieces.
  - Strings cannot be built anywhere else: `var s = "a" + "b"` is a compile error.

### Limits

- **Program size**:
  - 24 lines of 64 columns, 400 tokens, 511 code words, 255 words of string data and 255 globals.
  - 64 labels, 32 variables in scope, 16 functions.
  - Blocks nest 8 deep. Expressions nest 8 operators or parentheses deep.
  - A long `else if` chain counts as one level of nesting.
- **Numbers**:
  - Integers are 20-bit (−524288 … 524287) and wrap.
  - `/` truncates: `7 / 2` is `3`.
  - Numbers from −257792 to −257537 do not print as numbers, because that range holds string tags.
- **Booleans**:
  - A boolean passed as a parameter prints as `1` / `0`.
  - So does a boolean returned by a function used before its definition.
  - A boolean used in arithmetic is a number (`true + 1` is `2`).
- **Not supported**:
  - objects, `.length`, `undefined` / `null`;
  - nested functions or closures, the ternary operator, `do` / `switch`;
  - `++` inside an expression;
  - string comparison by content.
- **Console**: 8 columns × 16 rows. Long lines wrap, and output past 16 rows wraps to the top.

### Errors

The status line names the error:

- undefined variable or function;
- `break` outside a loop, `return` outside a function;
- a missing or unexpected `}`;
- joining strings outside `console.log`;
- too many labels, variables or functions, or nesting too deep;
- otherwise, `syntax error (n)`.

An error code of 99 means a token appeared where no parser variant accepts it.

## Pipeline

1. **Editor readback** (`ui/ui_rb.py`; the font comes from `ui/mkfont2.py`).
   - A variable font axis copies the code of one column into a sentinel glyph's width.
   - Probes measure that width, and each line × column has a latch cell.
   - The scan is frame-locked, so it moves exactly one column per frame.
   - After Run, the scan does one more full sweep, then raises a flag. That flag shows the compiler.
2. **Character chain** (`ccpage5.py`): one element per slot, 24 lines × 65.
   - The lexer is specialized per character class, picked by the parent's class via container query.
   - Completed tokens go into token registers (view timelines).
   - The lexer emits a newline token after a line whose last token can end a statement.
3. **Token chain**: one element per token.
   - Parser variants are selected by `@container style(--vh: mode) and style(--tcq: token-code)`.
   - A variant only contains the code reachable from its mode and token.
   - Variants that change nothing share one pass-through rule.
   - The parser emits code words as fixed overlays named after their RAM cells.
4. **Font CPU** (`gen_fvm4.py` with `UI=1`).
   - It starts once the compiler reports done.
   - The runtime library (`lib_src.js`, built into the ROM by `libbuild.js`) holds `printNum`, `puts`,
     `printBool`, their newline-terminated forms, and `addc`.

The compiler exists in two forms that must agree:

- `cc_ref.py`: the reference, one character at a time, written the way the CSS computes.
- `cc_dsl.py`: the same step in a small expression DSL that compiles to CSS (`dsl.py`).

## Tests

`./runtests.sh` runs levels 1–4; `./runtests.sh ui` adds level 5. The browser levels need `playwright-core`
(`PW=` its path) and Chrome (`CHROME=` its path).

| Level | What runs | Checked against |
|---|---|---|
| oracle | `node suite_expect.js suite`: each `suite/*.js` under Node | writes the expected `*.out` |
| L1 | `suite_ref.py`: reference compiler and bytecode simulator (20-bit) | Node's output |
| L2 | `cmp_dsl.py`: the DSL evaluated in Python, level by level (`SPEC=1`: the page's specialized variants) | the reference: parser state, tables, every code word, label and data word |
| L3 | `suite_css.py` + `suite_css.js`: the generated CSS compiler in Chrome. One page; each program is written into its latch cells | the reference, word for word; `suite_err/*.js` must be rejected |
| L4 | `suite_machine.py`: the font CPU's model (`uarch4`, 4-word cache lines, traps) runs each compiled image | Node's output |
| L5 | `ui_seq.js`: the real page. Type each program, Run, read the console | Node's output on the 8 × 16 console grid |

`suite/` holds 89 programs. They cover each feature and the cases between them, for example:

- dangling `else`;
- `else if` chains, with and without braces;
- `break` in nested loops;
- short-circuit side effects;
- semicolon insertion, including where it must *not* happen.

`suite_err/` holds 14 programs the compiler must reject.
