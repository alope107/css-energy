# JavaScript, compiled and run by a stylesheet

`dist/js_in_css.xhtml` is one static XHTML page, and no script runs on it. You type a JavaScript program into its
editor (or pick one of ten samples) and press Run. The program then goes through four stages:

1. **CSS reads the text back.** A variable-font axis copies characters into glyph widths, and CSS measures them.
2. **CSS compiles it.** One nested element per character lexes, and one per token parses and generates register code.
3. **CSS runs it.** Each layout pass executes up to 32 instructions of a register machine as a chain of nested
   elements, out of a cache of RAM held in custom properties. Strings, arrays and objects have instructions of their
   own: `+` builds a string in CSS, `a[i]` and `o.x` read and write in place, a trap calls the runtime library in ROM
   for the rest. (Until 2026-10-21 it was a stack machine, last at commit `212175a`; until 2026-10-19 a GSUB "CPU"
   font ran it while Chrome shaped text, last at `181cbb7`.)
4. **The output appears.** It shows in a 9 × 16 console.

It works in Chrome only, and has been tested only on headless Chromium 153.

**Status (2026-10-20).**

- Every test level passes: 135 programs checked against Node's output and 47 the compiler must reject, plus
  differential tests that check thousands of generated, reformatted and mutated programs against Node (`make fuzz`).
  The CPU's checks: C1 (its model, every program) and C2 (a CPU-only page per program, 111 under 1,500 steps).
- Strings and arrays are values: strings are built anywhere and compared by their characters, arrays grow, both have
  their common methods, and `console.log` prints arrays and objects as Node does.
- On the page, FizzBuzz 1–15 compiles in about 2.45 s from Run (including the 1.2 s readback sweep), runs in about
  1.2 s, and halts about 3.6 s after Run. On CPU-only pages FizzBuzz halts ~0.95 s after load.
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
  Assigning to a `const` (`=`, `op=`, `++`, `--`), declaring one without `=`, and a `let` / `const` of a name its scope
  already declares are compile errors; a `const` array's elements can still be assigned. All of this is compile time
  only.
- **Functions**: top-level `function` declarations with parameters, locals, recursion, calls before the definition,
  and `return` with or without a value. A call passes exactly as many arguments as the function has parameters.
- **Control flow**: `if` / `else` / `else if`, `while`, `do … while`, `for (;;)` (any part may be empty), `switch`
  with `case` / `default`, `break`, `continue`. Bodies may be a block or a single statement; a dangling `else` binds
  as in JavaScript. `switch` compares with `===` in order; a `case` value can be any expression, `default` can stand
  anywhere, and bodies fall through until `break`.
- **Values**: integers, `true` / `false`, `null`, strings, arrays and objects. `0` and `""` are false, as are `false`
  and `null`.
- **Samples**: the chips above the editor switch between your program and ten samples (`samples/`: FizzBuzz, a
  sieve, recursive Fibonacci, a diamond of stars, Hanoi, insertion sort and binary search, a binary search tree,
  a Caesar cipher, Collatz, a bank account with `switch`). Each editor keeps its edits.
- **Strings**:
  - Literals in `"..."` or `'...'` with escapes `\n \t \r \\ \" \'`.
  - Built anywhere with `+` and `+=`: `"n = " + n`, `s += c`, `1 + 2 + "x"` (`"3x"`). A number joins as its decimal
    digits, a boolean as `true` / `false`, an array as its elements joined by commas, an object as `[object Object]`.
  - Compared by their characters: `===`, `!==`, `==`, `!=`; `<`, `>`, `<=`, `>=` by character codes, as in
    JavaScript. `switch` on a string works.
  - `s.length`, `s[i]` (a one-character string), and the methods `charAt`, `charCodeAt`, `indexOf`, `lastIndexOf`,
    `includes`, `startsWith`, `endsWith`, `slice` (negative indexes count from the end), `substring`, `toUpperCase`,
    `toLowerCase`, `trim`, `split` (`""` splits into characters), `repeat`, `concat`, `toString`; `String(x)`,
    `String.fromCharCode(c)`, `parseInt(s)` and `Number(s)`.
  - Strings are values: they can be passed, returned, stored in arrays and objects, and used as object keys, also
    when built at run time (`count[word]++`).
- **Arrays**:
  - Literals of any values (`[1, "a", x + 1, [2, 3], {k: 4}]`, `[]`, a trailing comma); each evaluation makes a new
    array.
  - `a[i]` reads and writes, nested (`g[r][c] += 1`); writing at or past the end grows the array (a gap fills with 0);
    reading past the end gives 0. `a.length` follows the array.
  - The methods `push`, `pop`, `shift`, `unshift`, `indexOf`, `lastIndexOf`, `includes` (strings by their characters),
    `join` (default `","`), `slice`, `concat`, `reverse`, `fill`, `toString`.
  - Arrays are references (`b = a` shares, `a === b` compares identity), passed, returned and stored anywhere.
