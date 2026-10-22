#!/usr/bin/env python3
"""simall.py out.json [prog.js ...] — csssim.py (K = 32) on every suite program (or those given): passes, steps, executed
levels and an estimated time (6 ms a pass + 0.34 ms a level: exp/csscpu/README.md), in parallel; with a second json, compare."""
import sys, os, json, glob
from multiprocessing import Pool
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'machine'), os.path.join(ROOT, 'compiler')]
def one(path):
    import csssim as sim, cssref as ref
    s = sim.Sim(ref.load(path)); lv = 0
    while not s.st['halt'] and s.passes < 300000: n, _ = s.run_pass(32); lv += n
    return os.path.basename(path), dict(passes=s.passes, steps=s.st['steps'], levels=lv, est=round(6 * s.passes + 0.34 * lv))
if __name__ == '__main__':
    if sys.argv[1] == 'cmp':
        a, b = (json.load(open(f)) for f in sys.argv[2:4]); ta = tb = 0
        rows = sorted(((b[k]['est'] / max(1, a[k]['est']), k) for k in a if k in b))
        for r, k in rows:
            ta += a[k]['est']; tb += b[k]['est']
            if abs(r - 1) > 0.02: print(f"{k:28s} passes {a[k]['passes']:6d} -> {b[k]['passes']:6d}  est {a[k]['est'] / 1000:8.2f} -> {b[k]['est'] / 1000:8.2f} s  x{r:.2f}")
        print(f"total est {ta / 1000:.1f} -> {tb / 1000:.1f} s"); sys.exit()
    progs = sys.argv[2:] or sorted(glob.glob(os.path.join(ROOT, 'tests', 'suite', '*.js'))) + sorted(glob.glob(os.path.join(ROOT, 'tests', 'programs', '*.js')))
    with Pool() as p: res = dict(p.map(one, progs))
    json.dump(res, open(sys.argv[1], 'w'), indent=0)
    print(len(res), 'programs; passes', sum(r['passes'] for r in res.values()), 'est', round(sum(r['est'] for r in res.values()) / 1000, 1), 's')
