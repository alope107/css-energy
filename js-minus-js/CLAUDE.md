# js-minus-js

JavaScript compiled by CSS and run by a font. `dist/js_in_css.xhtml` is a static page: CSS reads back the text
typed into its editor, CSS compiles it to bytecode, and a GSUB "CPU" font executes it while Chrome shapes text.
`README.md` has the language, limits and error codes; `docs/` has ARCHITECTURE (how it works), ENGINE_NOTES (the
Chrome behaviour it depends on), BENCHMARKS (measurements) and HISTORY (dead ends, open leads).

## Hard rules (the project's constraints, not preferences)

- **No JavaScript in the product pages, ever.** Harness scripts that drive or measure a page are fine.
- **Chrome / Chromium only.** No cross-browser work.
- **Speed over size.** Optimise compile speed and execution speed; payload size doesn't matter.
- **Compilation happens at run time, in CSS.** Building the compiled program into the page at build time is not
  an acceptable shortcut.
- **Test in a headless browser yourself.** Don't hand pages to the user to check; run the harnesses.
- **Don't claim a speed-up without a measurement.** The machine model (`tools/traps.py`) predicts run time in
  shapings, but only Chrome confirms it.

## Commands

```
npm install && pip install -r requirements.txt     # once
make page            # build/js_in_css.xhtml: lib -> image -> CPU font -> page (~25 s, reproducible)
make test            # fast gate, no browser (~10 s): Node oracle, L1, quick fuzz, L2, L4
make fuzz            # differential tests vs Node on ~10,000 programs: L1, L2, L4 (~1.5 min; tests/fuzz/fuzz.py)
make l3              # the generated CSS compiler in Chrome vs the reference (~40 s)
make l5-smoke        # the real page typed like a user, 6 programs + 2 errors (~30 s)
make l5              # every program under 1,500 steps (~5.5 min; run in the background)
make l5-input        # the editor under user input: edits, pastes, selection (~30 s)
make dist            # copy the built page to dist/
python3 tools/traps.py tests/suite/fizzbuzz.js     # code words, steps, shapings, traps (no browser)
python3 compiler/cc_ref.py prog.js                 # compile and run one program
SPEC=1 python3 tests/cmp_dsl.py tests/suite/x.js   # L2 on one program
```

- `l2`, `fuzz`, `fuzz-l3`, `l3`, `l5*` skip while nothing they depend on changed (`up to date`); `RERUN=1` forces a run
  (`../shared/README.md#checks-in-make`).
- The Python levels use every CPU (`tests/par.py`, `JOBS=N`) and the browser levels 6 browsers (`SHARDS=N`), with the
  serial run's verdicts. The harness scripts run alone default to 1 browser: time with them, not through make
  (`../shared/README.md#parallel-runs`).
- Browser setup: `tools/browser.js`, the shared launcher (profile `fontcpu`, `CHROME=/path` overrides;
  `../shared/README.md`). After changing it or `tools/page.js`: repo-root `make test-shared`, then `make test`,
  `make l3`, `make l5-smoke`.
