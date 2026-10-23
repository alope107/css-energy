# A register machine (proof of concept)

Can js-minus-js run faster on a register machine than on its stack machine? This directory holds a register ISA, its
reference compiler and simulator, its pass model and its CSS CPU, for a subset of the language, and compares them
with main's stack machine on the same programs. Branch `regvm`.

## Why it should be faster

The CSS CPU runs up to K = 32 instructions per layout pass, one chain level each, and a pass ends early on a cache
miss or on a second console write. In compute-bound programs most passes run all 32 levels (main: primes 50 of 60
passes, collatz 59 of 66, fib 249 of 350), so the number of instructions executed sets the number of passes, and
passes set the run time. A stack machine spends most of its instructions moving values: `a = b + c` is LOAD, LOAD,
ADD, STORE. A three-address instruction that reads its operands where they live does it in one.

## The machine

**Instructions** are two words at an even address, so both are in one 4-word cache block and one cache lookup fetches
them: `word0 = op · 8192 + A`, `word1 = (B − 512) · 1024 + C`. A is a destination, a jump target or flags; B and C are
source operands; LOADK, PRINTK and CALL use word1 whole (a 20-bit constant, a frame offset).

**Operands** (10 bits): 0–255 a global (`data_base + o`), 256–767 a frame slot (`fp + o − 256`), 768–1023 the constant
`o − 896`. Constants outside −128 … 127 and string values are loaded by LOADK.

