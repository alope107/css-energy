# css-physics vs js-minus-js: techniques compared

Both projects compute inside Chrome's rendering pipeline with no script on the page. css-physics (rigid3d.css)
runs a rigid-body solver as registered custom properties gated by `@container` queries. js-minus-js compiles
JavaScript with CSS and executes the bytecode in a GSUB "CPU" font while Chrome shapes a line of text. This report
lists what they share, where they differ, and which techniques could move from one to the other. Numbers are from
each project's `docs/BENCHMARKS.md` (Chromium 153, the same devcontainer; css-energy's numbers were re-measured on the
Ubuntu mini PC on 2026-10-17) unless marked *(estimate)*.

## What both rely on

The two projects found many of the same engine facts independently. Most of these are already written down in
both `CLAUDE.md`/`AGENTS.md` files.

| Technique | css-physics | js-minus-js |
|---|---|---|
| State survives frames in layout, read back by view timelines | 13 registers per body, two per element (`top` and `left`) in a 10⁶ px scroller | CPU registers as view-timeline subjects; RAM as remembered sizes |
| Two useful passes per frame | 2 physics steps per frame | at most 2 shapings per frame; a third issue runs on stale state |
| 6 significant digits through `var()` | 6 bodies per decimal word in the wake digests | 20-bit machine words kept signed, \|v\| < 2¹⁹ |
| Few registered properties, names reused | `SHARE`: level-local props share names | pooled temp names `qp<i>` (13k → 2.6k) |
| Parity copies avoid self-reference | `J0/J1` accumulators aliased to `K` in the next element | `--p-<name>-A/B` parser state |
| Per-frame drivers are non-inherited | clock on `#LT`, pointer zeroed by `.rz` | wall clock on `#clk`, `inherits: false` drivers |
| Deep nested chains as the program | one element per Gauss–Seidel round (67 at 64 bodies) | one element per character (1,561) and per token (400) |
| Data-dependent work selected by `@container` | gates per body, pair and plane | one parser variant per (mode, token) |
| Integer fields packed into one number | decimal digit words | control-stack entries `kind × 4096 + a × 64 + b` |

## Where they differ

- **Shape of the work.** css-physics bakes the topology into the stylesheet: every pair of bodies has its own
  rules, so cost and size grow with N². js-minus-js runs a generic step on every level and picks a specialised
  variant by data, so its CSS is fixed and its depth grows with the input.
- **Where the arithmetic happens.** css-physics does all math in `calc()`. js-minus-js moved execution into
  HarfBuzz, where one shaping runs 32 micro-cycles, and keeps CSS for compiling and servicing traps.
- **What a frame costs.** css-physics is style-bound: 50–100 ms per pass at 48–64 awake bodies, almost all
  `UpdateLayoutTree`. js-minus-js is split: about 17 ms of shaping, 5 ms restyling `#cpu`, and layout that
  includes restyles of size containers.
- **Idle cost.** css-physics works hard to make a sleeping scene free (about 1 ms per pass). js-minus-js only
  needs to be fast while running.
- **Testing.** js-minus-js has five test levels, including a Python twin of the CSS compiler (`cc_dsl.py`) that
  must match the reference word for word. css-physics has a pass/fail smoke test and sanity checks in Chrome.

## From js-minus-js, useful in css-physics

1. **A Python twin of the generated CSS (highest value).** js-minus-js writes each step once in a DSL that
   evaluates in Python and compiles to CSS, and level 2 checks the two agree. css-physics already holds every
   declaration as `(level, gate, name, expr)` in `g.decl`. A small evaluator over that list would give
   browser-free tests of the inliner, simplifier, gating and `SHARE` renaming, step by step against a reference
   state. Today a subtle generator bug only shows if the smoke test's floor, overlap or speed limits trip.
2. **A cost model that runs without a browser.** `tools/traps.py` predicts js-minus-js run time in shapings.
   The same evaluator, counting matched blocks, properties and tokens per pass with the cost table in
   BENCHMARKS.md §2, would predict a css-physics step. `tools/cen.js` already applies such a model, but needs
   Chrome to know which gates are active.
3. **`invalidationTracking` traces.** js-minus-js found that 98% of its style resolutions happened inside
   layout by tracing with `disabled-by-default-devtools.timeline.invalidationTracking`. css-physics has never
   looked at which elements restyle per pass, only at totals. That trace would show directly whether the
   register elements, the render tree or the levels are restyled more than expected.
4. **Sibling selectors instead of `:has()` for controls.** js-minus-js reads run state with
   `#run:checked ~ …`. css-physics sets gravity, reset, shake, scene and grab with `#app:has(…)`. The cost only
   lands on presses, so this is low priority; it is worth one measurement of a grab press at 64 bodies.
