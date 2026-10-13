"""style() query forms, 24k rules on #b, parent #c1 (pres): registered integer equality (false / true),
boolean form style(--g0) (declared non-initial?), unregistered flag equality, and the same under a name that is
absent with 1 named ancestor."""
REG = ("@property --t{syntax:'<number>';inherits:true;initial-value:0}@property --o{syntax:'<number>';inherits:false;initial-value:0}"
       "@property --g0{syntax:'<integer>';inherits:true;initial-value:0}@property --h{syntax:'<integer>';inherits:true;initial-value:7}")
HEAD = "@keyframes t{from{--t:0}to{--t:1000}}#a{animation:t 1000s linear infinite}#b{--o:var(--t)}"
R = 24000
def emit(name, rule, c1='--g0:calc(var(--t) * 0);--h:calc(var(--t) * 0 + 7);--u:0;--v:1'):
    rules = ''.join(rule.format(k=k) for k in range(R))
    css = f"{REG}{HEAD}#c1{{container-name:pres q1 q2;{c1}}}{rules}"
    open(name, 'w').write(f'<!doctype html><style>{css}</style><div id=a><div id=c1><div id=b></div></div></div>')
emit('sf_eqF.html', '@container pres style(--g0: 1){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('sf_eqT.html', '@container pres style(--h: 7){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('sf_boolF.html', '@container pres style(--g0){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('sf_boolT.html', '@container pres style(--h){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('sf_unregF.html', '@container pres style(--u: 1){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('sf_unregT.html', '@container pres style(--v: 1){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('sf_unregboolF.html', '@container pres style(--w){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('sf_unnamedF.html', '@container style(--g0: 1){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('sf_nameF.html', '@container pres{{#b{{--o:calc(var(--t) * {k})}}}}')