**Frames** use one register, fp. A frame is `[return word] fp`, then the parameters, the locals, and the temps: the
operand stack's slot d is `fp + 1 + npar + nloc + d`, where nloc is the function's final count of locals, a label the
linker adds (as main's ENTER count is). A call's slot takes the return word and its arguments go above it:
`CALL target, off` writes `off · 8192 + return address` at `fp + off` and adds off to fp; `RET v` writes v over the
return word, which is the caller's slot for the value, and subtracts off. No ENTER, no saved fp, no sp. Top-level code
runs with fp = sp0.

**ISA** (`rc_ref.OPN`, in class order): ADD SUB MUL DIV MOD LT GT LE GE EQ NE (A = B op C); MOV NEG LOADK; JMP, the
compare-and-branch forms JLT JGT JLE JGE JEQ JNE (jump to A if B op C), HALT; JZ JNZ (0 and the empty string are
false); CALL RET NOT; PRINT B (A: separator · 2 + boolean), PRINTK (the value in word1), PUTC.

**The CSS CPU** (`gen_rcss.py`) is `machine/gen_css.py`'s machine (registers as view timelines, fill and prefetch,
K levels of fetch > execute > commit, stall on the first miss, latches, read ports, console) with these instructions
in six classes, each reading only what its instructions read (a rule evaluates every declaration in it): alu (B, C,
the write), mov (B, the write), jump (B, C), test (B and a string's length), call (CALL, RET, NOT), out. The class is
arithmetic on the opcode. There is no ROM: the subset needs no runtime library.

## The compiler

`rc_ref.py` subclasses `compiler/cc_ref.py`: the same lexer, tables, modes and control stack, one token per step,
fixed-size stacks, no lookahead, so it can become CSS as `cc_dsl.py` did. Only code generation differs. An operand is a
descriptor on an operand stack (a variable, a constant, a temp) and code is emitted when an operator pops, as one
instruction reading the operands where they are:

- The last operator of an assignment's value writes the target directly: `n = n + 1` is `ADD n, n, #1`.
- A comparison that a branch takes stays pending and fuses into it: `while (i <= 15)` is `JGT end, i, #15`; a final
  `!` becomes the other branch.
- `for` tests jump into the body (one jump fewer per iteration than main's layout).
- Calls put arguments in the caller's temps; an expression statement's value is dropped without code.
- Order of evaluation: an operand still waiting on the stack is copied to its temp before something changes it: a
  global before a call, a variable before its `++` / `--`, and every variable at the start of a conditional region
  (`&&`, `||`, `?:`), since a copy made inside one would be made on one path only. `x op= e` reads x first.
- console.log's `+` chains keep their pieces on the operand stack and print them at the argument's end, as main's
  pnK does.

The subset (error 90 outside it): integers, booleans, string literals as values (printed, compared by identity),
`var` / `let` / `const`, functions, `if` / `else`, `while`, `do` / `while`, `for`, `break`, `continue`, `return`, every
operator but `+` on strings outside console.log and `<` `>` `<=` `>=` on strings, `?:`, `= op= ++ --`, `console.log`,
`putc`. Not in it: arrays, objects, methods, `.length`, heap strings, `switch`, the runtime library.

## Results

**Correctness.** `python3 exp/regvm/suite.py`: 87 suite programs inside the subset match Node's output, the 47
`suite_err` programs are rejected. `regfuzz.py` (tests/fuzz/fuzz.py with rc_ref and rsim): ~5,600 generated
programs inside the subset, the suite in 11 layouts, 3,000 mutants: no failures (an output that differs from Node's
exactly as main's does, a value wrapped into a tag range, is counted, not failed). C2 in Chrome
(`pages.py` + `tests/csscpu_pages.js`): 85/85 pages halt with Node's console and rc_ref's step count.

**Instructions executed** (`suite.py`): 12,317 against main's 29,300 over the 87 programs, 2.38× fewer; per
program 1.25× (a function returning a string) to 5.5× (`str_concat`). Code is 9% larger in words (two words per
instruction).

**Passes** (`rsim.py`, K = 32):

| Program | Steps reg / main | Passes reg / main | How main's passes end |
|---|---|---|---|
| primes | 781 / 1,695 | 32 / 60 | 50 of 60 at K |
| collatz | 782 / 1,941 | 31 / 66 | 59 at K |
| func_recursion | 799 / 1,950 | 31 / 67 | 57 at K |
| fib | 3,437 / 8,450 | 164 / 350 | 249 at K |
| deep_recursion | 3,507 / 8,414 | 1,064 / 1,412 | 1,410 misses |
| fizzbuzz | 148 / 415 | 29 / 31 | 13 console writes, 12 misses |
| is_prime | 205 / 445 | 37 / 38 | 24 console writes |
| gcd | 39 / 91 | 7 / 7 | misses |

Compute-bound programs take about half the passes. Output-bound ones gain little: a pass writes the console once
(one 4-cell chunk), whatever the ISA, and FizzBuzz prints 15 lines. Miss-bound ones gain a little (smaller frames).

**A chain level** (`exp/csscpu/chainbench.js` on `BENCH=1` pages: the chain alone, from the first pass that runs all 32
levels; the minimum of 41 trials, on a machine at load ~5): a register level costs 5–9% more than a stack level,
for 2.2–2.5× the work.

| Program | Stack (main) µs per level | Register µs per level |
|---|---|---|
| primes | 372, 375 | 391, 409 |
| collatz | 350, 388 | 378, 391 |
| fib | (main's bench page fails its end-state check) | 450, 456 |

**Run time in Chrome** (`MAXLOAD=8 VARIANTS="base reg regl" exp/regvm/bench.sh 5`, 2026-10-21, headless Chromium 153,
mini PC; other sessions kept the load at 5–8, so absolute times are ~1.3–1.9× a quiet machine's: main's primes ran
1,487 ms quiet, 1,876 here). Run time is first step → HALT (`machine/halttime.js` runMs, polled every 30 ms), six
interleaved rounds per program, a fresh browser per run; the ratio is the median of the per-round ratios to main
(IQR in brackets). reg: the register CPU; regl: with `LOOPCOPY=2`.

| Program | Main ms | Register ms | Ratio | Register + loop copy ms | Ratio |
|---|---|---|---|---|---|
| primes | 1,876 | 886 | 0.50 (0.49–0.53) | 844 | 0.49 (0.44–0.50) |
| collatz | 3,132 | 1,355 | 0.43 (0.42–0.43) | 1,179 | 0.38 (0.37–0.38) |
| func_recursion | 2,309 | 938 | 0.41 (0.40–0.46) | 918 | 0.40 (0.37–0.41) |
| fib | 12,460 | 6,178 | 0.50 (0.44–1.27 †) | 5,308 | 0.44 (0.43–0.46) |
| cond_logic | 1,387 | 860 | 0.63 (0.58–0.64) | 768 | 0.56 (0.53–0.57) |
| else_if_long | 3,143 | 1,975 | 0.63 (0.59–0.63) | 1,952 | 0.63 (0.60–0.65) |
| is_prime | 1,199 | 987 | 0.81 (0.71–0.82) | 952 | 0.86 (0.72–0.89) |
| fizzbuzz | 1,731 | 1,295 | 0.67 (0.59–0.97) | 1,300 | 0.81 (0.50–0.86) |
| nested_loops | 363 | 252 | 0.98 (0.69–1.06 †) | 174 | 0.67 (0.48–0.68) |
| gcd | 220 | 177 | 0.77 (0.54–0.88) | 63 | 0.28 (0.24–0.73) |

A repeat of primes, 30 rounds (load ~7–9): main 2,830 ms, register 1,365 ms, ratio 0.491 (0.470–0.497).
gcd and nested_loops run for a few polling intervals: their ratios are noise.

Compute-bound programs run 2.0–2.6× faster: half the passes, each level ~5–9% dearer. Output-bound ones (is_prime,
FizzBuzz) gain 1.2–1.5×: a pass writes one console chunk whatever the ISA.

† **Three runs didn't halt** in this session: one each of register primes, fib and nested_loops (of 60 register-page
runs; 0 of 60 main and 0 of 60 loop-copy runs) ran to halttime's 300 s limit with the page responsive. Not
reproduced since: 232 more runs of the same pages with the same harness, alone or 4 at once, and C2 three times for
each machine at load ~20 (main 3 × 111/111, register 3 × 85/85). One earlier C2 run (6 browsers, load ~20) showed a
page halted with the right step count and an empty console (`str_escape`), also not reproduced. halttime.js now
prints the CPU's registers when a run doesn't halt, so the next one can be diagnosed.

## Leads

- **Loop tests copied** (`LOOPCOPY=1`, `=2` with a `for`'s one-instruction step too): a loop whose test is one
  instruction on variables emits it again at the loop's bottom instead of jumping back to it; with the step, a `for`
  iteration has no jump at all. Suite steps 12,317 → 11,949 → 11,715; collatz 782 → 671, nested_loops 79 → 51,
  cond_logic 359 → 293. Costs one or two instructions of state per control-stack entry in the CSS compiler.
- **Output**: one console chunk per pass caps output-bound programs; a second console write set per pass would
  help both machines.
- **Two-level selects**: a 16-way `if()` costs ~4.7 µs (16 entries, ~8 conditions tested); as 4 × 4, ~3.2 µs. A level
  evaluates dozens (lookups, the write's set).

## Toward feature parity

- **The compiler in CSS**: rc_ref's code generation in `cc_dsl.py`'s DSL. New state: the operand stack (≤ 8
  descriptors with their types; a big constant pending only on top), the pending comparison. At most 5 instructions
  (10 words) are emitted per token on the suite (the page's limit is 12 words). Temps add the function's local count:
  a label times 1, 1024 or 1025 in a word, where code words now take a label times 1.
- **Strings, arrays, objects**: the runtime library compiled to register code (rc_ref can compile `lib_src.js`'s
  dialect given `peek` / `poke` and the intrinsics), the object and array instructions in three-address form, traps
  as calls at a fixed frame offset.
- **The collector's roots**: a frame's slots can hold stale values (main's ENTER zeroes locals for this); the register
  machine needs the same, or roots limited to what is live at each call site.

## Files

| File | What |
|---|---|
| `rc_ref.py` | the compiler (a cc_ref subclass) and the simulator; `python3 rc_ref.py prog.js -d` |
| `rsim.py` | the CSS CPU's pass model, beside main's (`csssim.py`) |
| `gen_rcss.py` | the CSS CPU (CPU-only pages; `BENCH=1` for `exp/csscpu/chainbench.js`) |
| `mkimage.py` | a RAM image for gen_rcss.py and `machine/halttime.js` |
| `suite.py`, `regfuzz.py`, `pages.py` | L1, the fuzzer, C2 pages |
| `bench.sh` | main vs register CPU-only pages, interleaved (`../../../shared/js/ab.js`) |
