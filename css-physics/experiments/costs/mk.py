"""Inheritance-depth test: 2000 inherited registered props set near the top of a 50-deep chain.
  deep_inh.html / deep_noninh.html / root_inh.html -> all ~4.8 ms (no per-level copy cost)"""
import sys
M=2000; D=50
def page(name, deep_inh, big_at_root):
    regs=''.join(f"@property --b{i}{{syntax:'<number>';inherits:true;initial-value:0}}" for i in range(M))
    regs+=''.join(f"@property --d{k}{{syntax:'<number>';inherits:{'true' if deep_inh else 'false'};initial-value:0}}" for k in range(D))
    big=';'.join(f'--b{i}:calc(var(--t) * {i})' for i in range(M))
    nest=''
    for k in range(D): nest+=f'<div class=l{k}>'
    nest+='</div>'*D
    lv=''.join(f'.l{k}{{--d{k}:calc(var(--t) + {k})}}' for k in range(D))
    # consumer at the bottom reads a few big props
    css=f'''{regs}@property --t{{syntax:'<number>';inherits:true;initial-value:0}}
@keyframes t{{from{{--t:0}}to{{--t:1000}}}}
#a{{animation:t 1000s linear infinite}}
{'#a' if big_at_root else '.l0'}{{{big}}}
{lv}
.l{D-1}{{--z:calc(var(--b5) + var(--b1999))}}'''
    open(name,'w').write(f'<!doctype html><style>{css}</style><div id=a>{nest}</div>')
page('deep_inh.html',True,False)
page('deep_noninh.html',False,False)
page('root_inh.html',True,True)
