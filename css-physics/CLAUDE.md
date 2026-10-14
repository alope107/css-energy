# rigid3d.css

A 3D rigid-body physics engine (boxes and spheres in a tray) that runs entirely in Chrome's style engine. `src/gen3d.py` generates the CSS; `src/build3d.py` builds pages. Read `docs/ARCHITECTURE.md` before changing the generator; `docs/BENCHMARKS.md` has the measured cost model; `docs/HISTORY.md` lists what already failed (check it before proposing an idea) and, at its end, the open ideas not yet tried.

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
- Motion checks: `node tools/filmstrip.js page.html out.png [delay] [dur]` (compositor frames as a contact sheet, plus a snap-back score); `node tools/transcheck.js page.html` (transform transitions must restart where the running one was; `--selftest-ok` / `--selftest-bad` check the checker).

## Working style for performance work
- Hypothesis → microbenchmark or freeze+ablate → change → short tests at 16–32 bodies → validate at 48/64 only now and then (a 64-body build takes about 30 s, and its runs are slow).
- Anything that changes how things move (transitions, animations, interpolation) needs a motion check, not just screenshots and fps: run `filmstrip.js` on it and the unchanged page, look at the contact sheet, and compare the snap-back scores. A settled screenshot and a 60 fps draw count both looked perfect on a page whose bodies jumped back and forth.
- Timings are noisy: interleave repeats and compare relatively. Sanity-check that a change kept physics correct (`smoke.sh`, `sleepy.js`) before reporting a speedup.
- Record every new measurement in `docs/BENCHMARKS.md` and every dead end, with its reason, in `docs/HISTORY.md`.

## Non-obvious gotchas
- `var()` of a registered number keeps only **6 significant digits**; the wake digests rely on this (6 bodies per decimal word).
- `@container` rules with an **absent** container name are cheap only at shallow depth: the lookup walks every ancestor and scans its name list (about 0.2 µs + 0.6 ns × depth × names; about 0.2 + 0.01 × depth µs in the engine). A present name costs 0.16 µs, `style(--flag)` 0.4 µs, `style(--flag: 1)` 0.7 µs, a range query 1.6 µs. Gate with owner names (`b{i}`), and put `container-name: var(--AN)` on **every** level: Chrome only re-matches style-container-dependent rules for direct children. Nested queries evaluate the innermost first.
- `style(--x)` (no value) on a registered property is true iff its value differs from the initial value; 0/1 gates use it (`BOOLQ`).
- CSS math functions (`mod`, `round`, `pow`) are dear: a digit extraction costs about 5 µs. Anything computed per sleeping body per pass kills the sparse regime; charge awake bodies instead (the digests do).
- Spatial cells were measured and lost (`CELLS=1` builds them; HISTORY.md). The N² floor is the rule visits (about 3 per pair), not the near tests.
- `freeze3.js` wobbles every register: a frozen page's base is 2–3× the live base. Compare frozen variants with each other only.
- Sparse-regime benchmark: `SCENE=field TRAY=2 FIELD_GAP=30 COUNTS=64 PLAIN=1 python3 src/build3d.py out/g64.html` then `node tools/sparse.js out/g64.html 64 c`; freeze mid-drag with `BODY=k node tools/freezegrab.js`.
- Gauss–Seidel order: tray planes **first**, then pair rounds. Planes-last leaves stacks with phantom velocities that never sleep.
- Keep the `.ts` timeline-scope wrappers **above** `#RB`. Inside `.rz`, rendering vanishes.
- The camera constants (`PERSP`, `TILT`, `CAM_TY`, `CAM_DIST`) are duplicated in `gen3d.py`, `ui3d.css` (as placeholders filled by build3d) and the grab/perf tools' `proj()`. Change all of them together.
- RATE below 90 doesn't settle piles. Sleep is tested on displacement, not velocity.
- The CSS `font` shorthand resets `font-variation-settings`; declare the latter after it.
- Non-PLAIN builds prefix and minify every engine name; debug only on PLAIN builds.

## User preferences
- **Never merge into `main` until the user says so.** That covers merges of any kind, rebasing or cherry-picking onto it, and committing on it directly. Finish the work on a branch or worktree, report, and wait. A go-ahead for one merge doesn't cover the next.
- **Whenever you have something new for the user, build it and give them a link to test it by hand, plus the build's path.** Build a user page (not `PLAIN`) with `python3 src/build3d.py out/<name>.html` (in that checkout or worktree). Serve the repo root in the background with `python3 -m http.server 8765 --bind 127.0.0.1 --directory /workspaces/css-energy` (VS Code forwards the port), link `http://localhost:8765/<path from the repo root>` (a worktree's build: `.claude/worktrees/<name>/css-physics/out/<name>.html`), and check the link with `curl -sI` first. The link is in addition to your own headless checks (Hard rules), not instead of them.
- Terse, direct. Explain the reasoning behind conclusions, label estimates vs measurements, and cite sources for claims about the outside world.
- When reviewing user-shared code, critique rather than rewrite. When sharing config or code files, give the whole file.

## When compacting
Preserve: the files modified, the benchmark commands and numbers from this session, and any hypothesis still being tested.
