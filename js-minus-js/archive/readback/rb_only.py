import sys; sys.path.insert(0, '/root/ui'); sys.path.insert(0, '/root/cc')
import ui_rb, ccpage5
L, P = 24, 64
src = open('/root/cc/fizz.js').read()
tls = [f'--ch{k}_{j}' for k in range(L) for j in range(P)] + [f'--cl{k}_{j}' for k in range(L) for j in range(P)]
page = f'''<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/><style><![CDATA[
:root {{ --accent: #2456c9; --ink: #111; }} body {{ timeline-scope: {", ".join(tls)}; }}
#app {{ position: relative; overflow: hidden; margin: 20px; max-width: 700px; }}
{ui_rb.css(L, P, 8)}
]]></style></head><body><main id="app"><div class="width-reader"></div><input type="checkbox" id="run"/><span class="scanpos"></span>
<div class="frame"><div id="ed" contenteditable="true" spellcheck="false">{ui_rb.editor_html(src)}</div></div><div class="rbout"></div>
{ui_rb.probes_html(L, P, 8)}</main></body></html>'''
open('/tmp/rbonly.xhtml', 'w').write(page)
