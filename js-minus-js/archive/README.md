# archive/

`results/` holds raw logs the docs cite. Nothing here is part of the build or the tests.

- `results/machine/`: `fullrun.js` runs of the old pages to HALT (`*.log` stdout, `*.err` progress and RSS), `hb4_img.log`.
- `results/compiler/`: compile-chain generator timings (`cc*.json`) and `ui_fizz.json`.
- `results/suite/`: L3 and L5 logs from 2026-10-10 and the first clean-repo runs.

The superseded code and spikes (earlier compile chains, the pure-CSS VM, cpu/cpu2, cache sweeps, HarfBuzz
benchmarks, readback probes) were removed on 2026-10-15. Commit `91d73bc` is the last that has them:
`git show 91d73bc:js-minus-js/archive/<path>`, or `git checkout 91d73bc -- js-minus-js/archive` for all of it.
Their paths were already stale (`/root/cc`, `/root/vm`, `/tmp/...`): fix them before running anything.
[../docs/HISTORY.md](../docs/HISTORY.md) says why each approach was replaced.
