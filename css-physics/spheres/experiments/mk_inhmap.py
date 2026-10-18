"""Does an element's restyle cost grow with the number of inherited registered custom properties it receives?
#P declares P inherited registered numbers from an animated clock (all change every frame); M children each set one
transform from one of them.  mode: inh (registered, inherits:true) | non (registered, inherits:false; children read a
constant instead) | unreg (unregistered custom properties) | few (only the M read props change; the other P-M constant)
  im_P{P}_M{M}_{mode}.html"""
import sys
def page(P, M, mode):
    regs = "@property --t{syntax:'<number>';inherits:true;initial-value:0}"
    if mode != 'unreg':
        inh = 'false' if mode == 'non' else 'true'
        regs += ''.join(f"@property --p{k}{{syntax:'<number>';inherits:{inh};initial-value:0}}" for k in range(P))
    decl = ''.join(f'--p{k}:calc(var(--t) * {k % 7 + 1});' if (mode != 'few' or k < M) else f'--p{k}:{k};' for k in range(P))
    css = (regs + '@keyframes t{from{--t:0}to{--t:100000}}#A{animation:t 100000s linear infinite}'
           f'#P{{{decl}}}.c{{position:absolute;width:4px;height:4px;background:red}}')
    kids = ''.join(f'<i class=c style="transform:translate(calc(var(--{"t" if mode == "non" else "p" + str(k % P)}) * 0.001px), {k}px)"></i>' for k in range(M))
    open(f'im_P{P}_M{M}_{mode}.html', 'w').write(f'<!doctype html><style>{css}</style><div id=A><div id=P>{kids}</div></div>')
for P in (100, 1000, 3000):
    for mode in ('inh', 'non', 'unreg', 'few'):
        page(P, 200, mode)
