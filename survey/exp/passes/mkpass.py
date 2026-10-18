#!/usr/bin/env python3
"""mkpass.py MODE out.html — how many useful style+layout passes does Chrome run per frame?

A view-timeline register (css-physics/js-minus-js style) holds a counter n: a subject at offset n in a tall scroller
drives @keyframes into --n, and the subject's position is n + 1. Every pass that sees a fresh timeline value advances
it, so increments per frame = useful passes per frame (the repo sees 2).

MODE base:  just the register.
MODE cis:   plus an element with contain-intrinsic-size: auto whose size follows n (content-visibility: auto, so its
            remembered size is recorded by Blink's internal ResizeObserver every time it changes).
MODE cvh:   the same with content-visibility: hidden after a visible pass (a js-minus-js RAM leaf written every pass).
MODE ro:    an anchor-positioned element with position-try fallbacks whose chosen fallback flips with n's parity
            (anchor positioning's "last successful position" runs in the ResizeObserver step).
"""
import sys
MODE, OUT = sys.argv[1], sys.argv[2]
H = 100000
css = [f"@property --n {{ syntax: '<integer>'; inherits: true; initial-value: 0; }}",
       f'@keyframes kn {{ from {{ --n: {H}; }} to {{ --n: -1; }} }}',
       '#top { timeline-scope: --tn; animation: kn auto linear both; animation-timeline: --tn; }',
       f'.sc {{ position: absolute; left: 0; top: 0; width: 1px; height: {H}px; overflow: hidden; visibility: hidden; }}',
       '.sub { position: absolute; left: 0; width: 1px; height: 1px; view-timeline: --tn block; top: calc((mod(var(--n) + 1, 50000)) * 1px); }',
       '.out { counter-reset: n var(--n); font: 20px monospace; } .out::before { content: counter(n); }']
extra = ''
if MODE == 'cis':
    css.append('.cis { content-visibility: auto; contain-intrinsic-size: auto 10px; width: calc(10px + mod(var(--n), 100) * 1px); height: 10px; }')
    extra = '<div class="cis"><b>x</b></div>'
elif MODE.startswith('nest'):   # nestD: D remembered-size elements, each nested inside the previous (deeper every time)
    D = int(MODE[4:])
    css.append('.cis { content-visibility: auto; contain-intrinsic-size: auto 10px; width: calc(10px + mod(var(--n) + var(--k), 100) * 1px); min-height: 10px; }')
    extra = ''.join(f'<div class="cis" style="--k: {d}">' for d in range(D)) + '<b>x</b>' + '</div>' * D
elif MODE.startswith('sib'):    # sibD: D remembered-size siblings at the same depth
    D = int(MODE[3:])
    css.append('.cis { content-visibility: auto; contain-intrinsic-size: auto 10px; width: calc(10px + mod(var(--n) + var(--k), 100) * 1px); height: 10px; }')
    extra = ''.join(f'<div class="cis" style="--k: {d}"><b>x</b></div>' for d in range(D))
elif MODE == 'cvh':
    css.append('.cvh { content-visibility: if(style(--n: 0): visible; else: hidden); contain-intrinsic-size: auto 10px; width: fit-content; height: 1px; }'
               '.cvh > b { display: block; width: calc(10px + mod(var(--n), 100) * 1px); height: 1px; }'
               '.cvh2 { content-visibility: visible; contain-intrinsic-size: auto 10px; width: calc(10px + mod(var(--n), 100) * 1px); height: 1px; }')
    extra = '<div class="cvh2"><b></b></div>'
elif MODE == 'ro':
    css.append('.anc { anchor-name: --a; position: absolute; left: 300px; top: 300px; width: 10px; height: 10px; }'
               '.pos { position: absolute; position-anchor: --a; width: calc(50px + mod(var(--n), 2) * 400px); height: 10px;'
               ' left: anchor(right); top: anchor(top); position-try-fallbacks: flip-inline; }')
    extra = '<div class="anc"></div><div class="pos"></div>'
html = f'<div id="top"><div class="sc"><div class="sub"></div></div><div class="out"></div>{extra}</div>'
open(OUT, 'w').write(f'<!doctype html><meta charset="utf-8"><style>{chr(10).join(css)}</style>{html}')
print(OUT)
