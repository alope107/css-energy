"""ablk.py image.json N S [top] — per-lookup cost in the full pipeline: shaping time with lookup i dropped from every cycle."""
import json, sys, os, time
import uharfbuzz as hb
import hbtest
from hbtest import state_of
from otl import build_gsub, build_gdef
from fontbase import make_font
image = json.load(open(sys.argv[1])); N, S = int(sys.argv[2]), int(sys.argv[3])
cpu = hbtest.CPU(image, N); P = cpu.P
P.build(S, top13=cpu.top13, ptype='P', export_stage=cpu.export, debug_features=0)
L = P.all_lookups; nl = P.nlib; nc = len(P.cycle_lookups)
index = list(range(len(L)))                       # identity: each lookup once in the LookupList
cyc0 = nl
SA = 2
npre = P.lookup_counts["pre"]; PRE = list(range(nl - npre, nl))
TAIL = list(range(cyc0 + nc, len(L)))
feats = [("cv01", PRE + [cyc0 + i for _ in range(SA) for i in range(nc)]), ("cvtt", PRE + [cyc0 + i for _ in range(SA) for i in range(nc)] + TAIL)]
for d in range(nc):
    feats.append((f"x{d:03d}", PRE + [cyc0 + i for _ in range(SA) for i in range(nc) if i != d]))
# LookupList with repeats: features reference indices into index_list; build index_list = lookups in order, features by position
idx_list = list(range(len(L)))
gsub = build_gsub(L, idx_list, feats)
twins = {g for t in cpu.twin.values() for g in t.gl()}
gdef = build_gdef({g: (1 if g in twins else 3) for g in range(1, P.nglyphs)}, P.mark_sets)
make_font('ablk.ttf', ['.notdef'] + [f'g{g}' for g in range(1, P.nglyphs)], {}, {0xF0000 + g: f'g{g}' for g in range(1, P.nglyphs)}, gsub, gdef)
font = hb.Font(hb.Face(hb.Blob.from_file_path('ablk.ttf')))
m = hbtest.MACH(image, N); texts = []; i = 0
while not m.halted and len(texts) < 12:
    if i % 61 == 0: texts.append(''.join(chr(0xF0000 + g) for g in cpu.encode(state_of(m))))
    m.service(m.shaping(S)); i += 1
def run(f):
    tot = 0
    for t in texts:
        best = 1e9
        for _ in range(5):
            b = hb.Buffer(); b.add_str(t); b.guess_segment_properties()
            t0 = time.perf_counter(); hb.shape(font, b, {f: True}); best = min(best, time.perf_counter() - t0)
        tot += best
    return tot / len(texts)
full = run('cv01')
if len(sys.argv) > 5: print('with tail', run('cvtt')); sys.exit()
rows = [((full - run(f"x{d:03d}")) / SA, P.cycle_lookups[d].name, len(P.cycle_lookups[d].subtables)) for d in range(nc)]
print(f"full {full*1e3:.2f} ms per {SA} cycles, {full/SA*1e6:.0f} us/cycle")
for us, n, k in sorted(rows, reverse=True)[:int(sys.argv[4]) if len(sys.argv) > 4 else 25]:
    print(f'{us*1e6:8.1f} us  {n:24} {k:3}')
print(f'sum {sum(r[0] for r in rows)*1e6:.0f} us/cycle')
