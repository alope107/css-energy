# js-minus-js

JavaScript compiled and run by CSS. `dist/js_in_css.xhtml` is a static page: CSS reads back the text typed into its
editor (through a readback font), CSS compiles it to bytecode, and a CPU made of style rules executes it, a chain of
instructions per layout pass. (Until 2026-10-19 the CPU was a GSUB font run while Chrome shaped text; its code last
exists at commit `181cbb7`.)
`README.md` has the language, limits and error codes; `docs/` has ARCHITECTURE (how it works), ENGINE_NOTES (the
Chrome behaviour it depends on), BENCHMARKS (measurements) and HISTORY (dead ends, open leads).

## Hard rules (the project's constraints, not preferences)

- **No JavaScript in the product pages, ever.** Harness scripts that drive or measure a page are fine.
- **Chrome / Chromium only.** No cross-browser work.
- **Speed over size.** Optimise compile speed and execution speed; payload size doesn't matter.
- **Compilation happens at run time, in CSS.** Building the compiled program into the page at build time is not
  an acceptable shortcut.
- **Test in a headless browser yourself.** Don't hand pages to the user to check; run the harnesses.
- **Don't claim a speed-up without a measurement.** `machine/csssim.py` predicts passes, but only Chrome confirms
  run time.

## Commands

```
npm install && pip install -r requirements.txt     # once
make page            # build/js_in_css.xhtml: lib -> image -> page (~40 s, reproducible)
make test            # fast gate, no browser (~10 s): Node oracle, L1, quick fuzz, L2, C1
make fuzz            # differential tests vs Node on ~10,000 programs: L1, L2, C1 (~1.5 min; tests/fuzz/fuzz.py)
make l3              # the generated CSS compiler in Chrome vs the reference (~40 s)
make l5-smoke        # the real page typed like a user, 6 programs + 2 errors (~30 s)
make l5              # every program under 1,500 steps (~5.5 min; run in the background)
make l5-input        # the editor under user input: edits, pastes, selection (~30 s)
make c2              # a CPU-only page per program under 1,500 steps runs to HALT (~30 s)
make l5-net          # the network programs (tests/suite/net_*) on the page, served with the gateway (~1 min)
node net/server.js .. 8767   # serve the repo root with the network gateway (fetch / read need it; README Network)
make dist            # copy the built page to dist/
python3 machine/csssim.py tests/suite/fizzbuzz.js  # steps and passes, how passes end (no browser)
python3 compiler/cc_ref.py prog.js                 # compile and run one program
SPEC=1 python3 tests/cmp_dsl.py tests/suite/x.js   # L2 on one program
```

- `l2`, `fuzz`, `fuzz-l3`, `l3`, `l5*`, `c2` skip while nothing they depend on changed (`up to date`); `RERUN=1` forces a run
  (`../shared/README.md#checks-in-make`).
- The Python levels use every CPU (`tests/par.py`, `JOBS=N`) and the browser levels 6 browsers (`SHARDS=N`), with the
  serial run's verdicts. The harness scripts run alone default to 1 browser: time with them, not through make
  (`../shared/README.md#parallel-runs`).
- Browser setup: `tools/browser.js`, the shared launcher (profile `fontcpu`, `CHROME=/path` overrides;
  `../shared/README.md`). After changing it or `tools/page.js`: repo-root `make test-shared`, then `make test`,
  `make l3`, `make l5-smoke`.
