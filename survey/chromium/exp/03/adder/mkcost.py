import sys
N = int(sys.argv[1])
def style(name, low):
    syms = []
    for k in range(30, -1, -1):
        on = (k < 15) if low else (15 <= k < 31)
        g = (0xE000 + (k if low else k - 15)) if on else 0xE0FF
        syms.append(f'{2**k} "\\{g:X}"')
    syms.append('0 "\\E0FF"')
    return f'@counter-style {name}{{system:additive;additive-symbols:{",".join(syms)}}}'
base = f'''@font-face{{font-family:Adder;src:url(adder.ttf)}}
@property --t{{syntax:'<number>';inherits:true;initial-value:0}}
@property --q{{syntax:'<integer>';inherits:false;initial-value:0}}
@keyframes t{{from{{--t:0}}to{{--t:100000}}}}
{style('lo', True)}{style('hi', False)}
body{{margin:0}}
.acc{{counter-reset:acc 0;animation:t 1000s linear infinite}}
.acc i{{display:block;height:0}}
.r{{display:inline-block;font:1024px/0 Adder;height:1px;overflow:hidden;vertical-align:top}}
.lo::after{{content:counter(acc, lo)}}.hi::after{{content:counter(acc, hi)}}
'''
variants = {
 'ctr': '.acc i{counter-increment:acc calc(var(--t) * 7 + sibling-index())}',
 'ctrnr': '.acc i{counter-increment:acc calc(var(--t) * 7 + sibling-index())}',
 'reg': '.acc i{--q:calc(var(--t) * 7 + sibling-index())}',
 'none': '',
 'ctrconst': '.acc i{counter-increment:acc calc(7 + sibling-index())}',
}
for v, rule in variants.items():
    readers = '' if v in ('ctrnr',) else '<span class="r lo"></span><span class="r hi"></span>'
    open(f'cost_{v}_{N}.html', 'w').write(f'<!doctype html><style>{base}{rule}</style><div class=acc>{"<i></i>" * N}{readers}</div>')
