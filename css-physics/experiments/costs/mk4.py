"""Per-token costs (1000 props): k_base, k_lit20, k_var20, k_mul20, k_par20, k_fn10, k_unreg20."""
M=1000
def page(name, decl):
    regs=''.join(f"@property --b{i}{{syntax:'<number>';inherits:false;initial-value:0}}" for i in range(M))
    regs+="@property --u{syntax:'<number>';inherits:true;initial-value:0}"
    body=';'.join(decl(i) for i in range(M))
    css=f'''{regs}@property --t{{syntax:'<number>';inherits:true;initial-value:0}}
@keyframes t{{from{{--t:0}}to{{--t:1000}}}}
#a{{animation:t 1000s linear infinite;--u:calc(var(--t) * 2)}}
#b{{{body}}}'''
    open(name,'w').write(f'<!doctype html><style>{css}</style><div id=a><div id=b></div></div>')
page('k_base.html', lambda i: f'--b{i}:calc(var(--t) * {i})')
page('k_lit20.html', lambda i: f'--b{i}:calc(var(--t) * {i}'+''.join(f' + {j}.5' for j in range(20))+')')
page('k_var20.html', lambda i: f'--b{i}:calc(var(--t) * {i}'+''.join(f' + var(--u)' for j in range(20))+')')
page('k_mul20.html', lambda i: f'--b{i}:calc(var(--t) * {i}'+''.join(f' * 1.0001' for j in range(20))+')')
page('k_par20.html', lambda i: f'--b{i}:calc(var(--t) * {i} + '+'('*20+'1'+')'*20+')')
page('k_fn10.html', lambda i: f'--b{i}:calc(var(--t) * {i}'+''.join(f' + max(var(--u), 1)' for j in range(10))+')')
page('k_unreg20.html', lambda i: f'--c{i}:calc(var(--t) * {i}'+''.join(f' + var(--u)' for j in range(20))+')')