- After a Chrome upgrade run `make engine-check` at the repo root (re-checks ENGINE_NOTES' probes).
- Long browser runs exceed tool timeouts: run them in the background, write to a file, poll it.
- `exp/csscpu/README.md` has the CSS CPU's measurements and Blink's style costs (what a rule test, a declaration and
  an `if()` cost); its tools (`chainbench.js`, `passcost.js`, `stylecount.js`) time the chain alone and per pass.

## Layout

```
compiler/  cc_ref.py (reference compiler + simulator)  cc_dsl.py + dsl.py (same step as CSS)  ccpage5.py (compile chain)
           lib_src.js (runtime in jsc's dialect) + rtlib.py (builds the ROM: jsc, hand-written routines) -> lib.json
           layout.json (the memory map, the runtime cells, the jump table)
           mkimage.py (machine images: the page's, or `--ram` with the program in RAM)
machine/   gen_css.py (page: CSS CPU, RAM, console; UI=1 adds editor and compiler)  csssim.py (its pass-by-pass model)
           cssref.py (the ISA as a stepper)  memtree.py (RAM)  uipage.py (editor page parts)  uarch.py (ISA constants)
           ui_seq.js halttime.js trace.js (browser harnesses)
readback/  ui_rb.py (editor scan)  mkfont2.py (readback font)
tests/     suite/*.js + .out (Node oracle)  suite_err/*.js (must be rejected)  fuzz/ (differential tests)  level harnesses
tools/     browser.js page.js (harness helpers)  vsz.py (compiler size)
net/       server.js (web server + network gateway: the modem's documents and protocol)  device.py shim.js (the same
           protocol for the models and Node)  probe/ (what CSS can request and read back)  xhtml-tests/ (the user's tests)
```

## How to make changes

### Language or compiler change (details: `.claude/skills/language-feature`)

1. Test first: `tests/suite/<name>.js` (at most 24 lines × 64 columns) or `tests/suite_err/`; `make expect`.
2. Change `cc_ref.py` until `make l1` passes, then mirror it in `cc_dsl.py` (same state, order of effects, failure
   codes; new state in `parse_state_names()` / `LEX_STATE` and `ref_state()` in `tests/cmp_dsl.py`) until `make l2`
   reports `ALL OK`. Teach the program generator (`tests/fuzz/progen.py`) the feature, within what the language
   guarantees, and run `python3 tests/fuzz/fuzz.py gen -n 2000`, `fmt` and `mut -n 2000`.
3. Note `tools/vsz.py` before and after (now 338 variants, 70,478 temps). Every temp,
   every rule (applied or not) and every label port costs on each of 400 token levels.
4. `make fuzz` and `make l3` (`make fuzz-l3` too if the lexer or the page changed), then `make page && make l5-smoke`,
   then `make dist`.

### Instructions and runtime (`machine/gen_css.py`, `machine/csssim.py`, `compiler/rtlib.py`)

- Every instruction is defined three times: `cc_ref.run()` (the reference), `csssim.py` (the CSS CPU's model, pass by
  pass) and `gen_css.py`'s instruction classes. Change all three; `make test` (C1: csssim against Node on every suite
  program) and `make c2` (the pages in Chrome) check them.
