# The primitives, their alternatives, and what to change

A survey of the browser machinery the three projects stand on: what each primitive is, how it's used, the alternatives
to it, and which of those alternatives were measured here (headless Chromium 153.0.8010.12, the image's build, on the
mini PC; load average 0.4–3 during the runs, so read ratios rather than absolute numbers). Every experiment is in
`survey/exp/` and is reproducible with the commands in the last section. Labels: **measured** (run here, this
session), **researched** (Chromium/HarfBuzz source, M153 branch 8010), **untested** (reasoning only).

## Headline findings

1. **The "two useful passes per frame" limit is not a limit.** A nest of D elements with
   `contain-intrinsic-size: auto` whose size changes every pass makes Chrome run D + 2 useful style+layout passes per
   frame (D = 32: 33.7 passes per frame at 60 fps). Blink re-arms its post-layout scroll-timeline snapshot whenever the
   ResizeObserver step delivers, and the internal observer behind remembered sizes counts. The nest only counts if
   each element is deeper than the last. *(measured)*
2. **Remembered sizes then update every pass, not once per frame.** A `content-visibility: hidden` leaf inside the
   nest reads back the previous pass's size (lag 0–2 passes). Without the nest it reads a frame-old value. This
   removes js-minus-js's reason for one write channel per issue (ENGINE_NOTES 14). *(measured)*
