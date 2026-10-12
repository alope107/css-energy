# Chromium spike: the CPU state string as ::before content across spans, inputs via counters; compare widths with HarfBuzz
import json, base64, sys
import uharfbuzz as hb
import uarch
from cpu2 import CPU
from hbtest import state_of
meta = json.load(open('fcpu.json')); image = json.load(open('image.json'))
N, S = meta['N'], meta['S']
cpu = CPU(image, N); cpu.P.assign_gids()
m = uarch.Machine(image, N)
for _ in range(int(sys.argv[1]) if len(sys.argv) > 1 else 0): m.service(m.shaping(S))
st = state_of(m)
# expected spans from HarfBuzz
font = hb.Font(hb.Face(hb.Blob.from_file_path('fcpu.ttf')))
text = ''.join(chr(0xF0000 + g) for g in cpu.encode(st))
b = hb.Buffer(); b.add_str(text); b.guess_segment_properties(); hb.shape(font, b, {'cv01': True})
gids = [i.codepoint for i in b.glyph_infos]
adv = {}
f2 = font
for name in meta['spans']: pass
# span sums from positions
pos = [p.x_advance for p in b.glyph_positions]
cells = meta['cells']
exp = {}
for c, a in zip(cells, pos):
    if c['span']: exp[c['span']] = exp.get(c['span'], 0) + a
# input values for the counters
def digit(v, j): return (v >> (4 * j)) & 15
vals = {'PC': st['pc'], 'SP': st['sp'], 'FP': st['fp'], 'RES': st['res'] & 0xFFFFF, 'RESV': st['resv']}
def cellval(c):
    r, kind, j = c['input']
    if kind == 'digit': return digit(vals[r], j)
    if kind == 'value': return vals[r]
    k = int(r[1:]); ln = st['lines'][k]
    if kind == 'vf': return int(st['vp'] == k)
    if kind == 'vd': return 0 if not ln else (2 if ln[2] else 1)
    if kind == 'tag': return 0 if not ln else digit(ln[0], j)
    if kind == 'val': return 0 if not ln else digit(ln[1] & 0xFFFFF, j)
# group consecutive cells into spans (named spans for readback, anonymous runs otherwise)
groups = []
for c in cells:
    key = c['span'] or None
    if groups and groups[-1][0] == key and key is not None: groups[-1][1].append(c)
    elif groups and key is None and groups[-1][0] is None: groups[-1][1].append(c)
    else: groups.append((key, [c]))
styles = {}
html_spans = []; css = []
for gi, (name, cs) in enumerate(groups):
    parts = []; sets = []
    for c in cs:
        if c['input']:
            sty = 'st_' + c['type'].replace('.', '_')
            styles[sty] = c['symbols']
            cn = f'c{c["pos"]}'
            sets.append(f'{cn} {cellval(c)}'); parts.append(f'counter({cn}, {sty})')
        else:
            parts.append('"\\%X "' % c['static'])
    cls = f'g{gi}'
    css.append(f'.{cls}::before {{ content: {" ".join(parts)}; }}')
    if sets: css.append(f'.{cls} {{ counter-set: {" ".join(sets)}; }}')
    html_spans.append(f'<span class="{cls}"{f" id={name}" if name else ""}></span>')
for sty, syms in styles.items():
    css.append(f'@counter-style {sty} {{ system: fixed 0; symbols: {" ".join(chr(34) + chr(92) + "%X " % s + chr(34) for s in syms)}; }}')
font64 = base64.b64encode(open('fcpu.woff2', 'rb').read()).decode()
open('spike.html', 'w').write(f"""<!doctype html><meta charset=utf-8><style>
@font-face {{ font-family: FontCPU; src: url(data:font/woff2;base64,{font64}); }}
#p {{ font: 16px/1 FontCPU; font-feature-settings: "cv01" 1; white-space: pre; width: max-content; }}
{chr(10).join(css)}
</style><div id=p>{''.join(html_spans)}</div>""")
json.dump(exp, open('spike_expected.json', 'w'))
print('spans', len(exp), 'example', {k: exp[k] for k in list(exp)[:6]})
