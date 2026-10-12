"""Per-property cost by form (2000 props on one element): r_var1, r_const, r_constcalc, u_var1, u_const, r_var5,
  r_var1_long, r_chain, r_if. See docs/BENCHMARKS.md section 2."""
M=2000
def page(name, decl, reg=True, syntax='<number>'):
    regs=''.join(f"@property --b{i}{{syntax:'{syntax}';inherits:false;initial-value:0}}" for i in range(M)) if reg else ''
    body=';'.join(decl(i) for i in range(M))
    css=f'''{regs}@property --t{{syntax:'<number>';inherits:true;initial-value:0}}
@keyframes t{{from{{--t:0}}to{{--t:1000}}}}
#a{{animation:t 1000s linear infinite}}
#b{{{body}}}'''
    open(name,'w').write(f'<!doctype html><style>{css}</style><div id=a><div id=b></div></div>')
page('r_var1.html', lambda i: f'--b{i}:calc(var(--t) * {i})')
page('r_const.html', lambda i: f'--b{i}:{i}')
page('r_constcalc.html', lambda i: f'--b{i}:calc({i} * 2 + 1)')
page('u_var1.html', lambda i: f'--b{i}:calc(var(--t) * {i})', reg=False)
page('u_const.html', lambda i: f'--b{i}:{i}', reg=False)
page('r_var5.html', lambda i: f'--b{i}:calc(var(--t) * {i} + var(--t) * var(--t) - var(--t) / (1 + var(--t)))')
page('r_var1_long.html', lambda i: f'--b{i}:calc(var(--t) * {i} + 1 * 2 + 3 * 4 + 5 * 6 + 7 * 8 + 9 * 10)')
page('r_chain.html', lambda i: f'--b{i}:calc(var(--{"t" if i==0 else "b"+str(i-1)}) + 1)')
page('r_if.html', lambda i: f'--b{i}:if(style(--t: 5): 1; else: calc(var(--t) * {i}))')
