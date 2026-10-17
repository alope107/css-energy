# rigid3d.css

A 3D rigid-body physics engine (boxes and spheres in a tray) that runs entirely in Chrome's style engine. `src/gen3d.py` generates the CSS; `src/build3d.py` builds pages. Read `docs/ARCHITECTURE.md` before changing the generator; `docs/BENCHMARKS.md` has the measured cost model; `docs/HISTORY.md` lists what already failed (check it before proposing an idea) and, at its end, the open ideas not yet tried.

## Hard rules
- IMPORTANT: generated pages contain **no JavaScript**, ever, unless the user explicitly asks. JS is fine in `tools/` and `experiments/` (test harnesses only).
- Chrome first, and Firefox 159+ (158 with `layout.css.scroll-driven-animations.enabled`) must keep working: run `BROWSER=firefox bash tools/smoke.sh 16` too after generator changes. Chrome's speed wins any trade-off; Firefox-only fixes go in `@supports (-moz-appearance: none)` blocks (ARCHITECTURE.md §6). Speed matters; CSS payload size does not (but load time does).
- Verify your own work in headless Chromium and report numbers or screenshots as evidence. Don't ask the user to test something you can test.
- Don't open or `cat` generated pages: they're 1–30 MB. Use grep, Python or the tools.

## Setup
- Python 3.10+ (stdlib only for `src/`); `pip install fonttools` for `experiments/fonts`.
- `npm install && npx playwright install chromium`. Tools use Playwright's Chromium, or set `CHROME=/path/to/chrome`; if Playwright's own build isn't installed (the npm package is newer than the devcontainer image), they fall back to the image's `/usr/local/bin/chromium` and say so. Tools resolve page paths against the cwd: run from the repo root.
- The tools share their harness code with js-minus-js through `../shared/` (`shared/README.md`): the launcher (profile `physics`: `--no-sandbox`, the flags every number in BENCHMARKS.md was taken with), tracing, motion checks, ablation. What only this project's tools share is in `tools/lib/physics.js` (camera projection, BODYINFO, freezing). After changing either, run `make test-shared` at the repo root and `smoke.sh`.
- Firefox for the tools: `BROWSER=firefox` (evaluate-based tools only: smoke, floatcheck, grabtest, perf3, …; the tracing ones need Chrome). It uses Playwright's Firefox, else the newest `/ms-playwright/firefox-*` of the devcontainer image, or `FIREFOX=/path`. **Don't `npx playwright install` in the devcontainer:** it garbage-collects the image's other browsers, `/usr/local/bin/chromium`'s target included (restore with `npx playwright@1.63.0 install`).
- avar2 needs Chrome 148+. Chromium 153 for Linux: `npm i @sparticuz/chromium@153.0.0`, then `node -e "require('@sparticuz/chromium').default.executablePath().then(console.log)"`. Launch flags: `--no-sandbox --no-zygote --single-process --use-angle=swiftshader --enable-unsafe-swiftshader`; one page per browser in single-process mode.
- `make engine-check` at the repo root re-checks the Chrome behaviours this engine depends on (6-digit `var()`, boolean `style()`, the `font` shorthand, …; `engine/README.md`). Run it after any Chrome upgrade.

