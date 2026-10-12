# Experiments

Microbenchmarks and feasibility tests behind `docs/BENCHMARKS.md`. Each generator writes its pages to the **current directory**, so run them in a scratch dir and measure with the repo tools:

```bash
mkdir -p /tmp/x && cd /tmp/x && python3 ~/repo/experiments/costs/mk2.py
node ~/repo/tools/stylebench.js r_const.html,r_var1.html 500 1500     # median style pass per page
```

| Dir | What it tests | Result (see BENCHMARKS.md) |
|---|---|---|
| `costs/mk2.py`, `mk4.py` | cost per registered/unregistered property and per token type | about 1.5–2 µs per prop, about 0.35 µs per op, about 0.5 µs per var() |
| `costs/mk.py` | inherited custom props down a 50-deep chain | no per-level copy cost |
| `costs/mk3.py` | paused-animation evaluator vs calc | about 400 µs per element: dead |
| `costs/mk_gating.py` | `@container` rules with absent/present names, nested, style() | absent name ≈ free; present + false style() ≈ 3.5 µs |
| `costs/mk_flags.py` | the all-pairs broadphase at 48 bodies | about 12.5 µs per pair flag |
| `fonts/vf.py` | minimal variable-font builder (fontTools): HVAR glyph advances, MVAR metrics, axes ±16384 = F2DOT14 | — |
| `fonts/t1.py` + `t1.js` | `1ch`/`1ic`/`1ex`/`1cap` read HVAR/MVAR at style time | exact, including bilinear terms |
| `fonts/t2.py` | cost of new font instances vs calc | about 15–20 µs per new instance; cached ≈ free |
| `fonts/t3.py NA R M tag` | instance cost vs axis count and regions | 35 µs (8 axes) … 840 µs (256 axes, 800 regions) |
| `compositor/mk.py name heavy tr\|no`, `mk2.py` | transform transitions keep the compositor at 60 fps while the main thread is busy | 59 vs 8 fps (synthetic) |
| `iframes/` (`mkchild.py`, `par*.html`, `procs2.js`) | renderer processes for same-origin, sandboxed and cross-site iframes | only cross-site splits (serve with `python3 -m http.server 8765`) |
| `ident/` | `var(ident(...))` dynamic lookup | unsupported in 141 and 153 |
