"""What does reading a register back cost, and what does it depend on?
R register elements (2 values each, top/left in a 1e6 px scroller) move every frame, driven by a clock (no feedback);
their 2R values are read back with scroll-driven animations on nested elements of G animations each, and one element
below sums them all (so every value is used). One style pass per frame.
  rb_{name}.html, name = {R}_{G}_{type}_{scope}
    type:  number | integer | length     (the registered syntax of the read-back properties)
    scope: nest (timeline-scope on wrappers of 24 names, as the engine) | one (one list on one wrapper) | all (timeline-scope: all)
  rb_{R}_none.html: the registers move, nothing reads them (the floor)
Measure: node tools/stylebench.js page 800 1500 (or ../shared/js/ab.js -p med)"""
import sys

HS = 1_000_000


def page(R, G, typ, scope, name):
    T = 2 * R
    syn = {'number': '<number>', 'integer': '<integer>', 'length': '<length>'}[typ]
    unit = 'px' if typ == 'length' else ''
    hi = 1000 if typ != 'integer' else 1000000
    css = ["@property --clk{syntax:'<number>';inherits:true;initial-value:0}"]
    css += [f"@property --v{k}{{syntax:'{syn}';inherits:true;initial-value:0{unit}}}" for k in range(T)]
    css.append("@property --sum{syntax:'<number>';inherits:true;initial-value:0}")
    css.append('@keyframes clk{from{--clk:0}to{--clk:100000}}#CL{animation:clk 100000s linear infinite}')
    css.append('.lv{position:absolute;inset:0}.regs{position:fixed;left:0;top:0;width:0;height:0;overflow:clip;visibility:hidden}'
               f'.sc{{position:absolute;left:0;top:0;width:{HS}px;height:{HS}px;overflow:hidden}}.sc i{{position:absolute;width:1px;height:1px}}')
    for k in range(R):
        css.append(f'#r{k}{{view-timeline:--t{2 * k} block,--t{2 * k + 1} inline;'
                   f'top:calc({(k * 977) % 900000}px + var(--clk) * 1px);left:calc({(k * 631) % 900000}px + var(--clk) * 0.5px)}}')
    html = '<div id=CL class=lv>'
    nts = 0
    if G:
        css += [f'@keyframes q{k}{{from{{--v{k}:0{unit}}}to{{--v{k}:{hi}{unit}}}}}' for k in range(T)]
        if scope == 'all':
            html += '<div class=lv style="timeline-scope:all">'
            nts = 1
        elif scope == 'one':
            html += '<div class=lv style="timeline-scope:' + ','.join(f'--t{k}' for k in range(T)) + '">'
            nts = 1
        else:
            for s in range(0, R, 24):
                html += '<div class=lv style="timeline-scope:' + ','.join(f'--t{2 * k},--t{2 * k + 1}' for k in range(s, min(R, s + 24))) + '">'
                nts += 1
        groups = [list(range(i, min(T, i + G))) for i in range(0, T, G)]
        for gi, gr in enumerate(groups):
            css.append(f'#g{gi}{{animation-name:{",".join(f"q{k}" for k in gr)};animation-duration:{",".join(["auto"] * len(gr))};'
                       f'animation-timing-function:linear;animation-fill-mode:both;animation-timeline:{",".join(f"--t{k}" for k in gr)}}}')
            html += f'<div class=lv id=g{gi}>'
        div = '1px' if typ == 'length' else '1'
        css.append('#S{--sum:calc(' + ' + '.join(f'var(--v{k}) / {div}' for k in range(T)) + ')}')
        html += '<div class=lv id=S></div>' + '</div>' * len(groups)
    html += '<div class=regs><div class=sc>' + ''.join(f'<i id=r{k}></i>' for k in range(R)) + '</div></div>'
    html += '</div>' * nts + '</div>'
    open(f'rb_{name}.html', 'w').write(f'<!doctype html><style>{"".join(css)}</style><body>{html}</body>')


R = int(sys.argv[1]) if len(sys.argv) > 1 else 450
page(R, 0, 'number', 'nest', f'{R}_none')
for G in (8, 32, 128, 2 * R):
    page(R, G, 'number', 'nest', f'{R}_{G}_number_nest')
for typ in ('integer', 'length'):
    page(R, 32, typ, 'nest', f'{R}_32_{typ}_nest')
for scope in ('one', 'all'):
    page(R, 32, 'number', scope, f'{R}_32_number_{scope}')
