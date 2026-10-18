# shared/

Harness code used by the projects' tools: launching Chromium, tracing, page probes, A/B timing, motion checks, freezing
and ablation. Only the tools use it. The product pages never run script.

Each project still has its own commands, unchanged (`node tools/tr.js …` in css-physics, `node machine/halttime.js …`
in js-minus-js, `node tools/e2e.js` in paint). They now import what they share from here. This directory has no npm dependencies: `browser.js`
loads `playwright` / `playwright-core` from the project of the tool that runs, so each project keeps its own
`node_modules`.

| File | What it is | Used by |
|---|---|---|
| `js/browser.js` | `profile('physics' \| 'fontcpu')`: `launch()`, `open(browser, file, pageOpts, gotoOpts)`, `fileUrl()`, `envArgs()` | every browser tool. css-physics through `tools/lib/physics.js`, js-minus-js through `tools/browser.js`, paint through `tools/lib.js` (profile `physics`, persistent contexts via `.chromium` and `.executablePath()`) |
| `js/page.js` | `countFrames(page, ms)`, `vars(page, sel, names)`, `pollUntil()` | css-physics tools |
| `js/trace.js` | `record(page, {categories, browser}, during)`; `durations`, `median`, `bigmed`, `aggregate`, `selfTime`, `saveTrace`; category presets `CATS` | css-physics `tr`, `stylebench`, `sparse`, `grabcen`, `traceagg`, `compframes`; js-minus-js `machine/trace.js` |
| `js/ab.js` | A/B timing: interleaved, rotated rounds of any measurement command, ratios to the first variant with their spread | both (command line) |
| `js/filmstrip.js`, `js/transcheck.js` | motion checks: compositor frames as a contact sheet with a snap-back score; transform-transition continuity | css-physics `tools/filmstrip.js`, `tools/transcheck.js`; js-minus-js `tools/filmstrip.js` |
| `js/freeze.js` | the wobbling-constant clock that freezes a page's state for profiling | css-physics `freeze3.js`, `freezegrab.js` (via `tools/lib/physics.js`) |
| `py/ablate.py` | copies of a page with families of `@container` blocks removed (string- and comment-aware; never overwrites the source, `.xhtml` included) | css-physics `tools/ablate.py`; any js-minus-js page |
| `py/passprof.py` | per-frame passes, style+layout ms and shaping ms from a saved trace | js-minus-js `machine/passprof.py`; css-physics `TRACE=… CAT=… tools/tr.js` |
| `make/checks.mk`, `make/logged.sh`, `make/report.sh`, `js/runid.js` | checks as make targets: skipped while nothing they depend on changed | every project's Makefile (below) |
| `test/` | unit tests (`make test-shared` at the repo root) | |

## Browser profiles

The two projects measure with different Chromium flags, and every number in their `docs/BENCHMARKS.md` was taken with
its own flags. `--disable-gpu` changes the raster and compositor path, so the flags are part of the measurements.

| Profile | Project | npm package | Executable | Flags |
|---|---|---|---|---|
| `physics` | css-physics | `playwright` | `CHROME`, else Playwright's own Chromium, else the image's | `--no-sandbox` |
| `fontcpu` | js-minus-js | `playwright-core` | `CHROME`, else `@sparticuz/chromium` (Linux x64), else Playwright's own, else the image's | `--no-sandbox --no-proxy-server --disable-gpu` |

Tools that used other flags still pass them: `launch({args: [...]})` replaces the profile's flags, and
`launch({extraArgs: envArgs('FLAGS')})` appends. Don't merge the profiles without re-measuring both baselines.

Without `CHROME`, `launch()` tries Playwright's own browser build (`fontcpu`: `@sparticuz/chromium` first, on Linux x64
only, its one build). If that build isn't installed, it falls back to the devcontainer image's Chromium
(`/usr/local/bin/chromium`, the binary `CHROME` points at there anyway) and says so on stderr. That happens in the
devcontainer, because the npm package (1.64) is newer than the Playwright image (v1.63) and asks for a build the image
doesn't have.

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

