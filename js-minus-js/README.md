# JavaScript, compiled and run by a stylesheet

`dist/js_in_css.xhtml` is one static XHTML page, and no script runs on it. You type a JavaScript program into its
editor (or pick one of ten samples) and press Run. The program then goes through four stages:

1. **CSS reads the text back.** A variable-font axis copies characters into glyph widths, and CSS measures them.
2. **CSS compiles it.** One nested element per character lexes, and one per token parses and generates register code.
3. **CSS runs it.** Each layout pass executes up to 32 instructions of a register machine as a chain of nested
   elements, out of a cache of RAM held in custom properties. Strings, arrays and objects have instructions of their
   own: `+` builds a string in CSS, `a[i]` and `o.x` read and write in place, and the runtime library in ROM has
   instructions that copy, compare and allocate a cache line at a time; user code is fetched through a cache of its own. (Until 2026-10-21 it was a stack machine, last at commit `212175a`; until 2026-10-19 a GSUB "CPU"
   font ran it while Chrome shaped text, last at `181cbb7`.)
4. **The output appears.** It shows in a 9 × 16 console.

It works in Chrome only, and has been tested only on headless Chromium 153.

**Status (2026-10-22).**

- Every test level passes: 135 programs checked against Node's output and 47 the compiler must reject, the ten
  samples through the compiler in Chrome and on the page, plus differential tests that check thousands of generated,
  reformatted and mutated programs against Node (`make fuzz`). The CPU's checks: C1 (its model, every program) and C2
  (a CPU-only page per program, under 1,500 steps); all the programs as CPU-only pages, objects included.
- The machine is a register machine since 2026-10-21, with the runtime's work on memory as machine instructions and a
  code cache since 2026-10-22. On 25 programs on CPU-only pages it is 1.74× faster than the register machine before it
  and 1.53× than the stack machine with those instructions (geometric means; strings, arrays and objects up to 7.6×,
  compute as fast; BENCHMARKS §15), with compile time unchanged.
- On the page, FizzBuzz 1–15 compiles in about 2.3 s from Run (including the 1.2 s readback sweep) and halts about
  3.2 s after Run.
