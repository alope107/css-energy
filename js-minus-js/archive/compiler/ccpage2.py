#!/usr/bin/env python3
"""ccpage2.py source.js lib.json out_prefix — the compiler as CSS, lexer/parser split.

One nested element per source character (plus two NULs). Every level runs the lexer (cc_dsl.LexProg): lexer
state and lexer outputs alternate by character parity (.lvA reads *-A, writes *-B; .lvB the reverse). The
parser (cc_dsl.Prog) runs only on the level after a token completed: its rules sit inside
  @container style(--l-o_tkany-X: 1) and style(--l-o_pp-X: p)
(the parent's lexer outputs), so levels without a token declare no parser properties at all and the parser
state simply inherits through them. Parser state alternates by token parity (-0 / -1): the parser reads
parity p = parent's o_pp and writes 1-p.

Outputs: per level up to EMAX code words and one array-data word from the parser, one string byte from the
lexer. Each is a position:fixed element, display:none unless valid, whose anchor-name is the RAM cell it
stands for (--c<index>) and whose width is word + WOFF px (+ the label's anchor width for label-relative
words; label anchors --lab<j> sit at the bottom of the chain).
"""
import sys, json
from dsl import css as tocss
import cc_dsl as D, cc_ref as R

WOFF = 1 << 20
OTH = {'A': 'B', 'B': 'A'}

def reg(name, inh):
    return f'@property --{name} {{ syntax: "<integer>"; inherits: {"true" if inh else "false"}; initial-value: 0; }}'

