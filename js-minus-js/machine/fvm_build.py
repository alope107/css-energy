#!/usr/bin/env python3
"""fvm_build.py image.json N S out_prefix — build the font CPU (woff2) and the metadata the page generator needs."""
import sys, json, time
import os, importlib
CM = importlib.import_module(os.environ.get('CPUMOD', 'cpu2'))
CPU, width = CM.CPU, CM.width
from fontbase import make_font
from otl import build_gdef
image = json.load(open(sys.argv[1])); N, S = int(sys.argv[2]), int(sys.argv[3]); out = sys.argv[4]
t0 = time.time()
cpu = CPU(image, N); P = cpu.P
gsub = P.build(S, top13=cpu.top13, ptype='P', export_stage=cpu.export, debug_features=0)
B4 = hasattr(CM, 'WB')
twins = {g for t in cpu.twin.values() for g in t.gl()}
gdef = build_gdef({g: (1 if g in twins else 3) for g in range(1, P.nglyphs)}, P.mark_sets)
names = ['.notdef'] + [f'g{g}' for g in range(1, P.nglyphs)]
adv = cpu.advances()
make_font(out + '.woff2', names, {names[g]: a for g, a in adv.items()}, {0xF0000 + g: f'g{g}' for g in range(1, P.nglyphs) if g not in twins},
          gsub, gdef, family='FontCPU', woff2=True)
make_font(out + '.ttf', names, {names[g]: a for g, a in adv.items()}, {0xF0000 + g: f'g{g}' for g in range(1, P.nglyphs) if g not in twins}, gsub, gdef)
# cell bindings: which input cells take a value from CSS, and which glyph every other cell starts as
inputs = {}
for h, r in [('HPC', 'PC'), ('HSP', 'SP'), ('HFP', 'FP'), ('HRES', 'RES')]:
    for j in range(width(r)): inputs[cpu.core[f'{h}{j}'].pos] = (r, 'digit', j)
inputs[cpu.core['RESV'].pos] = ('RESV', 'value', 0)
for k, ln in enumerate(cpu.lines):
    inputs[ln['VF'].pos] = (f'L{k}', 'vf', 0); inputs[ln['VD'].pos] = (f'L{k}', 'vd', 0)
    for j in range(4): inputs[ln[f'TAG{j}'].pos] = (f'L{k}', 'tag', j)
    if B4:
        for w in range(CM.WB):
            inputs[ln[f'WS{w}'].pos] = (f'L{k}', 'ws', w)
            for j in range(5): inputs[ln[f'VAL{w}_{j}'].pos] = (f'L{k}', 'val', w * 8 + j)
    else:
        for j in range(5): inputs[ln[f'VAL{j}'].pos] = (f'L{k}', 'val', j)
span_of = {}
for name, cells in cpu.spans:
    for c in cells: span_of[c.pos] = name
cells = []
for c in P.cells:
    cells.append(dict(pos=c.pos, type=c.type.name, static=0xF0000 + c.type.g(c.type.values[0]),
                      input=inputs.get(c.pos), span=span_of.get(c.pos),
                      symbols=[0xF0000 + c.type.g(v) for v in c.type.values] if c.pos in inputs else None))
CVALS = CM.CVALS
meta = dict(N=N, S=S, B=(CM.WB if B4 else 1), cells=cells, spans=[n for n, _ in cpu.spans], cvals=[list(v) for v in CVALS],
            subtables_per_cycle=P.subtables_per_cycle, lookups=P.lookup_counts, nglyphs=P.nglyphs)
json.dump(meta, open(out + '.json', 'w'))
import os
print(f'{out}.woff2 {os.path.getsize(out + ".woff2")} bytes (ttf {os.path.getsize(out + ".ttf")}), {P.nglyphs} glyphs, {len(P.cells)} cells, '
      f'{P.subtables_per_cycle} subtables/cycle, lookups {P.lookup_counts}, {time.time() - t0:.1f}s')
