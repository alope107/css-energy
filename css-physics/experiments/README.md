# Experiments

Microbenchmarks and feasibility tests behind `docs/BENCHMARKS.md`. Each generator writes its pages to the **current directory**, so run them in a scratch dir and measure with the repo tools:

```bash
mkdir -p /tmp/x && cd /tmp/x && python3 ~/repo/experiments/costs/mk2.py
node ~/repo/tools/stylebench.js r_const.html,r_var1.html 500 1500     # median style pass per page
```

| Dir | What it tests | Result (see BENCHMARKS.md) |
|---|---|---|
| `costs/mk2.py`, `mk4.py` | cost per registered/unregistered property and per token type | about 1.5–2 µs per registered prop, about 0.1–0.15 µs per op, about 0.17 µs per var() |
| `costs/mk.py` | inherited custom props down a 50-deep chain | no per-level copy cost |
| `costs/mk3.py` | paused-animation evaluator vs calc | about 87 µs per element vs 12 µs for calc: dead |
| `costs/mk_gating.py` | `@container` rules with absent/present names, nested, style() | absent name ≈ 0.13 µs per rule (free in Chromium 141); present + false style() ≈ 0.9 µs |
| `costs/mk_flags.py` | the all-pairs broadphase at 48 bodies | about 2.9 µs per pair flag |
| `costs/mk_part.py`, `part_depth.py`, `part_order.py`, `part_styleform.py`, `part_feat.py` | rule matching at scale: absent-name walk vs depth and list length, nesting order, `style()` forms, range queries, `if()` idents | absent name ≈ 0.2 µs + 0.6 ns × depth × names; `style(--x)` 0.4 µs, `style(--x: 1)` 0.7, range 1.6; inner query first |
| `costs/mk_regs.py` | the register readback floor vs register count, moving registers and per-body readback elements | about 2 µs per static register element; per-body split no better |
| `costs/mk_inherit2.py` | inherited custom properties declared below the chain root vs depth | no depth × properties term |
| `fonts/vf.py` | minimal variable-font builder (fontTools): HVAR glyph advances, MVAR metrics, axes ±16384 = F2DOT14 | — |
| `fonts/t1.py` + `t1.js` | `1ch`/`1ic`/`1ex`/`1cap` read HVAR/MVAR at style time | exact, including bilinear terms |
| `fonts/t2.py` | cost of new font instances vs calc | about 4 µs per new instance over calc; cached ≈ free |
| `fonts/t3.py NA R M tag` | instance cost vs axis count and regions | 35 µs (8 axes) … 416 µs (256 axes, 200 regions per output) |
| `compositor/mk.py name heavy tr\|no`, `mk2.py` | transform transitions keep the compositor at 60 fps while the main thread is busy | 55–61 compositor draws/s vs 6 main frames/s (synthetic); transitions halve the main-thread rate |
| `iframes/` (`mkchild.py`, `par*.html`, `procs2.js`) | renderer processes for same-origin, sandboxed and cross-site iframes | only cross-site splits (serve with `python3 -m http.server 8765`); the 12,000-element child no longer saturates a process, so raise the count |
| `ident/` | `var(ident(...))` dynamic lookup | unsupported in 141 and 153 |
| `touch/handles.html`, `touch/android.js` | the touch input (handles, follower) without the engine, driven on the Android emulator (`../../shared/android/`) | grabs on slow, quick and diagonal drags, flings and press-then-drag; drops 30–400 ms after the finger lifts there (emulator input latency); `:active` shows on a held finger and clears when it moves (ARCHITECTURE.md "Touch") |
