import json, time, sys
import uharfbuzz as hb
from cpu2 import CPU
from fontbase import make_font
from otl import build_gdef, build_gsub
import uarch
from hbtest import state_of
image = json.load(open('image.json')); N = int(sys.argv[1])
cpu = CPU(image, N); P = cpu.P
P.build(1, top13=cpu.top13, ptype='P')
sets, cyc = P.all_lookups[:P.nlib], P.cycle_lookups
lookups = sets + cyc
index = list(range(len(lookups)))
feats = [(f'z{i:03d}', [len(sets) + i] * 1) for i in range(len(cyc))]
gsub = build_gsub(lookups, index, feats)
gdef = build_gdef({g: 3 for g in range(1, P.nglyphs)}, P.mark_sets)
names = ['.notdef'] + [f'g{g}' for g in range(1, P.nglyphs)]
make_font('t.ttf', names, {}, {0xF0000 + g: f'g{g}' for g in range(1, P.nglyphs)}, gsub, gdef)
font = hb.Font(hb.Face(hb.Blob.from_file_path('t.ttf')))
m = uarch.Machine(image, N); m.prologue()
text = ''.join(chr(0xF0000 + g) for g in cpu.encode(state_of(m)))
rows = []
for i, lk in enumerate(cyc):
    t = 0
    for _ in range(20):
        b = hb.Buffer(); b.add_str(text); b.guess_segment_properties()
        t0 = time.perf_counter(); hb.shape(font, b, {f'z{i:03d}': True}); t += time.perf_counter() - t0
    rows.append((t / 20 * 1e3, lk.name, len(lk.subtables)))
b = hb.Buffer(); b.add_str(text); b.guess_segment_properties(); t0 = time.perf_counter(); hb.shape(font, b, {}); base = (time.perf_counter() - t0) * 1e3
for ms, name, ns in sorted(rows, reverse=True): print(f'{ms - base:8.3f} ms  {name:20} {ns} subtables')
print('empty shape', round(base, 3), 'ms; total', round(sum(r[0] - base for r in rows), 2))
