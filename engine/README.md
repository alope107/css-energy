# engine/

Checks of the Chrome behaviour css-physics and js-minus-js are built on. Several facts may be bugs rather than
specified behaviour, and the projects only work while they hold. Run both after every Chrome upgrade (the
devcontainer's Playwright image tag).

```bash
make engine-check     # node engine/check.js: facts, pass/fail, both browser profiles (~20 s)
make engine-costs     # node engine/costs.js: the style-engine cost table against the docs (~2 min, no other browser jobs)
```

paint's facts (which loads register a dictionary, history from cache, ~1,000 frames per page) are exercised by its own
`make test`.

## Facts (`check.js`)

Each probe is a minimal page testing one fact, plus a control that must behave normally whatever the fact (if the
control fails the probe reports BROKEN, so a probe that observes nothing can't pass). Each page shows both sides of its
fact, so a change in Chrome flips a reading.

| Probe | Fact | Who relies on it |
|---|---|---|
| `style-int-256` | `@container style(--v: N)` never matches a calc()-computed registered `<integer>` ≥ 256 (a literal 256 matches) | js-minus-js dispatch values < 256 (ENGINE_NOTES 1) |
| `var-6-digits` | a calc()-computed registered `<integer>`, or any registered `<number>`, keeps 6 significant digits through `var()`: 1048575 → `1.04858e+06` | js-minus-js words \|v\| < 2¹⁹ (ENGINE_NOTES 2); css-physics 6 bodies per digest word |
| `style-bool` | `style(--x)` with no value is true iff a registered `--x` differs from its initial value; an unregistered one iff declared | css-physics `BOOLQ`, the `style(--GIr)` grab bug |
| `style-range` | range queries such as `style(--h > 5)` work | css-physics cost model (BENCHMARKS §2) |
| `if-style` | `if(style(--k: v): a; else: b)` selects by a custom property | js-minus-js `display: if(…)`, read ports |
| `anchor-last` | with a shared anchor name, `anchor-size()` reads the last element in tree order | js-minus-js compiler overlays (ENGINE_NOTES 21) |
| `anchor-hidden` | an element in a `display: none` subtree is no anchor: `anchor-size()` reads the fallback | js-minus-js sparse RAM (ENGINE_NOTES 42) |
| `html-nesting-512` | the HTML parser stops nesting at 512; XHTML nests as deep as the markup | js-minus-js pages are XHTML (ENGINE_NOTES 19) |
| `font-resets-fvs` | the `font` shorthand resets `font-variation-settings` declared before it | both |
| `play-state-base` | `animation-play-state` computed from an element's own animated property doesn't pause it (read from the base style) | js-minus-js (ENGINE_NOTES 9) |
| `touch-snap-defer` | a scroll-snap container re-snaps after a layout change at once, except while a scroll gesture is active anywhere on the page: then when it ends (`LocalFrameView::ShouldDeferLayoutSnap`) | css-physics touch: the follower `#FO` (ARCHITECTURE.md "Touch") |
| `scroll-axis-lock` | `scroll-axis-lock: none` stops a touch drag that starts nearly horizontal from locking to that axis | css-physics touch handles |
| `touch-3d-scroll` | a touch drag scrolls a 3D-transformed scroller by the finger's movement unprojected onto its plane (offset = screen movement / on-screen scale) | css-physics touch handles: the drag in world units |
| `quirks-lax-css` | a quirks-mode page applies a same-origin stylesheet whatever its Content-Type; a standards-mode one only `text/css` or none | js-minus-js: a `data:` child reading CORS JSON as CSS (57); the NET modem's answers until 2026-10-22 (ENGINE_NOTES 50) |
| `responsive-iframe` | `frame-sizing: content-height` sizes an iframe to an opted-in child's content height, no lower than its height at the child's load (a flag in 153) | js-minus-js: a `data:` child's return channel (51, 57) |
| `fragment-scroll` | a same-origin child navigated to `#t` scrolls the page's `overflow: hidden` box around it to `#t`, on both axes, through an `overflow: clip` box | js-minus-js NET modem's answers (56) |
| `var-ident` (watch) | `var(ident("--m" var(--k)))` is unsupported; if it ships, both projects gain dynamic indexing | — |

Chromium 153.0.8010.12 (2026-10-14, and on the mini PC 2026-10-17): every fact holds under both profiles; `var-ident`
is still unsupported. The touch facts (2026-10-18) hold under both; they drive real gestures (CDP touch on a
touch-emulated phone viewport goes through Chromium's gesture recognizer).

Not probed (they need a running engine): view-timeline and remembered-size update rates, the third style pass, the
transition latch, restyles inside size containers (js-minus-js ENGINE_NOTES 14–16, 37–38, 23, 34, 41).

## Costs (`costs.js`)

Re-measures the microbenchmarks behind css-physics `docs/BENCHMARKS.md` §2 (same templates as
`css-physics/experiments/costs/`, measured like `tools/stylebench.js`). The documented values in `costs.js` are the
mini PC's from 2026-10-17; per-unit costs that drift past half the documented low or twice the high are flagged.
After a real change, update css-physics BENCHMARKS §2 (js-minus-js ENGINE_NOTES 7 cites it).
