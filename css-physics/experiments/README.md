# Experiments

The style-engine microbenchmarks behind [`docs/BENCHMARKS.md`](../docs/BENCHMARKS.md), which holds the current
results. Each generator writes its pages to the **current directory**, so run it in a scratch dir and measure with the
repo tools:

```bash
mkdir -p /tmp/x && cd /tmp/x && python3 ~/repo/experiments/costs/mk2.py
node ~/repo/tools/stylebench.js r_const.html,r_var1.html 500 1500     # median style pass per page
```

| Dir | What it tests | Results |
|---|---|---|
| `costs/mk2.py`, `mk4.py` | cost per registered/unregistered property and per token | §2 |
| `costs/mk_gating.py` | `@container` rules with absent/present names, nested, style() | §2 Container-query gating |
| `costs/mk_part.py`, `part_depth.py`, `part_order.py`, `part_styleform.py` | rule matching at scale: absent-name walk, nesting order, `style()` forms, range queries, `if()` idents | §2 Rule matching |
| `costs/mk_flags.py` | the all-pairs broadphase at 48 bodies | §1 N² costs |
| `costs/mk_regs.py` | register readback floor, per-body readback elements | §2 Register readback |
| `touch/handles.html`, `touch/android.js` | the touch input (handles, follower) without the engine, on the Android emulator (`../../shared/android/`) | ARCHITECTURE.md "Touch" |
| `safari/probe.html`, `safari/static.py` | what the engine needs from a browser, pass/fail without script: the loop in miniature (steps per second, gates that follow animated values), single features; `static.py` makes a page with the solver off (drawing only) | ARCHITECTURE.md §7 |
| `widgets/` | for fun: real HTML controls (buttons, checkboxes, a select, text fields, a video, a marquee) on the box faces of an 8-body engine, some wired back into it with `:has()` | `widgets/README.md` |

The dead-end experiments (variable fonts as compute, compositor interpolation, iframe processes, `ident()`, inherited
properties, paused-animation evaluators, feature probes) were removed on 2026-10-18; their results are in BENCHMARKS
and HISTORY, and `git checkout 83d4fde -- css-physics/experiments` restores them. `make engine-check` now probes the
browser features.
