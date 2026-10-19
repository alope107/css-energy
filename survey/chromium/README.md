# Chromium survey: Blink and HarfBuzz, read for css-energy

How the parts of Chrome the three projects stand on actually work, read from the source, with what each means for
css-physics, js-minus-js and paint: bottlenecks, unused features, what's coming, and how to fit the engine better. It
builds on the earlier targeted survey ([../ENGINE_RESEARCH.md](../ENGINE_RESEARCH.md),
[../PRIMITIVES.md](../PRIMITIVES.md)) and corrects it in places (below).

**Sources.** Chromium main `22b3b159` (2026-10-18, M158) and the M153 branch (8010, what the repo tests on), plus
single files from 155 (stable, 8059) and 157 (beta, 8103). HarfBuzz at the revisions Chrome bundles: 14.3.1-10
(153), 14.4.0-86 (155), 14.5.1-141 (157, main); HarfRust, Fontations and OTS from their repos; chromestatus,
chromiumdash, Gerrit, csswg-drafts, wpt.fyi. **Probes**: small pass/fail and ratio runs in headless Chromium
153.0.8010.12 on the mini PC, with other agents loading the machine (load average 4–7), so timings are ratios; the
HarfBuzz profile used a zig-built HarfBuzz at Chrome's exact revisions. Labels in every chapter: *(code)*,
*(measured)*, *(docs)*, *(inference)*. Scripts and probe pages: `exp/<chapter>/` (§ Reproducing).

## Chapters

| Chapter | Covers | Headline |
|---|---|---|
| [01-lifecycle.md](01-lifecycle.md) | BeginFrame → commit, the lifecycle loop and every re-run trigger, slow-main-thread scheduling, throttling, threads and processes, costs outside style/layout, profiling | An SVG child document sends a number to its parent **across processes, every frame, without script**; same-process feedback through it runs the lifecycle 700× in one frame |
| [02-style-engine.md](02-style-engine.md) | RuleSet, matching, container queries, MPC, base-style reuse, cascade, recalc propagation, `if()`, `@function`, mixins, loading | A `style()` gate costs one mini-cascade per *block* per pass, and stale gates keep costing until a result flips |
| [03-values-and-properties.md](03-values-and-properties.md) | `CSSVariableData`, registration, `var()` substitution, calc, precision, style-query equality, value functions, counters | Nothing caches a parsed value: every registered declaration is re-parsed per element per pass; a counter is an exact int32 adder |
| [04-animations-and-scroll.md](04-animations-and-scroll.md) | keyframes → cascade, transitions and latches, scroll/view timelines, triggers, snap, anchoring, scroll buttons, SMIL, view transitions | The per-registered-property cost is one loop (keyframe snapshot); transition latches work **per pass**; SMIL and `::scroll-button` are script-free inputs |
| [05-layout.md](05-layout.md) | LayoutNG trees, dirty bits, caches, relayout boundaries, out-of-flow and anchors, size containers, inline layout, flex/grid/table/multicol, precision | Anchored readers restyle every pass; anchor maps are rebuilt per level (ENGINE_NOTES 40); `display: contents` chains restyle in O(D²) |
| [06-text-and-fonts.md](06-text-and-fonts.md) | font loading, OTS, Fontations, variation instances, shaping ranges, `HarfBuzzShaper`, font funcs, `ShapeResult`, precision, HarfRust in Blink | A CPU shaping is ~99% HarfBuzz; counter-driven lines can't chain inside one layout, `content: if()` lines can |
| [07-harfbuzz.md](07-harfbuzz.md) | the CPU font as HarfBuzz sees it, plans and stages, lookup application, caches, limits, a per-lookup profile, versions, HarfRust | Half the HarfBuzz time follows a trap; a self-recursive lookup **halts** the shaping (−30%); shaper stages run one LookupList entry 2× or 6× past the 16,384 cap |
| [08-interactivity-and-loading.md](08-interactivity-and-loading.md) | input paths, invokers, popovers, forms, editing, keyboard, pointer, persistent state, dictionaries, speculation rules, loader limits, `GOAWAY` | paint can write dictionaries with a `Speculation-Rules` header and no frames; `Clear-Site-Data` is a static reset |
| [09-roadmap.md](09-roadmap.md) | flag diffs 153/155/157/main, chromestatus, CSSWG, Interop 2026, other engines, a probe watch list | `ident()` dynamic names are specified and in Safari TP, still test-only in Blink; a 156 ResizeObserver change can add a pass per frame |