3. **Shapings can be chained inside one layout pass.** K levels of "text line → anchor-size readers → size-container
   restyle → next line" ran exactly at K = 16 with 76 values per line and 300 service properties per level. With a
   `contain: layout` wrapper per level (so each level's fixed readers have their own containing block), cost is
   linear: ~1.5 ms per level at 8 values, ~5 ms per level at 76. All-fixed elements, as js-minus-js uses today, grow
   like K². The font CPU spends ~53 ms of non-shaping work per shaping step today. *(measured)*
4. **Grid placement is dynamic indexing.** `grid-row: var(--addr)` on a size-container item stretched to its row reads
   the value of row `addr`. At 4,096 cells with 32 ports, a frame costs 5.2 ms against 23.8 ms for js-minus-js's
   `if()`-mux + `anchor-size()` port, which is about 15 µs per port against ~200–600 µs. *(measured)*
5. **css-physics: inlining multi-use temps does *not* pay in the engine.** `INL_ONLY1=0` removes 4% of the props but
   the frozen 48-body step is unchanged (12 rounds: 0.991, IQR 0.933–1.035, against an A-vs-A of 1.020). A first
   6-round run without a control showed 0.92: noise. Inlining more (threshold 17 or 30) is 15–18% slower, though a
   microbenchmark says a temp is worth inlining up to ~5 uses. *(measured; css-physics HISTORY)*
6. **paint: CSS can tell a pending probe from a failed one.** An `<img alt>` probe is 0×0 while pending, the alt
   text's box (here 64×20) after a miss of any kind, and (v+1)×1 on a hit. That makes staged, frequency-ordered
   probing and an immediate per-cell retry possible. It saves 15 requests per cell *written* with the first-probed
   colour. A never-written cell still pays its 16 probes and the retry, so a mostly blank canvas saves little.
   *(measured tri-state; savings derived)*
7. **Dead ends confirmed:**
   - AAT `morx` is 4.5× faster than equivalent GSUB in HarfBuzz but stripped by Blink's OTS config.
   - `@function` still costs +1.3–1.6 µs per call in 153.
   - HarfRust (`--enable-blink-features=HarfRustShaping`) runs the CPU font ~24% slower, but has no 16,384-subtable
     cap.

   *(measured; research for the OTS config)*

---

## 1. Inventory: the primitives and where they're used

| # | Primitive | Mechanism | css-physics | js-minus-js | paint |
|---|---|---|---|---|---|
| P1 | View-timeline register | value → element offset in a scroller → `view-timeline` progress → `@keyframes` into a registered property; fresh every pass | 13 per body, 2 per element (top/left), `.ts` scope nests | CPU registers, scan registers, token registers, latch-cell registers | — |
| P2 | Size-container readback | `width: anchor-size(…)` on a fixed size container; `100cqi / 1px` inside; restyles inside layout | — | 76 state readers, 4 read ports, console | the probe-row reader (`--bv`) |
| P3 | Remembered-size RAM | `content-visibility: hidden` + `contain-intrinsic-size: auto`; visible for one pass to write; updated at the RO step | — | 16K RAM leaves, decode-tree writes, sparse `display: none` groups | — |
| P4 | Transition latch | `transition: --x 0s <1e6 s delay>` holds a value | — | editor latch cells, RAM group `--live` | — |
| P5 | Registered props + `calc()` | typed values, inherited down chains; ~1.3 µs const, ~1.3–2.6 µs calc, ~0.1 µs per extra token | the whole solver (175k props at 48) | the compiler DSL (67k temps), the trap service (~900 props) | — |
| P6 | `@container style()` | rule gating and dispatch, evaluated per rule per restyle | gates per body/pair/plane, owner names `b{i}` | parser variants per (mode, token) | — |
| P7 | `if()` mux | value selection by `style()` tests, used to choose names | `--A{i}` container names | anchor-name muxes (128 tests per port) | pixel colour |
| P8 | Nested chains | one element per step, state inherited; `display: contents`; XHTML past 512 | one level per GS round | 1,561 character + 401 token levels | — |
| P9 | GSUB font CPU | lookups aliased S times in the LookupList; GDEF marks + mark-filtering sets | — | 32 micro-cycles per shaping, ~1,274 glyph cells | — |
| P10 | Text as I/O | counters → `@counter-style` → glyphs; span widths read back | — | state line, console | — |
| P11 | Variable-axis lookup switching | `font-variation-settings` → FeatureVariations → lookup set; GPOS kern cancels a sentinel | — | editor scan (`SCAN` axis) | — |
| P12 | Passes per frame | stale view timelines re-run style+layout | 2 steps per frame | ≤ 2 issues per frame | — |
| P13 | Anchors | `anchor-name` + `anchor-size()`; last in tree order wins | pointer marker | RAM reads, overlays, labels | probe row |
| P14 | Pointer/touch | `:hover` + `anchor-name`; scroll handles; deferred layout snap | grab, touch drag | — | `<object>` width as palette input |
| P15 | Documents and fetches | `<object>` navigation = new fetch memo; `Use-As-Dictionary` store; dcz probes; sentinels | — | — | the whole store |

---

## 2. Alternatives, primitive by primitive

### P1. View-timeline registers

| Alternative | Strengths | Weaknesses | Status |
|---|---|---|---|
| **Pass pump** (finding 1) on top of P1 | D + 2 useful passes per frame for a handful of tiny elements; no change to the registers | each pass costs a full style+layout; gains only fixed per-frame cost (settle pass, paint, animation service) | measured: js-minus-js UI page K = 3, run 8.4–8.5 s vs 8.9–9.1 s (~6%); CPU-only page no gain (57 vs 58 ms per shaping) |
| Size-container readback (P2) | same pass, inside layout; chains (finding 3) | the dependent subtree restyles inside layout; only 2 values per container | measured (chain) |
| Remembered size as a register | survives `display` toggles; per pass with the pump | one write per visible pass | measured (finding 2) |
| Anchor-positioned registers | no scrollers | ~5 ms layout per frame (141); the anchor query merges every anchor each pass | css-physics HISTORY |
| Scroll-snap position as a register | snapping is an argmin over targets; the root scroll survives reloads (paint HISTORY) | re-snaps once per layout at best, deferred during gestures | untested as a register |
| `timeline-trigger` / `animation-trigger` (146) | edge-triggered latches without the 1e6 s trick | only fires on timeline-range entry/exit; unknown cost | researched, untested |
| `scroll-state()` queries | cheap booleans (snapped, stuck, scrollable) | one bit, no values | researched |

### P2. Size-container readback

The fixed alternatives: anchor-size() is only valid in an abspos element's sizing/inset properties, so a length can
only become a number through `cq*` units or a view timeline. **`progress()`** (138) is ~23% cheaper than
`clamp((v − lo) / (hi − lo), 0, 1)` *(measured: 2,000 props, 2.48 vs 3.21 ms)*: worth using where registers are
normalised. **Grid tracks** (P7 below) are a second in-layout reader that needs no anchors at all.

What the trace says it costs today in js-minus-js *(measured, FizzBuzz mid-run, invalidation trace)*:
- **1,331 element restyles per pass, 61% inside layout.**
- `.vp3`, the innermost read port, holds ~600 inherited next-state properties. Its ~150 children (readers, `#state`,
  `.head`, `.regs`) restyle inside layout every pass.
- `#state`'s ~120 spans restyle twice per pass (once in recalc, once in layout).
- The 128 console readers under `#clkw` restyle every pass although the console changes on a few passes in a hundred.

### P3. Remembered-size RAM

| Alternative | Strengths | Weaknesses | Status |
|---|---|---|---|
| Same leaves, **inside the pump nest** | writes readable the next pass (finding 2), so one channel set can serve every issue of a frame | the leaves must sit deeper than the nest's deepest element; `content-visibility: auto` on the nest would contain the anchors, but `visible` works | measured |
| **Grid-track RAM**: cells as grid items, row height = value, ports placed with `grid-row: var(--a)` | no `anchor-name` on 16K leaves (each rendered anchor costs ~1.5 µs per layout, ENGINE_NOTES 40); ports ~15 µs each, so many ports are cheap | a grid re-lays out O(rows) when a port moves (~3 ms per pass at 4,096 rows); overlays become `max()`, not "last wins" | measured (ports), untested as RAM |
| Dictionary store (paint) | persists across reloads | K requests per read, seconds of latency | paint |
| Transition-latched cells | pure style | per-cell addressing rules; one transition start per frame | untested for RAM |

### P4. Transition latch

The latch is frame-granular: a transition starts from the previous frame's value. That is why the editor scan is
frame-locked (one column per frame, 64 frames, ~1.2 s). **Alternative: remembered-size latch cells inside the pump
nest**, written and held per pass. With several passes per frame, the scan could take several columns per frame.
*(untested; the per-pass write is measured)*

### P5. Registered properties + `calc()`

Measured on 2,000-prop pages (one element under an animated parent, as css-physics mk2.py; ms per frame of style):

| Variant | ms | Per prop |
|---|---|---|
| inline `calc(var(--t) * k)` | 2.65 | 1.3 µs |
| `@function --f1(--x, --k)` doing the same | 5.81 | +1.6 µs per call |
| ~10-op expression inline / as `@function` / `@function` with 2 locals | 7.88 / 10.45 / 12.28 | +1.3 µs per call, +0.9 µs per local |
| `clamp(0, (v − lo) / w, 1)` / `progress(v, lo, hi)` | 3.21 / 2.48 | −23% |
| 1,000 temps × U consumers vs temp inlined (U = 1, 2, 3, 5) | 3.69/1.97, 5.53/3.98, 6.83/5.71, 10.44/9.94 | inlining wins up to ~U = 5 |

Alternatives considered:
- **`@function`**: dead. It's slower, results aren't cached, recursion is impossible (cycle detection is keyed on the
  function), and any call makes the element skip the matched-properties cache. *(measured; researched)*
- **Unregistered properties** (0.5 µs) are only token substitution. A registered property is what materialises a value.
  Inlining (above) is the profitable form of "unregistered".
- **Typed `attr()`** (133): per-element numeric constants without per-element rules, but it bypasses the
  matched-properties cache. *(researched)*
- **`sibling-index()`**: free per-element indices (js-minus-js's scan already uses it).
- **Vector lanes**:
  - A registered `<length-percentage>` keeps `px` and `%` apart: 2 lanes for linear operations only.
  - Colours carry 4 channels through `color-mix()` and relative colour syntax, but no CSS function turns a channel
    back into a `<number>`.

  Both are dead for feedback loops. *(reasoning)*
- **`random()`** ships in 156, not 153. **`ident()`** is test-only, so `var(ident(…))` dynamic indexing is still out.
  *(researched)*

### P6. `@container style()` gating

The cost table is in css-physics BENCHMARKS §2. Alternatives:
- Owner names (in use).
- `display: none` subtrees, which cost nothing per pass (js-minus-js groups).
- Static-class selectors: a rule whose selector misses the element's id/class buckets is never visited. That's free,
  but static, so it only helps for gates known at build time.

The N² floor in css-physics is rule *visits* (about 3 per pair, 0.67 µs each in a one-body drag). Nothing here
removes visits without moving the pair loop out of the cascade; see contact slots below.

### P7. `if()` muxes for dynamic names

| Port design (4,096 cells, every port's address changes every frame) | 4 ports | 32 ports |
|---|---|---|
| two-level 64 × 64 `if()` → `anchor-size()` (js-minus-js) | 5.28 ms | 23.76 ms |
| `grid-row: calc(var(--a) + 1)`, port stretched, `100cqh` | 4.83 ms | 5.19 ms |

At 1,024 cells, grid ports cost ~15 µs each (128 / 512 / 2,048 ports: 2.6 / 7.9 / 33.8 ms over baseline) against
~200 µs for the mux (128 ports: 26.5 ms). *(measured, all reads exact)*

- **css-physics contact slots** (its open idea): 64 bodies × 4 slots × 13 values ≈ 3,300 ports ≈ 50 ms per pass. The
  pair-rule floor they would replace is ~4 ms (one-body drag) to ~36 ms (pile). Break-even is around 400 bodies.
  **Don't build it at ≤ 96 bodies.**
- **js-minus-js read ports:** grid placement makes extra ports nearly free (prefetch, two lines per service) and lets
  the RAM drop its 16K `anchor-name`s.

### P8. Nested chains

There is no alternative for inheritance-carried state. One new variant: **size-container chains** carry state
*within one layout pass* (finding 3). Each level must be a separate containing block: nested `position: absolute`
readers make every reader the containing block of the next, and the spans stop being acceptable anchors (measured:
garbage). Nested `fixed` readers under a `contain: layout` wrapper per level work.

### P9. The GSUB CPU

| Alternative | Strengths | Weaknesses | Status |
|---|---|---|---|
| **AAT `morx`** state machines | one subtable carries state across the whole run (no 64-glyph context); **9.6–10.7 ns per glyph per pass vs 40–44 ns for the equivalent GSUB rsub ripple (4.5×)** | Blink's OTS passes only GSUB/GPOS/GDEF/COLR/CPAL/CBDT/CBLC/sbix/CFF2/STAT/variation tables/BASE. `morx` is dropped: the font renders unshaped | measured (uharfbuzz + Chrome); researched (`BlinkOTSContext::GetTableAction`) |
| Graphite | — | not built (no `OTS_GRAPHITE`, `hb-graphite2.cc` excluded) | researched |
| **HarfRust** shaper (`--enable-blink-features=HarfRustShaping`, off in 153, test-only on main) | **no subtable cap**: 18,000 aliased subtables ran exactly, where HarfBuzz drops the whole GSUB | the CPU font runs FizzBuzz to HALT in 9.0 s vs 7.3 s (~24% slower), output exact | measured |
| HarfBuzz WASM shaper | real loops | not in any shipping browser | ENGINE_NOTES 32 |
| avar2 two-input LUTs | arithmetic at style time via `1ch` | a new instance per value (47–106 µs) | css-physics BENCHMARKS §3 |
| MATH-table stretchy operators (MathML) | glyph assembly computes `ceil(target / part)`; capped at 32,768 glyphs; observable in layout | odd I/O; one division per operator | researched, untested |

Corrections to the repo's notes:
- **The 16,384 cap is HarfBuzz's sanitizer (`HB_SANITIZE_MAX_SUBTABLES`), not OTS.** It counts every LookupList
  reference.
- **Past the cap, current HarfBuzz drops the entire GSUB**, not the last lookups: 15,000 subtables count exactly,
  18,000 render unshaped, in both uharfbuzz and Chrome *(measured)*. ENGINE_NOTES 26 and js-minus-js CLAUDE.md say
  "drops the last lookups".
- HarfBuzz merges a lookup index listed twice in one stage, so aliasing needs distinct LookupList entries (as `otl.py`
  does). *(researched)*

### P10. Text as I/O

**One padded `numeric` counter per value** instead of one counter per digit doesn't fit:
- Every digit position has its own glyph type (HPC0–HPC3).
- The 320 cache-word digits are interleaved by nibble across the 4 words of a line.

A font redesign (a generic digit type and a positional pre-stage) would save ~1 ms per pass. Low value.
*(measured layout; estimate)*

### P11. Editor scan

The scan advances one column per frame because the latches are transitions. Two untested alternatives:
- **Pack two characters per sentinel** (95² = 9,025 < 32,767 font units), and use `::before` as well as `::after`.
  That's up to 4 characters per line per frame.
- **Per-pass latches** (P4 above).

Either could take the 1.2 s sweep toward 0.3 s.

### P12. Passes per frame

| Option | Passes per frame | Status |
|---|---|---|
| Stale view timelines (today) | 2 useful + a settle pass | — |
| **Pass pump**, D nested remembered-size elements | D + 2 | measured |
| Siblings instead of a nest | 3 (the RO loop needs increasing depth) | measured |
| Anchor `position-try` flipping per pass | 2 (no effect) | measured |
| **Chained shapings** in one layout | K shapings in 1 pass | measured (toy) |

ENGINE_NOTES 37 ("more than two issues per frame run on stale state; 3 or 4 gave duplicates") is probably the
write-channel cap, not staleness. `gen_fvm4.py` sets `CH = 'ABCD'[:2 * K]`, so K = 3 or 4 had no channels for its
extra issues. With channels widened (`survey/exp/patches/gen_fvm4-kissues.patch`), K = 3, 4, 6 and 8 all halt with the model's exact 476 steps and
correct output. *(measured)* The pump is what makes the extra issues actually run. K = 8 is slow (13 s vs 6.5 s)
because 16 channels multiply the RAM trees' per-pass properties (90 ms recalcs). Finding 2 is the way out.

### P13–P15

- **Pointer and touch:** no better primitive found.
  - Already dead ends (css-physics HISTORY): `:has()` hover, `:active` on sliders, `scroll-state(snapped)`.
  - Researched, irrelevant: Early Hints only act on preconnect, preload and modulepreload.
- **paint's store:** alternatives to dictionaries, all worse:
  - root scroll: 48 bits, synchronous;
  - HTTP cache timing: flaky;
  - `:visited`: unreadable by design;
  - cookies: need server logic, against the static-hosting rule;
  - URL fragment: one id at a time, written by the user.
- **paint's reads:** the new primitive is the `<img alt>` tri-state (finding 6). How it changes reads:

| Canvas (480 cells) | Today | Staged: one likely colour first, the other 15 on a miss | Saving |
|---|---|---|---|
| 20% written (10% with the first-probed colour), 80% never written | 7,680 + 6,144 retry = 13,824 | 13,824 − 48 × 15 = 13,104 | 5% |
| fully written, 60% with the first-probed colour | 7,680 | 288 + 3,072 = 3,360 | 56% |

A never-written cell misses every probe and pays the retry, whatever the order, so the saving is 15 requests per cell
written with the first-probed colour. Real canvases are mostly never-written paper.

Completion is visible per cell: every probe is non-zero once it has finished. So the retry can start the moment a
cell's probes have all missed, instead of after the two-sentinel timer, and loads fall under Cloudflare's 10,000
requests per connection far more often. The cost is one extra round trip for non-background cells. A network
failure still looks like a miss, so "never written" vs "read failed" stays ambiguous. *(derived from the measured
tri-state)*

---

## 3. Recommendations, by expected payoff

### js-minus-js

1. **Chain shapings inside one layout pass** (finding 3). This is the biggest lever.
   - Today a shaping step costs ~74 ms, of which ~21 ms is HarfBuzz. A chained level adds ~5 ms (toy) plus the
     service logic re-run inside layout. 8 levels per frame would roughly double to 2.5× execution speed *(estimate)*.
   - Requirements: a `contain: layout` wrapper per level, fixed readers, XHTML.
   - Gating: a write-back or a miss on a written line must end the chain for that frame (remembered sizes don't change
     inside one pass), as `--go` gates issues today.
   - First step: chain the real `f4cc_16` font twice under one pass with no trap service and time it.
2. **Cut the in-layout restyles** (P2): 1,331 per pass.
   - Move the readers, `.head` and `.regs` out of `.vp3`. Fixed elements can sit anywhere after `#state` in tree order.
   - Make the next-state properties `inherits: false` where only `.vp3` reads them.
   - Stop the 128 console readers restyling every pass (for example, show them only on passes that print).
   - Each step is cheap to A/B with `halttime.js`.
3. **Pass pump + per-pass RAM** (findings 1–2): put the RAM trees under a nest of ~K + 2 remembered-size elements,
   drop to one channel set, run K = 4–6 issues per frame. Measured so far: correct at K = 3–8, ~6% faster at K = 3 with
   per-issue channels.
4. **Grid-placement read ports** (P7): RAM leaves without `anchor-name`, extra ports for next-line prefetch.
5. **Faster editor sweep** (P4, P11): two characters per sentinel, or per-pass latches.
6. **Compile-chain animations keep running after the compile**: ~5,600 `serviceAnimations` per frame, ~10 ms per frame
   (~5%). Worth a way to retire the chain's sources once the code words are committed.
7. Fix the notes: ENGINE_NOTES 26 (the whole GSUB is dropped), 37 (channel cap, not staleness), 14 (per pass with a
   pump).

### css-physics

1. ~~Ship multi-use inlining~~: no effect on re-measurement with an A-vs-A control, and more inlining is slower
   (finding 5; HISTORY).
2. **`progress()`** in register positions: trivial, a fraction of a millisecond.
3. **Close the contact-slot idea** for ≤ 96 bodies (P7 numbers): reading a partner's value costs ~15 µs per value even
   with grid ports.
4. **Pass pump: low value here.** Per-frame overhead is ~1 ms at 48 bodies, so more steps per frame only lengthen
   frames. Worth a try in Firefox (one step per frame today), but Firefox re-samples timelines only next frame (bug
   2048416), so it may not help. *(untested)*
5. Don't use `@function`.

### paint

1. **Staged probing with `<img alt>` probes** (finding 6). Probe one likely colour first, show the other 15 only on a
   miss, retry per cell on all-miss, and drop the sentinel chain. It saves 15 requests per cell written with that colour
   and the 3 s retry wait. Never-written cells cost the same as today, so the gain on mostly blank canvases is small.
   - Check that the alt box is the same size everywhere: pin its font and box with CSS, or use a fixed-size inline
     box.
2. Early Hints won't help: Chrome ignores `rel=compression-dictionary` in a 103. *(researched)*

### Repo-wide

- **`engine/check.js` probes to add:** pass pump (D + 2 passes), per-pass remembered sizes, morx stripped, GSUB
  dropped past 16,384 subtables, `<img alt>` tri-state.
- **Watch item:** HarfRust. If Chrome switches shapers, the CPU font loses ~24% but can raise S (S = 64 is −24%
  shapings in the model).
- **`engine-costs` cases to add:** `@function` and `progress()`.

---

## 4. Far-fetched ideas left untested

- **Flex `order` as a sort.** `order: var(--key)` sorts items natively and the positions read back as ranks. With
  lo/hi sentinel items per body, a body's neighbour count along an axis is a rank difference: a sweep-and-prune
  broadphase in O(N log N). css-physics's near tests are only ~17% of a step and pair identities still need per-pair
  work, so little payoff below a few hundred bodies.
- **Scroll snap as argmin.** The snap target is the nearest snap area, so a "nearest neighbour" can be computed in
  layout. Same readback problem as above.
- **`timeline-trigger`** as an edge detector replacing the 1e6 s latch.
- **MATH-table stretchy operators** for integer division in layout.
- **Cross-site iframes for parallelism:** they get their own processes (css-physics measured 2), but the only
  script-free channel is the iframe's size, parent to child: no way to read a result back.

---

## 5. Reproducing

All from the worktree root (`.claude/worktrees/primitives-survey`). Outputs go to `survey/exp/out/` (not committed).

```bash
# morx vs GSUB (uharfbuzz speed, then Chrome)
cd survey/exp/aat && for m in morx gsub; do python3 mkcounter.py $m 5 ctr_$m.ttf; python3 mkcounter.py $m 256 big_$m.ttf; done
node chrome_morx.js                         # morx 40/70/70 px (unshaped), gsub 60/60/40 px
python3 mkcap.py 5000 cap5000.ttf && python3 mkcap.py 6000 cap6000.ttf && python3 mkcap.py 5 cap5.ttf && node capcheck.js
cd ..
# @function, progress(), inlining
python3 fn/mkfn.py out/fn && node bench.js --rounds 3 out/fn/*.html
# chained shapings (CB=contain: one containing block per level)
CB=contain python3 chain/mkchain.py 16 76 300 out/chain/con16_r76.xhtml && node chain/check.js out/chain/con16_r76.xhtml
node bench.js --rounds 3 out/chain/*.xhtml
# read ports
python3 index/mkidx.py grid 4096 32 out/idx/g.html && python3 index/mkidx.py mux 4096 32 out/idx/m.html && node bench.js out/idx/g.html out/idx/m.html
# passes per frame, per-pass remembered sizes
for m in base cis nest8 nest32 sib4; do python3 passes/mkpass.py $m out/pass/$m.html; done; node passes/rate.js out/pass/*.html
python3 passes/mkram.py 8 out/pass/ram8d.html deep    # then probe --n --m --lo (max/min lag)
# paint tri-state (starts its own serve.js on 8791/8792)
node paint/imgstate.js
# js-minus-js K issues per frame: wider write channels and RONEST=D, kept as a patch so main's js-minus-js is untouched
cd ../.. && git apply survey/exp/patches/gen_fvm4-kissues.patch && cd js-minus-js && python3 compiler/mkimage.py --ram tests/suite/fizzbuzz.js out/fizz.json
RONEST=6 python3 machine/gen_fvm4.py out/fizz.json ../../../../js-minus-js/build/f4cc_16 out/k4n.html --issue=4
IMG=out/fizz.json node ../../../../js-minus-js/machine/halttime.js out/k4n.html 60
# css-physics inlining
cd ../css-physics && COUNTS=48 PLAIN=1 INL_ONLY1=0 INL_DEPTH=3 python3 src/build3d.py out/m48.html   # vs default p48
```
