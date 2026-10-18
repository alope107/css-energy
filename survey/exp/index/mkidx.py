#!/usr/bin/env python3
"""mkidx.py MODE M P out.html — P read ports into M cells, the address of every port changing every frame.

MODE mux:  js-minus-js's port: cell k is an element with anchor-name --c<k> and width = value; a port is a fixed size
           container whose width is anchor-size() of a name chosen by a two-level if() (64-way high, 64-way low).
MODE grid: cell k is a grid item in row k + 1 with height = value; a port is a grid item in column 2 placed with
           grid-row: var(--a) + 1, stretched to its row, a size container: 100cqh is the value (grid tracks as RAM).
MODE none: the ports' addresses change but nothing reads (baseline for the clock and the address arithmetic).
Values are static (cell k holds (k * 37) mod 1000 + 1); --a_p = (frame clock * (p + 1) * 7 + p) mod M.
"""
import sys
MODE, M, P, OUT = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
val = lambda k: (k * 37) % 1000 + 1
css = ["@property --t { syntax: '<integer>'; inherits: true; initial-value: 0; }", '@keyframes clk { from { --t: 0; } to { --t: 60000; } }',
       '#root { animation: clk 1000s linear infinite; }', '.ram { height: 0; overflow: hidden; }']
css += [f"@property --a{p} {{ syntax: '<integer>'; inherits: true; initial-value: 0; }} @property --ah{p} {{ syntax: '<integer>'; inherits: true; initial-value: 0; }}"
        f" @property --al{p} {{ syntax: '<integer>'; inherits: true; initial-value: 0; }} @property --v{p} {{ syntax: '<integer>'; inherits: true; initial-value: 0; }}" for p in range(P)]
css.append('#root { ' + ' '.join(f'--a{p}: mod(var(--t) * {(p + 1) * 7} + {p}, {M}); --ah{p}: round(down, var(--a{p}) / 64); --al{p}: mod(var(--a{p}), 64);' for p in range(P)) + ' }')
html = []
if MODE == 'mux':
    css.append('.cell { height: 1px; }')
    html.append('<div class="ram">' + ''.join(f'<div class="cell" style="anchor-name: --c{k}; width: {val(k)}px"></div>' for k in range(M)) + '</div>')
    def mux(p):
        outer = []
        for h in range((M + 63) // 64):
            inner = ' '.join(f'style(--al{p}: {l}): --c{h * 64 + l};' for l in range(64) if h * 64 + l < M)
            outer.append(f'style(--ah{p}: {h}): if({inner} else: --c0);')
        return f"if({' '.join(outer)} else: --c0)"
    css.append('.port { position: fixed; left: 0; top: 0; height: 1px; container-type: inline-size; visibility: hidden; }')
    for p in range(P):
        css.append(f'.port{p} {{ width: anchor-size({mux(p)} width, 0px); }} .port{p} > i {{ --v{p}: round(100cqi / 1px); }}')
    html.append(''.join(f'<div class="port port{p}"><i></i></div>' for p in range(P)))
elif MODE == 'grid':
    css.append('.g { display: grid; grid-template-columns: 1px 1px; grid-auto-rows: auto; height: 0; overflow: hidden; align-items: start; }')
    css.append('.g > .cell { grid-column: 1; width: 1px; }')
    css.append('.g > .port { grid-column: 2; align-self: stretch; container-type: size; }')
    for p in range(P):
        css.append(f'.port{p} {{ grid-row: calc(var(--a{p}) + 1); }} .port{p} > i {{ --v{p}: round(100cqh / 1px); }}')
    html.append('<div class="g">' + ''.join(f'<div class="cell" style="grid-row: {k + 1}; height: {val(k)}px"></div>' for k in range(M))
                + ''.join(f'<div class="port port{p}"><i></i></div>' for p in range(P)) + '</div>')
open(OUT, 'w').write(f'<!doctype html><meta charset="utf-8"><style>{chr(10).join(css)}</style><div id="root">{"".join(html)}</div>')
print(OUT)
