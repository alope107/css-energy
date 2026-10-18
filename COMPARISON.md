# css-physics, js-minus-js and paint: techniques compared

css-physics runs a rigid-body solver as registered custom properties gated by `@container` queries. js-minus-js
compiles JavaScript with CSS and runs the bytecode in a GSUB "CPU" font while Chrome shapes text. paint stores state
in Chrome's compression-dictionary store. Numbers are from each project's `docs/BENCHMARKS.md`.

## What css-physics and js-minus-js share

| Technique | css-physics | js-minus-js |
|---|---|---|
| State kept in layout, read back by view timelines | 13 registers per body, `top`/`left` in a 10⁶ px scroller | CPU registers as view-timeline subjects; RAM as remembered sizes |
| Two useful passes per frame | 2 physics steps per frame | at most 2 shapings per frame; a third issue runs on stale state |
| 6 significant digits through `var()` | 6 bodies per decimal digest word | 20-bit words kept signed, \|v\| < 2¹⁹ |
| Few registered properties, names reused | `SHARE`: level-local props share names | pooled temp names `qp<i>` |
| Parity copies avoid self-reference | `J`/`K` accumulators | `--p-<name>-A/B` parser state |
| Per-frame drivers are non-inherited | clock on `#LT`, pointer zeroed by `.rz` | wall clock on `#clk` |
| Deep nested chains as the program | one element per Gauss–Seidel round | one element per character and per token |
| Data-dependent work selected by `@container` | gates per body, pair and plane | one parser variant per (mode, token) |

They differ in shape: css-physics bakes the topology into the stylesheet (rules per pair, N² growth) and does all
math in `calc()`; js-minus-js runs a fixed generic step selected by data and does its arithmetic in HarfBuzz.
css-physics is style-bound and works hard to make idle scenes free; js-minus-js only needs to be fast while running.

## Open ideas across projects

| From → to | Idea | Effort | Value |
|---|---|---|---|
| js-minus-js → css-physics | A Python evaluator over `g.decl` as a reference test, like js-minus-js's `cc_dsl.py` twin checked at L2. Today a generator bug only shows if the smoke test's limits trip. Would also give a browser-free cost model. | medium | high |
| js-minus-js → css-physics | **Anchor-name reads as dynamic indexing.** js-minus-js's read port picks an anchor name `--c<k>` with a two-level `if()` (O(√N) `style()` tests) and reads it with one `anchor-size()`. K contact slots per body reading partners by name would make the pair rules O(N·K) instead of O(N²). Caveats: the value arrives in layout, so the solver must sit under a size-container reader; anchor-positioned registers once cost ~5 ms of layout per frame; the broadphase still has to rank partners. js-minus-js measured both layout costs: a size container restyles its dependent subtree inside layout every pass its size is dirty, and every rendered anchor costs ~1.5 µs per layout pass, read or not (its ENGINE_NOTES 34, 40). First step: a microbenchmark at 64 bodies. | small, then large | could remove the N² pair rules |
| js-minus-js → css-physics | One `invalidationTracking` trace of a 64-body pass (js-minus-js found 98% of its restyles inside layout this way). | small | shows which elements restyle |
| css-physics → js-minus-js | **Transition latches may pay for every `@property`.** A transition restart costs ~0.05 µs per registered property; js-minus-js has ~4,200 and latches each editor character with a transition. *(estimate)* ~0.2 ms per restart, ~5 ms per frame during the ~19 ms/frame readback sweep. Measure it. | small | could speed up compile |
| css-physics → js-minus-js | Freeze and ablate the trap service (memory tree, PRINT, EXT) to attribute its ~100 ms of style+layout per frame. `shared/py/ablate.py` already works on the XHTML; freezing the CPU is open because its state lives in layout. | medium | attribution |
| css-physics → js-minus-js | Put the dispatch test that rejects more variants first: `and` short-circuits left to right (ENGINE_NOTES 7 states the rule). `ccpage5.py` tests `style(--vh)` before the `--tcq` set; nobody has checked which rejects more. | small | small |
| paint → js-minus-js | A save area: 480 entries of 4–8 bits that survive reloads, read once at boot into RAM, written back ([paint/docs/ARCHITECTURE.md](paint/docs/ARCHITECTURE.md), "Feeding a CSS machine"). Needs its own domain: `workers.dev` is a public suffix, so every Worker and preview shares the site's 500 dictionaries, and paint uses up to 480 ([deploy/README.md](deploy/README.md)). At 8 bits a boot is ~123k probes *(derived)*, past Cloudflare's ~10k requests per connection. | medium | programs that survive a reload |
| others → paint | Engine probes for paint's Chrome facts (which loads register a dictionary, the frame limit, history from cache) in `engine/check.js` style, instead of only the 6-minute end-to-end test. | small | a Chrome change caught in seconds |

Not transferable: execution in a GSUB font for physics (a rotation matrix costs ~105 µs in a font against ~36 µs in
CSS); remembered-size RAM for css-physics (updates once per frame, halving the step rate); owner-named container
gating for js-minus-js (an absent name walks every ancestor, and its token levels sit under ~2,000); sleeping,
digests and spatial partitioning (a compiler and a CPU have no idle parts).

## paint's overlap

paint's state lives in the network stack and on disk: it survives reloads, arrives asynchronously, and is measured in
requests, not passes. It shares the layout-size-to-number read (`anchor-size()` → `calc(100cqw / 1px)` → registered
`<integer>`), the transition latch, and `if()` selection. Facts it found that matter to the others: Chrome allows about
1,000 frames per page and every `<iframe>` takes one even hidden and lazy (a hidden `<object>` takes none); one fetch
per URL per document; history traversal serves CSS-initiated fetches from cache.
