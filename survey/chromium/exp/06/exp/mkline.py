# mkline.py MODE FEAT out.html
# MODE: cells (one ::before counter per cell, 1274 items, like the CPU page), spans173 (173 spans, statics+counters as
# in the page), one (all statics in one text node + one changing counter). FEAT: value of cv01.
import json, sys
mode, feat, out = sys.argv[1], sys.argv[2], sys.argv[3]
m = json.load(open('f4cc_16.json'))
cells = m['cells']
css, html = [], []
def ch(c): return c['static'] if c['static'] is not None else c['symbols'][0]
syms = cells[-1]['symbols'] or [0xF0001] * 16
# a cyclic counter style over 16 PUA glyphs of an input cell type (any cell with symbols)
sc = next(c for c in cells if c['symbols'])['symbols']
css.append('@counter-style hx { system: cyclic; symbols: ' + ' '.join('"\\%X "' % s for s in sc) + '; }')
if mode == 'cells':
    for i, c in enumerate(cells):
        if i == 0:
            html.append('<span class="t"></span>')
        else:
            html.append('<span>&#x%X;</span>' % ch(c))
elif mode == 'pseudo':   # every cell a ::before counter like the page: counter value animated on cell 0 only
    for i, c in enumerate(cells):
        cls = 't' if i == 0 else 'c%d' % i
        if i: css.append('.c%d::before { content: "\\%X "; }' % (i, ch(c)))
        html.append('<span class="%s"></span>' % cls)
elif mode == 'one':
    html.append('<span class="t"></span>' + ''.join('&#x%X;' % ch(c) for c in cells[1:]))
html_s = ''.join(html)
page = f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: FontCPU; src: url(f4cc_16.woff2); }}
@property --x {{ syntax: "<integer>"; inherits: false; initial-value: 0; }}
@keyframes k {{ from {{ --x: 0; }} to {{ --x: 1600; }} }}
{chr(10).join(css)}
.t {{ animation: k 1s steps(1600) infinite; counter-set: q var(--x); }}
.t::before {{ content: counter(q, hx); }}
#state {{ position: fixed; top: 0; left: 0; font: 1024px/1 FontCPU; font-feature-settings: "cv01" {feat}; white-space: pre; width: max-content; visibility: hidden; }}
</style></head><body><div id="state">{html_s}</div></body></html>'''
open(out, 'w').write(page)
