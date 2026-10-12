---
name: benchmark
description: Measure performance of the compiler or the font CPU (model shapings, compile time in Chrome, run time on the page, per-frame traces) and record results in docs/BENCHMARKS.md.
---
# Benchmark

Pick the cheapest tool that answers the question, and always measure before and after in the same session.

| Question | Tool | Notes |
|---|---|---|
| Will the page run this program faster? | `python3 tools/traps.py prog.js` | Model only, instant. Shapings track wall time (a frame holds at most 2); traps end shapings. `MISS=1` prints misses by cache line. |
| How long does the CSS compiler take? | `make l3`, the per-program `ms` column | Run → done, without readback. About 322 ms + 13 ms per code word. |
| How long does the real page take? | `EXP1=build/ui_exp/fizzbuzz.grid node machine/ui_seq.js build/js_in_css.xhtml` (initial FizzBuzz; run `python3 tests/suite_ui.py` once to write the grid), or `make l5-smoke` | `compiledMs` includes the 64-frame readback sweep; `haltMs` is Run → HALT. |
| Where does a frame go? | `RUN=1 node machine/trace.js build/js_in_css.xhtml 6`, then `python3 machine/passprof.py trace.json` | `RUN=1` presses Run and waits 8 s (`RUNWAIT`) so the trace covers CPU frames; without it you trace the idle editor scan. Writes `trace.json` in the cwd (gitignored). Gives passes per frame, style+layout ms and shaping ms per frame. Ignore the harness's mouse-move hit tests. |
| HarfBuzz alone | `CPUMOD=cpu4 python3 machine/hbtest.py build/ccimg.json 16 32` | Needs uharfbuzz. Shapes the real font and checks it against the model; reports ms per shaping. |
| Compiler CSS size | `python3 tools/vsz.py`, `python3 tools/lp.py` | Temps per mode, label ports per variant. |

## Rules

- **Never claim a speed-up from the model alone when the page is the question.** Confirm in Chrome.
- **Run comparisons back to back on the same machine.** The headless sandbox's run-to-run noise is about ±3%.
- **Record every result in `docs/BENCHMARKS.md`.** Give what was measured, the command, the numbers, the date,
  and *(derived)* for computed values.
- **Older benchmark scripts are in `archive/machine/`.** They include the HarfBuzz per-lookup timers, the cache
  sweeps and ablations. Their paths are stale (`/root/vm`), so fix them before running.