## Commands (repo root)
- Debug build (readable names + BODYINFO, which the tools need): `COUNTS=16 PLAIN=1 python3 src/build3d.py out/p16.html` (`SCENE=tower|rain|stack`, `NBOX_FIX=4` for 4 boxes and the rest spheres)
- Smoke and regression tests (pass/fail, ~3 min): `bash tools/smoke.sh 16`. Run it after every generator change. Besides the physics check it runs `statcheck.py` (every scene declares every body's start state; boolean gates only on 0/1 flags), `floatcheck.js` (no body asleep in mid-air, on load or after switching scenes) `grabtest.js` (dragging one body moves no other) and `overlaycheck.js` (the grab ring, pin and tether follow the drag). Each of these guards a bug that shipped.
- Step cost: `node tools/tr.js out/p16.html 1500 1500`; compare variants with `bash tools/bench.sh 3 a.html b.html`, or with ratios and their spread: `node ../shared/js/ab.js -p bigmed 'node tools/tr.js {} 1500 1500' a.html b.html` (pass one page twice for the noise floor)
- User-level fps (chaos/settle/idle/drag/hold): `node tools/perf3.js out/p48.html`
- Profile one step: `node tools/freeze3.js out/p48.html 4000 FZ out/p48.html`, then `python3 tools/ablate.py out/FZ_p48.html pairs='--(tcp|np|p\d+_\d+(uA|uB|ov))' all=.`, then `tr.js` on each
- Published site: `bash tools/make_site.sh` (the default build into `site/`, with 24 as the default page; the CSS is split into ≤14 MB files)
- Motion checks: `node tools/filmstrip.js page.html out.png [delay] [dur]` (compositor frames as a contact sheet, plus a snap-back score); `node tools/transcheck.js page.html` (transform transitions must restart where the running one was, within one frame's motion along the path; `--selftest-ok` must pass, `--selftest-bad` and `--selftest-small` (10 px off the path) must fail).

## Working style for performance work
- Hypothesis → microbenchmark or freeze+ablate → change → short tests at 16–32 bodies → validate at 48/64 only now and then (a 64-body build takes about 30 s, and its runs are slow).
- Anything that changes how things move (transitions, animations, interpolation) needs a motion check, not just screenshots and fps: run `filmstrip.js` on it and the unchanged page, look at the contact sheet, and compare the snap-back scores. A settled screenshot and a 60 fps draw count both looked perfect on a page whose bodies jumped back and forth.
- Timings are noisy: interleave repeats and compare relatively. Sanity-check that a change kept physics correct (`smoke.sh`, `sleepy.js`) before reporting a speedup.
- Record every new measurement in `docs/BENCHMARKS.md` and every dead end, with its reason, in `docs/HISTORY.md`.

## Non-obvious gotchas
- `var()` of a registered number keeps only **6 significant digits**; the wake digests rely on this (6 bodies per decimal word).
- `@container` rules with an **absent** container name are cheap only at shallow depth: the lookup walks every ancestor and scans its name list (about 0.2 µs + 0.6–0.9 ns × depth × names; about 0.2 + 0.01 × depth µs in the engine). A present name costs 0.2 µs, `style(--flag)` 0.5 µs, `style(--flag: 1)` 0.8 µs, a range query 1.7 µs (mini PC, 2026-10-17). Gate with owner names (`b{i}`), and put `container-name: var(--AN)` on **every** level: Chrome only re-matches style-container-dependent rules for direct children. Nested queries evaluate the innermost first.
- `style(--x)` (no value) on a registered property is, in Chrome, true iff its value differs from the initial value (in Firefox: always); `BOOLQ=1` gates 0/1 flags with it (off by default, for Firefox). Never for a multi-valued flag: `style(--GIr)` as body 0's grab gate was true whenever any body was held, so every drag also pulled body 0 (the generator now skips flags tested against other values).
- Scene start states cascade: the first scene's `#INI` rule is overridden by the selected scene's, so every scene rule must declare every body's `--isc` (start sleep counter), or a body keeps another scene's "asleep" and hangs in mid-air. Test scene switches with a real press (~150 ms): an instant click flips the radio without the reset.
- CSS math functions (`mod`, `round`, `pow`) are dear: a digit extraction costs about 5 µs. Anything computed per sleeping body per pass kills the sparse regime; charge awake bodies instead (the digests do).
- Spatial cells were measured and lost (`CELLS=1` builds them; HISTORY.md). The N² floor is the rule visits (about 3 per pair), not the near tests.
- `freeze3.js` wobbles every register: a frozen page's base is 2–3× the live base. Compare frozen variants with each other only.
- Sparse-regime benchmark: `SCENE=field TRAY=2 FIELD_GAP=30 COUNTS=64 PLAIN=1 python3 src/build3d.py out/g64.html` then `node tools/sparse.js out/g64.html 64 c`; freeze mid-drag with `BODY=k node tools/freezegrab.js`.
- Gauss–Seidel order: tray planes **first**, then pair rounds. Planes-last leaves stacks with phantom velocities that never sleep.
- Keep the `.ts` timeline-scope wrappers **above** `#RB`. Inside `.rz`, rendering vanishes.
- The camera constants (`PERSP`, `TILT`, `CAM_TY`, `CAM_DIST`) are duplicated in `gen3d.py`, `ui3d.css` (as placeholders filled by build3d) and `tools/lib/physics.js` (the tools' projection). Change all of them together.
- RATE below 90 doesn't settle piles. Sleep is tested on displacement, not velocity.
- The CSS `font` shorthand resets `font-variation-settings`; declare the latter after it.
- Non-PLAIN builds prefix and minify every engine name; debug only on PLAIN builds.
- Firefox (ARCHITECTURE.md §6): `style(--flag)` is always true on a registered property (hence `BOOLQ=0`); `x - hypot(…)` evaluates as `x + hypot(…)` (hence `1 * hypot`); no `if()`; no typed division before 158 (`tan(atan2(a, b))` is a / b); style-query rules aren't re-matched after animation-driven changes (the `#LM` size-container clock forces it, and #LW restores the arena's size under it; anything positioned in percentages or sized in `cq*` units below #LM would follow #LM's changing box: register such a value, like `--u`); one physics step per frame, not two, so it runs at about half speed on 60 Hz; intersecting 3D planes aren't split but drawn in document order.

## When compacting
Preserve: the files modified, the benchmark commands and numbers from this session, and any hypothesis still being tested.