def mux_shift(prop, n, base):
    """--c<v> for v in [base, base+n): prop holds v, prop-h holds (v - base) // 32"""
    hi = []
    for h in range((n + 31) // 32):
        lo = ' '.join(f'style(--{prop}: {base + h * 32 + l}): --c{base + h * 32 + l};' for l in range(32) if h * 32 + l < n)
        hi.append(f'style(--{prop}-h: {h}): if({lo} else: none);')
    return f'if({" ".join(hi)} else: none)'

def mux_lab(prop, n):
    return 'if(' + ' '.join(f'style(--{prop}: {j}): --lab{j};' for j in range(n)) + ' else: --nolab)'

def build(src_text, lib, prefix, code_base=4608, data_base=4096, code_cells=1024, data_cells=512, ovgate=True):
    lp = D.LexProg(data_base)
    pp = D.Prog(data_base, code_base, lib['print'], lib['puts'])
    LX, PX = lp.x, pp.x
    lst, pst = D.LEX_STATE, D.parse_state_names()
    lout = set(lp.out); pout = set(pp.out)
    props = []
    for n in lst:
        for p in 'AB': props.append(reg(f's-{n}-{p}', True))
    for n in pst:
        for p in '01': props.append(reg(f'p-{n}-{p}', True))
    for n, _ in LX.temps:
        if n in lout:
            for p in 'AB': props.append(reg(f'l-{n}-{p}', True))
        else: props.append(reg(f'l-{n}', False))
    for n, _ in PX.temps: props.append(reg(f'q-{n}', n in pout))
    props += [reg(f'q-o_a{s}-h', False) for s in range(R.EMAX)] + [reg('q-o_da-h', False)]
    props += [reg(f'l-o_sa-{p}-h', False) for p in 'AB']
    props += [reg('c', False), reg('cn', False)]
    css = []
    # ---- lexer, every level
    for rd in 'AB':
        wr = OTH[rd]
        def ref(kind, n, rd=rd, wr=wr):
            if kind == 'S': return f'var(--s-{n}-{rd})'
            if kind == 'I': return 'var(--l-o_tkany-%s)' % rd if n == 'ptk' else f'var(--{n})'
            return f'var(--l-{n}-{wr})' if n in lout else f'var(--l-{n})'
        decl = [f'--l-{n}{"-" + wr if n in lout else ""}: {tocss(node, ref)};' for n, node in LX.temps]
        decl += [f'--s-{n}-{wr}: {tocss(LX.cur[n], ref)};' for n in lst]
        css.append(f'.lv{rd} {{\n' + '\n'.join(decl) + '\n}')
    # parser outputs default to "nothing emitted" on levels where the parser does not run
    css.append('.lvA, .lvB { ' + ' '.join(f'--q-o_v{s}: 0;' for s in range(R.EMAX)) + ' --q-o_dv: 0; }')
    # ---- parser, gated on the parent's lexer outputs
    for rd in 'AB':                       # char parity of this level: parent's lexer outputs carry suffix rd
        for p in '01':
            w = '1' if p == '0' else '0'
            def ref(kind, n, rd=rd, p=p):
                if kind == 'S': return f'var(--p-{n}-{p})'
                if kind == 'I': return f'var(--l-o_{n}-{rd})'
                return f'var(--q-{n})'
            decl = [f'--q-{n}: {tocss(node, ref)};' for n, node in PX.temps]
            decl += [f'--p-{n}-{w}: {tocss(PX.cur[n], ref)};' for n in pst]
            css.append(f'@container style(--l-o_tkany-{rd}: 1) and style(--l-o_pp-{rd}: {p}) {{ .lv{rd} {{\n' + '\n'.join(decl) + '\n} }')
    init = {f's-{n}-A': v for n, v in D.initial_lex(data_base).items()}
    init.update({f'p-{n}-0': v for n, v in D.initial_parse(data_base).items()})
    init.update({'l-o_tkany-A': 0, 'l-o_pp-A': 0})
    css.append('#cc { ' + ' '.join(f'--{n}: {v};' for n, v in init.items()) + ' }')
    # ---- overlays
    E = R.EMAX; cb0 = code_base - 4096
    css.append('.ov, .ovd, .ovs { position: fixed; top: 0; left: 0; height: 1px; visibility: hidden; display: none; }')
    for s in range(E):
        a = f'q-o_a{s}'
        body = (f'display: block; --{a}-h: round(down, calc((var(--{a}) - {cb0}) / 32));'
                f' --an: {mux_shift(a, code_cells, cb0)}; --ln: {mux_lab(f"q-o_l{s}", R.NL)};'
                f' anchor-name: var(--an);'
                f' width: calc((var(--q-o_w{s}) + {WOFF}) * 1px + anchor-size(var(--ln) width, 0px));')
        css.append(f'@container style(--q-o_v{s}: 1) {{ .ov.k{s} {{ {body} }} }}')
    css.append(f'@container style(--q-o_dv: 1) {{ .ovd {{ display: block; --q-o_da-h: round(down, calc(var(--q-o_da) / 32));'
               f' anchor-name: {mux_shift("q-o_da", data_cells, 0)}; width: calc((var(--q-o_dw) + {WOFF}) * 1px); }} }}')
    for x in 'AB':        # string bytes from the lexer; a .lvA level wrote its outputs with suffix B
        o = OTH[x]
        css.append(f'@container style(--l-o_sv-{o}: 1) {{ .lv{x} > .ovs {{ display: block; --l-o_sa-{o}-h: round(down, calc(var(--l-o_sa-{o}) / 32));'
                   f' anchor-name: {mux_shift(f"l-o_sa-{o}", data_cells, 0)}; width: calc((var(--l-o_sw-{o}) + {WOFF}) * 1px); }} }}')
    css.append('#cc, #cc div { height: 0; }')
    css.append('.lb { display: block; height: 1px; }')
    # ---- chain
    s = [ord(ch) for ch in src_text] + [0, 0]
    nlev = len(s)
    fo = OTH['A' if (nlev - 1) % 2 == 0 else 'B']          # output suffix written by the deepest level
    fin = lambda n: f'if(style(--l-o_pp-{fo}: 0): var(--p-{n}-0); else: var(--p-{n}-1))'
    for j in range(R.NL):
        css.append(f'.lb{j} {{ anchor-name: --lab{j}; width: calc(max(0, {fin(f"lab{j}")}) * 1px); }}')
    css.append(f'.ccerr {{ --e: {fin("err")}; --n: {fin("cp")}; counter-set: e var(--e) n var(--n); }}'
               ' .ccerr::after { content: "compiled: " counter(n) " words, error " counter(e); }')
    props += [reg('e', False), reg('n', False)]
    slots = ''.join(f'<b class="ov k{k}"></b>' for k in range(E)) + '<b class="ovd"></b><b class="ovs"></b>'
    opens = ''.join(f'<div class="lv{"A" if i % 2 == 0 else "B"}" style="--c:{s[i]};--cn:{s[i + 1] if i + 1 < nlev else 0}">{slots}' for i in range(nlev))
    bottom = ''.join(f'<i class="lb lb{j}"></i>' for j in range(R.NL)) + '<p class="ccerr"></p>'
    body = f'<div id="cc">{opens}{bottom}{"</div>" * nlev}</div>'
    open(prefix + '.css', 'w').write('\n'.join(props + css))
    open(prefix + '.html', 'w').write(body)
    return dict(levels=nlev, lex_temps=len(LX.temps), parse_temps=len(PX.temps), css_bytes=sum(len(x) for x in props + css))

if __name__ == '__main__':
    src = open(sys.argv[1]).read(); lib = json.load(open(sys.argv[2]))
    print(build(src, lib, sys.argv[3]))
