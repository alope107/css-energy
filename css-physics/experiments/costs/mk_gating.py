"""Container-query gating costs. Writes:
  cq0.html                no gated rules (baseline)
  cqa{R}.html             R rules @container zz{k}{...}, name absent             -> ~free
  cqn{R}.html             R rules nested: present name, then absent name        -> ~free
  cqm{R}.html             R rules nested: absent, absent                         -> ~free
  n*.html                 3-deep nests (present/present/absent etc.)             -> ~free
  sqp5000.html            5000 @container pres style(--gK: 7), name present, false, container restyles -> ~3.5 us/rule
  sqa5000.html            same with the name absent                              -> ~0.1 us/rule
Measure: node tools/stylebench.js cq0.html,cqa50000.html,... 500 1500"""
def page(name, R, mode):
    regs = "@property --t{syntax:'<number>';inherits:true;initial-value:0}@property --o{syntax:'<number>';inherits:false;initial-value:0}"
    rules = ''
    for k in range(R):
        if mode == 'absent': rules += f'@container zz{k}{{#b{{--o:calc(var(--t) * {k})}}}}'
        elif mode == 'nested': rules += f'@container pres{{@container zz{k}{{#b{{--o:calc(var(--t) * {k})}}}}}}'
        elif mode == 'nest2': rules += f'@container zz{k}{{@container yy{k}{{#b{{--o:calc(var(--t) * {k})}}}}}}'
    css = f"{regs}@keyframes t{{from{{--t:0}}to{{--t:1000}}}}#a{{animation:t 1000s linear infinite}}#c1,#c2,#c3{{container-name:pres q1 q2}}#b{{--o:var(--t)}}{rules}"
    open(name, 'w').write(f'<!doctype html><style>{css}</style><div id=a><div id=c1><div id=c2><div id=c3><div id=b></div></div></div></div></div>')

def nest(name, R, names):
    regs = "@property --t{syntax:'<number>';inherits:true;initial-value:0}@property --o{syntax:'<number>';inherits:false;initial-value:0}"
    def wrap(k):
        inner = f'#b{{--o:calc(var(--t) * {k})}}'
        for n in reversed(names): inner = f'@container {n.format(k=k)}{{{inner}}}'
        return inner
    css = f"{regs}@keyframes t{{from{{--t:0}}to{{--t:1000}}}}#a{{animation:t 1000s linear infinite}}#c1{{container-name:p1 p2 p3}}#b{{--o:var(--t)}}{''.join(wrap(k) for k in range(R))}"
    open(name, 'w').write(f'<!doctype html><style>{css}</style><div id=a><div id=c1><div id=b></div></div></div>')

def styleq(name, R, present):
    regs = "@property --t{syntax:'<number>';inherits:true;initial-value:0}@property --o{syntax:'<number>';inherits:false;initial-value:0}"
    regs += ''.join(f"@property --g{k}{{syntax:'<integer>';inherits:false;initial-value:0}}" for k in range(R))
    rules = ''.join(f'@container {"pres" if present else "abs"} style(--g{k}: 7){{#b{{--o:calc(var(--t) * {k})}}}}' for k in range(R))
    css = f"{regs}@keyframes t{{from{{--t:0}}to{{--t:1000}}}}#a{{animation:t 1000s linear infinite}}#c1{{container-name:pres q1;--g0:calc(var(--t) * 0)}}#b{{--o:var(--t)}}{rules}"
    open(name, 'w').write(f'<!doctype html><style>{css}</style><div id=a><div id=c1><div id=b></div></div></div>')

page('cq0.html', 0, 'absent')
for R in (10000, 50000):
    page(f'cqa{R}.html', R, 'absent'); page(f'cqn{R}.html', R, 'nested'); page(f'cqm{R}.html', R, 'nest2')
nest('n0.html', 0, []); nest('nppa.html', 20000, ['p1', 'p2', 'zz{k}']); nest('nppp.html', 2000, ['p1', 'p2', 'p3']); nest('napp.html', 20000, ['zz{k}', 'p2', 'p3'])
styleq('sq0.html', 0, True); styleq('sqp5000.html', 5000, True); styleq('sqa5000.html', 5000, False)