- **Objects**:
  - Literals `{a: 1, "b c": 2, 3: x, d: {e: 4}}`: identifier, string or number keys, values of any type nested to any
    depth, `{}`, a trailing comma.
  - Reads and writes by name or value: `o.a`, `o.d.e`, `o["b c"]`, `o[3]`, `o[k]`, `a[i].x`, `f().y`. `o.a`, `o["a"]`
    and `o[k]` with `k = "a"` (a literal or a string built at run time) are the same property; `o[1]` is not `o["1"]`.
  - Assignment statements: `o.x = e`, `o.x op= e`, `o.x++`, `o[k] = e`, `o.a.b[i] += 1`. A new key grows the object
    without limit.
  - Objects are references (`q = p` shares, `p === q` compares identity); they can be passed, returned and stored in
    arrays and objects.
- **Memory**: strings, arrays and objects live in a heap; a copying garbage collector reclaims what is unreachable when
  it is full.
- **Operators**: `+ - * / %`, `< > <= >= == != === !==`, `!`, unary `-`; `&&` / `||` short-circuit and return an
  operand (`0 || 7` is `7`, `"" || "x"` is `"x"`); `c ? a : b`, nested either way.
- **Assignment**: `=`, `+= -= *= /= %=` and `++ --` (also on `a[i]` and `o.x`) as statements; `x++ x-- ++x --x` also
  inside expressions (`a[i++]`, `while (n--)`).
- **Output**: `console.log(a, b, ...)` and `putc(code)`. An array or object prints as Node prints it on one line:
  `[ 1, 'a', [ 2 ] ]`, `{ k: 1, 'a b': [] }`, `[Array]` / `[Object]` below depth 2.
- **Comments**: `//` and `/* */`.
- **Semicolons**: optional where JavaScript inserts them. A newline after a complete statement ends it unless it is
  inside `( [`, a call or a `for (…)` header, or the next line continues it (starts with `.` `[` `(` `?` `:` `,` or a
  binary operator; `++x` on a new line is a new statement). After `return` a newline always ends the statement. A `}`
  also ends one (`{ x++ }`).

### How values work

- The machine has three-address instructions (`ADD x, a, b`) on globals, a function's frame slots and small
  constants; the compiler keeps an expression's values in the frame's temps past the locals, with no allocator.
- A string is a tagged pointer (its first character's address minus 2^18), an array its pointer word's address plus
  2^18, an object its chunk's address minus 15 · 2^15: the machine tells them from numbers at run time by range. A
  string is `[length][characters][0]`, in the program's string area (literals and property names, interned: equal
  literals are one string) or in the heap.
- `a[i]` is one instruction (GETX) for an array inside its length; `a[i] = v` likewise (SETX). Anything else (an
  object, a string, an index past the end) goes to a routine in ROM. `+` and the comparisons are one instruction
  (DADD, DLT, …) that computes numbers; `+` with a string builds the new string in CSS, one word per execution; arrays,
  objects and string comparisons go to ROM. Where the compiler knows both are numbers it emits the plain instruction.
- The compiler tracks types statically (boolean, string, number, unknown; from comparisons and `!`, literals and
  arithmetic, a variable's last assignment, a function's returns, a method's result) so that booleans print as
  `true` / `false`: `console.log(1 < 2)` prints `true`. Only 0 / 1 depend on the static type; strings, arrays,
  objects and numbers are told apart at run time.
- Each `console.log` argument is one PRINT instruction, which writes up to 4 console cells per execution and repeats
  until it is done; several share a layout pass when their cells fall in different RAM banks (the console's rows start
  one bank apart). A `+` chain with a string in it isn't built: its pieces (up to 4) are printed in turn (or, if a
  comparison, `&&` / `||` or `?:` follows, joined into one string first).

### How objects work

