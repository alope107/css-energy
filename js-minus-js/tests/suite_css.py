"""suite_css.py [page.xhtml] [dir] — level 3: the CSS compiler itself (ccpage5) in Chromium.
Builds ONE fake-latch page (the latch cells' --lv set by the harness, as the scan readback would leave them) and
an expectation file: for every test, cc_ref's code words and data image on the padded source. suite_css.js then
types each program into the cells, runs the chain, and compares every overlay word."""
import sys, os, json, glob
import os, sys; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]  # repo root
import ccpage5 as C, cc_ref as R
L, P, T = 24, 64, 400
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build', 'suite_css.xhtml')
HERE = os.path.dirname(os.path.abspath(__file__))
dirs = sys.argv[2:] or [os.path.join(HERE, 'suite'), os.path.join(HERE, 'suite_err')]
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
exp = {}
for f in sorted(f for d in dirs for f in glob.glob(d + '/*.js')):
    src = open(f).read().rstrip('\n')
    c = R.Compiler(R.LAYOUT['data_base'], R.LAYOUT['code_base'], lib); words, data = c.compile(C.padded_source(src, L, P))
    im = R.image_mem(c, {}, data, lib['init'])
    lines = src.split('\n')
    exp[os.path.basename(f)[:-3]] = dict(lines=[[ord(ch) for ch in ln] for ln in lines], err=c.err,
                                         code={str(a): w for a, w in words.items()}, data={str(a): v for a, v in im.items()})
exp['_base'] = R.LAYOUT['rom_size']           # anchor --c<k> is RAM index k = address - rom_size
os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
json.dump(exp, open(out + '.exp.json', 'w'))
if os.path.exists(out) and os.environ.get('REBUILD') != '1': print('page exists; expectations written'); sys.exit()
css, html, tls, info = C.build(lib, L, P, T)
cells = ''.join('<div class="row">' + ''.join(f'<i style="--lv: 0">{C.cell_html(k, j)}</i>' for j in range(P)) + '</div>' for k in range(L))
page = (f'<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/><style><![CDATA[@property --lv {{ syntax: "<integer>"; inherits: false; initial-value: -1; }}\n'
        f'body {{ timeline-scope: {", ".join(tls)}; }} .rows {{ height: 0; overflow: hidden; position: relative; }} .row {{ position: relative; }}\n'
        f'{C.cell_css()}\n{css}\n#run:checked ~ #ccw {{ animation: none; --ccgo: 1; }}]]></style></head><body><input type="checkbox" id="run"/><div class="rows">{cells}</div>{html}</body></html>')
open(out, 'w').write(page)
print(info, len(page))
