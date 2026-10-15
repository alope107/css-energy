---
name: benchmark
description: Measure performance of the compiler or the font CPU (model shapings, compile time in Chrome, run time on the page, per-frame traces) and record results in docs/BENCHMARKS.md.
---
# Benchmark

Pick the cheapest tool that answers the question, and always measure before and after in the same session.

| Question | Tool | Notes |
|---|---|---|
| Will the page run this program faster? | `python3 tools/traps.py prog.js` | Model only, instant. Shapings track wall time (a frame holds at most 2); traps end shapings. `MISS=1` prints misses by cache line. |
| How long does the CSS compiler take? | `make l3`, the per-program `ms` column | Run → done, without readback. About 158 ms + 6.4 ms per code word. |
| How long does the real page take? | `EXP1=build/ui_exp/fizzbuzz.grid node machine/ui_seq.js build/js_in_css.xhtml` (initial FizzBuzz; run `python3 tests/suite_ui.py` once to write the grid), or `make l5-smoke` | `compiledMs` includes the 64-frame readback sweep; `haltMs` is Run → HALT (detected through the page's `--isHALT`). Run-to-run noise is about ±0.2 s on ~8.5 s. |
| The CPU without the editor and compile chain? | build a RAM image as `tests/suite_machine.py` does (code and data in RAM, `expected` = the console grid), `python3 machine/gen_fvm4.py img.json build/f4cc_16 out.html`, then `IMG=img.json node machine/halttime.js out.html` | Isolates machine changes from UI costs: FizzBuzz halts 4.8 s after load there vs 8.5 s after Run on the page. |
| Is B faster than A, beyond the noise? | `EXP1=build/ui_exp/fizzbuzz.grid node ../shared/js/ab.js -p haltMs 'node machine/ui_seq.js {}' a.xhtml b.xhtml` (or `-p haltMs 'IMG=img.json node machine/halttime.js {} 60'` on CPU-only pages) | Rotated, interleaved rounds, each run a fresh browser; prints each variant's ratio to A per round (median and IQR). Run A against A first: with 6 rounds, the A-vs-A ratio itself can sit a few percent from 1. Shared with css-physics (`shared/README.md`). |
| Where does a frame go? | `RUN=1 RUNWAIT=3500 node machine/trace.js build/js_in_css.xhtml 4`, then `python3 machine/passprof.py trace.json` | `RUN=1` presses Run and waits `RUNWAIT` ms (default 8000) so the trace covers CPU frames; without it you trace the idle editor scan. **The window must sit inside the run**: FizzBuzz halts about 8.5 s after Run, so use `RUNWAIT=3500` and 4 s; a window past HALT shows idle frames (shaping 17 ms instead of 34 per frame) and flatters everything. For a CPU-only page (no Run) use `WAIT=700` (ms after load). Writes `trace.json` in the cwd (gitignored). Gives passes per frame, style+layout ms and shaping ms per frame. Ignore the harness's mouse-move hit tests. |
| Which elements get restyled or relaid out per pass? | a trace with `disabled-by-default-devtools.timeline.invalidationTracking` (add the category to `trace.js`'s list) | `StyleResolver::ResolveStyle` instants and `LayoutInvalidationTracking` events carry node names and reasons. In the 2026-10-13 traces 98% of style resolutions were inside `Layout`, under the size-container readers. |
| HarfBuzz alone | `CPUMOD=cpu4 python3 machine/hbtest.py tests/programs/jsc_self.json 16 16` | Needs uharfbuzz. Shapes the real font and checks it against the model; reports ms per shaping. Writes `cpu.ttf` in the cwd. Not `build/ccimg.json`: its RAM holds no program (the page's CSS compiler supplies it), so it never halts. |
| Compiler CSS size | `python3 tools/vsz.py`, `python3 tools/lp.py` | Temps per mode, label ports per variant. |

## Rules

- **Never claim a speed-up from the model alone when the page is the question.** Confirm in Chrome.
- **Run comparisons back to back on the same machine.** The headless sandbox's run-to-run noise is about ±3%.
- **Record every result in `docs/BENCHMARKS.md`.** Give what was measured, the command, the numbers, the date,
  and *(derived)* for computed values.
- **Older benchmark scripts were removed from `archive/machine/`.** They include the HarfBuzz per-lookup timers, the
  cache sweeps and ablations. `archive/README.md` lists them and how to restore them from git. Their paths are stale
  (`/root/vm`), so fix them before running.
