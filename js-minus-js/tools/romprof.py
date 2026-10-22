#!/usr/bin/env python3
"""romprof.py prog.js ... — where a program's passes go (csssim.py, K = 32): user code, or the ROM routine user code
called (inclusive: everything under that call), the innermost ROM function (exclusive), and ROM's opcode mix.
Estimated cost: 6 ms per pass + 0.34 ms per executed level (exp/csscpu/README.md), shared among the pass's instructions.
TOP=n rows; OPS=1 the opcode mix."""
import sys, os, json, bisect, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'machine'), os.path.join(ROOT, 'compiler')]
import csssim as sim, cssref as ref
from uarch import OPN
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
names = dict(lib['fns']); names.update({n: a for n, a in lib['rt']['labels'].items() if not n.startswith(('mk_', 'b2s_f', 'add', 'sx_', 'gx_'))})
names['(jump table)'] = ref.LA['vec_base']
starts = sorted((a, n) for n, a in names.items()); addrs = [a for a, _ in starts]
def fn(pc):
    if pc >= ref.ROMN: return 'user'
    i = bisect.bisect_right(addrs, pc) - 1
    return starts[i][1] if i >= 0 else '?'
K = int(os.environ.get('K', 32)); TOP = int(os.environ.get('TOP', 12))
def prof(path):
    s = sim.Sim(ref.load(path)); incl = collections.Counter(); excl = collections.Counter(); ops = collections.Counter()
    state = {'entry': 'user', 'pass': []}
    ex0 = s.execute
    def ex(cw):
        pc = s.st['pc']; r = ex0(cw)
        if pc >= ref.ROMN and s.st['pc'] < ref.ROMN: state['entry'] = fn(s.st['pc'])
        elif pc < ref.ROMN and s.st['pc'] >= ref.ROMN: state['entry'] = 'user'
        state['pass'].append((state['entry'] if pc < ref.ROMN else 'user', fn(pc), OPN[s.st['mem'].get(pc, 0) // 8192] if pc < ref.ROMN else None))
        return r
    s.execute = ex
    while not s.st['halt'] and s.passes < 200000:
        state['pass'] = []; e0 = state['entry']
        n, why = s.run_pass(K)
        cost = 6 + 0.34 * n; P = state['pass'] or [(e0, e0, None)]
        for i, x, o in P:
            incl[i] += cost / len(P); excl[x] += cost / len(P)
            if o: ops[o] += 1
    return s, incl, excl, ops
if __name__ == '__main__':
    for path in sys.argv[1:]:
        s, incl, excl, ops = prof(path); T = sum(incl.values())
        print(f"{os.path.basename(path)}: passes {s.passes} steps {s.st['steps']} est {T / 1000:.1f} s; ROM {100 * (1 - incl['user'] / T):.0f}%")
        print('   called from user code:', ', '.join(f"{k} {100 * v / T:.0f}%" for k, v in incl.most_common(TOP)))
        print('   innermost:', ', '.join(f"{k} {100 * v / T:.0f}%" for k, v in excl.most_common(TOP)))
        if os.environ.get('OPS'): n = sum(ops.values()); print('   ROM ops:', ', '.join(f"{k} {100 * v / n:.0f}%" for k, v in ops.most_common(16)))