5. **Anchor-name reads as dynamic indexing (a real lead, untried).** A js-minus-js read port
   (`machine/gen_fvm4.py`, `mux()` and `.rp<w>`) works in two steps. A two-level `if()` picks an anchor name
   `--c<k>`: at most 64 + 64 `style()` tests for a bank's 4,096 cells, so O(√N), once per port. Then one `anchor-size()`
   reads the whole word. css-physics has assumed it has no dynamic indexing, which is why every pair of bodies
   has its own rules. With this technique, a body could keep K contact slots: each slot picks its partner's
   register elements by name and reads their positions directly. That would make the pair rules O(N·K) instead
   of O(N²). Caveats:
   - The value arrives in layout. It reaches style only inside a size-container reader, so the solver that uses
     it would have to sit under that reader. js-minus-js found that restyles inside size containers dominated
     its layout until it slimmed its readers.
   - css-physics once read registers through anchor positioning and measured about 5 ms of layout per frame
     (HISTORY.md, from an earlier session's summary).
   - Choosing which K partners to keep is still a ranking over candidates, which the broadphase digests would
     have to supply.

   A first test is a microbenchmark: N register elements and N·K readers that each pick a partner by name, timed
   against the per-pair rules at 64 bodies.
6. **Layer isolation for static panes.** `will-change: transform` on js-minus-js's editor saved about 7 ms of
   paint per frame. css-physics paints under 1 ms per frame, so this does not pay there today.

Not transferable, with reasons:

- **Execution in a GSUB font.** Physics needs fractional, branchy math. The variable-font experiments in
  css-physics already rejected font compute for this (a rotation matrix costs about 105 µs in a font against
  about 36 µs in CSS).
- **Remembered-size RAM leaves.** They hold state with no per-pass cost, but update only once per frame. That
  would halve css-physics's step rate.

## From css-physics, useful in js-minus-js

1. **Transition latches may be paying for every `@property` on the page (worth one experiment).** css-physics
   measured that each transition restart costs time in proportion to the page's registered properties, about
   0.05 µs per property per restart. js-minus-js latches each editor character with a transition on `--lv` and has
   about 3,800 `@property` rules. *(estimate)* That is about 0.2 ms per latch restart, or about 5 ms per frame if
   a column's 24 latches restart each frame, against a sweep of about 19 ms per frame (1.2 s over 64 columns). If
   a measurement confirms it, the sweep, which is half of compile time, could get cheaper by moving the latches
   into a document or iframe with few registrations, or by cutting `@property` count further.
2. **The rule-matching cost table.** css-physics measured matching tiers at scale in Chromium 153 (its
   BENCHMARKS.md §2). js-minus-js's ENGINE_NOTES.md quoted 1.6–4 µs per container rule from an earlier, undated
   measurement (it now cites these figures too); the current figures are lower:
   - a present name with a false `style()` costs 0.8 µs per rule;
   - `style(--x)` without a value (true when a registered property differs from its initial value) costs 0.5 µs;
   - range queries such as `style(--x > 5)` work, at about 1.7 µs.
3. **Query order.** `and` evaluates left to right and stops at the first false test, and nested
   `@container` rules evaluate the innermost query first. js-minus-js dispatches with
   `style(--vh: m) and style(--tcq: tc)`, so whichever test rejects more variants should come first. The
   expected gain is small, because each variant is tested once per level, but the change is one line.
4. **Freeze and ablate.** css-physics profiles one step by baking the state into constants (`freeze3.js`) and
   deleting families of rules (`ablate.py`). js-minus-js could attribute its 100 ms of style and layout per frame
   the same way: freeze the CPU registers, then strip the trap service's families (memory tree, PRINT, EXT) one at
   a time.
   The ablation half is ready: `shared/py/ablate.py` works on js-minus-js's XHTML (it skips braces in CSS strings
   and never overwrites the source), and `shared/js/freeze.js` has the wobbling-constant clock. Freezing the CPU
   is still open, because much of its state lives in layout (view timelines, remembered sizes), not in custom properties.

Not transferable, with reasons:

- **Owner-named container gating.** An absent container name is a cheap rejection only near the root: Chrome
  walks every ancestor looking for it. css-physics measured about 0.2 µs plus 0.6 ns per ancestor per name.
  js-minus-js's token levels sit under about 2,000 ancestors, so an absent name would cost more there than the
  `style()` test it replaces. A present name is also unsafe there: it could resolve to a distant ancestor that
  once had the same mode.
- **Sleeping and neighbourhood digests.** These exist to make idle bodies free. A compiler pass and a CPU have
  no idle parts to skip.
- **Spatial partitioning.** css-physics measured it and it lost (its HISTORY.md, Phase 4). It has no analogue in
  js-minus-js.

## Suggested next steps

| Project | Step | Effort | Expected value |
|---|---|---|---|
| js-minus-js | Measure latch restarts against the `@property` count during the readback sweep | small | could speed up compile, unknown how much |
| css-physics | Python evaluator over `g.decl` as a reference test | medium | safer generator changes; a browser-free cost model |
| css-physics | One `invalidationTracking` trace of a 64-body pass | small | shows which elements restyle |
| css-physics | Microbenchmark anchor-name partner reads for contact slots | small, then large to build | could remove the N² pair rules |
| js-minus-js | Freeze-and-ablate the trap service | medium | attributes 100 ms per frame |
| js-minus-js | Reorder the dispatch test (ENGINE_NOTES.md already has the new costs) | small | small |
