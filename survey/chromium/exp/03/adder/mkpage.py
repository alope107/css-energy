import sys
N = int(sys.argv[1]) if len(sys.argv) > 1 else 64
K = 123457
def style(name, low):
    syms = []
    for k in range(29, -1, -1):
        on = (k < 15) if low else (15 <= k < 30)
        g = (0xE000 + (k if low else k - 15)) if on else 0xE0FF
        syms.append(f'{2**k} "\\{g:X}"')
    syms.append('0 "\\E0FF"')
    return f'@counter-style {name}{{system:additive;additive-symbols:{",".join(syms)}}}'
css = f'''@font-face{{font-family:Adder;src:url(adder.ttf)}}
@property --hiw{{syntax:'<number>';inherits:true;initial-value:0}}
@property --low{{syntax:'<number>';inherits:true;initial-value:0}}
@property --ok{{syntax:'<integer>';inherits:false;initial-value:0}}
@property --v{{syntax:'<integer>';inherits:false;initial-value:0}}
{style('lo', True)}{style('hi', False)}
body{{margin:0}}
.acc{{counter-reset:acc 0}}
.acc i{{display:block;height:0}}
.calc i{{counter-increment:acc calc(sibling-index() * {K})}}
.varbig i{{--v:calc(sibling-index() * {K});counter-increment:acc var(--v)}}
.varlit i{{--v:1048575;counter-increment:acc var(--v)}}
.r{{display:inline-block;font:1024px/0 Adder;height:1px;overflow:hidden;vertical-align:top}}
.lo::after{{content:counter(acc, lo)}}
.hi::after{{content:counter(acc, hi)}}
.dec::after{{content:counter(acc)}}
#lo1{{anchor-name:--lo}}#hi1{{anchor-name:--hi}}
.rdhi{{position:fixed;left:0;top:100px;height:1px;width:anchor-size(--hi width);container-type:inline-size}}
.mid{{--hiw:calc(100cqw / 1px)}}
.rdlo{{position:fixed;left:0;top:110px;height:1px;width:anchor-size(--lo width);container-type:inline-size}}
#res{{--low:calc(100cqw / 1px);--ok:calc(1 - sign(abs(var(--hiw) * 32768 + var(--low) - {K * N * (N + 1) // 2})))}}
'''
items = '<i></i>' * N
body = f'''<div class="acc calc" id=a1>{items}<span class="r lo" id=lo1 data-w></span><span class="r hi" id=hi1 data-w></span><span class=dec id=d1 data-w style="font:10px monospace"></span></div>
<div class="acc varbig">{items}<span class="r lo" id=lo2 data-w></span><span class="r hi" id=hi2 data-w></span></div>
<div class="acc varlit">{items}<span class="r lo" id=lo3 data-w></span><span class="r hi" id=hi3 data-w></span></div>
<div class=rdhi><div class=mid><div class=rdlo><i id=res data-read="--hiw --low --ok"></i></div></div></div>'''
open(f'adder{N}.html', 'w').write(f'<!doctype html><style>{css}</style>{body}')
print('expected', K * N * (N + 1) // 2, 'hi', (K * N * (N + 1) // 2) >> 15, 'lo', (K * N * (N + 1) // 2) & 32767,
      '| varlit', 1048575 * N, (1048575 * N) >> 15, (1048575 * N) & 32767)