- After a Chrome upgrade run `make engine-check` at the repo root (re-checks ENGINE_NOTES' probes).
- Long browser runs exceed tool timeouts: run them in the background, write to a file, poll it.

## Layout

```
compiler/  cc_ref.py (reference compiler + simulator)  cc_dsl.py + dsl.py (same step as CSS)  ccpage5.py (compile chain)
           lib_src.js -> lib.json (runtime library)  rtlib.py (object runtime + GC in ROM)  layout.json (the memory map)
           mkimage.py (machine images: the page's, or `--ram` with the program in RAM)
machine/   uarch.py/uarch4.py (CPU model)  cpu4.py cpugen.py otl.py fvm_build.py (font)  gen_fvm4.py (page)  memtree.py (RAM)
           ui_seq.js halttime.js trace.js (browser harnesses)  hbtest.py (font vs model in uharfbuzz)
readback/  ui_rb.py (editor scan)  mkfont2.py (readback font)
tests/     suite/*.js + .out (Node oracle)  suite_err/*.js (must be rejected)  fuzz/ (differential tests)  level harnesses
tools/     browser.js page.js (harness helpers)  traps.py  vsz.py (compiler size)
```

## How to make changes

### Language or compiler change (details: `.claude/skills/language-feature`)

1. Test first: `tests/suite/<name>.js` (at most 24 lines × 64 columns) or `tests/suite_err/`; `make expect`.
2. Change `cc_ref.py` until `make l1` passes, then mirror it in `cc_dsl.py` (same state, order of effects, failure
   codes; new state in `parse_state_names()` / `LEX_STATE` and `ref_state()` in `tests/cmp_dsl.py`) until `make l2`
   reports `ALL OK`. Teach the program generator (`tests/fuzz/progen.py`) the feature, within what the language
   guarantees, and run `python3 tests/fuzz/fuzz.py gen -n 2000`, `fmt` and `mut -n 2000`.
3. Note `tools/vsz.py` before and after (now 355 variants). Every temp,
   every rule (applied or not) and every label port costs on each of 400 token levels.
4. `make fuzz` and `make l3` (`make fuzz-l3` too if the lexer or the page changed), then `make page && make l5-smoke`,
   then `make dist`.

### Object instructions and runtime (`machine/uarch.py`, `compiler/rtlib.py`)

- SCANI SCAN LDF PUTV NEW SETF ENDK OVER JNEG are defined twice: microcode in `uarch.py` (compiled into the font by
  `cpu4.py`) and in `cc_ref.run()`. Change both together.
- After changing them or `cpu4.py` / `cpugen.py`, run the font against the model on an object program, not only
  FizzBuzz: `python3 compiler/mkimage.py --ram tests/suite/obj_tree.js img.json && CPUMOD=cpu4 python3 machine/hbtest.py img.json 16 32`
  (stops at the first differing shaping). L4 only checks the model against itself.
- S × subtables per cycle (fvm_build prints them) must stay ≤ 16,384, so ≤ 512 at S = 32. Past that, HarfBuzz drops
  the last lookups without an error and the decoded state reads 0.

### Runtime-library change (`compiler/lib_src.js`)

- The lib is baked into the CPU font; `make page` rebuilds lib → image → font → page.
- Compare `tools/traps.py tests/suite/fizzbuzz.js tests/programs/t*.js` before and after. Shapings track wall time;
  steps don't. User code sits in RAM behind a 16-line cache of 4-word lines; ROM never misses. A constant ≥ 8192
  needs SHL13, which traps.

### Machine or page change (`machine/`, `readback/`)

- Run `make l5-smoke`, and `make l5-input` for anything touching the editor or the scan.
- Speed claims: time FizzBuzz to HALT with `machine/ui_seq.js` before and after, back to back (noise ±0.05 s on
  ~10.8 s), or interleave with `../shared/js/ab.js` after an A-vs-A run (`.claude/skills/benchmark`).
- Frame profiles: keep the trace window inside the run, `RUN=1 RUNWAIT=3500 node machine/trace.js page 4`. FizzBuzz
  halts ~10.8 s after Run; a window past HALT shows idle frames and flatters everything.
- To separate machine costs from the UI's, time a CPU-only page (`gen_fvm4.py` without `UI=1` on a `mkimage.py --ram`
  image; `machine/halttime.js`, which never presses Run): FizzBuzz 6.3 s from load vs 10.8 s after Run on the
  page. **Without `UI=1` the page is HTML: name it `.html`.** As `.xhtml` Chrome parses it as XML, there is no `#cpu`,
  and every harness fails on its first read.

## Done means

- `make test` passes; `make l3` and `make fuzz` for any compiler change; `make l5-smoke` for any change that reaches
  the page.
- `dist/` is rebuilt if the page changed.
- Measured effects are in `docs/BENCHMARKS.md`; new Chrome behaviour is in `docs/ENGINE_NOTES.md`.
- Paste the tests' summary lines as evidence; don't just say they pass.

## Pitfalls (details in docs/ENGINE_NOTES.md; read it before touching CSS)

- `@container style()` never matches a calc()-computed integer ≥ 256. Keep dispatch values small.
- A registered `<integer>` crossing `var()` keeps 6 significant digits. Keep machine words signed (|v| < 2^19).
- Every registered property costs time on every animated element. Reuse pooled temp names.
- `animation-play-state` driven by an animated value is ignored, and animations created paused don't take their
  timeline's value. Gate with `display` instead.
- Inherited properties that change every frame restyle the whole subtree. Make driver state `inherits: false`.
- Pages must be XHTML: the chains are ~2,000 elements deep and HTML stops nesting at 512.
- With colliding anchor names `anchor-size()` reads the last in tree order; compiler overlays override RAM this way.
  Never put an overlay on a cell the program writes.
- `cc_ref.py` and `cc_dsl.py` change together. In the DSL a local named `le` or `lt` shadows the comparison helpers
  in `token()`. A new fallthrough between modes must go in `token()`'s `FALL` map, or the block silently vanishes
  from specialised variants.
- Error 99 on the page means no parser variant accepts that token. L3 accepts any nonzero error for `suite_err`.
- `tests/suite` programs must fit the editor (24 × 64); the page truncates long lines, so `suite_ref.py` fails one
  that doesn't.
- A fuzz failure is in `build/fuzz/`; `python3 tests/fuzz/show.py build/fuzz/<name>` replays it. Check it is inside
  the language (README Limits) before fixing the compiler: the shrinker drops lines, which can remove a declaration
  the generator relied on. A real one becomes a `tests/suite` regression test.
- Label the CSS you add (`lbl.section` / `lbl.group` in gen_fvm4.py, ccpage5.py, ui_rb.py;
  `../shared/README.md#labels-in-generated-css`). `python3 ../shared/py/csslabel.py build/js_in_css.xhtml` prints the
  page's outline.
- Code that HISTORY names (`gen_vm.py`, `ccpage.py`, `cpu.py`, …) was removed: `git checkout 91d73bc -- js-minus-js/archive`.
