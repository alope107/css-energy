"""prof4.py image.json N [top] — per-lookup cost in context: time(pre + 1 cycle + first d+1 lookups of cycle 2)
minus time(... first d). Median over states of min-of-5 timings."""
import json, sys, os, time, statistics
import uharfbuzz as hb
import hbtest
from hbtest import state_of
from otl import build_gsub, build_gdef
from fontbase import make_font
image = json.load(open(sys.argv[1])); N = int(sys.argv[2])
cpu = hbtest.CPU(image, N); P = cpu.P
P.build(2, top13=cpu.top13, ptype='P', export_stage=cpu.export, debug_features=0)
L = P.all_lookups; nl = P.nlib; nc = len(P.cycle_lookups); npre = P.lookup_counts['pre']; nlib = nl - npre
idx = list(range(nl)) + [nl + i for i in range(nc)] + [nl + i for i in range(nc)]
PRE = list(range(nlib, nl)); C1 = list(range(nl, nl + nc)); C2 = list(range(nl + nc, nl + 2 * nc))
feats = [(f'p{d:03d}', PRE + C1 + C2[:d]) for d in range(nc + 1)]
gsub = build_gsub(L, idx, feats)
twins = {g for t in cpu.twin.values() for g in t.gl()}
gdef = build_gdef({g: (1 if g in twins else 3) for g in range(1, P.nglyphs)}, P.mark_sets)
make_font('prof4.ttf', ['.notdef'] + [f'g{g}' for g in range(1, P.nglyphs)], {}, {0xF0000 + g: f'g{g}' for g in range(1, P.nglyphs)}, gsub, gdef)
font = hb.Font(hb.Face(hb.Blob.from_file_path('prof4.ttf')))
m = hbtest.MACH(image, N); texts = []; i = 0
while not m.halted and len(texts) < int(os.environ.get('NST', 16)):
    if i % 53 == 0: texts.append(''.join(chr(0xF0000 + g) for g in cpu.encode(state_of(m))))
    m.service(m.shaping(int(os.environ.get('S', 16)))); i += 1
def t1(t, f):
    best = 1e9
    for _ in range(5):
        b = hb.Buffer(); b.add_str(t); b.guess_segment_properties()
        t0 = time.perf_counter(); hb.shape(font, b, {f: True}); best = min(best, time.perf_counter() - t0)
    return best
T = [[t1(t, f'p{d:03d}') for d in range(nc + 1)] for t in texts]
rows = []
for d in range(nc):
    rows.append((statistics.median(T[s][d + 1] - T[s][d] for s in range(len(texts))), P.cycle_lookups[d].name, len(P.cycle_lookups[d].subtables)))
cyc = statistics.median(T[s][nc] - T[s][0] for s in range(len(texts)))
print(f'one cycle: {cyc*1e6:.0f} us ({nc} lookups, {len(P.cells)} cells)')
for us, n, k in sorted(rows, reverse=True)[:int(sys.argv[3]) if len(sys.argv) > 3 else 30]:
    print(f'{us*1e6:8.1f} us  {n:26} {k:3}')
