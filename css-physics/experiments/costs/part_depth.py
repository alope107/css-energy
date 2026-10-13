"""absent/present-name rule cost vs ancestor depth D and names per ancestor M (24k rules on the deepest element).
dp{D}_{M}.html: D nested divs, each with M container names (n0..n{M-1}); 24000 rules @container zz{k} on #b.
dq{D}_{M}.html: same, rules name the LAST name of the list (present, far down the list) + false style().
dr{D}_{M}.html: same, rules name the FIRST name of the list + false style()."""
REG = ("@property --t{syntax:'<number>';inherits:true;initial-value:0}@property --o{syntax:'<number>';inherits:false;initial-value:0}"
       "@property --g0{syntax:'<integer>';inherits:true;initial-value:0}")
HEAD = "@keyframes t{from{--t:0}to{--t:1000}}#a{animation:t 1000s linear infinite}#b{--o:var(--t)}"
R = 24000
for D in (4, 32, 100):
    for M in (3, 32, 128):
        names = ' '.join(f'n{j}' for j in range(M))
        for kind in ('p', 'q', 'r'):
            if kind == 'p':
                rules = ''.join(f'@container zz{k}{{#b{{--o:calc(var(--t) * {k})}}}}' for k in range(R))
            else:
                nm = f'n{M - 1}' if kind == 'q' else 'n0'
                rules = ''.join(f'@container {nm} style(--g0: 7){{#b{{--o:calc(var(--t) * {k})}}}}' for k in range(R))
            css = f"{REG}{HEAD}.lv{{container-name:{names};--g0:calc(var(--t) * 0)}}{rules}"
            html = '<div id=a>' + ''.join('<div class=lv>' for _ in range(D)) + '<div id=b></div>' + '</div>' * D + '</div>'
            open(f'd{kind}{D}_{M}.html', 'w').write(f'<!doctype html><style>{css}</style>{html}')
