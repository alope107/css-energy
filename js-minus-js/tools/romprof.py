#!/usr/bin/env python3
"""romprof.py prog.js ... — where a program's passes go (csssim.py, K = 32): user code, or the ROM routine user code called
(inclusive: everything under that call), the innermost ROM function (exclusive), and the opcode mix in ROM.
Each pass is shared among the instructions it executed (a stalled one counts once); est = 6 ms a pass + 0.34 ms an executed
level (exp/csscpu/README.md), for comparisons only. TOP=n rows; OPS=1 the opcode mix."""
import sys, os, json, bisect, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'machine'), os.path.join(ROOT, 'compiler')]
import csssim as sim, cssref as ref
from cc_ref import OPN
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
starts = sorted((a, n) for n, a in lib['entries'].items()); addrs = [a for a, _ in starts]
ROMN = ref.ROMN
def fn(pc): return 'user' if pc >= ROMN else starts[bisect.bisect_right(addrs, pc) - 1][1]
TOP = int(os.environ.get('TOP', 12))

for path in sys.argv[1:]:
    s = sim.Sim(ref.load(path))
    incl, excl, ops = collections.Counter(), collections.Counter(), collections.Counter()
    ends = collections.Counter(); top = None; passes = 0; levels = 0
    orig = s.execute
    cur = []
    def ex(cw):
        global top
        pc = s.st['pc']
        if pc >= ROMN: top = None
        elif top is None: top = fn(pc)
        w0 = s.st['mem'].get(pc, 0) if pc < ROMN else s.st['mem'].get(pc, 0)
        cur.append((top or 'user', fn(pc), OPN[w0 // 8192] if pc < ROMN else None))
        return orig(cw)
    s.execute = ex
    while not s.st['halt'] and s.passes < 400000:
        cur.clear(); n, why = s.run_pass(32); passes += 1; ends[why] += 1; levels += len(cur)
        if not cur: continue
        share = 1 / len(cur)
        for t, f, o in cur:
            incl[t] += share; excl[f] += share
            if o: ops[o] += 1
    est = 6 * passes + 0.34 * levels
    rom = sum(v for k, v in incl.items() if k != 'user')
    print(f"{os.path.basename(path)}: {passes} passes, {levels} levels, est {est / 1000:.1f} s; ends {dict(ends)}; ROM {rom / passes:.0%} of passes")
    print('  inclusive (from user code):', ', '.join(f'{k} {v / passes:.0%}' for k, v in incl.most_common(TOP)))
    print('  exclusive:', ', '.join(f'{k} {v / passes:.0%}' for k, v in excl.most_common(TOP)))
    if os.environ.get('OPS'):
        tot = sum(ops.values()); print('  ROM ops:', ', '.join(f'{k} {v / tot:.0%}' for k, v in ops.most_common(TOP)))
