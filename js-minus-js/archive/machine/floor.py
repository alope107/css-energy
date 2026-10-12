import json, sys, time
import uharfbuzz as hb
import hbtest
from hbtest import state_of
from otl import build_gsub, build_gdef
from fontbase import make_font
image = json.load(open('image.json')); N = 16
cpu = hbtest.CPU(image, N); P = cpu.P
P.build(1, top13=cpu.top13, ptype='P', export_stage=cpu.export, debug_features=0)
L = P.all_lookups; names = [l.name for l in L]
pick = {n: names.index(n) for n in ['K5 vf', 'K3 init', 'K3 gather:G3', 'K3 any', 'K2 MAR.1', 'K3 busA1'] if n in names}
idx = list(range(len(L))); feats = []
for tag, (n, i) in zip(['aaaa', 'bbbb', 'cccc', 'dddd', 'eeee', 'ffff'], pick.items()):
    base = len(idx); idx += [i] * 100; feats.append((tag, list(range(base, base + 100))))
gsub = build_gsub(L, idx, feats)
twins = {g for t in cpu.twin.values() for g in t.gl()}
gdef = build_gdef({g: (1 if g in twins else 3) for g in range(1, P.nglyphs)}, P.mark_sets)
make_font('floor.ttf', ['.notdef'] + [f'g{g}' for g in range(1, P.nglyphs)], {}, {0xF0000 + g: f'g{g}' for g in range(1, P.nglyphs)}, gsub, gdef)
font = hb.Font(hb.Face(hb.Blob.from_file_path('floor.ttf')))
m = hbtest.MACH(image, N)
for _ in range(300): m.service(m.shaping(16))
t = ''.join(chr(0xF0000 + g) for g in cpu.encode(state_of(m)))
def tm(f):
    best = 1e9
    for _ in range(9):
        b = hb.Buffer(); b.add_str(t); b.guess_segment_properties()
        t0 = time.perf_counter(); hb.shape(font, b, {f: True} if f else {}); best = min(best, time.perf_counter() - t0)
    return best
e = tm(None)
for tag, (n, i) in zip(['aaaa', 'bbbb', 'cccc', 'dddd', 'eeee', 'ffff'], pick.items()):
    print(f'{n:16} {(tm(tag) - e) / 100 * 1e6:7.2f} us per application ({len(L[i].subtables)} subtables)')
