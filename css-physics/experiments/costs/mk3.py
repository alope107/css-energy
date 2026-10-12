"""Paused-animation evaluator (animation-delay: calc(var(--x) * -1s)) vs calc: an1, an2add, calc20, calc20b, none.
  Result: ~400 us per element for the animation path (dead end)."""
import random
E_N=200; K=20
rng=random.Random(1)
regs=''.join(f"@property --o{k}{{syntax:'<number>';inherits:false;initial-value:0}}" for k in range(K))
base=f'''{regs}@property --t{{syntax:'<number>';inherits:true;initial-value:0}}
@property --x{{syntax:'<number>';inherits:false;initial-value:0}}
@property --y{{syntax:'<number>';inherits:false;initial-value:0}}
@keyframes t{{from{{--t:0}}to{{--t:1000}}}}
#a{{animation:t 1000s linear infinite}}
#a i{{display:block;--x:calc(0.5 + 0.5 * sin(var(--t) + sibling-index()));--y:calc(0.5 + 0.5 * cos(var(--t) * 1.7 + sibling-index()))}}
'''
kf1='@keyframes f1{'+''.join(f'{p}%{{'+';'.join(f'--o{k}:{rng.uniform(-9,9):.4f}' for k in range(K))+'}' for p in (0,25,50,75,100))+'}'
kf2='@keyframes f2{'+''.join(f'{p}%{{'+';'.join(f'--o{k}:{rng.uniform(-9,9):.4f}' for k in range(K))+'}' for p in (0,25,50,75,100))+'}'
kids='<i></i>'*E_N
def w(n,css): open(n,'w').write(f'<!doctype html><style>{base}{css}</style><div id=a>{kids}</div>')
w('an1.html', kf1+'#a i{animation:f1 1s linear paused both;animation-delay:calc(var(--x) * -1s)}')
w('an2add.html', kf1+kf2+'#a i{animation:f1 1s linear paused both,f2 1s linear paused both;animation-composition:replace,add;animation-delay:calc(var(--x) * -1s),calc(var(--y) * -1s)}')
w('calc20.html', '#a i{'+';'.join(f'--o{k}:calc(var(--x) * {rng.uniform(-9,9):.4f} + {rng.uniform(-9,9):.4f})' for k in range(K))+'}')
w('calc20b.html', '#a i{'+';'.join(f'--o{k}:calc(var(--x) * {rng.uniform(-9,9):.4f} + var(--y) * {rng.uniform(-9,9):.4f})' for k in range(K))+'}')
w('none.html', '')
