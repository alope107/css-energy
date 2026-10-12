import sys, json
import uharfbuzz as hb
from cpu2 import CPU
from fontbase import make_font
from otl import build_gdef, build_gsub
import uarch
from hbtest import state_of
image = json.load(open('image.json')); N = int(sys.argv[1]); K = int(sys.argv[2]); fields = sys.argv[3].split(','); X = int(sys.argv[4]) if len(sys.argv) > 4 else 0; S0 = int(sys.argv[5]) if len(sys.argv) > 5 else 8
cpu = CPU(image, N); P = cpu.P
P.build(1, top13=cpu.top13, ptype='P')
nL, cyc = P.nlib, P.cycle_lookups
lookups = P.all_lookups[:nL + len(cyc)]
index = list(range(nL)) + [nL + i for _ in range(K + 1) for i in range(len(cyc))]
feats = [('full', list(range(nL, nL + K * len(cyc))))] + [(f'p{i:03d}', [nL + K * len(cyc) + i]) for i in range(len(cyc))]
gsub = build_gsub(lookups, index, feats)
gdef = build_gdef({g: 3 for g in range(1, P.nglyphs)}, P.mark_sets)
make_font('lk.ttf', ['.notdef'] + [f'g{g}' for g in range(1, P.nglyphs)], {}, {0xF0000 + g: f'g{g}' for g in range(1, P.nglyphs)}, gsub, gdef)
font = hb.Font(hb.Face(hb.Blob.from_file_path('lk.ttf')))
def shape(text, f):
    b = hb.Buffer(); b.add_str(text); b.guess_segment_properties(); hb.shape(font, b, {f: True} if f else {})
    return [i.codepoint for i in b.glyph_infos]
m = uarch.Machine(image, N)
for _ in range(X): m.service(m.shaping(S0))
text = ''.join(chr(0xF0000 + g) for g in cpu.encode(state_of(m)))
g = shape(text, 'full') if K else [ord(ch) - 0xF0000 for ch in text]
def show(gids, label):
    r = {(c.field if c.region == 'core' else f'L{c.line}.{c.field}'): P.by_gid[x][1] for c, x in zip(P.cells, gids)}
    print(f'{label:28}', ' '.join(f'{f}={r[f]}' for f in fields))
show(g, 'start')
for i, lk in enumerate(cyc):
    g = shape(''.join(chr(0xF0000 + x) for x in g), f'p{i:03d}')
    show(g, lk.name)
