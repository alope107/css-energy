# shared/

Harness code used by both projects: launching Chromium, tracing, page probes, A/B timing, motion checks, freezing and
ablation. Only the tools use it. The product pages never run script.

Each project still has its own commands, unchanged (`node tools/tr.js …` in css-physics, `node machine/halttime.js …`
in js-minus-js). They now import what they share from here. This directory has no npm dependencies: `browser.js`
loads `playwright` / `playwright-core` from the project of the tool that runs, so each project keeps its own
`node_modules`.

| File | What it is | Used by |
|---|---|---|
| `js/browser.js` | `profile('physics' \| 'fontcpu')`: `launch()`, `open(browser, file, pageOpts, gotoOpts)`, `fileUrl()`, `envArgs()` | every browser tool. css-physics through `tools/lib/physics.js`, js-minus-js through `tools/browser.js` |
| `js/page.js` | `countFrames(page, ms)`, `vars(page, sel, names)`, `pollUntil()` | css-physics tools |
| `js/trace.js` | `record(page, {categories, browser}, during)`; `durations`, `median`, `bigmed`, `aggregate`, `selfTime`, `saveTrace`; category presets `CATS` | css-physics `tr`, `stylebench`, `sparse`, `grabcen`, `traceagg`, `compframes`; js-minus-js `machine/trace.js` |
| `js/ab.js` | A/B timing: interleaved, rotated rounds of any measurement command, ratios to the first variant with their spread | both (command line) |
| `js/filmstrip.js`, `js/transcheck.js` | motion checks: compositor frames as a contact sheet with a snap-back score; transform-transition continuity | css-physics `tools/filmstrip.js`, `tools/transcheck.js`; js-minus-js `tools/filmstrip.js` |
| `js/freeze.js` | the wobbling-constant clock that freezes a page's state for profiling | css-physics `freeze3.js`, `freezegrab.js` (via `tools/lib/physics.js`) |
| `py/ablate.py` | copies of a page with families of `@container` blocks removed (string- and comment-aware; never overwrites the source, `.xhtml` included) | css-physics `tools/ablate.py`; any js-minus-js page |
| `py/passprof.py` | per-frame passes, style+layout ms and shaping ms from a saved trace | js-minus-js `machine/passprof.py`; css-physics `TRACE=… CAT=… tools/tr.js` |
| `test/` | unit tests (`make test-shared` at the repo root) | |

## Browser profiles

The two projects measure with different Chromium flags, and every number in their `docs/BENCHMARKS.md` was taken with
its own flags. `--disable-gpu` changes the raster and compositor path, so the flags are part of the measurements.

| Profile | Project | npm package | Executable | Flags |
|---|---|---|---|---|
| `physics` | css-physics | `playwright` | `CHROME`, else Playwright's own Chromium | `--no-sandbox` |
| `fontcpu` | js-minus-js | `playwright-core` | `CHROME`, else `@sparticuz/chromium` | `--no-sandbox --no-proxy-server --disable-gpu` |

Tools that used other flags still pass them: `launch({args: [...]})` replaces the profile's flags, and
`launch({extraArgs: envArgs('FLAGS')})` appends. Don't merge the profiles without re-measuring both baselines.

Without `CHROME`, the `physics` profile needs Playwright's own browser build. Playwright 1.64 asks for a newer build
than the devcontainer's v1.63 image ships, so keep `CHROME` set (the devcontainer sets it).

## A/B timing (`js/ab.js`)

```bash
# css-physics: bigmed step cost, 5 rotated rounds
node ../shared/js/ab.js -p bigmed 'node tools/tr.js {} 1500 1500' out/a.html out/b.html
# js-minus-js: FizzBuzz to HALT on CPU-only pages
IMG=img.json node ../shared/js/ab.js -r 3 -p haltMs 'node machine/halttime.js {} 60' a.html b.html
```

Each run is a fresh process. Round r starts at variant r, so load drift hits every variant alike. Read the ratio
column: a swing in machine load cancels out of a ratio taken in the same round. Pass the same page twice to see the
noise floor; an A-vs-A ratio should straddle 1.00. `-p name` takes a JSON field (the js-minus-js harnesses print JSON
lines) or the first number after `name` in text output.

## Changing shared code

Both projects depend on it, so check both:

- `make test-shared` (unit tests, no browser);
- css-physics `bash tools/smoke.sh 16`;
- js-minus-js `make test`, `make l3` and `make l5-smoke`;
- for a change in measurement code (`trace.js`, `page.js`, the profiles): old against new on the same pages, with
  `ab.js`.
