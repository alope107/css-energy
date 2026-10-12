"""lp.py — label ports per parser variant. Each port is an element on every token level (400), so the maximum
over variants matters. Lists the variants with the most ports and the totals."""
import sys, json, collections
import os, sys; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]  # repo root
from dsl import isK
import cc_ref as R, cc_dsl as D
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
progs = [(k, D.Prog(4096, 4608, lib, *k)) for k in D.variant_keys()]
progs = [(k, p) for k, p in progs if not (isK(p.x.cur['err']) and p.x.cur['err'].v != 0)]
names = {v: k for k, v in vars(R).items() if k.startswith('S_')}
inv = {D.tcode(4, v): v for v in D.PUNCT}
top = sorted(((p.nlports, len(p.x.temps), names[k[0]], k[1], k[2]) for k, p in progs), key=lambda x: (-x[0], -x[1]))[:14]
for x in top: print(x)
print('total temps', sum(len(p.x.temps) for _, p in progs), 'variants', len(progs))
