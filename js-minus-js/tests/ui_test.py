"""ui_test.py source.js out.html [L P T] — the typed-input compiler driven by fake latch cells (no editor/scan):
each (line, column) cell holds the code as --v, exactly what the scan readback leaves in its latches."""
import sys, json
import os, sys; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]  # repo root
import ccpage5 as C
src = open(sys.argv[1]).read().rstrip('\n'); out = sys.argv[2]
L, P, T = (int(x) for x in (sys.argv[3:6] if len(sys.argv) > 5 else (24, 64, 400)))
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
import os
pad = [ord(ch) for ch in C.padded_source(src, L, P)] + [0, 0]
css, html, tls, info = C.build(lib, L, P, T, static_src=pad if os.environ.get("STATIC") else None, short=os.environ.get("SHORT", "1") == "1")
lines = src.split('\n')
cells = []
for k in range(L):
    ln = lines[k] if k < len(lines) else ''
    row = ''.join(f'<i style="--lv: {ord(ln[j]) if j < len(ln) else 0}">{C.cell_html(k, j)}</i>' for j in range(P))
    cells.append(f'<div class="row">{row}</div>')
page = (f'<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/><style><![CDATA[@property --lv {{ syntax: "<integer>"; inherits: false; initial-value: -1; }}\n'
        f'body {{ timeline-scope: {", ".join(tls)}; }} .rows {{ height: 0; overflow: hidden; position: relative; }} .row {{ position: relative; }}\n'
        f'{C.cell_css()}\n{css}\n#run:checked ~ #ccw {{ animation: none; --ccgo: 1; }}]]></style></head><body><input type="checkbox" id="run"/><div class="rows">{"".join(cells)}</div>{html}</body></html>')
open(out, 'w').write(page)
print(info, len(page))
