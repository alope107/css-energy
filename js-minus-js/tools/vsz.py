"""vsz.py — size of the compiler's parser variants: how many (mode, token) variants survive (pure errors are dropped),
their temps and their label ports. Every temp is a custom-property declaration on each token level whose variant
matches, and every label port is an element on all 400 token levels, so watch the total temps and the maximum ports."""
import os, sys; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]  # repo root
import json, collections
from dsl import isK
import cc_ref as R, cc_dsl as D
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
progs = [(k, D.Prog(R.LAYOUT['data_base'], R.LAYOUT['code_base'], lib, *k)) for k in D.variant_keys()]
progs = [(k, p) for k, p in progs if not (isK(p.x.cur['err']) and p.x.cur['err'].v != 0)]
names = {v: k for k, v in vars(R).items() if k.startswith('S_')}
punct = lambda tk, tv: {1: 'NUM', 2: 'ID', 3: 'STR', 5: 'EOF'}.get(tk) or (repr(chr(tv)) if tv and tv > 31 else f'P{tv}')
bym = collections.Counter(); cnt = collections.Counter()
for k, p in progs: bym[names[k[0]]] += len(p.x.temps); cnt[names[k[0]]] += 1
for m, t in bym.most_common(): print(f'{m:12} variants {cnt[m]:3} temps {t:6} avg {t // cnt[m]}')
print('largest (temps, label ports):')
for t, lp, m, tk, tv in sorted(((len(p.x.temps), p.nlports, names[k[0]], k[1], k[2]) for k, p in progs), key=lambda x: -x[0])[:10]:
    print(f'  {t:5} temps  {lp:2} ports  {m} {punct(tk, tv)}')
print('most label ports:')
for lp, t, m, tk, tv in sorted(((p.nlports, len(p.x.temps), names[k[0]], k[1], k[2]) for k, p in progs), key=lambda x: (-x[0], -x[1]))[:5]:
    print(f'  {lp:2} ports  {t:5} temps  {m} {punct(tk, tv)}')
print('total temps', sum(len(p.x.temps) for _, p in progs), 'variants', len(progs), 'max ports', max(p.nlports for _, p in progs))