- `fetch(url)` and `read()` reach the network through a gateway that serves the page ([Network](#network)).
- Numbers: [docs/BENCHMARKS.md](docs/BENCHMARKS.md). How it works: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start

```
npm install                       # playwright-core + @sparticuz/chromium (Linux x64), for the harnesses only
pip install -r requirements.txt   # fontTools, brotli (the readback font)
make page                         # -> build/js_in_css.xhtml (about 7 s; reproducible)
make test                         # fast tests, no browser (about 5 s)
make fuzz                         # differential tests against Node, no browser (about 30 s)
make l3                           # the CSS compiler in Chrome (about 40 s)
make c2                           # the CSS CPU on CPU-only pages (about 30 s)
make l5-smoke                     # the real page, typed like a user (about 30 s)
```

Open `dist/js_in_css.xhtml` (or `build/js_in_css.xhtml`) in Chrome. Elsewhere than Linux x64, set
`CHROME=/path/to/chrome` for the harnesses. Toolchain: Python 3.12+, fontTools 4.65+ (the readback font), Node 22+;
the page needs CSS `if()`, `sibling-index()`, anchor positioning and view timelines.

## The language

Everything in the [learnxinyminutes JavaScript tutorial](https://learnxinyminutes.com/javascript/) compiles and prints
what Node prints (`tests/suite/` has it section by section, beside 160 other programs). In detail:

- **Values**: numbers (JavaScript's doubles), strings, `true` / `false`, `null`, `undefined`, `NaN`, `Infinity`,
  arrays, objects and functions. `typeof` names them; `false`, `null`, `undefined`, `NaN`, `0`, `-0` and `""` are
  falsy. `===` compares without conversion, `==` as JavaScript does (`"5" == 5`, `null == undefined`).
- **Numbers**: `+ - * / %` (`5 / 2` is `2.5`, `0.1 + 0.2` is `0.30000000000000004`), the bitwise operators
  `& | ^ ~ << >> >>>` on 32-bit integers, comparisons, literals like `1.5`, `2e-3`, `1e21`. Numbers print as Node
  prints them (the shortest digits that read back). `Math.abs floor ceil round trunc sign sqrt exp log sin cos tan
  pow min max random`, `Math.PI` / `E` / `LN2` / `LN10` / `LOG2E` / `LOG10E` / `SQRT2` / `SQRT1_2`;
  `parseInt`, `parseFloat`, `Number`, `String`.
- **Declarations**: `var`, `let`, `const` (`var a = 1, b = 2;`). `let` / `const` are block-scoped and shadow outer
  names; `var` is function-scoped and hoisted (read before its declaration runs, it is `undefined`); function
  declarations are hoisted. Assigning to an undeclared name makes a global (`window.x` / `globalThis.x` are the same
  global). Assigning to a `const` and redeclaring a `let` are compile errors.
- **Functions**: declarations, function expressions (anonymous, named, immediately invoked), arrow functions
  (`(a, b) => { ... }`, `x => x * 2`, `() => 3`, `a => b => a + b`), nested two deep, with closures: an inner function
  keeps its outer function's variables after that returns. Functions are values: passed, returned, stored, printed
  (`[Function: f]`), called with any number of arguments (missing ones are `undefined`).
- **`this`**: a method call (`o.f()`, `o[k]()`) passes the object; `f.call(t, ...)`, `f.apply(t, array)` and
  `f.bind(t, ...)` choose it; otherwise it is the global object (`window`, `globalThis`); an arrow's is its enclosing
  function's.
- **Prototypes**: `new F(...)`, `F.prototype`, `o.__proto__` (read and assigned), `Object.create(p)`, inherited
  properties and methods, `hasOwnProperty`, `for (k in o)` over the chain. `new Number(x)` / `new String(x)` /
  `new Object()` are wrapper objects (`typeof` `'object'`, truthy, `==` their value, printed `[Number: 12]`);
  `String.prototype.f = function () { ... this ... }` adds a method to every string.
- **Control flow**: `if` / `else`, `while`, `do … while`, `for (;;)`, `for (x of array)`, `for (k in object)`,
  `switch` (with `===`, fall-through, `default` anywhere), `break` / `continue`, also to a label (`outer:`).
  Bodies may be a block or one statement.
- **Strings**: `'...'` or `"..."` with escapes; built with `+` / `+=` from anything (`"13" + !0` is `"13true"`);
  compared by character codes; `s.length`, `s[i]`, `charAt`, `charCodeAt`, `indexOf`, `lastIndexOf`, `includes`,
  `startsWith`, `endsWith`, `slice`, `substring`, `toUpperCase`, `toLowerCase`, `trim`, `split`, `repeat`, `concat`,
  `toString`, `String.fromCharCode`.
- **Arrays**: literals, `a[i]` (reading past the end gives `undefined`; writing past it grows the array),
  `a.length`, `push`, `pop`, `shift`, `unshift`, `indexOf`, `lastIndexOf`, `includes`, `join`, `slice`, `concat`,
  `reverse`, `fill`, `splice` (up to 8 arguments), `toString`.
- **Objects**: literals with identifier, string or number keys; `o.x`, `o["x"]`, `o[k]` read and assign (a missing
  property is `undefined`); methods; keys built at run time find the same property as a literal.
- **Timers**: `setTimeout(f, ms)`, `setInterval(f, ms)`, `clearTimeout`, `clearInterval`. The callbacks run once the
  program is done, by due time and then in the order they were set, as a browser runs them (no time passes: the
  machine runs them at once). `alert(x)` prints `x` (the page has no dialogs).
- **Errors at run time**: calling something that isn't a function stops with `Uncaught TypeError: not a function`,
  reading a name that was never declared or assigned with `Uncaught ReferenceError`.
- **Output**: `console.log(a, b, ...)` and `putc(code)`; arrays and objects print as Node prints them on one line.
- **Network**: `fetch(url)` and `read()` (see [Network](#network)).
- **Syntax**: `//` and `/* */` comments; semicolons are optional where JavaScript inserts them (a newline ends a
  complete statement unless it is inside brackets or the next line continues it; after `return` it always ends it).
- **Memory**: strings, arrays, objects, functions, closures' variables and doubles live in a heap that a copying
  garbage collector reclaims.

### How values work

- A value is one 20-bit word. Integers in −229,376 … 262,143 are themselves; the rest of the range is cut into slots
  of 2^15 that tell the kinds apart: strings, arrays, objects, functions, closure environments and boxed doubles are
  addresses with a slot's offset, and the specials (`true`, `false`, `null`, `undefined`, `NaN`, `±Infinity`, `-0`)
  are the top slot's last eight words.
- The machine has three-address instructions (`ADD x, a, b`) on globals, a function's frame slots and small
  constants; the compiler keeps an expression's values in the frame's temps past the locals, with no allocator.
- Arithmetic and comparisons are one instruction for two integers whose result is an integer; anything else (a
  double, a string compared, `NaN`) goes to a routine in ROM, which computes with an FPU: a CSS class whose
  operations are one `calc()` each, which Chrome evaluates in IEEE doubles. `+` with a string builds the string in CSS.
- A string is `[length][characters][0]`, in the program's string area (literals and property names, interned) or in
  the heap. A function is an 8-word heap block: its code, its parameter count, its environment, its name, its
  prototype. A call of a function value is one instruction when the arguments match its parameters (an inner
  function's takes a second execution, which puts its environment in its frame); anything else (padding, `this` for
  a function that uses it, a bound function, `apply`) goes through ROM.
- Each `console.log` argument is one PRINT instruction, which writes up to 4 console cells per execution; a `+`
  chain with a string in it isn't built: its pieces are printed in turn.

### How objects work

An object is a chain of 8-word heap chunks (three key/value pairs and a link). Its keys end with 0, or with a link to
its prototype's first chunk, which `o.x` (one instruction, GETP, probing one pair per execution) follows as it follows
a chunk's own link: inherited properties are read without leaving the machine. An assignment stops at the prototype
and adds the key to the object itself. `o[k]` with a number or one of the program's strings as `k` probes in the
machine too; a key built at run time is first matched by its characters. Details:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §3.6.

### Limits

- **Program size**: 24 lines of 64 columns, 400 tokens, 1,023 code words (511 instructions); 768 words of string data
  (the length + 2 for every string literal and every `.name` in the program) and 231 globals (a double literal
  takes one too); 64 labels (an `if` takes 1 or 2, a loop up to 4, a function 3 or 4: functions use them fastest; a
  `switch` takes 2, plus 2 per `case` and 1 for a `default`), 32 variables in scope, 16 functions; 32 distinct strings
  and property names (one interning table; a method's name doesn't count when `(` follows it directly); blocks and
  expressions nest 8 deep (a long `else if` chain counts as one level), with at most 10 values pending in an expression
  and 24 counting the arguments of the calls under way; at most 4 unary operators in a row before a binary one
  (`!!!!x * y` is fine, `!!!!!x * y` isn't); an array literal of at most 127 elements.
- **Functions** nest two deep (a function inside a function, not a third level; error 41). A function declared at
  the top level and called by its name must be called with as many arguments as it has parameters (error 76); a
  function value can be called with any number.
- **Memory**: RAM is 16K words (`compiler/layout.json`); the stack has about 7,500 words, so recursion can go a few
  hundred to a thousand calls deep (a call takes its frame: its `this`, the parameters, the locals and the
  expression's temps). The heap holds 3,072 words of live data (an object of up to 3 keys or a double takes 8 words, a
  function 8, a string its length + 3 rounded up to 8, an array 4 words + 1 per element, rounded up to 8); more halts
  with `out of memory`.
- **Numbers** print exactly as Node does except below about 10^-6 with many digits or from 10^22 with many digits,
  where the machine's 17 digits aren't always the shortest. A literal may end in a dot (`1.` is 1, as in JavaScript,
  so `1.x` and `12.length` are error 48).
- **`console.log`** prints each argument as soon as it is computed, where JavaScript computes them all first:
  `console.log("a", f())` prints what `f` prints after `a `. It is a statement, or what a `return` or an arrow's
  expression body gives (`undefined`: `x => console.log(x)`), not a value elsewhere (`var x = console.log(1)`: error 30). Node breaks a long array or object over several lines; the machine prints one line. Node lists
  an object's integer keys first in ascending order; the machine prints its number keys first in the order they were
  added.
- **Printing functions**: a function's name is its declaration's or its object key's; Node also names a function after
  the variable it is assigned to (`var f = function () {}` prints `[Function: f]` there, `[Function (anonymous)]`
  here). `String(f)` gives `function f() { [native code] }`, not the source.
- **`this`** outside a function and in a plain call is the global object, but it isn't the globals: `this.x = 1` doesn't
  make a global `x`.
- **An arrow's expression body** ends at `)` `,` `;` `}` or a line end; inside `[ ... ]` or before a ternary's `:`
  wrap it in parentheses. A newline inside an expression body ends it when the statement around it could end there.
- **Timers** run after the program in due order, but no time passes (`setTimeout(f, 5000)` doesn't wait), and a
  program with a `setInterval` it never clears runs forever.
- **Not supported**: array methods that take a function (`map`, `forEach`, `filter`, `reduce`, `sort`, ...), template
  literals, classes, `try` / `catch` / `throw`, `in`, `instanceof`, `delete`, default and rest parameters, spread,
  destructuring, `arguments`, getters and setters, `**`, `??` and `?.`, `JSON`, `Object.keys`, `Array.isArray`,
  regular expressions, and most methods beyond the lists above. Properties of functions other than `prototype`, of
  numbers, and of arrays other than `length` and the methods.
- **Strings**: ASCII only; a string's characters can't be assigned. A method is only called (`s.toUpperCase` without
  `()` reads a property, which a string looks up in `String.prototype`). `parseInt`, `Number`, `String`, `Math`,
  `Object`, `fetch`, `read`, `setTimeout`, `setInterval`, `clearTimeout`, `clearInterval` and `alert` are reserved names.
- **Scoping**: a `var` after a `let` / `const` of the same name in the same scope isn't an error, use before
  declaration in an inner block (`let x = x + 1`) isn't caught, and a `var` read before its declaration inside a
  function is an error (4) rather than `undefined`. A function's parameter shadows a `let` of an enclosing block, but
  inside a function nested in another, an outer block's `let` can still win over the outer function's parameter of the
  same name. A `for (let i ...)` loop has one `i`, not one per iteration: functions made in the loop all see its last
  value (`for (let i = 0; i < 3; i++) setTimeout(() => console.log(i))` prints 3 three times).
- **`do … while`**: `if (a) do s; while (c); else …` is rejected (drop that `;`); `do s;; while (c)` is accepted.
- **Console**: 9 columns × 16 rows. Long lines wrap, and output past 16 rows wraps to the top.
- **Network**: one request at a time, GET only, no headers; a status above 511 reads as 511. A round trip carries 2 URL
  bytes or 8 body bytes. Without the gateway (`file:`, a static server) `fetch` returns `-1` after about 20 s.

### Error codes

The status line shows a message for the common errors and `syntax error (n)` for the rest.

| Code | Meaning | Code | Meaning |
|---|---|---|---|
| 3 | expected an operand | 41 | a function nested more than two deep |
| 4–7 | undefined variable | 78 | `let` / `const` of a name its scope already declares |
| 8 | a statement can't start with this token | 44–46 | unexpected `,` `]` `)` |
| 9–10 | name expected after `var` / `++` | 47 | unbalanced `(` |
| 20 | too many labels (64) | 48 | unexpected token after an operand |
| 21 | blocks nested too deeply (8) | 80 | a `for (x of / in ...)` variable of the outer function |
| 22 | expression too deep (8 operators, 10 values, 24 with pending arguments, 5 unary operators in a row, 127 array elements) | 50–53 | statement or `for` header ended in the wrong place |
| 23 | too many functions (16) | 54–55 | unexpected `}` |
| 24 | too many variables (32) | 56 | `break` / `continue` outside a loop |
| 25 | too many globals (231) | 57 | `return` outside a function |
| 26 | too much string data | 60 | (the runtime library: an undefined function) |
| 30, 38–39 | malformed `console.log`, or used as a value | 61 | a token emits too much code at once (7 instructions) |
| 32–37 | malformed `if` / `while` / `for` / `function` / arrow header (36: a parameter that is a reserved word) | 62 | program too long (more than 1,023 words) |
| 40 | missing `}` at end of input | 77 | a method called with a number of arguments it doesn't take (`apply`: two) |
| 64 | assignment to a `const` | 65 | `const` without `=` |
| 66 | `while` expected after a `do` body | 67 | `:` without `?` (or a label inside a `for` header) |
| 68 | too many strings and property names (32) | 69 | property name expected after `.` (or not one of `Math`'s) |
| 70 | a property assignment must be a statement | 71 | object literal: key expected |
| 72 | `:` expected after an object key or `default` | 73 | `case` / `default` outside a `switch` |
| 74 | a `switch` body must start with `case` / `default` | 75 | a second `default` |
| 76 | a call by name passes a different number of arguments than another call or the definition | | |
| 99 | page only: no parser variant accepts this token here | | |

The page reports 99 where the reference compiler gives a more specific syntax-error code.

## Network

The page can't make requests by itself, so the server it comes from does: `net/server.js` serves the page and is a
**gateway**. It performs the GET (any URL: relative ones resolve against the page, absolute `http(s)` ones go out from
the server, so CORS doesn't apply) and hands the body back a byte at a time. What CSS does is talk to the gateway,
with no script:

- `fetch` and `read` are made of one instruction, `NET`, which sends a word and waits for four answers at once, two
  from each of two "modem" iframes: a READ brings 2 bytes per answer.
- The request: the page sets the height of the modem iframes to the word. The modem's document reads its height
  (`100vh`) and sends it as a few `background-image` URLs that CSS chooses; a resize restyles the document, so the
  request goes out as soon as the page lays it out.
- The answer: the gateway answers with a new document for each modem (the old one asks for it as soon as it has
  loaded, and the gateway holds that request until the answers are ready). It places the element `#t` at x, y = two
  answers, and the load scrolls to `#t`. The scroll reaches the page's 100 px `overflow: hidden` box around the
  iframe, and scroll timelines read its `scrollLeft` and `scrollTop`.

```
node net/server.js .. 8767        # serve the repo root with the gateway (from js-minus-js/)
# then open http://localhost:8767/js-minus-js/dist/js_in_css.xhtml in Chrome
```

The gateway is a local tool: it fetches whatever the page asks for, from wherever it runs. The site the repo deploys
to is static, so it has no gateway, and `fetch` there returns `-1`. The modems start at the program's first network
word and load once per word each; between words they wait. How it works:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §3.8.