- In `gen_css.py` an instruction belongs to one class (a container-query rule); inside it, `if()` on `--op` picks
  addresses and results. An operand whose address comes from another read must name that read in the class's
  `deps`, exactly: latches (a stalled instruction's operands kept for its re-execution) are what guarantee progress.
- A value of a registered `<integer>` must be one term (`calc((a) * b)`, not `(a) * b`): Chrome takes the latter as
  invalid and uses 0, silently. `gen_css.py` refuses to write such a page.

### Runtime-library change (`compiler/lib_src.js`, `compiler/rtlib.py`)

- The lib is the ROM, a static table in the page's fetch rules (tiers of 1,024 words); `make page` rebuilds
  lib → image → page. `rtlib.py` runs jsc (`libbuild.js`) and appends the hand-written routines.
- jsc's dialect has no short-circuit `&&` / `||`, no `break`, blocks after every `if` / `while`, `//` comments only. No
  globals or string literals (they would land in the program's data area): fixed cells are `layout.json` `rt_cells`.
  Frames are roots: a tagged value in a local survives a collection (it is updated); a raw address must not be held
  across anything that allocates. Keywords are recognised by a 13-bit hash, so a new identifier can collide with one.
- Values are told apart by range (`cc_ref.isstr` / `isarr` / `isobj`): the tags are multiples of 2^15, so `peek(x - 1)`
  is the length of a string or an array.
- Compare `python3 machine/csssim.py tests/suite/fizzbuzz.js` (and the `tests/programs/t*.js`) before and after:
  passes track wall time, steps don't. Data sits in RAM behind a 32-line cache of 4-word lines (2-way); instructions
  in ROM never miss.

### Machine or page change (`machine/`, `readback/`)

- Run `make l5-smoke`, and `make l5-input` for anything touching the editor or the scan.
- Run `make c2` for anything touching the CPU.
- Speed claims: time FizzBuzz to HALT with `machine/ui_seq.js` before and after, back to back, or interleave with
  `../shared/js/ab.js` after an A-vs-A run (`.claude/skills/benchmark`).
- Frame profiles: keep the trace window inside the run, `RUN=1 RUNWAIT=<ms> node machine/trace.js page 1`; a window
  past HALT shows idle frames and flatters everything.
- To separate machine costs from the UI's, time a CPU-only page (`gen_css.py` without `UI=1` on a `mkimage.py --ram`
  image; `POLL=30 IMG=img.json node machine/halttime.js out.html`, which never presses Run): FizzBuzz ~1.0 s from
  load. **Without `UI=1` the page is HTML: name it `.html`.** As `.xhtml` Chrome parses it as XML, there is no
  `#cpu`, and every harness fails on its first read.

## Done means

- `make test` passes; `make l3` and `make fuzz` for any compiler change; `make l5-smoke` for any change that reaches
  the page; `make l5-net` for any change to `NET`, the modem (`gen_css.py`'s net class and slot) or `net/`.
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
  from specialised variants. A DSL `emit()` is a code record that each of the 12 output slots multiplexes: in a loop
  (`popops` runs 8 times) emit one word per iteration, not one per case.
- Error 99 on the page means no parser variant accepts that token. L3 accepts any nonzero error for `suite_err`.
- `tests/suite` programs must fit the editor (24 × 64); the page truncates long lines, so `suite_ref.py` fails one
  that doesn't.
- A fuzz failure is in `build/fuzz/`; `python3 tests/fuzz/show.py build/fuzz/<name>` replays it. Check it is inside
  the language (README Limits) before fixing the compiler: the shrinker drops lines, which can remove a declaration
  the generator relied on. A real one becomes a `tests/suite` regression test.
- Label the CSS you add (`lbl.section` / `lbl.group` in gen_css.py, ccpage5.py, ui_rb.py;
  `../shared/README.md#labels-in-generated-css`). `python3 ../shared/py/csslabel.py build/js_in_css.xhtml` prints the
  page's outline.
- Code that HISTORY names (`gen_vm.py`, `ccpage.py`, `cpu.py`, …) was removed: `git checkout 91d73bc -- js-minus-js/archive`.
  The font CPU (`gen_fvm4.py`, `cpu4.py`, `cpugen.py`, `otl.py`, `fvm_build.py`, `uarch4.py`, `hbtest.py`, `traps.py`, L4)
  last exists at `181cbb7`.
- The network (`NET`, ARCHITECTURE §3.8): the gateway's words exist four times, `net/server.js` (the page),
  `net/device.py` (cc_ref, cssref, csssim, the fuzzer), `net/shim.js` (Node) and `lib_src.js`; change them together.
  The modem's answer is a fragment scroll, which crosses same-origin documents only: keep the modem on the page's
  origin. The repo-root `http.server` has no gateway: there `fetch` waits ~20 s and returns -1. A network program's
  time is its round trips, not its steps: `suite_ui.py` lists every `net_*` program for `make l5-net`. The modems'
  boxes stay outside `#clk` (a hidden box restores its scroll offset: stale answers, ENGINE_NOTES 59), and the read
  path's runtime cells sit in cache sets the stack and code don't use (`layout.json` pads `rt_cells`). Time network
  programs with no `requestAnimationFrame` loop in the page: one runs them ~1.5× faster than a user sees
  (ENGINE_NOTES 64; `pagenet.js` counts frames only with `FRAMES=1`). The gateway holds each modem's next load until
  it has an answer, at most 4 per browser (Chrome opens 6 connections per host).
