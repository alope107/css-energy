# animation creation vs inheritance costs: chain of D display:contents levels each reading var(--a<i>) from sources
import sys
mode, D, NA = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
css = ['@property --v { syntax: "<integer>"; inherits: true; initial-value: 0; }', '@property --x { syntax: "<integer>"; inherits: false; initial-value: 0; }']
css += [f'@property --a{i} {{ syntax: "<integer>"; inherits: true; initial-value: 0; }} @keyframes k{i} {{ from {{ --a{i}: 100; }} to {{ --a{i}: -1; }} }}' for i in range(NA)]
css.append('body { timeline-scope: ' + ', '.join(f'--t{i}' for i in range(NA)) + '; }')
css.append('.reg { position: relative; height: 100px; overflow: hidden; width: 2px; } .reg > b { position: absolute; top: calc(var(--v) * 1px); height: 1px; width: 1px; display: block; } .reg > i { display: block; height: 100px; }')
css.append('.lv { display: contents; --x: calc(var(--a' + str(0) + ') + 1); } .gate { display: none; } body:has(#go:checked) .gate { display: contents; }')
src_anim = f'animation: {", ".join(f"k{i} auto linear both" for i in range(NA))}; animation-timeline: {", ".join(f"--t{i}" for i in range(NA))};'
regs = '<div style="height:0;overflow:hidden">' + ''.join(f'<div class="reg" style="--v: {i % 90}"><b style="view-timeline-name: --t{i}"></b><i></i></div>' for i in range(NA)) + '</div>'
levels = ''.join(f'<div class="lv" style="--x: var(--a{i % NA})">' for i in range(D)) + '</div>' * D
if mode == 'inside':     # sources created when the gate opens
    body = f'<input type="checkbox" id="go"/>{regs}<div class="gate"><div style="{src_anim} display: contents">{levels}</div></div>'
else:                    # permanent sources above the gate
    body = f'<input type="checkbox" id="go"/>{regs}<div style="{src_anim} display: contents"><div class="gate">{levels}</div></div>'
open(f'an_{mode}.xhtml', 'w').write(f'<html xmlns="http://www.w3.org/1999/xhtml"><head><style><![CDATA[{chr(10).join(css)}]]></style></head><body>{body}</body></html>')
if mode in ('nested', 'nested0'):
    P = 64; L = D // (P + 1)
    css2 = list(css)
    css2 += [f'@property --lc{j} {{ syntax: "<integer>"; inherits: true; initial-value: 0; }} @keyframes kl{j} {{ from {{ --lc{j}: 100; }} to {{ --lc{j}: -1; }} }}' for j in range(P)]
    css2 += [f'@property --s{q} {{ syntax: "<integer>"; inherits: true; initial-value: 0; }}' for q in range(30)]
    css2.append('.ls { display: contents; ' + ('' if mode == 'nested0' else f'animation: {", ".join(f"kl{j} auto linear both" for j in range(P))};') + ' }')
    css2.append('.lv { ' + ' '.join(f'--s{q}: calc(var(--s{(q + 1) % 30}) + var(--x));' for q in range(30)) + ' }')
    out = []
    for k in range(L):
        out.append(f'<div class="ls" style="animation-timeline: {", ".join(f"--t{(k * P + j) % NA}" for j in range(P))}">')
        out += [f'<div class="lv" style="--x: var(--lc{j})">' for j in range(P + 1)]
    lv = ''.join(out) + '</div>' * (L * (P + 2))
    body = f'<input type="checkbox" id="go"/>{regs}<div class="gate">{lv}</div>'
    open(f'an_{mode}.xhtml', 'w').write(f'<html xmlns="http://www.w3.org/1999/xhtml"><head><style><![CDATA[{chr(10).join(css2)}]]></style></head><body>{body}</body></html>')
