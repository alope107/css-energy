#!/usr/bin/env python3
"""mkfn.py outdir — 2,000 registered <number> props on one element under an animated parent (css-physics mk2.py's shape)."""
import sys, os
D = sys.argv[1]; os.makedirs(D, exist_ok=True); M = 2000
HEAD = ("@property --t{syntax:'<number>';inherits:true;initial-value:0}@keyframes t{from{--t:0}to{--t:1000}}"
        "#a{animation:t 1000s linear infinite}")
def reg(n, inh='false'): return f"@property --{n}{{syntax:'<number>';inherits:{inh};initial-value:0}}"
def page(name, decls, extra='', regs=None):
    regs = regs if regs is not None else [f'b{i}' for i in range(M)]
    css = HEAD + ''.join(reg(r) for r in regs) + extra + '#b{' + ';'.join(decls) + '}'
    open(os.path.join(D, name + '.html'), 'w').write(f'<!doctype html><style>{css}</style><div id=a><div id=b></div></div>')
page('base', [], regs=[])
page('inline1', [f'--b{i}:calc(var(--t) * {i + 1})' for i in range(M)])
F1 = '@function --f1(--x <number>, --k <number>) returns <number> { result: calc(var(--x) * var(--k)); }'
page('fn1', [f'--b{i}:--f1(var(--t), {i + 1})' for i in range(M)], F1)
# ~10 ops: a quadratic and clamp
E10 = lambda x, k: f'clamp(-1, ({x} * 0.3 + {k}) * ({x} * 0.7 - 2) / ({x} + 5) + {x} * {x} * 0.001, 1000)'
page('inline10', [f'--b{i}:calc({E10("var(--t)", i + 1)})' for i in range(M)])
F10 = '@function --f10(--x <number>, --k <number>) returns <number> { result: calc(' + E10('var(--x)', 'var(--k)') + '); }'
page('fn10', [f'--b{i}:--f10(var(--t), {i + 1})' for i in range(M)], F10)
F10L = ('@function --f10l(--x <number>, --k <number>) returns <number> { --p: calc(var(--x) * 0.3 + var(--k)); --q: calc(var(--x) * 0.7 - 2);'
        ' result: clamp(-1, var(--p) * var(--q) / (var(--x) + 5) + var(--x) * var(--x) * 0.001, 1000); }')
page('fn10local', [f'--b{i}:--f10l(var(--t), {i + 1})' for i in range(M)], F10L)
# progress() vs the clamp formula registers use
page('clampnorm', [f'--b{i}:clamp(0, (var(--t) - {i}) / 1000, 1)' for i in range(M)])
page('progress', [f'--b{i}:progress(var(--t), {i}, {i + 1000})' for i in range(M)])
# multi-use temps: 1000 temps, each used by U consumers, against the temp inlined into its consumers
T = 1000
tmp = lambda j: f'(var(--t) * 1.{j % 9 + 1} + {j})'
for U in (1, 2, 3, 5):
    regs = [f'u{j}' for j in range(T)] + [f'c{j}_{k}' for j in range(T) for k in range(U)]
    page(f'temp_u{U}', [f'--u{j}:calc{tmp(j)}' for j in range(T)] + [f'--c{j}_{k}:calc(var(--u{j}) * {k + 2} + 1)' for j in range(T) for k in range(U)], regs=regs)
    regs2 = [f'c{j}_{k}' for j in range(T) for k in range(U)]
    page(f'inl_u{U}', [f'--c{j}_{k}:calc({tmp(j)} * {k + 2} + 1)' for j in range(T) for k in range(U)], regs=regs2)
print('ok')
