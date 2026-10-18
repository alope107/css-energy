"""What does a moving sphere cost to render? A clock (--t) moves N wrappers through inherited registered props.
  rn_{mode}.html  modes:
    full    the engine's render: .view (perspective, scale) > .cam (preserve-3d) > .bw > .sh + .sp, gradients, box-shadow
    flat    the same without perspective/preserve-3d (2D translates)
    plain   3D, but .sp/.sh are plain coloured boxes (no gradients, shadow, opacity)
    one     3D, wrapper only (no children)
    nocq    full, but .view without the cqw scale"""
import sys
N = 64
def page(mode):
    regs = "@property --t{syntax:'<number>';inherits:true;initial-value:0}"
    regs += ''.join(f"@property --{c}{k}{{syntax:'<number>';inherits:true;initial-value:0}}" for k in range(N) for c in 'xyz')
    decl = ''.join(f'--x{k}:calc(sin(var(--t) * {1 + k % 5}) * 200);--y{k}:calc(cos(var(--t) * {1 + k % 3}) * 100 - 100);--z{k}:calc(sin(var(--t) * {2 + k % 4}) * 150);' for k in range(N))
    p3 = mode != 'flat'
    view = ('position:absolute;left:0;top:0;width:900px;height:560px;' + ('perspective:1500px;' if p3 else '') +
            ('' if mode == 'nocq' else 'transform-origin:0 0;transform:scale(tan(atan2(100cqw, 900px)));'))
    cam = 'position:absolute;left:50%;top:50%;width:0;height:0;' + ('transform-style:preserve-3d;transform:translate3d(0,95px,260px) rotateX(-28deg) rotateY(0.25rad)' if p3 else '')
    kid = 'position:absolute;left:0;top:0;display:block;' + ('transform-style:preserve-3d;' if p3 else '')
    if mode == 'plain':
        sp = 'width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;background:#5a5'
        sh = 'width:44px;height:44px;margin:-22px 0 0 -22px;background:#000'
    else:
        sp = ('width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;--c:hsl(120 72% 56%);background:radial-gradient(circle at 36% 30%,rgb(255 255 255/.6),rgb(255 255 255/0) 30%),'
              'radial-gradient(circle at 42% 38%,color-mix(in oklab,var(--c) 100%,#fff 6%),color-mix(in oklab,var(--c) 55%,#07080a) 76%,color-mix(in oklab,var(--c) 28%,#07080a));box-shadow:0 0 0 0px orange')
        sh = 'width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;background:radial-gradient(closest-side,rgb(0 0 0/.7),rgb(0 0 0/0))'
    if p3:
        bw = lambda k: f'transform:translate3d(calc(var(--x{k}) * 1px),calc(var(--y{k}) * 1px),calc(var(--z{k}) * 1px))'
        spt = 'transform:rotateY(-0.25rad) rotateX(28deg)'
        sht = lambda k: f'transform:translateY(calc(var(--y{k}) * -1px)) rotateX(90deg);opacity:0.5'
    else:
        bw = lambda k: f'transform:translate(calc(var(--x{k}) * 1px),calc(var(--y{k}) * 1px))'
        spt = ''
        sht = lambda k: f'transform:translateY(calc(var(--y{k}) * -1px));opacity:0.5'
    css = (regs + '@keyframes t{from{--t:0}to{--t:100000}}#A{animation:t 100000s linear infinite}'
           f'#P{{{decl}}}.st{{container-type:inline-size;width:900px;height:560px;position:relative}}.view{{{view}}}.cam{{{cam}}}.cam>*,.bw>*{{{kid}}}.sp{{{sp};{spt}}}.sh{{{sh}}}'
           + ''.join(f'#w{k}{{{bw(k)}}}' + (f'#w{k} .sh{{{sht(k)}}}' if mode != 'one' else '') for k in range(N)))
    inner = '' if mode == 'one' else '<i class=sh></i><i class=sp></i>'
    body = f'<div id=A><div id=P><div class=st><div class=view><div class=cam>' + ''.join(f'<div class=bw id=w{k}>{inner}</div>' for k in range(N)) + '</div></div></div></div></div>'
    open(f'rn_{mode}.html', 'w').write(f'<!doctype html><style>{css}</style>{body}')
for m in ('full', 'flat', 'plain', 'one', 'nocq'):
    page(m)
