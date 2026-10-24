#!/usr/bin/env python3
"""mkchain.py MUX POS N K out.html — in-pass reads: K nested levels, each a size container whose width is the RAM cell at
the address the level above computed (anchor-size), read back by the next level as 100cqw. RAM is a linked list (cell k
holds the next address), so level K holds the cell K hops from --addr (set on #chain by chainread.js). One style and
layout update, no frames.
  MUX  ifmux (two-level if() on the cell's anchor name) | cq (a style query on the level above picks one of sqrt N
       size-query rules on the level above by the high digit, a sqrt N-entry if() in it on the low) | keyf (paused discrete animation, delay = -address) |
       ident (a registered <custom-ident> = ident("--c" n); needs --enable-blink-features=CSSIdentFunction)
  POS  abs (each level absolute in the one above) | fixed (each level position: fixed, its container the one above)"""
import sys
MUX, POS, N, K, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
nxt = lambda k: (k * 7919 + 13) % N          # the list: cell k points at nxt(k)
OFF = 1                                      # width = address + OFF px (0 px is the fallback)
css = ['@property --addr { syntax: "<integer>"; inherits: false; initial-value: 0; }',
       '@property --a { syntax: "<integer>"; inherits: false; initial-value: 0; }',
       '@property --nm { syntax: "<custom-ident>"; inherits: false; initial-value: --c0; }',
       'body { margin: 0; } #mem { width: 10px; height: 10px; overflow: hidden; }',
       '.w { display: block; height: 0; width: max-content; } .w > i { display: block; height: 0; }',
       f'.lv {{ position: {"absolute" if POS == "abs" else "fixed"}; left: 0; top: 30px; height: 1px; container-type: inline-size; }}',
       f'.lv {{ --a: calc(round(100cqw / 1px) - {OFF}); width: anchor-size(var(--nm) width, 0px); }}',
       f'#chain {{ position: absolute; left: 0; top: 20px; width: 1px; height: 1px; --a: var(--addr); }}']
cells = ''.join(f'<div class="w" style="anchor-name: --c{k}"><i style="width: {nxt(k) + OFF}px" id="v{k}"></i></div>' for k in range(N))
if MUX == 'ifmux':
    n1 = 1
    while n1 * n1 < N: n1 *= 2
    css.append('@property --h { syntax: "<integer>"; inherits: false; initial-value: 0; } @property --l { syntax: "<integer>"; inherits: false; initial-value: 0; }')
    outer = []
    for h in range((N + n1 - 1) // n1):
        inner = ' '.join(f'style(--l: {i}): --c{h * n1 + i};' for i in range(n1) if h * n1 + i < N)
        outer.append(f'style(--h: {h}): if({inner} else: --c0);')
    css.append(f'.lv {{ --h: round(down, var(--pa) / {n1}); --l: mod(var(--pa), {n1}); --nm: if({" ".join(outer)} else: --c0); }}')
elif MUX == 'cq':
    # the level above is a size container as wide as this level's address + OFF: one size-query rule per high digit
    # (only the matching rule's if() is evaluated), an if() on the low digit inside it
    n1 = 1
    while n1 * n1 < N: n1 *= 2
    css.append('@property --l { syntax: "<integer>"; inherits: false; initial-value: 0; }')
    css.append(f'#chain {{ container-type: inline-size; width: calc((var(--addr) + {OFF}) * 1px); }}')
    css.append(f'.lv {{ --l: mod(var(--a), {n1}); }}')
    for h in range((N + n1 - 1) // n1):
        inner = ' '.join(f'style(--l: {i}): --c{h * n1 + i};' for i in range(n1) if h * n1 + i < N)
        css.append(f'@container (width >= {h * n1 + OFF}px) and (width < {(h + 1) * n1 + OFF}px) {{ .lv {{ --nm: if({inner} else: --c0); }} }}')
elif MUX == 'keyf':
    css.append('@keyframes nm { ' + ' '.join(f'{100 * k / N:.6f}% {{ --nm: --c{k}; }}' for k in range(N)) + f' 100% {{ --nm: --c{N - 1}; }} }}')
    css.append(f'.lv {{ animation: nm {N}s linear paused both; animation-delay: calc(-1s * var(--pa) - 0.25s); }}')
elif MUX == 'ident':
    css.append('.lv { --nm: ident("--c" var(--pa)); }')
# --pa: the address this level reads = the level above's --a (an inherited copy)
css.append('@property --pa { syntax: "<integer>"; inherits: false; initial-value: 0; }')
css.append('@property --ia { syntax: "<integer>"; inherits: true; initial-value: 0; }')
css.append('#chain, .lv { --ia: var(--a); } .lv { --pa: var(--ia); }')
# (the .lv rule sets --ia from its own --a; a child's --pa reads the parent's --ia through inheritance... but the child's own
#  --ia rule shadows it: give the child's read its own name)
css[-1] = '#chain { --ia: var(--a); } .lv { --pa: var(--ia); --ib: var(--a); } .lv > .lv { --pa: var(--ib); }'
css.insert(-1, '@property --ib { syntax: "<integer>"; inherits: true; initial-value: 0; }')
levels = ''
for i in range(K): levels = f'<div class="lv p{(K - 1 - i) % 2}" id="l{K - 1 - i}">{levels}</div>'
html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"/><title>chain {MUX} {POS} {N} {K}</title><style>{chr(10).join(css)}</style></head>
<body><div id="mem">{cells}</div><div id="chain" style="--addr: 0">{levels}</div></body></html>'''
open(out, 'w').write(html)