## Checks in make (`make/checks.mk`)

The slow checks are make targets, so make skips one while nothing it depends on has changed since it last passed:

| Project | Checks | Always run |
|---|---|---|
| css-physics | `smoke.sh` (= `make -k smoke N=…`): `smoke.js` per scene, `floatcheck.js`, `overlaycheck.js`, `grabtest.js` | `statcheck.py` (20 ms) |
| js-minus-js | `make l2`, `fuzz`, `l3`, `l5`, `l5-smoke`, `l5-input` | `expect`, `l1`, `l4` (< 1 s), `fuzz-quick` (~5 s) |
| paint | `make test-selftest`, `make test-e2e` | |
| repo root | `make engine-check` | `make engine-costs` (a measurement) |

**How.** A check's target is its log, `build/<check>.<config>.log` (css-physics: `out/smoke_<N>.<gen>_….<config>.log`;
root: `engine/build/`). `make/logged.sh` runs the check, shows its output, and writes the log only on a pass: exit 0, and for
the L2/L3/L5 harnesses, which exit 0 whatever happens, their summary lines (`-p`/`-f`). So make re-runs a check when
its last run failed or when any prerequisite is newer than its log. The phony target (`make l3`) then says
`up to date: … passed <time>` and shows the end of that pass's log, or nothing extra when the check just ran.

**What a check depends on** is in its rule, read from the harnesses (and checked against the files each check
actually opened, recorded once by tracing it): the page or site it loads, its harness and the shared JS (whole
directories, `tools/*.js`, `shared/js/*.js`, rather than single files), and the suite programs. What lives
outside the repo is in the log's name: `<config>` is a hash of what `js/runid.js` prints, the Node and Python versions,
the Playwright version, the browser executable and its `--version`, and the value of every environment variable the
check's scripts read by name (found in their source, so a new variable can't be left off; set in the environment or
on make's command line). A Chrome upgrade, `BROWSER=firefox` or `TYPEWAIT=900` is another target, so a pass under one
configuration never stands for another, and switching back finds the old pass. `<dir>/<name>.<config>.id` says what a
hash stands for. Make computes the hashes while it reads the Makefile (`$(call id,…)`, ~50 ms each), so `make -n` and
`make -q` agree with `make`. The css-physics pages carry the generator's hash the same way (`NBOX_FIX=4` builds other
pages). Pages are
rebuilt only when their generator (or a variable it reads) changed; `make expect` rewrites an `.out` only when it
changes.

- `RERUN=1` runs every check asked for, up to date or not (`RERUN=1 make l3`, `RERUN=1 bash tools/smoke.sh 16`). Use
  it for the evidence before a merge, for a suspected flake, and after changing `shared/make/` itself.
- `make -n l3` shows whether it would run; `make --debug=b l3` says which prerequisite is newer.

**What it can't see.** Only what the rules name. A harness that starts reading a new file outside the directories its
rule lists, or an input that isn't a file (machine load), isn't tracked. Make compares modification times, not
content: any edit, checkout or rebuild that touches a prerequisite re-runs the check (even when the bytes are the
same; `git checkout` of a file you'd edited counts), and a copy that keeps an old mtime (`cp -p`, `tar`) could hide a
change. Each worktree has its own logs. Old configurations' logs stay until deleted (js-minus-js `make clean`).

## Changing shared code

The projects depend on it, so check each:

- `make test-shared` (unit tests, no browser);
- `RERUN=1` on the commands below: their checks depend on `shared/js/*.js`, so they re-run anyway, but not on a
  change in `shared/make/`;
- css-physics `bash tools/smoke.sh 16`;
- js-minus-js `make test`, `make l3` and `make l5-smoke`;
- paint `make test`, for a change in `browser.js` (the only shared file it uses);
- for a change in measurement code (`trace.js`, `page.js`, the profiles): old against new on the same pages, with
  `ab.js`.
