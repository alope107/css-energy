# shared/

Harness code the projects' tools import: launching Chromium, tracing, A/B timing, motion checks, freezing, ablation,
and checks as make targets. The product pages never run script. No npm dependencies here: `browser.js` loads
`playwright` / `playwright-core` from the calling project's `node_modules`.

| File | What | Used by |
|---|---|---|
| `js/browser.js` | `profile('physics' \| 'fontcpu')`: `launch()`, `open()`, `fileUrl()`, `envArgs()` | every browser tool (css-physics via `tools/lib/physics.js`, js-minus-js via `tools/browser.js`, paint via `tools/lib.js`) |
| `js/page.js` | `countFrames`, `vars`, `pollUntil` | css-physics |
| `js/trace.js` | `record()`, `durations`, `median`, `bigmed`, `aggregate`, `selfTime`, `saveTrace`, presets `CATS` | css-physics `tr` and friends; js-minus-js `machine/trace.js` |
| `js/ab.js` | A/B timing (below) | both, command line |
| `js/filmstrip.js`, `js/transcheck.js` | motion checks: compositor contact sheet with a snap-back score; transition continuity | css-physics, js-minus-js `tools/filmstrip.js` |
| `js/freeze.js` | the wobbling-constant clock that freezes a page's state for profiling | css-physics `freeze3.js`, `freezegrab.js` |
| `py/ablate.py` | copies of a page with families of `@container` blocks removed (string/comment-aware, never overwrites the source) | css-physics `tools/ablate.py`; any js-minus-js page |
| `py/passprof.py` | passes per frame, style+layout ms and shaping ms from a saved trace | js-minus-js `machine/passprof.py`; css-physics `TRACE=… tools/tr.js` |
| `make/checks.mk`, `make/logged.sh`, `make/report.sh`, `js/runid.js` | checks as make targets (below) | every project's Makefile |
| `android/` | Chromium for Android on the emulator under software emulation (no KVM): setup, start/stop, kernel-level touch, a CDP client; touch semantics, not timing (`android/README.md`) | css-physics `experiments/touch/android.js` |
| `test/` | unit tests: `make test-shared` at the repo root | |

## Browser profiles

Every number in a project's `docs/BENCHMARKS.md` was taken with its own flags (`--disable-gpu` changes the raster and
compositor path). Don't merge the profiles without re-measuring both.

| Profile | Project | npm package | Executable | Flags |
|---|---|---|---|---|
| `physics` | css-physics, paint | `playwright` | `CHROME`, else Playwright's Chromium, else the image's | `--no-sandbox` |
| `fontcpu` | js-minus-js | `playwright-core` | `CHROME`, else `@sparticuz/chromium` (Linux x64), else Playwright's, else the image's | `--no-sandbox --no-proxy-server --disable-gpu` |

`launch({args})` replaces the profile's flags; `launch({extraArgs: envArgs('FLAGS')})` appends. In the devcontainer
Playwright's own build is usually missing (the npm package is newer than the image), so `launch()` falls back to
`/usr/local/bin/chromium` and says so on stderr.

## A/B timing (`js/ab.js`)

```bash
node ../shared/js/ab.js -p bigmed 'node tools/tr.js {} 1500 1500' out/a.html out/b.html            # css-physics
IMG=img.json node ../shared/js/ab.js -r 3 -p haltMs 'node machine/halttime.js {} 60' a.html b.html  # js-minus-js
```

Each run is a fresh process; round r starts at variant r, so drift hits every variant alike. Read the ratio column.
Pass one page twice for the noise floor (the ratio should straddle 1.00). `-p name` takes a JSON field or the first
number after `name` in text output.

## Checks in make

The slow checks are make targets whose target is their log, so make skips a check while nothing it depends on changed
since it last passed:

| Project | Checks | Always run |
|---|---|---|
| css-physics | `smoke.sh` (= `make -k smoke N=…`): `smoke.js` per scene, `floatcheck.js`, `overlaycheck.js`, `grabtest.js` | `statcheck.py` |
| js-minus-js | `make l2`, `fuzz`, `fuzz-l3`, `l3`, `l5`, `l5-smoke`, `l5-input` | `expect`, `l1`, `fuzz-quick`, `l4` |
| paint | `make test-selftest`, `make test-e2e`, `make test-goaway` | |
| repo root | `make engine-check` | `make engine-costs` |

- **The log** is `build/<check>.<config>.log` (css-physics `out/smoke_<N>.<gen>_….<config>.log`; root
  `engine/build/`). `logged.sh` writes it only on a pass (exit 0, and for the L2/L3/L5 harnesses, which always exit 0,
  their summary lines). The phony target then prints `up to date: … passed <time>` and the end of that log.
- **Prerequisites** are in each rule: the page or site, the harness, `shared/js/*.js` (whole directories), the suite
  programs. **`<config>`** hashes what lives outside the repo: `runid.js`'s output, Node/Python/Playwright versions, the
  browser executable and its `--version`, and every environment variable the check's scripts read by name. So a Chrome
  upgrade or `BROWSER=firefox` is another target, and switching back finds the old pass. `<name>.<config>.id` says
  what a hash stands for.
- `RERUN=1` runs every check asked for. Use it for the evidence before a merge, a suspected flake, and after changing
  `shared/make/`. `make -n l3` shows whether it would run; `make --debug=b l3` says which prerequisite is newer.
- **Blind spots:** files a harness starts reading outside its listed directories; inputs that aren't files (machine
  load). Make compares mtimes, not content: any touch re-runs a check, and a copy that keeps an old mtime (`cp -p`,
  `tar`) can hide a change. Each worktree has its own logs.

## Changing shared code

Run `make test-shared`, then with `RERUN=1`: css-physics `bash tools/smoke.sh 16`; js-minus-js `make test`, `make l3`,
`make l5-smoke`; paint `make test` for a change in `browser.js`. For measurement code (`trace.js`, `page.js`, the
profiles), compare old against new on the same pages with `ab.js`.