## The findings that matter most

Ranked by how much they could change the projects. Each is backed in its chapter; "verified" means re-run or re-read
by the lead after the chapter was written.

1. **Multicore is possible after all.** An SVG document in an `<object>` reports its natural size (outer `<svg
   width="1000em">`, font-size computed from its own state) to the parent on every font change, over IPC, and the
   parent's `anchor-size()` → `cqw` reader sees it one frame later. Precision float32 → 1/64 px. A child served with
   `Content-Security-Policy: sandbox` gets its own process (one per origin); `Origin-Agent-Cluster: ?1` gives one per
   origin even on one site: both static `_headers`. A whole CSS machine (XHTML in `<foreignObject>`, view-timeline
   readback) ran inside such a child and reported through it. css-physics HISTORY "Iframes for parallelism" and
   ENGINE_NOTES 32 say the reverse channel doesn't exist. *(measured; verified: cross-site child, 1-frame lag, every
   step exact)* → [01](01-lifecycle.md) §1.8, §2.3.
2. **An unbounded in-frame loop.** A same-origin SVG `<object>` whose natural size feeds its own viewport keeps
   `NeedsLayout()` true after pre-paint, and Blink re-runs the lifecycle until it converges: 700 iterations in one
   BeginMainFrame at ~70–80 µs each, no depth rule, no cap. Size queries and anchors refresh per iteration; timelines
   and remembered sizes don't. A register machine clocked by it is untested; an oscillating version hangs the tab.
   *(code + measured)* → [01](01-lifecycle.md) §1.4, §2.4.
3. **The CPU font's HarfBuzz time can drop by a third, and S can double.** Per shaping: 3,768 lookup passes, 2.42 M
   iterator steps of which 84% skip glyphs hidden by mark filtering; 48% of micro-cycle slots follow a trap and still
   cost 94%. A contextual lookup that calls itself trips the nesting limit and stops every later forward lookup:
   **0.70× per shaping**. One LookupList entry referenced from features in different shaper stages runs once per stage
   but is sanitized once: 64 cycles via `rvrn` + `cv01`, 192 via Arabic-script code points, all exact against the
   model; with the halt, S = 64 costs 1.12× per shaping for 15% fewer shapings. *(code + measured)* →
   [07](07-harfbuzz.md) §2.2–2.3.
4. **Chrome 155+ runs the CPU font 6–8% slower than 153** (HarfBuzz 14.4.0 moved the wide-mark-set test out of line);
   a flat bitmap per set makes it 0.73–0.76× of main. An upstream HarfBuzz issue worth filing. *(measured)* →
   [07](07-harfbuzz.md) §3.1, §5.
5. **Transition latches work per pass, not per frame.** The before-change style is the start of the current
   style+layout pass. The editor scan could take a column per pass (2×, more with a pass pump). PRIMITIVES §P4 was
   wrong. *(code + measured; verified)* → [04](04-animations-and-scroll.md) §1.3, §2.2.
6. **The "every registered property costs on every animated element" effect is one loop.** Each new or rebuilt
   keyframe model (transition restart, latch write, animation rebuild, element shown) walks every registration with an
   `initial-value`: 0.06 µs × R. It is css-physics BENCHMARKS §4's transition cost (24,896 × 0.06 ≈ 1.5 ms per body
   per pass) and probably part of js-minus-js's compile time (chain sources created at Run). Registrations without
   `initial-value` are free. A few-line upstream fix. *(code + measured; verified in 153 source)* →
   [04](04-animations-and-scroll.md) §1.4, §2.1.
