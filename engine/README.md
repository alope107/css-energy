# engine/

Checks of the Chrome behaviour both projects are built on. Several of these facts may be bugs rather than specified
behaviour, and the projects only work while they hold. Run both checks after every Chrome upgrade (the devcontainer's
Playwright image tag).

```bash
make engine-check     # node engine/check.js: facts, pass/fail, both browser profiles (~20 s)
make engine-costs     # node engine/costs.js: the style-engine cost table against the docs (~2 min, no other browser jobs)
```

## Facts (`check.js`)

Each probe is a minimal page that tests one fact. It also checks a control on the same page: a case that has to behave
normally whatever the fact. If the control fails, the probe reports BROKEN, so a probe that observes nothing can't
pass. Every page also shows both sides of its fact (a value on each side of 256, a first and a last anchor), so a
change in Chrome flips a reading.

| Probe | Fact | Who relies on it |
|---|---|---|
| `style-int-256` | `@container style(--v: N)` never matches a calc()-computed registered `<integer>` of 256 or more. (A literal 256 does match.) | js-minus-js: dispatch values stay below 256 (ENGINE_NOTES 1) |
| `var-6-digits` | A calc()-computed registered `<integer>`, or any registered `<number>`, keeps 6 significant digits when it crosses `var()`. 1048575 serializes as `1.04858e+06` and reads 1048580 in `calc()`. | js-minus-js: machine words stay \|v\| < 2¹⁹ (ENGINE_NOTES 2); css-physics: 6 bodies per decimal digest word |
| `style-bool` | `style(--x)` with no value is true iff a registered `--x` differs from its initial value, any value, not just 1. An unregistered `--x` is true iff declared. | css-physics: `BOOLQ` 0/1 gates, and the `style(--GIr)` grab bug |
| `style-range` | Range queries such as `style(--h > 5)` work. | css-physics cost model (BENCHMARKS §2) |
| `if-style` | `if(style(--k: v): a; else: b)` selects by a custom property. | js-minus-js: `display: if(…)`, read ports |
| `anchor-last` | When several elements share an anchor name, `anchor-size()` reads the last one in tree order. | js-minus-js: compiler overlays override RAM (ENGINE_NOTES 21) |
| `anchor-hidden` | An element in a `display: none` subtree is no anchor: `anchor-size(--n width, fallback)` reads the fallback. | js-minus-js: sparse RAM groups (ENGINE_NOTES 42) |
| `html-nesting-512` | The HTML parser stops nesting at 512 elements (600 nested divs: the innermost sits at depth 513); XHTML nests as deep as the markup. | js-minus-js: pages are XHTML (ENGINE_NOTES 19) |
| `font-resets-fvs` | The `font` shorthand resets `font-variation-settings` declared before it. | both (css-physics CLAUDE.md, js-minus-js ENGINE_NOTES 8) |
| `play-state-base` | `animation-play-state` computed from an element's own animated custom property doesn't pause its animations: Blink reads it from the base style. | js-minus-js: the compiler's sources keep running (ENGINE_NOTES 9). The original probe was lost; this is the literal reading. |
| `var-ident` (watch) | `var(ident("--m" var(--k)))`, dynamic property names, is not supported. If it ships, both projects gain dynamic indexing. | css-physics `experiments/ident` |

Results on Chromium 153.0.8010.12 (devcontainer), 2026-10-14: every fact PASS under both profiles, and `var-ident`
is still unsupported.

Observed while writing `var-6-digits`, and not a fact either project relies on yet: a plain `--y: var(--x)` from a
calc()-computed registered `<integer>` of 10⁶ or more into another `<integer>` is invalid at computed-value time. Its
serialization is `1.04858e+06`, not an integer token, so `--y` takes its initial value. A literal `--x: 1048575` keeps
all 7 digits. js-minus-js's ENGINE_NOTES 2 has the details.

Not probed (they need a running engine, not a minimal page):
- view-timeline and remembered-size update rates (js-minus-js ENGINE_NOTES 14–16);
- the third style pass (37–38);
- the transition latch (23);
- the costs of restyles inside size containers (34, 41).

## Costs (`costs.js`)

These re-measure the microbenchmarks behind css-physics `docs/BENCHMARKS.md` §2. js-minus-js's ENGINE_NOTES 7 and
css-physics's CLAUDE.md cite them. The pages use the same templates as `css-physics/experiments/costs/mk2.py`,
`mk_gating.py` and `part_styleform.py`. Each is measured as `css-physics/tools/stylebench.js` measures (median style
pass over 1.5 s, 3 interleaved rounds). Per-unit costs that drift past half the documented low or twice the high are
flagged.

First run, 2026-10-14 (Chromium 153.0.8010.12, physics profile), against the 2026-10-13 numbers:

| Case | Measured | Documented |
|---|---|---|
| registered `<number>`, constant | 1.45 µs per prop | 1.57 |
| registered, `calc(var(--t) * k)` | 2.12 | 2.15 |
| unregistered, constant | 0.52 | 0.49 |
| rule under a present container name, no `style()` | 0.15 µs per rule | 0.07–0.16 |
| present name + false `style(--g: 1)` | 0.56 | 0.56–0.74 |
| present name + false `style(--g)` | 0.33 | 0.40–0.41 |
| present name + false range `style(--h > 9)` | 1.56 | 1.57 |

Ubuntu mini PC (Intel i5-12600H), 2026-10-17, same Chromium and profile; `make engine-check`: all facts hold. The
documented column in `costs.js` now holds the mini PC's numbers from css-physics `docs/BENCHMARKS.md` §2:

| Case | Measured | Old documented (arm64 VM) |
|---|---|---|
| registered `<number>`, constant | 1.28 µs per prop | 1.57 |
| registered, `calc(var(--t) * k)` | 2.63 | 2.15 |
| unregistered, constant | 0.48 | 0.49 |
| rule under a present container name, no `style()` | 0.22 µs per rule | 0.07–0.16 |
| present name + false `style(--g: 1)` | 0.83 | 0.56–0.74 |
| present name + false `style(--g)` | 0.50 | 0.40–0.41 |
| present name + false range `style(--h > 9)` | 1.67 | 1.57 |
