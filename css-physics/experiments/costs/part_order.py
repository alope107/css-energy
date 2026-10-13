"""nested @container evaluation order and name-only costs (24k rules on #b, parent #c1 named pres with --g0:0, --h:7).
 oF_iT: outer style false, inner style true   oT_iF: outer true, inner false
 nameonly: @container pres{} (present, no style())    absent1: @container zz{k}{} with ONE named ancestor of 3 names
 unnamed: @container style(--g0: 7) (no name, false)"""
REG = ("@property --t{syntax:'<number>';inherits:true;initial-value:0}@property --o{syntax:'<number>';inherits:false;initial-value:0}"
       "@property --g0{syntax:'<integer>';inherits:true;initial-value:0}@property --h{syntax:'<integer>';inherits:true;initial-value:7}")
HEAD = "@keyframes t{from{--t:0}to{--t:1000}}#a{animation:t 1000s linear infinite}#b{--o:var(--t)}"
R = 24000
def emit(name, rule):
    rules = ''.join(rule.format(k=k) for k in range(R))
    css = f"{REG}{HEAD}#c1{{container-name:pres q1 q2;--g0:calc(var(--t) * 0);--h:calc(var(--t) * 0 + 7)}}{rules}"
    open(name, 'w').write(f'<!doctype html><style>{css}</style><div id=a><div id=c1><div id=b></div></div></div>')
emit('oF_iT.html', '@container pres style(--g0: 7){{@container pres style(--h: 7){{#b{{--o:calc(var(--t) * {k})}}}}}}')
emit('oT_iF.html', '@container pres style(--h: 7){{@container pres style(--g0: 7){{#b{{--o:calc(var(--t) * {k})}}}}}}')
emit('oF_iF.html', '@container pres style(--g0: 7){{@container pres style(--g0: 8){{#b{{--o:calc(var(--t) * {k})}}}}}}')
emit('nameonly.html', '@container pres{{#b{{--o:calc(var(--t) * {k})}}}}')
emit('absent1.html', '@container zz{k}{{#b{{--o:calc(var(--t) * {k})}}}}')
emit('unnamed.html', '@container style(--g0: 7){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('unnamedT.html', '@container style(--h: 7){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('flatF.html', '@container pres style(--g0: 7){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('and2F.html', '@container pres style(--h: 7) and style(--g0: 7){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('and2F2.html', '@container pres style(--g0: 7) and style(--h: 7){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('rangeT.html', '@container pres style(--h > 5){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('rangeF.html', '@container pres style(--h > 9){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('range2F.html', '@container pres style(8 < --h < 9){{#b{{--o:calc(var(--t) * {k})}}}}')
emit('rangevarF.html', '@container pres style(--h > calc(var(--g0) + 9)){{#b{{--o:calc(var(--t) * {k})}}}}')
