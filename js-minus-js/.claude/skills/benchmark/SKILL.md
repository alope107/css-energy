---
name: benchmark
description: Measure performance of the compiler or the CSS CPU (model passes, compile time in Chrome, run time on the page, per-pass costs, per-frame traces) and record results in docs/BENCHMARKS.md.
---
# Benchmark

Pick the cheapest tool that answers the question, and measure before and after in the same session. Current numbers
and the noise floor are in `docs/BENCHMARKS.md`.

| Question | Tool | Notes |
|---|---|---|
| Will the page run this program faster? | `python3 machine/csssim.py prog.js` | Model only, instant: steps, passes and how they end (miss, output, K levels). Passes track wall time. |
| How long does the CSS compiler take? | `node tests/suite_css.js build/suite_css.xhtml` (per-program `ms`), or `make l3 SHARDS=1` (`make l3` runs 6 browsers at once: its `ms` aren't timings) | Run → done, without readback. |
| How long does the real page take? | `EXP1=build/ui_exp/fizzbuzz.grid node machine/ui_seq.js build/js_in_css.xhtml` (run `python3 tests/suite_ui.py` once to write the grid), or `make l5-smoke` | `compiledMs` includes the readback sweep; `haltMs` is Run → HALT (the page's `--isHALT`). |
| The CPU without editor and compile chain? | `python3 compiler/mkimage.py --ram prog.js img.json`, `python3 machine/gen_css.py img.json out.html`, `POLL=30 IMG=img.json node machine/halttime.js out.html` | Name the page `.html`. `halttime.js` never presses Run. |
| What does a chain level, a pass, a declaration cost? | `exp/csscpu/`: `chainbench.js` (the chain alone from a real pass, `gen_css.py BENCH=1 PROG=prog.js`, `STALL=1`, `DUP=name`), `passcost.js`, `stylecount.js` (`PER=1`) | See `exp/csscpu/README.md` for the cost model and the pitfalls (identical levels hit the matched-properties cache). |
| Is B faster than A, beyond the noise? | `EXP1=build/ui_exp/fizzbuzz.grid node ../shared/js/ab.js -p haltMs 'node machine/ui_seq.js {}' a.xhtml b.xhtml` (CPU-only: `-p haltMs 'IMG=img.json node machine/halttime.js {} 60'`) | Interleaved rounds, fresh browser per run; ratio to A per round (median, IQR). Run A against A first. |
| Where does a frame go? | `RUN=1 RUNWAIT=3500 node machine/trace.js build/js_in_css.xhtml 4`, then `python3 machine/passprof.py trace.json` | **The window must sit inside the run** (ENGINE_NOTES 39); without `RUN=1` you trace the idle editor. CPU-only pages: `WAIT=700`. Ignore mouse-move hit tests. |
| Which elements restyle or relayout per pass? | add `disabled-by-default-devtools.timeline.invalidationTracking` to `trace.js`'s categories | `StyleResolver::ResolveStyle` instants and `LayoutInvalidationTracking` events carry node names and reasons (ENGINE_NOTES 34). |
| Readback sweep | `python3 readback/rb_only2.py rb.xhtml && node readback/rbsweep.js rb.xhtml tests/fizz.js 3` | Counts unread or wrong cells per sweep. `readback/rbtest.js page prog.js` prints what the latches read. |
| Compiler CSS size | `python3 tools/vsz.py` | Variants and temps per mode, the largest variants, label ports. |

## Rules

- **Never claim a speed-up from the model alone when the page is the question.** Confirm in Chrome.
- **Run comparisons back to back on the same machine**, and take medians (a CPU-only page has occasional +15% outliers).
- **Record every result in `docs/BENCHMARKS.md`**: what, the command, the numbers, the date, *(derived)* for computed
  values. Replace superseded numbers rather than keeping both.
- The old per-lookup HarfBuzz timers, cache sweeps and ablations are in git only (commit `91d73bc`, `archive/`).
