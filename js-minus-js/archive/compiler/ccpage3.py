#!/usr/bin/env python3
"""ccpage3.py source.js lib.json out_prefix — the compiler as CSS: lexer per character, parser per token,
parser specialised per (mode, token kind, punctuation) and selected by container query.

One nested element per source character (plus two NULs).
- Lexer (cc_dsl.LexProg) on every level. Lexer state and outputs alternate by character parity:
  .lvA reads *-A and writes *-B, .lvB the reverse; #cc seeds the A side.
- Parser (cc_dsl.Prog variants) only on the level after a token completed. Each variant is wrapped in
    @container style(--l-o_pp-X: p) and style(--p-err-p: 0) and style(--p-mode-p: M) and style(--l-o_tk-X: K) [and tv]
  (queries read the parent: its lexer outputs and the current parser state), so a level evaluates only the
  code reachable from its mode and token. Levels without a token declare nothing; parser state inherits
  through them. Parser state alternates by token parity (-0/-1).
- Symbol/function tables are not parser state: a step outputs at most one write per table; the next level
  applies it with one container rule per entry (delayed write), so the parser never copies the tables.
- Labels are not state: each definition is an in-flow anchor element (--lab<j>, width = value) on the
  defining level; code words that refer to a label add anchor-size(--lab<j> width) to their width.
- Code/data words: position:fixed elements, display:none unless valid, anchor-name = the RAM cell
  (--c<index>), width = word + WOFF px.
"""
import sys, json
from dsl import css as tocss, isK
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

import os
NEST = os.environ.get('NEST') == '1'
BUCKET = os.environ.get('BUCKET', '1') == '1'   # rule buckets by the previous characters' class
DELAYED = {f'o_{pre}{f}' for pre, last in (('y', 'k'), ('f', 'l')) for f in ('w', 'i', 'h1', 'h2', last)}

WORD = set(range(48, 58)) | set(range(65, 91)) | set(range(97, 123)) | {95, 36}
def cat(ch):
    """class category of a source character: word characters share one"""
    return 'w' if ch in WORD else str(ch)
LAST = {1: 61, 2: 61, 3: 61, 4: 61, 5: 38, 6: 124, 7: 43, 8: 45}     # last character of the two-char tokens
def tc_cats(tc):
    """categories of the character a token with this code ends on"""
    if tc in (1, 2): return {'w'}
    if tc == 3: return {'34'}
    if tc == 5: return {'0'}
    if tc == 4: return {str(c) for c in range(1, 128) if c not in WORD}
    v = D.PUNCT[tc - 6]
    return {str(LAST.get(v, v))}