7. **Style gates: per block, and stale ones linger.** A `style()` gate is one throwaway cascade
   (`StyleResolver::ComputeValue`) per `@container` *block* per pass in which the container's custom properties
   change. The evaluator keeps every query it ever evaluated and re-evaluates all of them until one flips: 5,000
   stale gates cost 10–20× (css-physics after a pile settles). Declarations on an element that animates a custom
   property are applied twice per pass. *(code + measured)* → [02](02-style-engine.md) §1.4–1.6.
8. **Nothing caches a parsed value.** A registered `calc(var(--t) * k)` is tokenized five times and allocates 6–10
   objects per element per pass; cost decomposes as 1 unit to declare, +2 to type, +3 for calc, +2.5 per `var()`
   hop, +1–2 per math function. Unregistered constants are 3× cheaper. The 6-digit cut is `%.6g` with an exact path
   for integers ≤ 999,999; animated `<integer>`s keep int32. *(code + measured)* → [03](03-values-and-properties.md)
   §1.2–1.4.
9. **js-minus-js's layout passes have named costs**: anchored readers restyle and relayout every time their
   containing block runs its out-of-flow pass (+2.25 µs each, ~65 µs at depth 2,000: the compile chain's code
   overlays); anchor maps re-allocate a reference per anchor per rebuilt level (ENGINE_NOTES 40); restyling a
   1,561-level `display: contents` chain is O(D²) (4.5–8.1 ms vs 1.1–1.8 with a block every 64 levels). *(code +
   measured)* → [05](05-layout.md) §1.5–1.8, §2.2.
10. **Chained shapings need `content: if()`, not counters.** Counter text changes only in `UpdateCounters()`, never
    inside a layout's size-container recalcs; PRIMITIVES finding 3 measured with a checker that forced extra passes.
    `content: if()` chains are exact in one `Layout` at ~3× the style cost of counters. *(code + measured)* →
    [06](06-text-and-fonts.md) §1.10.
11. **paint has a frame-free write path and a reset.** A `Speculation-Rules` response header with an `immediate`
    document rule prefetches links CSS makes visible; a prefetched response with `Use-As-Dictionary` registers and
    replaces. `Clear-Site-Data: "cache"` on any same-origin subresource wipes the origin's dictionaries. Also located:
    the 1,000-frame cap, a 1,350-request per-process ceiling (each request counted twice), and the `GOAWAY` race's
    k(k+1)/2 over-pop, unfixed on main. *(measured, code)* → [08](08-interactivity-and-loading.md) §1.8–1.9.
12. **Script-free input is richer than the projects use**: `::scroll-button` adds +1 per click with a 1 px snapport;
    SMIL `<set begin="id.click|keydown|change|…">` writes `class` or a `<foreignObject>` width; `accesskey` clicks
    even a `display: none` checkbox (Alt+R for Run); a range thumb is an anchor live under touch; `field-sizing:
    content` turns typed text into a width through the author's GSUB; arrow keys step a focused snap scroller.
    *(measured)* → [04](04-animations-and-scroll.md) §1.8–1.9, [08](08-interactivity-and-loading.md) §1.5–1.6.
13. **What's coming.** `ident()` as a substitution function (`var(ident("--m" var(--k)))`) was resolved by the CSSWG
    in August and passes all WPT in Safari TP; Blink has the old literal-only form at `test` with no CL: dynamic
    indexing is 2027+. `inherit()` works in 153 behind a flag (experimental, no milestone). Timeline names go global
    (experimental in 157). A ResizeObserver change in 156 adds a pass when observations are skipped. `random()` (156)
    is a per-element constant. HarfRust stays `test` (1.65× slower per CPU shaping in 153). The repo tests on 153, two
    milestones behind stable. *(code + docs)* → [09](09-roadmap.md) §0.

## What to do, per project

Ranked by expected gain × confidence. "Test" is the cheapest experiment that settles it.

### js-minus-js

