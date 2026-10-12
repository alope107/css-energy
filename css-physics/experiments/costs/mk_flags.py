"""All-pairs broadphase cost: N=48 bodies, positions animated on #a, 1128 near flags on #b.
  fl0.html (no flags) vs fl1.html (flags) -> ~12.5 us per flag (13-16 ms vs ~1 ms)"""
N = 48
regs = ''.join(f"@property --p{i}{a}{{syntax:'<number>';inherits:true;initial-value:0}}" for i in range(N) for a in 'xyz')
regs += ''.join(f"@property --np{a}_{b}{{syntax:'<integer>';inherits:false;initial-value:0}}" for a in range(N) for b in range(a + 1, N))
pos = ';'.join(f'--p{i}{a}:calc(sin(var(--t) + {i * 3 + k}) * 200)' for i in range(N) for k, a in enumerate('xyz'))
fl = ';'.join(f'--np{a}_{b}:calc(sign(max(0, 89.6 - hypot(var(--p{a}x) - var(--p{b}x), var(--p{a}y) - var(--p{b}y), var(--p{a}z) - var(--p{b}z)))))'
              for a in range(N) for b in range(a + 1, N))
for name, body in (('fl0', ''), ('fl1', fl)):
    css = f"{regs}@property --t{{syntax:'<number>';inherits:true;initial-value:0}}@keyframes t{{from{{--t:0}}to{{--t:1000}}}}#a{{animation:t 1000s linear infinite;{pos}}}#b{{{body}}}"
    open(name + '.html', 'w').write(f'<!doctype html><style>{css}</style><div id=a><div id=b></div></div>')
