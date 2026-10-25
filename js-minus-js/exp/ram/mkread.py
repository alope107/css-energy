#!/usr/bin/env python3
"""mkread.py VARIANT N out.html — a probe page: N RAM cells (width = the value) and one read port at an address
--addr, a non-inherited integer the harness (readaddr.js) sets on #mem and on the ports. How the port finds its cell:
  ifmux    the page's way: a two-level if() picks the cell's anchor name (sqrt N x sqrt N), anchor-size() reads it
  keyf     a paused discrete animation of a <custom-ident> whose keyframes are the names; animation-delay = -address
  ident    anchor-size(ident("--c" var(--addr))) (needs --enable-blink-features=CSSIdentFunction)
  dec      no names on the cells: a radix-16 decode tree (memtree.py's: enable and address masked level by level, two
           parities, inherited) names the one cell at the address --rd
  decni    the same tree with non-inherited properties, passed down by explicit inherit
  scope    two levels: a port inside each group of 256 (anchor-scope on the group's names) reads its group's cell, a
           top port reads that group's port (the harness sets --addr on every group port: a broadcast for free)
  grid     no names: cells are grid rows (height = value < 1000), a probe item in row --addr stretches to it
  none     the port reads a fixed name (what the rest costs)
  same     decni with the address arriving through layout in the same update: a box --addr + 1 px wide, a fixed size
           container sized by anchor-size() of it around the tree, which reads 100cqw
The DOM is the same radix-16 tree in every variant (display: contents nodes, the level of 256 cells a block)."""
import sys
V, N, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
val = lambda k: (k * 7919) % 99991 + 1
G = 256
D = 1
while 16 ** D < N: D += 1                     # leaf level D: cells; levels 0 … D-1 nodes; span of a level-d node 16^(D-d)
SAME = V == 'same'
if SAME: V = 'decni'
named = V in ('ifmux', 'keyf', 'ident', 'scope', 'none')
css = ['@property --addr { syntax: "<integer>"; inherits: false; initial-value: 0; }',
       'body { margin: 0; } #mem { width: 10px; height: 10px; overflow: hidden; }',
       '.tn { display: contents; } .g { display: block; height: 0; } .w { display: block; height: 0; width: max-content; } .w > i { display: block; height: 0; }',
       '.rp { position: absolute; left: 0; top: 20px; height: 1px; }']
def leaf(k, x):
    if V == 'grid': return f'<div class="w"><i style="--hv: {val(k) % 997 + 1}px; grid-row: {k + 1}" id="v{k}"></i></div>'
    return f'<div class="w x{x}"' + (f' style="anchor-name: --c{k}"' if named else '') + f'><i style="width: {val(k)}px" id="v{k}"></i></div>'
