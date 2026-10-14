# AGENTS.md

JavaScript compiled by CSS and run by a font. `dist/js_in_css.xhtml` is a static page: CSS reads back the text
typed into its editor, CSS compiles it to bytecode, and a GSUB "CPU" font executes it while Chrome shapes text.
The README describes the project; [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) explains how it works.

## Hard rules (the project's constraints, not preferences)

- **No JavaScript in the product pages, ever.** Harness scripts that drive or measure a page are fine.
- **Chrome / Chromium only.** No cross-browser work.
- **Speed over size.** Optimise compile speed and execution speed; payload size doesn't matter.
- **Compilation happens at run time, in CSS.** Building the compiled program into the page at build time is not
  an acceptable shortcut.
- **Test in a headless browser yourself.** Don't hand pages to the user to check; run the harnesses.
- **Don't claim a speed-up without a measurement.** The machine model (`tools/traps.py`) predicts run time in
  shapings, but only Chrome confirms it.

## Setup and commands

```
npm install && pip install -r requirements.txt     # once
make page            # build/js_in_css.xhtml: lib -> image -> CPU font -> page (~25 s, reproducible)
make test            # fast gate, no browser (~5 s): Node oracle, L1, L2, L4
make l3              # the generated CSS compiler in Chrome vs the reference (~1.5 min)
make l5-smoke        # the real page typed like a user, 6 programs + 2 errors (~1 min)
make l5              # every program under 1,500 steps (~10 min; run in the background)
make dist            # copy the built page to dist/
python3 tools/traps.py tests/suite/fizzbuzz.js     # code words, steps, shapings, traps (no browser)
```

- **Browser**: harnesses launch Chromium through `tools/browser.js`. `CHROME=/path` overrides; otherwise the npm
  package `@sparticuz/chromium` is used on Linux x64 (its only build), and elsewhere Playwright's own Chromium, falling
  back to the devcontainer image's `/usr/local/bin/chromium`. The launcher is shared with css-physics (`../shared/`, profile
  `fontcpu`: `--no-sandbox --no-proxy-server --disable-gpu`, the flags BENCHMARKS.md was measured with); `tools/page.js` reads
  the console grid and types into the editor. After changing either, run `make test-shared` at the repo root, `make test`,
  `make l3` and `make l5-smoke`.
- **Engine facts**: `make engine-check` at the repo root re-checks the notes in `docs/ENGINE_NOTES.md` that have a probe
  (`engine/README.md`). Run it after any Chrome upgrade.
- **Background runs**: long browser runs exceed default tool timeouts. Write their output to a file and poll it.
- **Single files**: `python3 compiler/cc_ref.py prog.js` compiles and runs one program; `python3
  tests/suite_ref.py` runs only L1; `SPEC=1 python3 tests/cmp_dsl.py tests/suite/x.js` runs L2 on one program.

## Layout

```
compiler/  cc_ref.py (reference compiler + simulator)  cc_dsl.py + dsl.py (same step as CSS)  ccpage5.py (compile chain)
           ccpage4.py (shared helpers: Names, muxes)    lib_src.js -> lib.json (runtime library; libbuild.js + jsc.js)
machine/   uarch.py/uarch4.py (CPU model)  cpu4.py cpugen.py otl.py fvm_build.py (font)  gen_fvm4.py (page)  memtree.py (RAM)
readback/  ui_rb.py (editor scan)  mkfont2.py (readback font)
tests/     suite/*.js + .out (Node oracle)  suite_err/*.js (must be rejected)  level harnesses
tools/     browser.js page.js (harness helpers)  traps.py  vsz.py  lp.py  filmstrip.js (motion check, ../shared)
archive/   superseded code, spikes, raw logs. Reference only: paths inside are stale, don't build on it.
```

## How to make changes

### Language or compiler change

1. **Write the test first.** Add `tests/suite/<name>.js` (at most 24 lines × 64 columns), or a program for
   `tests/suite_err/`. Run `make expect` so Node writes the `.out`.
2. **Change `compiler/cc_ref.py`.** Iterate until `make l1` passes.
3. **Mirror the change in `compiler/cc_dsl.py`.**
   - Same state, same order of effects, same failure codes.
   - Every new state variable must be added to `parse_state_names()` / `LEX_STATE`, and to `ref_state()` in
     `tests/cmp_dsl.py`.
   - `make l2` must report `ALL OK`. It compares parser state, tables, every code word, label and data word.
4. **Check the size.** Run `python3 tools/vsz.py` and `tools/lp.py` (they count variants before the page merges
   the no-op ones: 319, and 299 on the page). Every temp is CSS on each level, and every
   label port is an element on each of 400 token levels. Note the change in variant count, temps and ports
   before and after.
