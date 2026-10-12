"""vsz.py — size of the compiler's parser variants by starting mode: how many (mode, token) variants survive (pure
errors are dropped), and their temps. Every temp is one custom-property declaration evaluated on a token level
whose variant matches, so this is the CSS cost per level. Also lists the largest variants."""
import os, sys; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]  # repo root
import json, collections
from dsl import isK
import cc_ref as R, cc_dsl as D
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
progs = [(k, D.Prog(4096, 4608, lib, *k)) for k in D.variant_keys()]
progs = [(k, p) for k, p in progs if not (isK(p.x.cur['err']) and p.x.cur['err'].v != 0)]
names = {v: k for k, v in vars(R).items() if k.startswith('S_')}
punct = lambda tk, tv: {1: 'NUM', 2: 'ID', 3: 'STR', 5: 'EOF'}.get(tk) or (repr(chr(tv)) if tv and tv > 31 else f'P{tv}')
bym = collections.Counter(); cnt = collections.Counter()
for k, p in progs: bym[names[k[0]]] += len(p.x.temps); cnt[names[k[0]]] += 1
for m, t in bym.most_common(): print(f'{m:12} variants {cnt[m]:3} temps {t:6} avg {t // cnt[m]}')
print('largest:')
for t, m, tk, tv in sorted(((len(p.x.temps), names[k[0]], k[1], k[2]) for k, p in progs), key=lambda x: -x[0])[:10]:
    print(f'  {t:5} temps  {m} {punct(tk, tv)}')
print('total temps', sum(len(p.x.temps) for _, p in progs), 'variants', len(progs))
