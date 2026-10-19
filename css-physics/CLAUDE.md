# rigid3d.css

A 3D rigid-body physics engine (boxes and spheres in a tray) that runs entirely in Chrome's style engine. `src/gen3d.py` generates the CSS; `src/build3d.py` builds pages. Read `docs/ARCHITECTURE.md` before changing the generator; `docs/BENCHMARKS.md` has the measured cost model; `docs/HISTORY.md` lists what already failed (check it before proposing an idea) and the open ideas.

## Hard rules
- IMPORTANT: generated pages contain **no JavaScript**, ever, unless the user explicitly asks. JS is fine in `tools/` and `experiments/` (test harnesses only).
- Chrome first, and Firefox 159+ (158 with `layout.css.scroll-driven-animations.enabled`) must keep working: run `BROWSER=firefox bash tools/smoke.sh 16` too after generator changes. Chrome's speed wins any trade-off; Firefox-only fixes go in `@supports (-moz-appearance: none)` blocks (ARCHITECTURE.md §6). Speed matters; CSS payload size does not (but load time does).
- Verify your own work in headless Chromium and report numbers or screenshots as evidence. Don't ask the user to test something you can test.
- Don't open or `cat` generated pages: they're 1–30 MB. Use grep, Python or the tools.

## Setup
- Python 3.10+ (stdlib only). `npm install` for the tools; run them from the repo root (they resolve page paths against the cwd).
- Browser launch (`CHROME=`, the `physics` profile, the image's Chromium fallback) and the harness shared with js-minus-js: `../shared/README.md`. This project's own helpers are in `tools/lib/physics.js` (camera projection, BODYINFO, freezing). After changing either, run `make test-shared` at the repo root and `smoke.sh`.
- Firefox: `BROWSER=firefox` (evaluate-based tools only: smoke, floatcheck, grabtest, perf3, …; tracing needs Chrome); `FIREFOX=/path` overrides. **Don't `npx playwright install` in the devcontainer:** it garbage-collects the image's other browsers, `/usr/local/bin/chromium`'s target included (restore with `npx playwright@1.63.0 install`).
- After a Chrome upgrade: `make engine-check` at the repo root (the behaviours this engine depends on; `../engine/README.md`).

## Commands (repo root)
- Debug build (readable names + BODYINFO, which the tools need): `COUNTS=16 PLAIN=1 python3 src/build3d.py out/p16.html` (`SCENE=tower|rain|stack`, `NBOX_FIX=4` for 4 boxes and the rest spheres)
- Smoke and regression tests (pass/fail, ~4.5 min): `bash tools/smoke.sh 16`, after every generator change. Besides the physics check it runs `statcheck.py` (every scene declares every body's start state; boolean gates only on 0/1 flags), `floatcheck.js` (no body asleep in mid-air, on load or after switching scenes), `grabtest.js` (dragging one body moves no other) `overlaycheck.js` (the grab ring, pin and tether follow the drag) and, in Chromium, `touchcheck.js` (touch dragging on a phone-sized touch screen); each guards a bug that shipped. Make skips unchanged passing checks (`up to date`); `RERUN=1` runs them all.
- Step cost: `node tools/tr.js out/p16.html 1500 1500`; compare variants with `bash tools/bench.sh 3 a.html b.html` or `node ../shared/js/ab.js -p bigmed 'node tools/tr.js {} 1500 1500' a.html b.html` (pass one page twice for the noise floor).
- User-level fps (chaos/settle/idle/drag/hold): `node tools/perf3.js out/p48.html`
- Touch: `node tools/touchcheck.js out/p16.html` (real gestures through Chromium's gesture recognizer over CDP, phone viewport; `TOUCHCHECK_SHOT=x.png` saves a mid-drag frame); `TOUCH=1 [TOUCHDRAG=1] node tools/tr.js …` times touch mode. Synthetic touch has no show-press or long-press: for those and Android's input path, the emulator (`../shared/android/README.md`, ~9 min to boot, about 1 fps for the engine) with `experiments/touch/android.js`.
- Profile one step (freeze + ablate) and microbenchmarks: the `perf-profile` skill. Tool index: BENCHMARKS.md "How to measure".
- Sparse regime: `SCENE=field TRAY=2 FIELD_GAP=30 COUNTS=64 PLAIN=1 python3 src/build3d.py out/g64.html`, then `node tools/sparse.js out/g64.html 64 c`; freeze mid-drag with `BODY=k node tools/freezegrab.js`.
- Published site: `python3 src/build3d.py out/x.html` (one page per count, CSS over 14 MB split into linked files); CI deploys `../deploy/assemble.sh css-physics <dir>`
- Motion checks: `node tools/filmstrip.js page.html out.png [delay] [dur]` (compositor frames as a contact sheet, plus a snap-back score); `node tools/transcheck.js page.html` (transform transitions must restart where the running one was).

## Working style for performance work
- Hypothesis → microbenchmark or freeze+ablate → change → short tests at 16–32 bodies → validate at 48/64 only now and then (a 64-body build takes about 30 s).
- Anything that changes how things move (transitions, animations, interpolation) needs a motion check: `filmstrip.js` on it and on the unchanged page, comparing snap-back scores. Screenshots and fps looked perfect on a page whose bodies jumped back and forth.
- Timings are noisy: interleave repeats and compare relatively. Check physics (`smoke.sh`, `sleepy.js`) before reporting a speedup.
- Record new measurements in `docs/BENCHMARKS.md` (replace the old number, don't append history) and every dead end, with its reason, in `docs/HISTORY.md`.

## Non-obvious gotchas
- `var()` of a registered number keeps only **6 significant digits**; the wake digests rely on this (6 bodies per decimal word).
- `@container` rules with an **absent** container name are cheap only at shallow depth: the lookup walks every ancestor and scans its name list (about 0.2 µs + 0.6–0.9 ns × depth × names; about 0.2 + 0.01 × depth µs in the engine). A present name costs 0.2 µs, `style(--flag)` 0.5 µs, `style(--flag: 1)` 0.8 µs, a range query 1.7 µs (mini PC, 2026-10-17). Gate with owner names (`b{i}`), and put `container-name: var(--AN)` on **every** level, so each level finds its owner name at the parent (Chrome 141 also didn't re-match deeper named rules; not reproduced in 153, `../bugs/README.md`). Nested queries evaluate the innermost first.
- `style(--x)` (no value) on a registered property is, in Chrome, true iff its value differs from the initial value (in Firefox: always); `BOOLQ=1` gates 0/1 flags with it (off by default, for Firefox). Never for a multi-valued flag: `style(--GIr)` as body 0's grab gate was true whenever any body was held, so every drag also pulled body 0 (the generator now skips flags tested against other values).
- Scene start states cascade: the first scene's `#INI` rule is overridden by the selected scene's, so every scene rule must declare every body's `--isc` (start sleep counter), or a body keeps another scene's "asleep" and hangs in mid-air. Test scene switches with a real press (~150 ms): an instant click flips the radio without the reset.
- CSS math functions (`mod`, `round`, `pow`) are dear: a digit extraction costs about 5 µs. Anything computed per sleeping body per pass kills the sparse regime; charge awake bodies instead (the digests do; this is why spatial cells lost). The N² floor is the rule visits (about 3 per pair), not the near tests.
- `freeze3.js` wobbles every register: a frozen page's base is 2–3× the live base. Compare frozen variants with each other only.
- Gauss–Seidel order: tray planes **first**, then pair rounds. Planes-last leaves stacks with phantom velocities that never sleep.
- Keep the `.ts` timeline-scope wrappers **above** `#RB`. Inside `.rz`, rendering vanishes.
- The camera constants (`PERSP`, `TILT`, `CAM_TY`, `CAM_DIST`) live in `gen3d.py`, `ui3d.css` (placeholders filled by build3d) and `tools/lib/physics.js`: change all three.
- RATE below 90 doesn't settle piles. Sleep is tested on displacement, not velocity.
- The CSS `font` shorthand resets `font-variation-settings`; declare the latter after it.
- Non-PLAIN builds prefix and minify every engine name; debug only on PLAIN builds.
- Label the CSS you add (`lbl.section` / `lbl.group` in gen3d.py and build3d.py, `/* === … === */` in ui3d.css;
  `../shared/README.md#labels-in-generated-css`). `python3 ../shared/py/csslabel.py out/p16.html` prints a page's outline.
- Touch (ARCHITECTURE.md "Touch") rests on three Chrome behaviours `make engine-check` probes: layout re-snaps wait while a scroll gesture is active (the "finger down" bit), `scroll-axis-lock: none`, touch deltas unprojected onto a 3D-transformed scroller. Anything inherited from `#TI` changes every frame of a drag: zero it where unused (`.view`, `.rz`), as `--sx` is.
- Firefox (ARCHITECTURE.md §6): `style(--flag)` is always true (hence `BOOLQ=0`); `x - hypot(…)` is `x + hypot(…)` (hence `1 * hypot`); no `if()`; style-query rules aren't re-matched after animation-driven changes (the `#LM` size-container clock forces it, so anything below #LM positioned in percentages or sized in `cq*` units follows #LM's box: register such a value, like `--u`).

## When compacting
Preserve: the files modified, the benchmark commands and numbers from this session, and any hypothesis still being tested.
