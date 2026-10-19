# A CPU in style alone (toy)

Does an instruction executed by CSS style recalc cost less than one executed by the font CPU? `mkcpu.py` builds a page
that runs L instructions of the real ISA (`cc_ref.run()`'s semantics: stack, globals, locals, indirect loads and
stores, arithmetic with MUL / DIV / MOD, comparisons, jumps, CALL / ENTER / RET, INC, IDX, 35 ops) with no layout:
one instruction per three nested `display: contents` elements.

- `.f` fetches `mem[pc]` and decodes it. `.x` is dispatched by `@container style(--op: k)` and computes the op's
  addresses, reads, write and next PC / SP / FP. `.c` declares the registers and the one written word, picked by
  `@container style(--slot: s)`, so unwritten words inherit and no state needs parity copies.
- Memory is a 16-line × 4-word cache in custom properties, preloaded with the lines the run touches (nothing misses).
  `MAP=direct` (default `assoc`): the line is a hash of the block, the word picked with `if(style(--i: k): …)`;
  `assoc` compares the block with 16 tags and sums. The toy's hash is searched to avoid collisions on this run.
- `LAZY=1` (default): an op reads only the words it uses, inside its dispatched rule.

`bench.js` checks the last instruction's registers and every cached word against a Python stepper, then times 25
recalcs. Each trial changes the immediate of `PUSHI 3` in the loop, so every state after the first iteration changes,
and checks the whole end state again.

```
python3 exp/csscpu/mkcpu.py exp/csscpu/loop.js 200 build/cpu/d200.xhtml        # MAP=direct LAZY=1 …
node exp/csscpu/bench.js build/cpu/d200.xhtml
```

## Results (2026-10-19, headless Chromium 153, loaded machine)

Counting loop (`loop.js`, 12 instructions per iteration), all 25 trials exact, linear in L (100 and 200):

| Cache lookup | Every op reads its operands | Only the ops that use them |
|---|---|---|
| fully associative: 16 tag compares, 16-term sums | 0.72 ms | 0.57 ms |
| direct-mapped, `if()` select | 0.54 ms | 0.42 ms; 0.38 ms with lazy stack reads |

For comparison, the font CPU on the page costs ~8.6 ms per instruction (~24 ms of shaping and ~18 ms of CSS per
shaping of ~4.9 instructions; BENCHMARKS §11 on branch `chain-shapings`). Reads are most of what is left; the elements
themselves cost ~50 µs per instruction with trivial CSS.

**Measuring pitfall.** Blink stops restyling where computed values stop changing. A first harness varied the loop
counter, which the program overwrites in its first instructions, so only a few levels were recomputed and some pages
timed at 8 µs per instruction. A trial must change every later state, and the harness must check that it did.

## Not in the toy (what a machine needs on top)

Misses (an in-pass read port: the chain trick), write-backs (write channels, one set per pass), the console kept in
properties, PRINT and the object ops, the runtime library as cached code instead of font ROM, a cache that handles
collisions (2-way or 32 lines, costlier reads), view-timeline registers between passes, gating and HALT.