| # | Change | Expected | Test | Ch. |
|---|---|---|---|---|
| 1 | **Halt the shaping on a trap** (self-recursive abort lookup at the end of each cycle; readback from state glyphs instead of the `export` tail) | 0.70× HarfBuzz per shaping (0.52× derived if reverse lookups idle) | C-API runner of `hbtest.py` + CPU-only page in 153 | 07 §2.2 |
| 2 | **Stage multiplication** (`rvrn` + `cv01`, S = 64) with the halt | −15% shapings (FizzBuzz), 0.95× HarfBuzz total; −24% suite shapings modelled | `variant.py rvrn` on the CPU-only page, then L5 | 07 §2.3 |
| 3 | **Editor scan one column per pass**: drop the `--rbfresh` gate; latch inputs by inheritance, control from an ancestor or style query | sweep ~1.2 s → ~0.6 s (2×; more with a pump) | `make l5-input`, then Run → compiled | 04 §2.2 |
| 4 | **Gate `anchor-size()` on code overlays to words that reference a label** | up to ~30 ms per pass during compile at 511 words | `RERUN=1 make l3`, compare the per-word slope | 05 §2.2 |
| 5 | **Zero-height block every 32–64 chain levels** | full-chain restyle 3–6× cheaper | L3 + one L5 FizzBuzz | 05 §1.8 |
| 6 | **Gate the gather on RAM reads** (idle `G` cells outside coverage) | −20% HarfBuzz (derived) | `variant.py` + `verify.py` | 07 §2.5 |
| 7 | Measure the keyframe snapshot loop: A/B the page with 4,000 dummy `@property … initial-value` | if ≳ 0.1 s on Run → compiled, keep chain sources rendered and gate consumers | `ab.js` on Run → compiled | 04 §2.1 |
| 8 | Dispatch on `style(--v: calc(N))` instead of splitting ids below 256; negatives too | removes a constraint; survives the upstream fix | `style-int-256` variant in `engine/check.js` | 03 §1.5 |
| 9 | Strip custom declarations from pass-through wrappers; keep heavy declarations off animated elements (`#mem`, sources, `#cpu`) | ~2.7 µs per element restyled by inheritance; ~0.85 µs per moved declaration | invalidation trace before/after | 02 §2.3 |
| 10 | Narrow the four widest mark-filtering sets, then renumber glyphs | ~5% | `renum.py` + `verify.py` | 07 §2.4 |
| 11 | Input devices: `accesskey="r"` on `#run`; a focused snap scroller as a d-pad; `<select>` type-ahead as getchar; `field-sizing` input as a line register; `::scroll-button` as a step button | new language features (stdin) | a 10-line page per device writing one RAM cell | 08 §2, 04 §2.7 |
| 12 | If chained shapings are pursued: `content: if()` cells, not counters | several dependent shapings per `Layout` | `mkchain_if.py` with the real font | 06 §1.10 |
| 13 | *(speculation)* The same-process SVG `<object>` fixpoint loop as the CPU clock | orders of magnitude more cycles per frame, if cycle logic fits size containers | a 2-register counter, iterations per frame vs page size | 01 §2.4 |

Watch: CL 8559024 (calc-computed `<integer>` exact through `var()` → wider words); `ident()` (read ports as
`anchor-size(ident(…))`); `inherit()` (no parity copies); HarfRust (if ≤ 1.2× HarfBuzz, revisit S without the cap).

### css-physics

