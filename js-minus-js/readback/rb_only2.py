# standalone editor + frame-locked scan (ui_rb), for testing the readback alone. argv: out.xhtml [formula]
import os, sys; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]  # repo root
import ui_rb
L, P = 24, 64
out = sys.argv[1]
sw, dw = (int(x) for x in (sys.argv[2:4] if len(sys.argv) > 3 else (1, 1)))
css = ui_rb.css(L, P, 8, sw, dw)
tls = [f'--ch{k}_{j}' for k in range(L) for j in range(P)] + [f'--cl{k}_{j}' for k in range(L) for j in range(P)]
page = f'''<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/><style><![CDATA[
:root {{ --accent: #2456c9; --ink: #111; }} body {{ timeline-scope: {", ".join(tls)}, --rbrdT; }}
#app {{ position: relative; overflow: hidden; margin: 20px; width: 700px; height: 900px; contain: strict; }}
{css}
]]></style></head><body><input type="checkbox" id="run"/><main id="app"><div class="width-reader"></div>{ui_rb.regs_html()}<span class="scanpos"></span>
<div class="frame"><div id="ed" contenteditable="true" spellcheck="false">{ui_rb.editor_html("x")}</div></div><div class="rbout"></div>
{ui_rb.probes_html(L, P, 8)}</main></body></html>'''
open(out, 'w').write(page)
