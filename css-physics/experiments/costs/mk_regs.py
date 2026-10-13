"""The register readback floor: what do R register elements (two view timelines each, like the engine's) and the
2R animations that read them cost per pass, when all of them move and when only one body's do?
Structure mirrors the engine: timeline-scope wrappers (24 names each, or one list) > #LS (2R animations into
registered inherited props --S{k}) > D nested levels > .regs > R <i> elements. --t animates on #L0 and moves the
'moving' registers' top/left; the others are restyled too (inherited change) but keep their position.
  rg_R{R}_m{moving}_{scope}.html      scope: split (24 names per wrapper) | one (a single list)
  rg_R{R}_m{moving}_novt.html         no view timelines or animations at all: the bare restyle cost of R elements
  rg_R{R}_m{moving}_perbody.html      #LS split into R/7 nested elements of 14 animations each (one per 'body')
Measure: node tools/stylebench.js rg_*.html 600 1500"""
D = 60


def page(R, moving, mode):
    T = 2 * R
    regs = "@property --t{syntax:'<number>';inherits:true;initial-value:0}"
    regs += ''.join(f"@property --S{k}{{syntax:'<number>';inherits:true;initial-value:0}}" for k in range(T))
    css = [regs, '@keyframes t{from{--t:0}to{--t:100000}}#L0{animation:t 100000s linear infinite}',
           '.lv{position:absolute;inset:0}.regs{position:fixed;left:0;top:0;width:0;height:0;overflow:clip;visibility:hidden}'
           '.regs .sc{position:absolute;left:0;top:0;width:1000000px;height:1000000px;overflow:hidden}.regs i{position:absolute;width:1px;height:1px}']
    vt = mode != 'novt'
    if vt:
        css += [f'@keyframes q{k}{{from{{--S{k}:0}}to{{--S{k}:1000}}}}' for k in range(T)]
    bodies = -(-R // 7)   # 7 register elements (14 timelines) per body, as in the engine (13 registers)
    html = ''
    if vt:
        if mode == 'one':
            html += f'<div class=lv style="timeline-scope:{",".join(f"--t{k}" for k in range(T))}">'
            nts = 1
        else:
            nts = -(-R // 24)
            for s in range(nts):
                ks = range(s * 24, min(R, s * 24 + 24))
                html += '<div class=lv style="timeline-scope:' + ','.join(f'--t{2 * k},--t{2 * k + 1}' for k in ks) + '">'
    else:
        nts = 0
    if mode == 'perbody':
        for b in range(bodies):
            ks = range(b * 7, min(R, b * 7 + 7))
            names = ','.join(f'q{2 * k},q{2 * k + 1}' for k in ks)
            tls = ','.join(f'--t{2 * k},--t{2 * k + 1}' for k in ks)
            n = 2 * len(ks)
            html += f'<div class=lv style="animation-name:{names};animation-duration:{",".join(["auto"] * n)};animation-timing-function:linear;animation-fill-mode:both;animation-timeline:{tls}">'
        nls = bodies
    elif vt:
        html += (f'<div class=lv id=LS style="animation-name:{",".join(f"q{k}" for k in range(T))};animation-duration:{",".join(["auto"] * T)};'
                 f'animation-timing-function:linear;animation-fill-mode:both;animation-timeline:{",".join(f"--t{k}" for k in range(T))}">')
        nls = 1
    else:
        html += '<div class=lv id=LS>'
        nls = 1
    html += ''.join(f'<div class=lv id=L{l}>' for l in range(D))
    html += '<div class=regs><div class=sc>'
    for k in range(R):
        mv = k < moving
        top = f'calc({k * 7}px + {1 if mv else 0} * var(--t) * 1px)'
        left = f'calc({k * 5}px + {1 if mv else 0} * var(--t) * 0.5px)'
        vts = f'view-timeline:--t{2 * k} block,--t{2 * k + 1} inline;' if vt else ''
        html += f'<i style="{vts}top:{top};left:{left}"></i>'
    html += '</div></div>' + '</div>' * (D + nls + nts)
    open(f'rg_R{R}_m{moving}_{mode}.html', 'w').write(f'<!doctype html><style>{"".join(css)}</style>{html}')


for R in (420, 840):
    for moving in (7, R):
        for mode in ('split', 'one', 'novt', 'perbody'):
            page(R, moving, mode)
