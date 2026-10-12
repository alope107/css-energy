import sys
NB=40; HEAVY=int(sys.argv[2]); TR=sys.argv[3]; name=sys.argv[1]
regs="@property --t{syntax:'<number>';inherits:true;initial-value:0}"
regs+=''.join(f"@property --h{i}{{syntax:'<number>';inherits:false;initial-value:0}}" for i in range(HEAVY))
heavy=';'.join(f'--h{i}:calc(sin(var(--t) * {i % 13 + 1}) * cos(var(--t) + {i}) + var(--t) * 0.001 * {i})' for i in range(HEAVY))
faces=''.join(f'<b class=f{k}></b>' for k in range(6))
bodies=''.join(f'<div class=bw style="--i:{i}"><div class=bd>{faces}</div></div>' for i in range(NB))
tr = {'tr':'transition:transform 300ms linear;will-change:transform;','trnw':'transition:transform 300ms linear;','wc':'will-change:transform;','no':''}[TR]
css=f'''{regs}
@keyframes t{{from{{--t:0}}to{{--t:1000}}}}
body{{margin:0;background:#111}}
#app{{animation:t 1000s linear infinite}}
.heavy{{position:absolute;width:0;height:0;overflow:hidden;{heavy}}}
.view{{position:absolute;inset:0;perspective:900px}}
.cam{{position:absolute;left:50%;top:50%;transform-style:preserve-3d;transform:rotateX(-25deg)}}
.bw{{position:absolute;transform-style:preserve-3d;{tr}
  transform:translate3d(calc((mod(var(--i), 8) * 70 - 250 + 40 * sin(var(--t) * 2 + var(--i))) * 1px), calc((round(down, var(--i) / 8) * 60 - 150) * 1px), 0) rotateY(calc(var(--t) * 2rad + var(--i) * 1rad))}}
.bd{{transform-style:preserve-3d}}
.bd b{{position:absolute;width:40px;height:40px;margin:-20px;background:hsl(calc(var(--i) * 37) 60% 50%);backface-visibility:hidden}}
.f0{{transform:translateZ(20px)}}.f1{{transform:rotateY(180deg) translateZ(20px)}}.f2{{transform:rotateY(90deg) translateZ(20px)}}
.f3{{transform:rotateY(-90deg) translateZ(20px)}}.f4{{transform:rotateX(90deg) translateZ(20px)}}.f5{{transform:rotateX(-90deg) translateZ(20px)}}
'''
open(name,'w').write(f'<!doctype html><style>{css}</style><div id=app><div class=heavy></div><div class=view><div class=cam>{bodies}</div></div></div>')
