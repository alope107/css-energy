# per-lookup cost on realistic mid-run states (cycle boundaries sampled from a model-driven run)
import json, time, sys, random, os
import uharfbuzz as hb
import os, importlib
CPU = importlib.import_module(os.environ.get("CPUMOD", "cpu2")).CPU
from fontbase import make_font
from otl import build_gdef, build_gsub
import uarch, uarch4
from hbtest import state_of
image = json.load(open(os.environ.get('IMG', 'image.json'))); N = int(sys.argv[1]); S = int(sys.argv[2])
cpu = CPU(image, N); P = cpu.P
P.build(S, top13=cpu.top13, ptype='P')
nL, cyc = P.nlib, P.cycle_lookups
lookups = P.all_lookups[:nL + len(cyc)]
index = list(range(nL)) + [nL + i for _ in range(S) for i in range(len(cyc))] + [nL + i for i in range(len(cyc))]
base = nL + S * len(cyc)
feats = [(f'ss{k:02d}', list(range(nL, nL + k * len(cyc)))) for k in range(1, S)] + [(f'z{i:03d}', [base + i]) for i in range(len(cyc))]
gsub = build_gsub(lookups, index, feats)
gdef = build_gdef({g: 3 for g in range(1, P.nglyphs)}, P.mark_sets)
make_font('st.ttf', ['.notdef'] + [f'g{g}' for g in range(1, P.nglyphs)], {}, {0xF0000 + g: f'g{g}' for g in range(1, P.nglyphs)}, gsub, gdef)
font = hb.Font(hb.Face(hb.Blob.from_file_path('st.ttf')))
def shape(text, f):
    b = hb.Buffer(); b.add_str(text); b.guess_segment_properties(); hb.shape(font, b, {f: True} if f else {}); return b
m = (uarch4.Machine4 if os.environ.get('CPUMOD') == 'cpu4' else uarch.Machine)(image, N); random.seed(3); states = []
for i in range(1500):
    if i % 30 == 0:
        text = ''.join(chr(0xF0000 + g) for g in cpu.encode(state_of(m)))
        k = random.randrange(1, S)
        g = [x.codepoint for x in shape(text, f'ss{k:02d}').glyph_infos]
        states.append(''.join(chr(0xF0000 + x) for x in g))
    m.service(m.shaping(S))
    if m.halted: break
rows = []
t_empty = 0
def tmin(st, f, r=5):
    best = 1e9
    for _ in range(r):
        t0 = time.perf_counter(); shape(st, f); best = min(best, time.perf_counter() - t0)
    return best
states = states[:int(os.environ.get('NST', 20))]
for st in states: t_empty += tmin(st, None)
t_empty /= len(states)
for i, lk in enumerate(cyc):
    t = 0
    for st in states: t += tmin(st, f'z{i:03d}')
    rows.append((t / len(states) - t_empty, lk.name, len(lk.subtables)))
tot = sum(r[0] for r in rows)
for ms, name, ns in sorted(rows, reverse=True)[:int(sys.argv[3]) if len(sys.argv) > 3 else 15]:
    print(f'{ms * 1e6:8.1f} us  {name:16} {ns:3} subtables')
print(f'total {tot * 1e6:.0f} us per cycle over {len(states)} states')
