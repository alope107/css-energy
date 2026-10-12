#!/usr/bin/env python3
"""ccpage.py source.js lib.json out_prefix — the compiler as CSS: one nested element per source character.

Writes out_prefix.css and out_prefix.html. Each level declares the step program from cc_dsl (temps, then the
next state under the other parity name). Inside each level: 12 code-slot elements and one data element,
position: fixed, width = word + WOFF px (labels resolved with anchor-size() on the label anchors at the bottom
of the chain), anchor-name = the RAM cell they stand for (--c<index>), so a VM read of that address finds them.
"""
import sys, json, html
from dsl import css as tocss
import cc_dsl as D, cc_ref as R

WOFF = 1 << 20

def build(src_text, lib, prefix, code_base=4608, data_base=4096, code_cells=1024, data_cells=512):
    prog = D.Prog(data_base, code_base, lib['print'], lib['puts'])
    X = prog.x
    states = D.state_names()
    outs = set(prog.out)
    props = []
    for n in states:
        for p in 'AB': props.append(f'@property --s-{n}-{p} {{ syntax: "<integer>"; inherits: true; initial-value: 0; }}')
    for n, _ in X.temps:
        inh = 'true' if n in outs else 'false'
        props.append(f'@property --{tname(n)} {{ syntax: "<integer>"; inherits: {inh}; initial-value: 0; }}')
    props += [f'@property --{tname(f"o_a{s}")}-h {{ syntax: "<integer>"; inherits: false; initial-value: 0; }}' for s in range(R.EMAX)]
    props += [f'@property --{tname("o_da")}-h {{ syntax: "<integer>"; inherits: false; initial-value: 0; }}']
    props += ['@property --c { syntax: "<integer>"; inherits: false; initial-value: 0; }',
              '@property --cn { syntax: "<integer>"; inherits: false; initial-value: 0; }']
    css = []
    for rd, wr in (('A', 'B'), ('B', 'A')):
        def ref(kind, n, rd=rd):
            if kind == 'S': return f'var(--s-{n}-{rd})'
            if kind == 'I': return f'var(--{n})'
            return f'var(--{tname(n)})'
        decl = [f'--{tname(n)}: {tocss(node, ref)};' for n, node in X.temps]
        decl += [f'--s-{n}-{wr}: {tocss(X.cur[n], ref)};' for n in states]
        css.append(f'.lv{rd} {{\n' + '\n'.join(decl) + '\n}')
    init = D.initial_state(data_base)
    css.append('#cc { ' + ' '.join(f'--s-{n}-A: {v};' for n, v in init.items()) + ' }')
    # overlay slots
    def mux(prop, n, name, base=0):
        """if() over values 0..n-1 of prop (hi/lo nested by 32) -> --{name}{v+base}"""
        hi = []
        for h in range((n + 31) // 32):
            lo = ' '.join(f'style(--{prop}: {h * 32 + l + base}): --{name}{h * 32 + l + base};' for l in range(32) if h * 32 + l < n)
            hi.append(f'style(--{prop}-h: {h}): if({lo} else: --none);')
        return f'if({" ".join(hi)} else: --none)'
    E = R.EMAX
    cb0 = code_base - 4096
    for s in range(E):
        css.append(f'.ov.k{s} {{ --{tname(f"o_a{s}")}-h: round(down, calc((var(--{tname(f"o_a{s}")}) - {cb0}) / 32));'
                   f' --an: if(style(--{tname(f"o_v{s}")}: 1): {mux_shift(tname(f"o_a{s}"), code_cells, cb0)}; else: none);'
                   f' --ln: {mux_lab(tname(f"o_l{s}"), R.NL)};'
                   f' anchor-name: var(--an);'
                   f' width: calc((var(--{tname(f"o_w{s}")}) + {WOFF}) * 1px + anchor-size(var(--ln) width, 0px)); }}')
    css.append(f'.ovd {{ --{tname("o_da")}-h: round(down, calc(var(--{tname("o_da")}) / 32));'
               f' --an: if(style(--{tname("o_dv")}: 1): {mux_shift(tname("o_da"), data_cells, 0)}; else: none);'
               f' anchor-name: var(--an); width: calc((var(--{tname("o_dw")}) + {WOFF}) * 1px); }}')
    css.append('.ov, .ovd { position: fixed; top: 0; left: 0; height: 1px; visibility: hidden; }')
    css.append('#cc, #cc div { height: 0; }')
    css.append('.lb { display: block; height: 1px; }')
    fin = 'A' if len(src_text) % 2 == 0 else 'B'      # parity written by the last level (level i writes B if i even)
    nlev = len(src_text) + 1
    fin = 'B' if (nlev - 1) % 2 == 0 else 'A'
    for j in range(R.NL):
        css.append(f'.lb{j} {{ anchor-name: --lab{j}; width: calc(max(0, var(--s-lab{j}-{fin})) * 1px); }}')
    css.append(f'.ccerr {{ counter-set: e var(--s-err-{fin}) n var(--s-cp-{fin}); }} .ccerr::after {{ content: "compiled: " counter(n) " words, error " counter(e); }}')
    # chain
    s = [ord(ch) for ch in src_text] + [0]
    slots = ''.join(f'<b class="ov k{k}"></b>' for k in range(E)) + '<b class="ovd"></b>'
    opens = ''.join(f'<div class="lv{"A" if i % 2 == 0 else "B"}" style="--c: {s[i]}; --cn: {s[i + 1] if i + 1 < len(s) else 0}">{slots}' for i in range(len(s)))
    bottom = ''.join(f'<i class="lb lb{j}"></i>' for j in range(R.NL)) + '<p class="ccerr"></p>'
    body = f'<div id="cc">{opens}{bottom}{"</div>" * len(s)}</div>'
    open(prefix + '.css', 'w').write('\n'.join(props + css))
    open(prefix + '.html', 'w').write(body)
    return dict(levels=len(s), temps=len(X.temps), states=len(states), css_bytes=sum(len(x) for x in props + css))

def tname(n): return 't-' + n

def mux_shift(prop, n, base):
    """name --c<v> for v in [base, base+n): prop holds v; prop-h holds (v - base) // 32"""
    hi = []
    for h in range((n + 31) // 32):
        lo = ' '.join(f'style(--{prop}: {base + h * 32 + l}): --c{base + h * 32 + l};' for l in range(32) if h * 32 + l < n)
        hi.append(f'style(--{prop}-h: {h}): if({lo} else: none);')
    return f'if({" ".join(hi)} else: none)'

def mux_lab(prop, n):
    return 'if(' + ' '.join(f'style(--{prop}: {j}): --lab{j};' for j in range(n)) + ' else: --nolab)'

if __name__ == '__main__':
    src = open(sys.argv[1]).read(); lib = json.load(open(sys.argv[2]))
    print(build(src, lib, sys.argv[3]))