5. **Run `make l3`** to confirm the generated CSS agrees with the reference in Chrome.
6. **Rebuild and smoke-test the page** with `make page && make l5-smoke`, then `make dist`.

The `.claude/skills/language-feature` skill has the detailed version of this checklist.

### Runtime-library change (`compiler/lib_src.js`)

- **The lib is baked into the CPU font.** `make page` rebuilds lib → image → font → page.
- **Measure the cost with `tools/traps.py` before and after, on `tests/suite/fizzbuzz.js` and `tests/programs/t*.js`.**
  - Shapings track wall time on the page; steps don't.
  - User code lives in RAM behind a 16-line cache of 4-word lines. ROM (the lib) never misses.
  - A constant of 8192 or more needs SHL13, which traps.

### Machine or page change (`machine/`, `readback/`)

- Run `make l5-smoke`.
- For speed claims, time FizzBuzz to HALT with `machine/ui_seq.js` (initial program) or `machine/ui_run.js`, before
  and after, back to back in one session. Both press Run. Run-to-run noise is about ±0.2 s on ~8.5 s. For a ratio
  with its spread, interleave them: `EXP1=build/ui_exp/fizzbuzz.grid node ../shared/js/ab.js -p haltMs 'node
  machine/ui_seq.js {}' before.xhtml after.xhtml`, and run one page against itself first to see the noise floor.
- For a frame profile, keep the trace window inside the run: `RUN=1 RUNWAIT=3500 node machine/trace.js page 4`
  (FizzBuzz halts about 8.5 s after Run; a window past HALT shows idle frames and flatters everything).
- To separate machine costs from the UI's, time a CPU-only page (`gen_fvm4.py` without `UI=1` on a RAM image
  that holds the program; `machine/halttime.js`): FizzBuzz 4.8 s from load vs 8.5 s after Run on the page.
  (`halttime.js`, `fullrun.js` and `bench2.js` never press Run; they are for such CPU-only pages.) Without `UI=1`
  the page is HTML, not XHTML: name it `.html`. As `.xhtml` Chrome parses it as XML, there is no `#cpu`, and every
  harness fails on its first read.

## Done means

- `make test` passes.
- `make l3` passes for any compiler change.
- `make l5-smoke` passes for any change that reaches the page.
- `dist/` is rebuilt if the page changed.
- Measured effects are recorded in `docs/BENCHMARKS.md`.
- Anything new about how Chrome behaves is added to `docs/ENGINE_NOTES.md`.
- Paste the summary lines of the tests as evidence; don't just say they pass.

## Pitfalls (read docs/ENGINE_NOTES.md before touching CSS)

- **`@container style()` never matches a calc()-computed integer of 256 or more.** Keep dispatch values small.
- **A registered `<integer>` crossing `var()` keeps 6 significant digits.** Keep machine words signed (|v| < 2^19).
- **Every registered property costs time on every animated element.** Reuse pooled temp names; don't add
  per-variant properties.
- **`animation-play-state` driven by an animated value is ignored, and animations created paused don't take
  their timeline's value.** Gate with `display` instead.
- **Inherited properties that change every frame restyle the whole subtree.** Make driver state
  `inherits: false`.
- **Pages must be XHTML.** The chains are ~2,000 elements deep, and HTML stops nesting at 512.
- **When anchor names collide, `anchor-size()` reads the last element in tree order.** Compiler overlays rely on
  this to override RAM. Never put an overlay on a cell the program writes.
- **`cc_ref.py` and `cc_dsl.py` must change together.**
  - In the DSL, a local named `le` or `lt` shadows the comparison helpers inside `token()`. Use different names.
  - With a specialised starting mode, unreachable blocks are folded away by the `FALL` map in `token()`. A new
    fallthrough between modes must be added there, or the block silently disappears from that variant.
- **Error 99 on the page means no parser variant accepts that token** (pure-error variants are dropped). L3
  accepts any nonzero error for `suite_err` programs.
- **`tests/suite` programs must fit the editor (24 × 64).** `suite_ref.py` warns when one doesn't. The page
  truncates long lines, so such a test fails for the wrong reason.
- **`archive/` is not maintained.** Its scripts point at old absolute paths (`/root/cc`, `/root/vm`).

## Docs

| File | Contents |
|---|---|
| `README.md` | what it is; the language, its limits, error codes |
| `docs/ARCHITECTURE.md` | how each stage works, the memory map, ISA, tests, build |
| `docs/ENGINE_NOTES.md` | Chrome / Blink / HarfBuzz behaviour the design depends on |
| `docs/HISTORY.md` | how the design evolved, the dead ends and why, open leads |
| `docs/BENCHMARKS.md` | every measurement, with source and how to re-run |