def build(src_text, lib, prefix=None, code_base=4608, data_base=4096, code_cells=1024, data_cells=512, spec=True):
    """returns (css, html, info). Writes prefix.css / prefix.html when prefix is given."""
    lp = D.LexProg(data_base)
    if spec:      # variants whose only effect is a syntax error are left out: no rule matches -> sticky 'bad' bit
        progs = [(k, D.Prog(data_base, code_base, lib['print'], lib['puts'], *k)) for k in D.variant_keys()]
        progs = [(k, p) for k, p in progs if not (isK(p.x.cur['err']) and p.x.cur['err'].v != 0)]
        if os.environ.get('NOPARSE'): progs = progs[:1]
    else: progs = [(None, D.Prog(data_base, code_base, lib['print'], lib['puts']))]
    LX = lp.x
    lst, pst, tabs = D.LEX_STATE, D.parse_state_names(), D.table_names()
    tset = set(tabs)
    lout = set(lp.out)
    NLP = max(p.nlports for _, p in progs)
    E = R.EMAX
    # ---- registrations
    props = []
    for n in lst: props += [reg(f's-{n}-{x}', True) for x in 'AB']
    for n in pst: props += [reg(f'p-{n}-{x}', True) for x in '01']
    for n, _ in LX.temps:
        if n in lout: props += [reg(f'l-{n}-{x}', True) for x in 'AB']
        else: props.append(reg(f'l-{n}', False))
    tn = {}
    for _, p in progs:
        for n, _ in p.x.temps: tn[n] = tn.get(n, False) or n in p.out
    for n in [f'o_v{s}' for s in range(E)] + [f'o_lv{k}' for k in range(NLP)] + ['o_dv', 'o_yw', 'o_fw']:
        tn[n] = True
    for n, o in tn.items():
        if n in DELAYED: props += [reg(f'q-{n}-{x}', True) for x in 'AB']
        else: props.append(reg(f'q-{n}', o))
    props += [reg(f't-{n}', True) for n in tabs]
    props += [reg(f'q-o_a{s}-h', False) for s in range(E)] + [reg('q-o_da-h', False)] + [reg(f'l-o_sa-{x}-h', False) for x in 'AB']
    props += [reg('q-ran', False)] + [reg(f's-{n}-{x}', True) for n in ('bad', 'perr') for x in 'AB']
    props += [reg(f'l-{n}-{x}', n == 'vh') for n in ('cm', 'ce', 'vh') for x in 'AB']
    props += [reg('c', False), reg('cn', False), reg('e', False), reg('n', False)]
    css = []
    # ---- lexer, every level
    for rd in 'AB':
        wr = OTH[rd]
        def ref(kind, n, rd=rd, wr=wr):
            if kind == 'S': return f'var(--s-{n}-{rd})'
            if kind == 'I': return f'var(--l-o_tkany-{rd})' if n == 'ptk' else f'var(--{n})'
            return f'var(--l-{n}-{wr})' if n in lout else f'var(--l-{n})'
        decl = [f'--l-{n}{"-" + wr if n in lout else ""}: {tocss(node, ref)};' for n, node in LX.temps]
        decl += [f'--s-{n}-{wr}: {tocss(LX.cur[n], ref)};' for n in lst]
        # parser outputs default to "nothing" on levels where the parser does not run
        decl += [f'--q-o_v{s}: 0;' for s in range(E)] + ['--q-o_dv: 0;'] + [f'--q-o_lv{k}: 0;' for k in range(NLP)]
        decl += [f'--q-o_yw-{wr}: 0;', f'--q-o_fw-{wr}: 0;']
        # variant selector for the child's parser: vh = parity*32 + mode, or 64 + parity after an error; plus o_tc.
        # (kept < 256: Chrome's @container style() never matches a calc()-computed <integer> >= 256)
        cur = lambda n: f'if(style(--l-o_pp-{wr}: 0): var(--p-{n}-0); else: var(--p-{n}-1))'
        # errors: 'bad' = a token arrived and no variant took it (syntax error, reported as 99); 'perr' = first
        # error code the parser set. Either one stops the parser (vh = 127 matches nothing).
        decl += ['--q-ran: 0;',
                 f'--s-bad-{wr}: max(var(--s-bad-{rd}), calc(var(--l-o_tkany-{rd}) * calc(1 - var(--q-ran))));',
                 f'--s-perr-{wr}: if(style(--s-perr-{rd}: 0): {cur("err")}; else: var(--s-perr-{rd}));',
                 f'--l-cm-{wr}: {cur("mode")};', f'--l-ce-{wr}: max(var(--s-bad-{wr}), min(1, var(--s-perr-{wr})));',
                 f'--l-vh-{wr}: calc(var(--l-o_pp-{wr}) * 32 + var(--l-cm-{wr})'
                 f' + var(--l-ce-{wr}) * calc(127 - var(--l-o_pp-{wr}) * 32 - var(--l-cm-{wr})));']
        css.append(f'.lv{rd} {{\n' + '\n'.join(decl) + '\n}')
    # ---- delayed table writes: the parent's write port lands on this level
    wcats = set()                         # categories of tokens whose parser step can write a table
    for key, pg in progs:
        if any(not isK(r[0], 0) for r in pg.symw + pg.fnw):
            for tc in (D.key_tcodes(key) if key else range(1, 6 + len(D.PUNCT))): wcats |= tc_cats(tc)
    for rd in 'AB':
        wsel = ', '.join(f'.g{rd}{c}' for c in sorted(wcats)) if BUCKET else f'.lv{rd}'
        for pre, nm, fl, cnt in (('y', ('sh1_', 'sh2_', 'sk_'), ('h1', 'h2', 'k'), R.NS), ('f', ('fh1_', 'fh2_', 'fl_'), ('h1', 'h2', 'l'), R.NF)):
            for j in range(cnt):
                css.append(f'@container style(--q-o_{pre}w-{rd}: 1) and style(--q-o_{pre}i-{rd}: {j}) {{ {wsel} {{ '
                           + ' '.join(f'--t-{a}{j}: var(--q-o_{pre}{b}-{rd});' for a, b in zip(nm, fl)) + ' } }')
    # ---- parser variants, gated on the parent's lexer outputs and the current parser state
    for rd in 'AB':                       # this level's char parity; the parent's lexer outputs carry suffix rd
        wr = OTH[rd]
        for p in '01':
            w = '1' if p == '0' else '0'
            def ref(kind, n, rd=rd, p=p, wr=wr):
                if kind == 'S': return f'var(--p-{n}-{p})'
                if kind == 'I': return f'var(--t-{n})' if n in tset else f'var(--l-o_{n}-{rd})'
                return f'var(--q-{n}-{wr})' if n in DELAYED else f'var(--q-{n})'
            base = f'style(--l-o_pp-{rd}: {p})'
            groups = {}
            for key, pg in progs:
                PX = pg.x
                decl = [f'--q-{n}{"-" + wr if n in DELAYED else ""}: {tocss(node, ref)};' for n, node in PX.temps]
                decl += [f'--p-{n}-{w}: {tocss(PX.cur[n], ref)};' for n in pst] + ['--q-ran: 1;']
                if key is None: cond = f'style(--l-o_tkany-{rd}: 1) and {base}'
                else:
                    tcs = D.key_tcodes(key)
                    cond = f'style(--l-vh-{rd}: {int(p) * 32 + key[0]}) and ' + (f'style(--l-o_tc-{rd}: {tcs[0]})' if len(tcs) == 1 else
                                                                                 '(' + ' or '.join(f'style(--l-o_tc-{rd}: {t})' for t in tcs) + ')')
                if os.environ.get('EMPTY'): decl = ['--q-ran: 1;']
                sel = f'.lv{rd}'
                if BUCKET and key is not None:
                    sel = ', '.join(f'.p{rd}{c}' for c in sorted(set().union(*[tc_cats(t) for t in D.key_tcodes(key)])))
                body = f'{sel} {{\n' + '\n'.join(decl) + '\n}'
                if NEST and key is not None:
                    groups.setdefault(int(p) * 32 + key[0], []).append(f'@container {cond.split(" and ", 1)[1]} {{ {body} }}')
                else: css.append(f'@container {cond} {{ {body} }}')
            for h, rules in groups.items():
                css.append(f'@container style(--l-vh-{rd}: {h}) {{\n' + '\n'.join(rules) + '\n}')
    init = {f's-{n}-A': v for n, v in D.initial_lex(data_base).items()}
    init.update({f'p-{n}-0': v for n, v in D.initial_parse(data_base).items()})
    init.update({'l-o_tkany-A': 0, 'l-o_pp-A': 0, 'l-vh-A': 0, 's-bad-A': 0, 's-perr-A': 0})
    css.append('#cc { ' + ' '.join(f'--{n}: {v};' for n, v in init.items()) + ' }')
    # ---- word overlays
    cb0 = code_base - 4096
    css.append('.ov, .ovd, .ovs { position: fixed; top: 0; left: 0; height: 1px; visibility: hidden; display: none; }')
    for s in range(E):
        a = f'q-o_a{s}'
        body = (f'display: block; --{a}-h: round(down, calc((var(--{a}) - {cb0}) / 32));'
                f' anchor-name: {mux_shift(a, code_cells, cb0)}; --ln: {mux_lab(f"q-o_l{s}", R.NL)};'
                f' width: calc((var(--q-o_w{s}) + {WOFF}) * 1px + anchor-size(var(--ln) width, 0px));')
        css.append(f'@container style(--q-o_v{s}: 1) {{ .ov.k{s} {{ {body} }} }}')
    css.append(f'@container style(--q-o_dv: 1) {{ .ovd {{ display: block; --q-o_da-h: round(down, calc(var(--q-o_da) / 32));'
               f' anchor-name: {mux_shift("q-o_da", data_cells, 0)}; width: calc((var(--q-o_dw) + {WOFF}) * 1px); }} }}')
    for x in 'AB':        # string bytes from the lexer; a .lvA level wrote its outputs with suffix B
        o = OTH[x]
        css.append(f'@container style(--l-o_sv-{o}: 1) {{ .lv{x} > .ovs {{ display: block; --l-o_sa-{o}-h: round(down, calc(var(--l-o_sa-{o}) / 32));'
                   f' anchor-name: {mux_shift(f"l-o_sa-{o}", data_cells, 0)}; width: calc((var(--l-o_sw-{o}) + {WOFF}) * 1px); }} }}')
    # ---- label anchors
    css.append('.lp { display: none; height: 0; }')
    for k in range(NLP):
        css.append(f'@container style(--q-o_lv{k}: 1) {{ .lp{k} {{ display: block; anchor-name: {mux_lab(f"q-o_lj{k}", R.NL)};'
                   f' width: calc(max(0, var(--q-o_lx{k})) * 1px); }} }}')
    css.append('#cc, #cc div { height: 0; }')
    # ---- chain
    s = [ord(ch) for ch in src_text] + [0, 0]
    nlev = len(s)
    fo = OTH['A' if (nlev - 1) % 2 == 0 else 'B']          # output suffix written by the deepest level
    fin = lambda n: f'if(style(--l-o_pp-{fo}: 0): var(--p-{n}-0); else: var(--p-{n}-1))'
    css.append(f'.ccerr {{ --e: if(style(--s-perr-{fo}: 0): calc(var(--s-bad-{fo}) * 99); else: var(--s-perr-{fo})); --n: {fin("cp")}; counter-set: e var(--e) n var(--n); }}'
               ' .ccerr::after { content: "compiled: " counter(n) " words, error " counter(e); }')
    slots = (''.join(f'<b class="ov k{k}"></b>' for k in range(E)) + '<b class="ovd"></b><b class="ovs"></b>'
             + ''.join(f'<b class="lp lp{k}"></b>' for k in range(NLP)))
    par = lambda i: "A" if i % 2 == 0 else "B"
    cls = lambda i: f'lv{par(i)} p{par(i)}{cat(s[i - 1]) if i > 0 else "n"} g{par(i)}{cat(s[i - 2]) if i > 1 else "n"}'
    opens = ''.join(f'<div class="{cls(i)}" style="--c:{s[i]};--cn:{s[i + 1] if i + 1 < nlev else 0}">{slots}' for i in range(nlev))
    body = f'<div id="cc">{opens}<p class="ccerr"></p>{"</div>" * nlev}</div>'
    css_text = '\n'.join(props + css)
    if prefix:
        open(prefix + '.css', 'w').write(css_text)
        open(prefix + '.html', 'w').write(body)
    info = dict(levels=nlev, lex_temps=len(LX.temps), variants=len(progs), parse_temps=sum(len(p.x.temps) for _, p in progs),
                lports=NLP, css_bytes=len(css_text))
    return css_text, body, info

if __name__ == '__main__':
    src = open(sys.argv[1]).read(); lib = json.load(open(sys.argv[2]))
    print(build(src, lib, sys.argv[3], spec=len(sys.argv) < 5 or sys.argv[4] != 'generic')[2])