def tree(lo, d):
    span = 16 ** (D - d)
    if d == D: return leaf(lo, lo % 16)
    kids = ''.join(tree(lo + i * span // 16, d + 1) for i in range(16) if lo + i * span // 16 < N)
    if span == G or (d == 0 and span < G):
        gp = f'<div class="gp gp{lo // G}" style="--addr: 0"></div>' if V == 'scope' else ''
        sc = (' style="anchor-scope: ' + ', '.join(f'--c{k}' for k in range(lo, min(N, lo + G))) + '"') if V == 'scope' else ''
        kids = f'<div class="g"{sc}>{kids}{gp}</div>'
    return kids if d == 0 else f'<div class="tn d{d} x{(lo // span) % 16}">{kids}</div>'
body = tree(0, 0)
ne = lambda a, b: f"min(1, max(({a}) - ({b}), ({b}) - ({a})))"
if V == 'ifmux':
    n1 = 1
    while n1 * n1 < N: n1 *= 2
    css.append('@property --nm { syntax: "<custom-ident>"; inherits: false; initial-value: --c0; }')
    css.append('@property --h { syntax: "<integer>"; inherits: false; initial-value: 0; } @property --l { syntax: "<integer>"; inherits: false; initial-value: 0; }')
    outer = []
    for h in range((N + n1 - 1) // n1):
        inner = ' '.join(f'style(--l: {i}): --c{h * n1 + i};' for i in range(n1) if h * n1 + i < N)
        outer.append(f'style(--h: {h}): if({inner} else: --c0);')
    css.append(f'.rp {{ --h: round(down, var(--addr) / {n1}); --l: mod(var(--addr), {n1}); --nm: if({" ".join(outer)} else: --c0); width: anchor-size(var(--nm) width, 0px); }}')
elif V == 'keyf':
    css.append('@property --nm { syntax: "<custom-ident>"; inherits: false; initial-value: --c0; }')
    css.append('@keyframes nm { ' + ' '.join(f'{100 * k / N:.6f}% {{ --nm: --c{k}; }}' for k in range(N)) + f' 100% {{ --nm: --c{N - 1}; }} }}')
    css.append(f'.rp {{ animation: nm {N}s linear paused both; animation-delay: calc(-1s * var(--addr) - 0.25s); width: anchor-size(var(--nm) width, 0px); }}')
elif V == 'ident':
    css.append('.rp { width: anchor-size(ident("--c" var(--addr)) width, 0px); }')
elif V in ('dec', 'decni', 'same'):
    inh = 'true' if V == 'dec' else 'false'
    css += [f'@property --{x}{p} {{ syntax: "<integer>"; inherits: {inh}; initial-value: 0; }}' for x in 'ea' for p in 'AB']
    css.append('@property --hit { syntax: "<integer>"; inherits: false; initial-value: 0; }')
    css.append('#mem { --eA: 1; --aA: var(--addr); }' if not SAME else
               '#adr { position: absolute; left: 0; top: 40px; height: 1px; anchor-name: --ad; }'
               ' #wrap { position: fixed; left: 0; top: 0; height: 10px; width: anchor-size(--ad width, 0px); container-type: inline-size; }'
               ' #mem { --addr: calc(round(100cqw / 1px) - 1); --eA: 1; --aA: var(--addr); }'
               ' .rp { position: fixed; }')
    for d in range(1, D + 1):             # level d's node: its digit of the address, from parity X to Y
        X, Y = ('A', 'B') if d % 2 == 1 else ('B', 'A')
        sub = 16 ** (D - d)
        take = f'--e{X}: inherit; --a{X}: inherit; ' if V == 'decni' else ''
        for x in range(16):
            sel = f'.tn.d{d}.x{x}' if d < D else f'.w.x{x}'
            hit = f'calc(var(--e{X}) * (1 - {ne(f"mod(round(down, var(--a{X}) / {sub}), 16)", x)}))'
            if d < D: css.append(f'{sel} {{ {take}--e{Y}: {hit}; --a{Y}: calc(var(--e{Y}) * var(--a{X})); }}')
            else: css.append(f'{sel} {{ {take}--hit: {hit}; anchor-name: if(style(--hit: 1): --rd; else: none); }}')
    if V == 'decni':     # the group block sits between levels: it passes its parity on
        Xg = None
        for d in range(1, D + 1):
            if 16 ** (D - d + 1) == G or (d == 1 and 16 ** D < G): Xg = ('A', 'B')[(d - 1) % 2] if d > 1 else 'A'
        css.append(f'.g {{ --e{Xg}: inherit; --a{Xg}: inherit; }}')
    css.append('.rp { width: anchor-size(--rd width, 0px); }')
elif V == 'scope':
    css.append('.g { position: relative; } .gp { position: absolute; left: 0; top: 0; height: 1px; }')
    css.append('@property --nm { syntax: "<custom-ident>"; inherits: false; initial-value: --c0; }')
    css.append('@property --gn { syntax: "<custom-ident>"; inherits: false; initial-value: --g0; }')
    css.append('@property --l { syntax: "<integer>"; inherits: false; initial-value: 0; } @property --hh { syntax: "<integer>"; inherits: false; initial-value: 0; }')
    nG = (N + G - 1) // G
    for j in range(nG):
        inner = ' '.join(f'style(--l: {i}): --c{j * G + i};' for i in range(G) if j * G + i < N)
        css.append(f'.gp{j} {{ --l: mod(var(--addr), {G}); --nm: if({inner} else: --c0); width: anchor-size(var(--nm) width, 0px); anchor-name: --g{j}; }}')
    css.append('.rp { --hh: round(down, var(--addr) / %d); --gn: if(%s else: --g0); width: anchor-size(var(--gn) width, 0px); }' % (G, ' '.join(f'style(--hh: {j}): --g{j};' for j in range(nG))))
elif V == 'grid':
    css.append('#mem { display: grid; grid-template-columns: 10px; grid-auto-rows: auto; height: auto; overflow: visible; }')
    css.append('#mem .tn, #mem .g, #mem .w { display: contents; } #mem .w > i { height: var(--hv); width: 1px; grid-column: 1; }')
    css.append('#probe { grid-column: 1; grid-row: calc(var(--addr) + 1); align-self: stretch; width: 2px; anchor-name: --probe; }')
    css.append('.rp { width: anchor-size(--probe height, 0px); }')
    body = body.replace('<div class="g">', '<div class="g">', 1) + '<div id="probe" style="--addr: 0"></div>'
elif V == 'none':
    css.append('.rp { width: anchor-size(--c5 width, 0px); }')
body_html = (f'<div id="adr" style="width: 1px"></div><div id="wrap"><div id="mem">{body}</div></div><div class="rp" id="rp"></div>' if SAME else
             f'<div id="mem" style="--addr: 0">{body}</div><div class="rp" id="rp" style="--addr: 0"></div>')
html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"/><title>{V} {N}</title><style>{chr(10).join(css)}</style></head>
<body>{body_html}</body></html>'''
open(out, 'w').write(html)