An object is an 8-word heap chunk (three key/value pairs and an overflow link). `o.x` is one instruction (GETP) whose
key is the string's interned address, probing one pair per execution; allocation is a pointer bump (NEW); a copying
collector in ROM runs when the heap is full. A key built at run time is first matched by its characters against the program's strings
(then the object's own keys), so it finds the same property as the literal. Details:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §3.6.

### Limits

- **Program size**: 24 lines of 64 columns, 400 tokens, 1,023 code words (511 instructions); 768 words of string data
  (the length + 2 for every string literal and every `.name` in the program) and 255 words of globals; 64 labels (a
  `switch` takes 2, plus 2 per `case` and 1 for a `default`), 32 variables in scope, 16 functions; 32 distinct strings
  and property names (one interning table; a method's name doesn't count when `(` follows it directly); blocks and
  expressions nest 8 deep (a long `else if` chain counts as one level), with at most 10 values pending in an expression
  and 24 counting the arguments of the calls under way; at most 4 unary operators in a row before a binary one
  (`!!!!x * y` is fine, `!!!!!x * y` isn't); an array literal of at most 127 elements.
- **Memory**: RAM is 16K words (`compiler/layout.json`); the stack has about 7,500 words, so recursion can go a few
  hundred to a thousand calls deep (a call takes its frame: the parameters, the locals and the expression's temps).
  The heap holds 3,072 words of live data: about 384 objects of up to 3 pairs, or strings (length + 3 words) and arrays
  (4 words + 1 per element), each rounded up to 8; more halts with `out of memory`.
- **Numbers**: 20-bit integers (−524288 … 524287) that wrap; `/` truncates. Numbers in −255744 … −239761 are strings to
  the machine, in −475280 … −469137 objects and in 278384 … 284527 arrays: they print as those, and the collector may
  change them. Number keys must lie in −262143 … 262143.
- **Booleans** are 0 / 1 at run time: they print as `1` / `0` when passed as a parameter, returned by a function called
  before its definition, or stored in an array or object (`[1 < 2]` prints `[ 1 ]`). A value of `c ? a : b`, `a && b`
  or `a || b` mixing a boolean and a number prints as a boolean if it is `0` or `1`.
- **`console.log`** prints each argument as soon as it is computed, where JavaScript computes them all first:
  `console.log("a", f())` prints what `f` prints after `a `. It is a statement, not a value, and takes no trailing
  comma. Node breaks an array of more than 6 elements, or an array or object wider than 72 characters, over several
  lines; the machine prints them on one line. Node lists an object's integer keys first in ascending order; the machine
  prints its number keys first in the order they were added.
- **No `undefined` or `NaN`**: where JavaScript gives one the machine gives 0 (`a[i]` past the end, a missing
  property, `charCodeAt` past the end, `parseInt` of a non-number). A string compared with a number: `==` / `!=`
  compare identity (`"5" == 5` is false), `<` `>` compare the string's leading integer.
- **Strings**: ASCII only; a string's characters can't be assigned (`s[0] = "x"` does nothing). A method is only called
  (`s.toUpperCase` without `()` reads a property, which strings don't have); methods take the argument counts listed
  in [the methods table](compiler/cc_ref.py) (`slice()`, `slice(a)`, `slice(a, b)`; `indexOf` has no start index).
  `parseInt`, `Number` and `String` are reserved names.
- **Arrays**: no `sort` (or any method taking a function), `new Array`, holes or `delete`. `++` / `--` inside an
  expression work on variables only.
- **Scoping**: a `var` after a `let` / `const` of the same name in the same scope isn't an error, and use before
  declaration in an inner block (`let x = x + 1`) isn't caught.
- **`do … while`**: `if (a) do s; while (c); else …` is rejected (drop that `;`); `do s;; while (c)` is accepted.
- **Objects**: a missing property and `null` read as 0 and print `0`; duplicate keys in a literal keep the first value;
  no properties on arrays, strings or other non-objects; no prototypes, methods, `delete`, `in`, `for … in`,
  `Object.keys`; a property assignment is a statement, not an expression.
- **Not supported**: `undefined`, `typeof`, nested functions or closures, template literals, expression statements
  starting with a literal or `(`.
- **Console**: 9 columns × 16 rows. Long lines wrap, and output past 16 rows wraps to the top.

### Error codes

The status line shows a message for the common errors and `syntax error (n)` for the rest.

| Code | Meaning | Code | Meaning |
|---|---|---|---|
| 3 | expected an operand | 41 | function inside a function or block |
| 4–7 | undefined variable | 78 | `let` / `const` of a name its scope already declares |
| 8 | a statement can't start with this token | 44–46 | unexpected `,` `]` `)` |
| 9–10 | name expected after `var` / `++` | 47 | unbalanced `(` |
| 20 | too many labels (64) | 48 | unexpected token after an operand |
| 21 | blocks nested too deeply (8) | | |
| 22 | expression too deep (8 operators, 10 values, 24 with pending arguments, 5 unary operators in a row, 127 array elements) | 50–53 | statement or `for` header ended in the wrong place |
| 23 | too many functions (16) | 54–55 | unexpected `}` |
| 24 | too many variables (32) | 56 | `break` / `continue` outside a loop |
| 25 | too many globals (255) | 57 | `return` outside a function |
| 26 | too much string data | 60 | undefined function |
| 30, 38–39 | malformed `console.log`, or used as a value | 61 | a token emits too much code at once (7 instructions) |
| 32–37 | malformed `if` / `while` / `for` / `function` header | 62 | program too long (more than 1,023 words) |
| 40 | missing `}` at end of input | 77 | a method called with a number of arguments it doesn't take |
| 64 | assignment to a `const` | 65 | `const` without `=` |
| 66 | `while` expected after a `do` body | 67 | `:` without `?` |
| 68 | too many strings and property names (32) | 69 | property name expected after `.` |
| 70 | a property assignment must be a statement | 71 | object literal: key expected |
| 72 | `:` expected after an object key or `default` | 73 | `case` / `default` outside a `switch` |
| 74 | a `switch` body must start with `case` / `default` | 75 | a second `default` |
| 76 | a call passes a different number of arguments than another call or the definition | | |
| 99 | page only: no parser variant accepts this token here | | |

The page reports 99 where the reference compiler gives a more specific syntax-error code.
