M = 2000
def page(name, decl, syntax='<number>', reg=True):
    regs = ''.join(f"@property --b{i}{{syntax:'{syntax}';inherits:false{';initial-value:0' if syntax != '*' else ''}}}" for i in range(M)) if reg else ''
    body = ';'.join(decl(i) for i in range(M))
    css = f'''{regs}@property --t{{syntax:'<number>';inherits:true;initial-value:0}}
@keyframes t{{from{{--t:0}}to{{--t:1000}}}}
#a{{animation:t 1000s linear infinite}}
#b{{{body}}}'''
    open(name, 'w').write(f'<!doctype html><style>{css}</style><div id=a><div id=b></div></div>')
page('empty.html', lambda i: '--zz:1', reg=False)
page('n_const.html', lambda i: f'--b{i}:{i}')
page('i_const.html', lambda i: f'--b{i}:{i}', '<integer>')
page('s_const.html', lambda i: f'--b{i}:{i}', '*')
page('u_const.html', lambda i: f'--b{i}:{i}', reg=False)
page('n_var.html', lambda i: f'--b{i}:calc(var(--t) * {i})')
page('i_var.html', lambda i: f'--b{i}:calc(var(--t) * {i})', '<integer>')
page('s_var.html', lambda i: f'--b{i}:calc(var(--t) * {i})', '*')
page('u_var.html', lambda i: f'--b{i}:calc(var(--t) * {i})', reg=False)
page('n_digit.html', lambda i: f'--b{i}:sign(mod(round(down, var(--t) * {i} / 1000), 10))')
page('n_digit2.html', lambda i: f'--b{i}:calc(round(down, var(--t) * {i} / 1000) - 10 * round(down, var(--t) * {i} / 10000))')
page('n_clamp.html', lambda i: f'--b{i}:clamp(0, (var(--t) - {i}) / 500, 1)')
page('n_prog.html', lambda i: f'--b{i}:progress(var(--t), {i}, {i + 500})')
page('n_sign.html', lambda i: f'--b{i}:sign(max(0, {i} - var(--t)))')