| # | Change | Expected | Test | Ch. |
|---|---|---|---|---|
| 1 | **Parallel islands**: K sub-scenes as SVG documents (scene in `<foreignObject>`) in `<object>`s, each its own process via `Origin-Agent-Cluster` or CSP `sandbox`; coupling through font-size-encoded natural sizes | pair work K·(N/K)², run on K cores; kill if combined steps/s < 1.5× one page | two 24-body islands vs one 48-body page | 01 §2.3 |
| 2 | **Flush stale gate caches** when the awake set changes (one flip-on-change rule per level) | up to 0.6–2 µs × historical gates per pass after a pile settles | `sparse.js` on a settled tower vs the field scene, then with the rule | 02 §2.2 |
| 3 | **Move `#LS`/`#LT` declarations to a plain child** | ~0.7 ms per pass at 48 bodies | `ab.js` on the frozen 48 pile | 02 §2.2 |
| 4 | `timeline-scope` on `#LS` instead of the `.ts` nests (the 141-era 3× no longer holds) | 0.3–1 ms per pass at 48 (inference) | `ab.js`; check the "inside `.rz`" rendering issue first | 04 §2.4 |
| 5 | Unregister constants and `var()`-only pass-throughs; `progress()` for normalizations; `mod(round(down, w / B^k), B)` without `sign()` for 0/1 digits; base-4 digests (9 bodies per word) | ~0.5 µs per converted declaration; −31% per normalization | generator flags + `ab.js` with an A-vs-A control | 03 §2 |
| 6 | Measure the per-frame hover hit test (every layout dirties hover; a resting mouse re-hit-tests a big `preserve-3d` tree) | unknown | trace a frozen 48 scene, mouse inside vs outside | 08 §2, 01 §1.9 |
| 7 | Give the register scrollers a compositing layer (`overflow: hidden` scrollers dirty the root layer) | per-frame raster-invalidation conversion | `raster_invalidation_and_convert_time_ms` before/after | 01 §1.9 |
| 8 | A range slider (thumb as anchor) for camera/gravity; `interestfor` long-press as a touch "hold" bit | input, not speed | Android emulator | 08 §2 |

Confirmed dead: contact slots at ≤ 96 bodies (dynamic indexing still costs ~15 µs per port); layout reductions (not
cheaper than style); `@function`, mixins (bytes only), `random()` (per-element constant), triggers in registers
(silent in `overflow: hidden` scrollers). Watch: global timeline names (drop `.ts`), `inherit()` (drop K/J aliases),
CL 8559024 (re-check digests), the upstream snapshot-loop fix (pose transitions become affordable; snap-back is a
separate problem).

### paint

| # | Change | Expected | Test | Ch. |
|---|---|---|---|---|
| 1 | **Write through speculation-rules prefetch** (radio → visible link → `immediate` document rule) instead of cell `<object>`s | 0 frames, no per-load rewrites (−960 requests), writes outside the renderer's request budget; loses Back/Forward undo | 4×4 selftest site with the header and MIME | 08 §4 |
| 2 | **Staggered reads** keeping in-flight ≤ the server's stream limit | no `SpdySession` queue → no `GOAWAY` losses; retire the retry row (7,680 extra probes on a blank canvas) | staged build under `serve.js --goaway 2000` | 08 §2 |
| 3 | Show the blank-cell `<object>` only after the read finishes | 1 frame per cell instead of 2 (~960 of 1,000 today) | count `window.length` in `e2e.js` | 08 §2 |
| 4 | Static reset: `/reset` with `Clear-Site-Data: "cache"` behind a confirm `<dialog>` | a feature | add to `selftest/` | 08 §1.8 |
| 5 | *(inference)* Canvas-wide reads via cell documents that report their value as a natural size (SVG child, every frame; or a responsive iframe at load) | fill/count/export in CSS | one cell on 155+ | 01 §1.8, 09 §2.6 |

## Corrections to the repo's notes

What the source or a measurement says against what the docs say today. Not applied to the project docs; each line
names the chapter with the evidence.

