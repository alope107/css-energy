# rigid3d.css

A 3D rigid-body physics engine (boxes and spheres in a tray) that runs entirely in Chrome's style engine. `src/gen3d.py` generates the CSS; `src/build3d.py` builds pages. Read `docs/ARCHITECTURE.md` before changing the generator; `docs/BENCHMARKS.md` has the measured cost model; `docs/ROADMAP.md` lists what's next; `docs/HISTORY.md` lists what already failed (check it before proposing an idea).

## Hard rules
- IMPORTANT: generated pages contain **no JavaScript**, ever, unless the user explicitly asks. JS is fine in `tools/` and `experiments/` (test harnesses only).
- Chrome/Chromium only. Speed matters; CSS payload size does not (but load time does).
- Verify your own work in headless Chromium and report numbers or screenshots as evidence. Don't ask the user to test something you can test.
- Don't open or `cat` generated pages: they're 1–30 MB. Use grep, Python or the tools.

## Setup
- Python 3.10+ (stdlib only for `src/`); `pip install fonttools` for `experiments/fonts`.
- `npm install && npx playwright install chromium`. Tools use Playwright's Chromium, or set `CHROME=/path/to/chrome`. Tools resolve page paths against the cwd: run from the repo root.
- avar2 needs Chrome 148+. Chromium 153 for Linux: `npm i @sparticuz/chromium@153.0.0`, then `node -e "require('@sparticuz/chromium').default.executablePath().then(console.log)"`. Launch flags: `--no-sandbox --no-zygote --single-process --use-angle=swiftshader --enable-unsafe-swiftshader`; one page per browser in single-process mode.

## Commands (repo root)
- Debug build (readable names + BODYINFO, which the tools need): `COUNTS=16 PLAIN=1 python3 src/build3d.py out/p16.html` (`SCENE=tower|rain|stack`, `NBOX_FIX=4` for 4 boxes and the rest spheres)
- Physics smoke test (pass/fail, ~1 min): `bash tools/smoke.sh 16`. Run it after every generator change.
- Step cost: `node tools/tr.js out/p16.html 1500 1500`; compare variants with `bash tools/bench.sh 3 a.html b.html`
- User-level fps (chaos/settle/idle/drag/hold): `node tools/perf3.js out/p48.html`
- Profile one step: `node tools/freeze3.js out/p48.html 4000 FZ out/p48.html`, then `python3 tools/ablate.py out/FZ_p48.html pairs='--(tcp|np|p\d+_\d+(uA|uB|ov))' all=.`, then `tr.js` on each
- Published site: `bash tools/make_site.sh` (counts 8–64; the CSS is split into ≤14 MB files)

## Working style for performance work
- Hypothesis → microbenchmark or freeze+ablate → change → short tests at 16–32 bodies → validate at 48/64 only now and then (a 64-body build takes about 30 s, and its runs are slow).
- Timings are noisy: interleave repeats and compare relatively. Sanity-check that a change kept physics correct (`smoke.sh`, `sleepy.js`) before reporting a speedup.
- Record every new measurement in `docs/BENCHMARKS.md` and every dead end, with its reason, in `docs/HISTORY.md`.

## Non-obvious gotchas
- `var()` of a registered number keeps only **6 significant digits**; the wake digests rely on this (6 bodies per decimal word).
- `@container` rules with an **absent** container name are cheap (about 0.13 µs per rule per pass in Chromium 153; free in 141). A present name with a false `style()` costs about 0.9 µs per rule per pass. Gate with owner names (`b{i}`), and put `container-name: var(--AN)` on **every** level: Chrome only re-matches style-container-dependent rules for direct children.
- Gauss–Seidel order: tray planes **first**, then pair rounds. Planes-last leaves stacks with phantom velocities that never sleep.
- Keep the `.ts` timeline-scope wrappers **above** `#RB`. Inside `.rz`, rendering vanishes.
- The camera constants (`PERSP`, `TILT`, `CAM_TY`, `CAM_DIST`) are duplicated in `gen3d.py`, `ui3d.css` (as placeholders filled by build3d) and the grab/perf tools' `proj()`. Change all of them together.
- RATE below 90 doesn't settle piles. Sleep is tested on displacement, not velocity.
- The CSS `font` shorthand resets `font-variation-settings`; declare the latter after it.
- Non-PLAIN builds prefix and minify every engine name; debug only on PLAIN builds.

## User preferences
- Terse, direct. Explain the reasoning behind conclusions, label estimates vs measurements, and cite sources for claims about the outside world.
- When reviewing user-shared code, critique rather than rewrite. When sharing config or code files, give the whole file.

## When compacting
Preserve: the files modified, the benchmark commands and numbers from this session, and any hypothesis still being tested.
