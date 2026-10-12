---
name: language-feature
description: Add or fix a JavaScript language feature in the CSS compiler (syntax, operator, statement, value type, error) end to end, keeping cc_ref.py and cc_dsl.py in lockstep and passing every test level.
---
# Add a language feature

The compiler exists twice: `compiler/cc_ref.py` (reference) and `compiler/cc_dsl.py` (the same step, compiled to
CSS). Both change together, in this order.

1. **Specify with tests.**
   - Add `tests/suite/<feature>.js`: at most 24 lines × 64 columns, valid JavaScript whose output Node defines.
     Cover the interactions too, not just the happy path: braceless bodies, `else` binding, semicolon insertion,
     nesting.
   - Add a program the compiler must reject to `tests/suite_err/` if one applies.
   - Run `make expect` and read the generated `.out`. Avoid `undefined`, floats and objects, which the language
     doesn't have.
2. **Change the reference.** Edit `compiler/cc_ref.py`:
   - lexer: `char()`;
   - parser: `token()` and its helpers `end_expr_stmt`, `end_simple_stmt`, `complete_stmt`, `close_block`;
   - limits and codes at the top of the file.

   Iterate on `make l1`.
   - Keep it one step per character, with fixed-size state and no lookahead past the next character.
   - Use a new failure code if needed, and add it to the README's error table.
3. **Mirror the change in the DSL.** Edit `compiler/cc_dsl.py`:
   - Same effects in the same order, predicated with `with self.when(...)`.
   - Call `done()` wherever the reference `return`s. Where the reference falls through (`m = self.mode = X`),
     don't call it.
   - New state goes into `LEX_STATE` / `parse_state_names()` and into `ref_state()` in `tests/cmp_dsl.py`.
   - A new mode fallthrough goes into the `FALL` map in `token()`.
   - Avoid local names that shadow DSL helpers (`le`, `lt`, `eq`, `add`, …).
   - Run `make l2` until it reports `ALL OK`.
   - If L2 fails, run one program with `SPEC=1 python3 tests/cmp_dsl.py tests/suite/<feature>.js`. The
     mismatch list names the first diverging state variable.
4. **Check the size** with `python3 tools/vsz.py` and `python3 tools/lp.py`.
   - Report total temps and the maximum label ports before and after.
   - A jump in ports (elements on all 400 levels) or in temps (CSS per level) needs a reason or a fix: fold
     constants, collect labels, prune unreachable blocks.
5. **Run `make l3`** (about 3 minutes, in the background). Every program must match the reference word for word.
6. **If the runtime library changed** (`compiler/lib_src.js`), compare `python3 tools/traps.py
   tests/suite/fizzbuzz.js tests/programs/t*.js` before and after. Shapings are the cost.
7. **Rebuild and check the page**: `make page && make l5-smoke`, then `make dist`.
8. **Update the docs.**
   - The README's language, limits and error-code sections.
   - `docs/BENCHMARKS.md` if a cost moved.
   - `docs/ENGINE_NOTES.md` for any new Chrome behaviour.

Report with the summary line of each level as evidence.
