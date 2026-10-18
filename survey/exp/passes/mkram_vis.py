#!/usr/bin/env python3
"""mkram.py D out.html — are remembered sizes (js-minus-js RAM leaves) updated between passes of one frame?

Counter register n advances every pass (view timeline); D nested remembered-size elements re-arm extra passes. A leaf is
visible with width n + 1 on even n and content-visibility: hidden on odd n, so on odd passes its width is the
remembered size. A reader (anchor-size) gives w; lag = n - w (1 when the remembered size is from the previous pass).
A second register keeps the largest lag seen (m = max(m, lag) on odd passes), a third the smallest."""
import sys
D, OUT = int(sys.argv[1]), sys.argv[2]
H = 100000
reg = lambda n: f"@property --{n} {{ syntax: '<integer>'; inherits: true; initial-value: 0; }}"
css = [reg('n'), reg('m'), reg('lo'), reg('w'), reg('lag'), reg('odd'),
       *[f'@keyframes k{r} {{ from {{ --{r}: {H}; }} to {{ --{r}: -1; }} }}' for r in ('n', 'm', 'lo')],
       '#top { timeline-scope: --tn, --tm, --tlo; animation: kn auto linear both, km auto linear both, klo auto linear both; animation-timeline: --tn, --tm, --tlo; }',
       f'.sc {{ position: absolute; left: 0; top: 0; width: 1px; height: {H}px; overflow: hidden; visibility: hidden; }}',
       '.sub { position: absolute; left: 0; width: 1px; height: 1px; }',
       '.leaf { content-visibility: if(style(--odd: 1): hidden; else: visible); contain-intrinsic-size: auto 5px; width: fit-content; height: 1px; }', '.lw { width: fit-content; anchor-name: --leaf; }',
       '.leaf > b { display: block; height: 1px; width: calc((var(--n) + 1) * 1px); }',
       '.rd { position: fixed; left: 0; top: 0; height: 1px; width: anchor-size(--leaf width, 0px); container-type: inline-size; visibility: hidden; }',
       '.rd > i { display: block; --w: round(100cqi / 1px); --lag: calc(var(--n) - var(--w)); }',
       '#top { --odd: mod(var(--n), 2); }',
       '.rd .s1 { view-timeline: --tn block; top: calc(mod(var(--n) + 1, 50000) * 1px); }',
       '.rd .s2 { view-timeline: --tm block; top: calc((var(--m) + var(--odd) * max(0, var(--lag) - var(--m))) * 1px); }',
       '.rd .s3 { view-timeline: --tlo block; top: calc(if(style(--n: 0): 9999; else: calc(var(--lo) - var(--odd) * max(0, var(--lo) - var(--lag)))) * 1px); }',
       '.cis { content-visibility: visible; contain-intrinsic-size: auto 10px; width: calc(10px + mod(var(--n) + var(--k), 100) * 1px); min-height: 10px; }']
DEEP = len(sys.argv) > 3 and sys.argv[3] == 'deep'   # the leaf inside the innermost nest element (eligible in every RO round)
leaf = '<div class="lw"><div class="leaf"><b></b></div></div>'
rd = '<div class="rd"><i>' + ''.join(f'<div class="sc"><div class="sub s{k}"></div></div>' for k in (1, 2, 3)) + '</i></div>'
nest = ''.join(f'<div class="cis" style="--k: {d}">' for d in range(D)) + ('<b>x</b>' + leaf + rd if DEEP else '<b>x</b>') + '</div>' * D
html = f'<div id="top">{"" if DEEP else leaf}{nest}{"" if DEEP else rd}</div>'
open(OUT, 'w').write(f'<!doctype html><meta charset="utf-8"><style>{chr(10).join(css)}</style>{html}')
