# archive/: superseded code, spikes and raw results

This directory is for reference only.

- **Don't build on it.** Nothing here is part of the build or the tests.
- **Paths inside are stale.** Most scripts point at the sandbox directories they ran in (`/root/cc`, `/root/vm`,
  `/root/ui`, `/tmp/...`) and at sibling files that may not be here.
- **Generated pages and fonts were dropped.** Regenerate them from the generators if needed.

[../docs/HISTORY.md](../docs/HISTORY.md) explains why each approach was replaced, and
[../docs/BENCHMARKS.md](../docs/BENCHMARKS.md) cites the logs in `results/`.

## compiler/: earlier compile chains

| Files | What | Replaced because |
|---|---|---|
| `ccpage.py` | whole compiler step on every character level | 8.5 s recalc |
| `ccpage2.py` | lexer on every level, parser only after a token | 3.1 s recalc |
| `ccpage3.py` | parser variants per (mode, token) by container query; delayed table writes; label anchors | superseded by `ccpage4` (lexer per character class), then by `ccpage5` (typed input) |
| `ccpage5_v1…v4.py` | the typed-input chain, step by step | v2: animate on the chain root, not per level (~3 ms per level). v3: one source per line, pooled temps. v4: `display: contents` levels in XHTML |
| `cc_dsl_v1…v3.py` | earlier DSL compiler steps | v2 moved the tables out of parser state; v3 is the step before the 2026-10-10 language work |
| `cc_ref_v1.py`, `lib_v1.json`, `lib_v2.json` | compiler and runtime library before tagged strings and static types | the "4352" bug (strings printed as addresses) |
| `cmp_jsc.py` | checks `cc_ref` against jsc's code for the same program | jsc is no longer in the run path |
| `cctest.py`, `cctest.js`, `cccheck.py`, `runall.sh` | test harness for the fixed-program compile pages | replaced by `tests/` (levels L1–L5) |
| `proto.py`, `proto.js` | first nested-level prototype (D levels × P registered properties) | |
| `fuzz_css2.py` | fuzzes the DSL's compact CSS output against its Python evaluation | still useful, but its paths are stale |
| `build.js` | jsc bootstrap: self-compile into ROM, and the `--direct` mode | |
| `dbg*.js` | debugging | |
| `runtests.sh`, `README_typed_input_v1.md`, `README_typed_input_v2.md` | previous test runner and READMEs | |

## machine/: earlier CPUs, VMs and their tooling

| Files | What |
|---|---|
| `gen_vm.py` | the pure-CSS stack VM: ROM as `if()` branches, remembered-size RAM, K instructions per frame. Baseline: 3–4× slower than the font CPU |
| `gen_fvm.py`, `gen_fvm_v1.py`, `gen_fvm_flat.py` | font-CPU pages with 1-word cache lines (cpu2); `_flat` has the flat RAM (one rule per cell per channel) |
| `g4a.py`, `gen_fvm4_v1.py`, `gen_fvm4_v2.py` | early cpu4 pages. v1 reads two spans per reader. v2 has signed words. The current page is `machine/gen_fvm4.py` |
| `cpu.py`, `uarch_v1.py` | font CPU v1: FIFO cache with an evict buffer |
| `cpu2.py` | font CPU v2: ring cache, 1-word lines (cpu4 is built on it) |
| `jsc.js`, `build.js`, `image.json`, `direct.json`, `fizz.js` | the self-hosted compiler path: the self-compile workload, and fizz compiled directly into ROM |
| `sim2.py`, `sim3.py`, `sweep.py` | cache-design sweeps on the model (trap distance vs N, S, B) |
| `walkbench.py`, `stagetime*.py`, `hbbench*.py`, `prof4.py`, `ablk.py`, `floor.py`, `cmpf.py` | HarfBuzz per-lookup and per-shaping cost benchmarks (uharfbuzz) |
| `ablate.py` | strips parts of a page to find per-pass costs |
| `spike.py`, `evspike.js`, `probe*.py/js`, `diag.py` | Chromium-vs-HarfBuzz width probes and diagnostics |
| `dpr.js`, `dprchk.js`, `gw.js`, `shot.js`, `zerr.js` | device-pixel-ratio work (led to `machine/zoomfix.py`) |
| `dbg*.py`, `lkdbg.py`, `dbgpage.js`, `haltdump.js`, `snap.js` | per-cycle font-vs-model debuggers and page dumps |
| `bench.js`, `prof.js`, `runall*.sh` | old harnesses; the `runall` scripts record the commands behind `results/machine/*.log` |
| `dbgt/`, `ed/`, `t/` | test inputs: signed-word cases, GSUB context across newlines and `::before`, a self-compile of "Hi" |

## readback/

| Files | What |
|---|---|
| `gen_rb.py`, `template.html`, `rb_only.py` | the original readback page. Its scan is time-driven and its range is taken from the editor's width; both were replaced (they skipped columns and flickered) |
| `tl1–9.js` | probes for pausing or freezing view-timeline-driven animations. They found that `animation-play-state` is read from the base style, and that animations created paused don't take their timeline's value |
| `cqbench.py`, `cqrun.js`, `anbench.py` | cost probes: container-query modes, animation creation vs inheritance |

## spikes/

| Directory | Contents |
|---|---|
| `hb/` | the first HarfBuzz-in-Chrome probes: lookup budgets, LUT fonts, the toy GSUB VM, readback. `run_page.js` loads a page and evaluates a probe |
| `first_deliverable/` | `vmfont.py` (the toy VM font: aliased lookups, 16,000-step cap), `pageC.py`, `mk.py`, `fB.py` |
| `scratch/` | trace and scan debugging scripts; trap-distance models (`tr2.js`, `policy.js`); container-query probes (`t.js`, `t2.js`); `b.log` and `vmrun.log` |

## results/: raw logs behind docs/BENCHMARKS.md

| Directory | Contents |
|---|---|
| `machine/` | `fullrun.js` runs to HALT (`*.log` stdout, `*.err` progress and RSS) and `hb4_img.log` |
| `compiler/` | `cctest.js` timings of the compile-chain generators (`cc*.json`), plus `ui_fizz.json` |
| `suite/` | L3 and L5 logs from 2026-10-10 (`l3_results.log`, `l5_results.log`) and the final clean-repo runs (`l3_final.log`: 103/103; `l5_smoke_final.log`: 9/9) |
