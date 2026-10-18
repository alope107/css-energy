# Experiments

Microbenchmarks and feasibility tests behind [`docs/BENCHMARKS.md`](../docs/BENCHMARKS.md), which holds the current
results. Each generator writes its pages to the **current directory**, so run it in a scratch dir and measure with the
repo tools:

```bash
mkdir -p /tmp/x && cd /tmp/x && python3 ~/repo/experiments/costs/mk2.py
node ~/repo/tools/stylebench.js r_const.html,r_var1.html 500 1500     # median style pass per page
```

| Dir | What it tests | Results |
|---|---|---|
| `costs/mk2.py`, `mk4.py` | cost per registered/unregistered property and per token | §2 |
| `costs/mk.py`, `mk_inherit2.py` | inherited custom props down a deep chain | §2 Inheritance |
| `costs/mk3.py` | paused-animation evaluator vs calc | §2 (dead end) |
| `costs/mk_gating.py` | `@container` rules with absent/present names, nested, style() | §2 Container-query gating |
| `costs/mk_part.py`, `part_depth.py`, `part_order.py`, `part_styleform.py`, `part_feat.py` | rule matching at scale: absent-name walk, nesting order, `style()` forms, range queries, `if()` idents | §2 Rule matching |
| `costs/mk_flags.py` | the all-pairs broadphase at 48 bodies | §1 N² costs |
| `costs/mk_regs.py` | register readback floor, per-body readback elements | §2 Register readback |
| `fonts/vf.py`, `t1.py` + `t1.js`, `t2.py`, `t3.py NA R M tag` | variable-font metrics as compute: builder, correctness, instance cost, width scaling (`pip install fonttools`; avar2 needs Chrome 148+) | §3 |
| `compositor/mk.py name heavy tr\|no`, `mk2.py` | transform transitions on the compositor while the main thread is busy | §4 |
| `iframes/` (`mkchild.py`, `par*.html`, `procs2.js`) | renderer processes per iframe kind (serve with `python3 -m http.server 8765`; raise the child's element count) | §5 |
| `ident/` | `var(ident(...))` dynamic lookup | §6 (unsupported) |
| `touch/handles.html`, `touch/android.js` | the touch input (handles, follower) without the engine, on the Android emulator (`../../shared/android/`) | ARCHITECTURE.md "Touch" |