| Doc | Says | Should say | Ch. |
|---|---|---|---|
| js-minus-js ENGINE_NOTES 1 | style() never matches a calc-computed `<integer>` ≥ 256 | also negatives, `style(--v: var(--w))`, and `style(--g)` at a calc-computed initial ≥ 256; workaround `style(--v: calc(N))`; `if(style())` unaffected | 03 |
| ENGINE_NOTES 2 | 6 significant digits | `%.6g`, except integers ≤ 999,999 exact; literal and **animated** `<integer>`s keep int32 | 03 |
| ENGINE_NOTES 3 | registered integers stored as floats | doubles; `<integer>` serializes as int32; floats only in `<length>`, scroll offsets, layout | 03 |
| ENGINE_NOTES 4 | every registered property costs on every animated element | each keyframe-model rebuild walks every registration with an `initial-value` (0.06 µs each); steady state free | 04 |
| ENGINE_NOTES 6 | identical siblings share computed style | the matched-properties cache; any tree-scoped name (`anchor-name`, animation/timeline names, 153's `container-name`) disables it | 02 |
| ENGINE_NOTES 13 | an animation per level restyles the chain, ~3 ms per level | named-timeline lookup walks every ancestor per animation per restyle: O(depth²) | 04 |
| ENGINE_NOTES 26 | sanitizer drops the last lookups | (already corrected by ENGINE_RESEARCH Q3) and: the cap counts LookupList entries, stages multiply runs | 07 |
| ENGINE_NOTES 27 | contexts capped at 64 glyphs | only the input sequence; backtrack and lookahead aren't capped | 07 |
| ENGINE_NOTES 28 | cost ≈ rules × walk distance | distance in buffer glyphs, hidden ones included (each a mark-set test) | 07 |
| ENGINE_NOTES 29 | Chrome positions in whole device pixels | only without subpixel positioning; headless Linux keeps fractions. The rule stays right for portability | 06 |
| ENGINE_NOTES 32 | the only frame channel is parent → child | SVG children report natural size every frame, across processes | 01 |
| ENGINE_NOTES 37/38 | third pass unexplained | the settle pass is a ResizeObserver re-arm (RAM leaves after pass 2); an extra post-layout `UpdateCounters()` layout is a second candidate; settle with 01 §1.10's trace classification | 01, 03 |
| ENGINE_NOTES 40 | anchors merged into the containing block's query | one reference allocated per anchor per rebuilt ancestor fragment; only locked `content-visibility` or `display: none` stops it | 05 |
| ENGINE_NOTES 41 | redeclaring constant one level down doesn't stop it | it stops only where the element's *whole* inherited custom-property set is unchanged | 02 |
| ENGINE_NOTES 43 | advance ≤ 32,767 units | int32 16.16 px per glyph, saturating at 32,768 px; per glyph, not per span | 06 |
| css-physics ARCHITECTURE §1 | registers ≈ 26 bits (LayoutUnit) | ≈ 24 bits: timeline time is µs at 16 µs/px, subject position float; a bigger scroller gains nothing | 04, 05 |
| css-physics ARCHITECTURE §1, `gen3d.py` | 24-name `timeline-scope` nests ~3× cheaper | true in 141; in 153 a scope check is a linear scan, one list costs the same | 04 |
| css-physics HISTORY | iframes for parallelism: no channel back | SVG `<object>` children: a per-frame channel, own processes via `_headers` | 01 |
| css-physics BENCHMARKS §2 | absent name ≈ 0.2 µs + depth × names | that microbenchmark used a distinct name per rule; a repeated name walks once per element (0.07 µs per rule) | 02 |
| css-physics CLAUDE.md | digit extraction ≈ 5 µs | three math functions on top of a property; `mod` isn't slow | 03 |
| paint ARCHITECTURE/HISTORY | dcz header 36 bytes; HTTP/3 close fails everything in flight; link fetched when the network is idle; a cached response never registers; a hidden `<object>` takes no frame | 40 bytes (code right, doc wrong); in-flight retried over TCP, queued lost; main-thread idle; Blink's MemoryCache short-circuits, an HTTP-cache hit can register; only if never shown | 08 |
| survey PRIMITIVES finding 3, rec. 1 | K shapings chain inside one layout | with counters they don't (the checker forced passes); with `content: if()` they do | 06 |
| survey PRIMITIVES §P4 | transition latch is frame-granular | per pass | 04 |
| survey PRIMITIVES §P9, rec. | HarfRust ~24% slower | end to end; per shaping 1.65× in 153 (0.12), 1.34× standalone at 0.14, 1.21× at HEAD | 06, 07 |
| survey ENGINE_RESEARCH Q1 | max_ops charged only on nested calls and merges | also `unsafe_to_break` spans and, since 14.4.0, `move_to` (10.5% of the budget used) | 07 |
| survey ENGINE_RESEARCH Q8 | link dictionary fetch is CORS anonymous | that's the flagged path; the default is `cors` + `credentials: omit` | 09 |

## Bugs

The chapters list about 25 possible browser bugs. MREs for the reproducible Chrome ones, and the performance items worth
reporting upstream (the keyframe snapshot loop, stale container-query results, HarfBuzz's wide mark-set regression),
are in [../../bugs/README.md](../../bugs/README.md). One caveat for filing: **Blink drops animation taint through
registered properties** (02 §5, 04 §5), against css-variables-2, and both projects depend on it (css-physics owner
names, js-minus-js latches). A fix would break them.

## Ideas left open

Beyond the per-project tables, the chapters record unconventional ideas with their cheapest tests:
- **Exotic layout operators.** `flex-wrap: balance` with `flex-line-count` is a DP + bisection min-max partition
  (05 §1.11). `text-fit` is a divider (09 §4). `font-size-adjust` gives a ratio of two axis-dependent metrics at
  style time (06 §1.4). MathML stretchy operators compute `ceil()` (ENGINE_RESEARCH Q10).
- **Arithmetic in fonts.** A GSUB coprocessor line that reshapes only when its operands change (06 §4). Feature values
  as a byte input to AlternateSubst, nested ones included (07 §4). FeatureVariations 1.1 unions lookup sets per axis
  (157+, 07 §1.7).
- **State and timers.** Scroll anchoring as a per-pass integrator (a ratchet with suppression; 04 §1.8). Smooth scroll
  as a √Δ timer (04 §1.8). A view transition carries a few bits across a navigation (04 §1.10).
- **Persistence.** Prerenders as parallel write documents (08 §4). `scroll-initial-target` as a CSS → scroll write
  (08 §1.8).
- **Isolated cascades.** A same-origin SVG subdocument has its own `@property` registry, cascade and MPC, and its
  result lands in the parent in the same pass. It could isolate a service's many private properties (01 §4).
- **Counters as exact adders** across siblings, read back through a power-of-two-upem font (03 §1.9). Works; niche.

## Demos

[demos/index.html](demos/index.html): five script-free pages to try by hand in a real Chrome: the SVG child → parent
channel (same-process and cross-process), the `::scroll-button` counter, a SMIL click latch, and `accesskey` on a
hidden checkbox. Each was checked in headless 153.

## Reproducing

- **Source.** Chromium main: `git clone --depth 1 --filter=blob:none --sparse https://chromium.googlesource.com/chromium/src`,
  then `git sparse-checkout set --cone` on the directories each chapter cites. **Don't** `git show`/`diff` other
  branches in a partial clone: each blob is fetched lazily and it hangs for minutes. For a branch, use gitiles
  tarballs per directory: `exp/fetch_tree.sh refs/branch-heads/8010 <dest> <dir>…` (~1 s per directory), or one file
  with `curl -s 'https://chromium.googlesource.com/chromium/src/+/refs/branch-heads/8010/<path>?format=TEXT' |
  base64 -d`. HarfBuzz: `git clone https://github.com/harfbuzz/harfbuzz` and check out `12ee77ee` (main/157) or
  `dfdc088c` (153). The chapters write those checkouts as `$SP/src/chromium`, `$SP/src/chromium-153`,
  `$SP/src/harfbuzz-chromium`, `$SP/src/versions/<milestone>/`. **In the devcontainer they exist already, in
  `~/src/`** (so `$SP` = `~`; `~/src/README.md` lists them), until the container is rebuilt.
- **Probes.** `exp/<NN>/` holds each chapter's harnesses, generators and small pages (2.5 MB). Generated pages, fonts,
  HarfBuzz builds and the Rust toolchain aren't committed; the generators recreate them. Harnesses use
  `/usr/local/bin/chromium` and Playwright from `css-physics/node_modules`; a few scripts still name the scratch
  directory they ran in, so adjust paths before running.
- **HarfBuzz builds** (07): there is no C compiler in the image; `pip install --target <dir> ziglang`, then `python3
  -m ziglang c++ -O2` on HarfBuzz's amalgamated `src/harfbuzz.cc` with `exp/07/drv/drv.cc` (07 §6).
