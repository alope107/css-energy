"""Gating primitives at scale, for the spatial-partitioning design. #a animates --t; #c1 is the named
container (pres, o0); #b gets the rules. Writes into the current directory:
  base0.html              no gated rules
  abs{R}.html             R absent-name rules (R = 24k, 100k, 300k): the marginal cost of a rule nobody matches
  prs{R}.html             R present-name rules with a false style()
  nest{K}.html            8128 "pairs" x K rules: outer names o0..o{K-1} (only o0 present), inner absent + style()
  nestin1.html            8128 nests whose inner name is present and style() false
  flat3.html              8128 x 3 present+false rules (today's per-pair rule cost)
  eqvar.html, range*.html feature tests: --o on #b becomes 777 if the query form is supported and true
  eqvarcost/rangecost/or9 5000 rules of each query form
  ifid{K}.html            2000 unregistered props producing an ident with a K-branch if()
Measure: node tools/stylebench.js base0.html,abs24000.html,... 500 1500   (PROBE for the feature tests)"""
REG = ("@property --t{syntax:'<number>';inherits:true;initial-value:0}@property --o{syntax:'<number>';inherits:false;initial-value:0}"
       "@property --x{syntax:'<number>';inherits:true;initial-value:3}@property --y{syntax:'<number>';inherits:true;initial-value:3}"
       "@property --g0{syntax:'<integer>';inherits:true;initial-value:0}")
HEAD = "@keyframes t{from{--t:0}to{--t:1000}}#a{animation:t 1000s linear infinite}#b{--o:var(--t)}"


def emit(name, rules, cont='pres o0'):
    css = f"{REG}{HEAD}#c1{{container-name:{cont};--g0:calc(var(--t) * 0);--x:calc(var(--t) * 0 + 3);--y:calc(var(--t) * 0 + 3)}}{rules}"
    open(name, 'w').write(f'<!doctype html><style>{css}</style><div id=a><div id=c1><div id=b></div></div></div>')


body = lambda k: f'#b{{--o:calc(var(--t) * {k})}}'
emit('base0.html', '')
for R in (24000, 100000, 300000):
    emit(f'abs{R}.html', ''.join(f'@container zz{k}{{{body(k)}}}' for k in range(R)))
for R in (5000, 24000):
    emit(f'prs{R}.html', ''.join(f'@container pres style(--g0: 7){{{body(k)}}}' for k in range(R)))
P = 8128
for K in (1, 4, 6, 9):
    emit(f'nest{K}.html', ''.join(f'@container o{k % K}{{@container zz{p}_{k} style(--g0: 7){{{body(p)}}}}}' for p in range(P) for k in range(K)))
emit('nestin1.html', ''.join(f'@container o0{{@container pres style(--g0: 7){{{body(p)}}}}}' for p in range(P)))
emit('flat3.html', ''.join(f'@container pres style(--g0: 7){{{body(p)}}}' * 3 for p in range(P)))
emit('eqvar.html', '@container pres style(--x: var(--y)){#b{--o:777}}')
emit('eqvarcost.html', ''.join(f'@container pres style(--x: var(--y)){{{body(k)}}}' for k in range(5000)))
emit('range.html', '@container pres style(--x > 2){#b{--o:777}}')
emit('range2.html', '@container pres style(2 < --x < 4){#b{--o:777}}')
emit('rangecost.html', ''.join(f'@container pres style(--x > 5){{{body(k)}}}' for k in range(5000)))
emit('or9.html', ''.join('@container pres ' + ' or '.join(f'style(--g0: {7 + j})' for j in range(9)) + f'{{{body(k)}}}' for k in range(5000)))
for K in (4, 12):
    emit(f'ifid{K}.html', '#b{' + ''.join(f'--A{n}:if(' + ' '.join(f'style(--g0: {j}): n{n}_{j};' for j in range(K)) + ' else: );' for n in range(2000)) + '}')
emit('ifid0.html', '#b{' + ''.join(f'--A{n}:calc(var(--t) * {n});' for n in range(2000)) + '}')
