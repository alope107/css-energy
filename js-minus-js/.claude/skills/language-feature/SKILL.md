---
name: language-feature
description: Add or fix a JavaScript language feature in the CSS compiler (syntax, operator, statement, value type, error) end to end, keeping cc_ref.py and cc_dsl.py in lockstep and passing every test level.
---
# Add a language feature

The compiler exists twice: `compiler/cc_ref.py` (reference) and `compiler/cc_dsl.py` (the same step, compiled to
CSS). Both change together, in this order.

1. **Specify with tests.** Add `tests/suite/<feature>.js` (at most 24 lines × 64 columns, valid JavaScript whose
   output Node defines; avoid `undefined` and floats). Cover interactions: braceless bodies, `else` binding,
   semicolon insertion, nesting. Add a `tests/suite_err/` program if one applies. Run `make expect` and read the
   `.out`.
2. **Change the reference** (`cc_ref.py`): lexer `char()`; parser `token()` and its helpers `end_expr_stmt`,
   `end_simple_stmt`, `complete_stmt`, `close_block`; limits and codes at the top. Keep one step per character,
   fixed-size state, no lookahead past the next character. A new failure code goes in the README's error table.
   Iterate on `make l1` (its simulator is strict: a statement that leaves the stack unbalanced fails). Add the feature
   to the program generator `tests/fuzz/progen.py`, within what the language guarantees, and run `python3
   tests/fuzz/fuzz.py gen -n 2000`, `fmt` and `mut -n 2000`. A failure is in `build/fuzz/` (`tests/fuzz/show.py`
   replays it); each real one becomes a `tests/suite` test.
3. **Mirror it in the DSL** (`cc_dsl.py`):
   - Same effects in the same order, predicated with `with self.when(...)`. Call `done()` wherever the reference
     `return`s; not where it falls through (`m = self.mode = X`).
   - New state goes into `LEX_STATE` / `parse_state_names()` and `ref_state()` in `tests/cmp_dsl.py`; a new mode
     fallthrough into the `FALL` map in `token()`.
   - Don't name locals after DSL helpers (`le`, `lt`, `eq`, `add`, …).
   - `make l2` until `ALL OK`. On a failure, `SPEC=1 python3 tests/cmp_dsl.py tests/suite/<feature>.js` names the
     first diverging state variable.
4. **Check the size**: `python3 tools/vsz.py`; report variants, rules, total temps and max
   label ports before and after. Ports are elements on all 400 levels, temps are CSS per level, and every rule is
   tested on every level: a jump needs a reason or a fix (fold constants, collect labels, prune unreachable blocks,
   keep tokens out of shared classes that multiply variants).
5. **`make fuzz`** (~1.5 min: the DSL against the reference on generated, reformatted and mutated programs, rejected
   ones included) and **`make l3`** (~40 s, in the background): every program must match the reference word for
   word. If the lexer or the page's chain changed, **`make fuzz-l3`** too (L3 on 300 fuzz programs).
6. **If `lib_src.js` changed**, compare `python3 tools/traps.py tests/suite/fizzbuzz.js tests/programs/t*.js` before
   and after.
7. **Rebuild and check the page**: `make page && make l5-smoke`, then `make dist`.
8. **Docs**: the README's language, limits and error codes; `docs/BENCHMARKS.md` if a cost moved;
   `docs/ENGINE_NOTES.md` for new Chrome behaviour.

Report with the summary line of each level as evidence.
