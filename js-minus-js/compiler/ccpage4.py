#!/usr/bin/env python3
"""ccpage4.py source.js lib.json out_prefix — the compiler as CSS.

One nested element per source character (plus two NULs). Each level carries, as markup, its character and
the categories of the two characters before it (classes cA59 pB59 gAw ...), the same information as --c/--cn.

- Lexer: specialised per character (rule .cA<code> / .cB<code>, plain class selectors, no scanning).
  Lexer state and the token outputs the next level reads by var() alternate by character parity
  (.lvA reads *-A and writes *-B).
- Parser: one rule per (mode, token code) variant, selector = the classes of the characters such a token can
  end on (.p59 = "the previous character was ;"), condition = the parent's mode and token code:
      @container style(--l-vh: <mode>) and style(--l-o_tc: <token code>) { .p59 { ... } }
  so a level scans only the variants for tokens that can end on its previous character, and evaluates only
  the code reachable from that (mode, token). The variant body is parity-free: it reads the parser state
  through aliases --x-* and writes --q-new-*; two small token-level rules map those to the parity slots.
- Tables (symbols, functions): one write per step, applied one level later (delayed write rules bucketed by
  the class of the character two back). Labels: in-flow anchor elements --lab<j> on the defining level.
- Code/data words: position:fixed overlays, display:none unless valid, anchor-name --c<RAM index>,
  width = word + WOFF px (+ anchor-size(--lab<j>) for label-relative words).
- Errors: a token no variant accepts sets the sticky 'bad' bit (syntax error, 99); a parser error code is
  kept in 'perr'. Either stops the parser.
"""
import sys, json, re, os
from dsl import css2 as tocss, isK
import cc_dsl as D, cc_ref as R

WOFF = 1 << 20
OTH = {'A': 'B', 'B': 'A'}
WORD = set(range(48, 58)) | set(range(65, 91)) | set(range(97, 123)) | {95, 36}
LAST = {1: 61, 2: 61, 3: 61, 4: 61, 5: 38, 6: 124, 7: 43, 8: 45}     # last character of the two-char tokens
DELAYED_V = {f'o_{pre}{f}' for pre, last in (('y', 'k'), ('f', 'l'), ('i', 'v')) for f in ('h1', 'h2', last)}   # read by var() one level down
PORTS = ['o_yw', 'o_yi', 'o_yh1', 'o_yh2', 'o_yk', 'o_fw', 'o_fi', 'o_fh1', 'o_fh2', 'o_fl', 'o_iw', 'o_ii', 'o_ih1', 'o_ih2', 'o_iv']
LEX_SUF = {'o_tk', 'o_tv', 'o_th1', 'o_th2', 'o_tkany'}     # lexer outputs the next level reads by var(): parity-suffixed
TOKIN = ['tk', 'tv', 'th1', 'th2']

def cat(ch): return 'w' if ch in WORD else str(ch)
def tc_cats(tc):
    if tc in (1, 2): return {'w'}
    if tc == 3: return {'34'}
    if tc == 5: return {'0'}
    if tc == 4: return {str(c) for c in range(1, 128) if c not in WORD}
    v = D.PUNCT[tc - 6]
    return {str(LAST.get(v, v))}

def mux_shift(prop, n, base, shift=0):
    """--c<v + shift> for v in [base, base+n): prop holds v, prop-h holds (v - base) // 32"""
    hi = []
    for h in range((n + 31) // 32):
        lo = ' '.join(f'style(--{prop}: {base + h * 32 + l}): --c{base + h * 32 + l + shift};' for l in range(32) if h * 32 + l < n)
        hi.append(f'style(--{prop}-h: {h}): if({lo} else: none);')
    return f'if({" ".join(hi)} else: none)'

def mux_lab(prop, n):
    return 'if(' + ' '.join(f'style(--{prop}: {j}): --lab{j};' for j in range(n)) + ' else: --nolab)'

class Names:
    """registered properties; long names in the generator, short names in the output"""
    def __init__(self, short=True):
        self.reg = {}; self.short = short
    def add(self, name, inh):
        self.reg[name] = self.reg.get(name, False) or inh
    def rename(self, text):
        if not self.short: return text
        keys = sorted(self.reg)
        m = {k: f'z{i:x}' for i, k in enumerate(keys) if k not in ('c', 'cn', 'e', 'n')}
        return re.sub(r'--([A-Za-z0-9_-]+)', lambda mo: '--' + m.get(mo.group(1), mo.group(1)), text)
    def props(self):
        return [f'@property --{n} {{ syntax: "<integer>"; inherits: {"true" if i else "false"}; initial-value: 0; }}' for n, i in self.reg.items()]

def build(src_text, lib, prefix=None, code_base=4608, data_base=4096, short=True):
    """Memory (RAM index = address - 4096): globals/arrays 0..255, strings 256..511, code 512..1022 (511 words),
    count of initialised globals/arrays at 1023, their initial values staged at 1024..1279 (the lib's startup
    routine copies them into place, so the program can write them; code and strings are never written)."""
    initw = lib.get('init', 5120)
    code_cells = initw - 1 - code_base; data_cells = R.SDATA
    ishift = initw - data_base
    lst, pst, tabs = D.LEX_STATE, D.parse_state_names(), D.table_names()
    tset = set(tabs)
    progs = [(k, D.Prog(data_base, code_base, lib['print'], lib['puts'], *k)) for k in D.variant_keys()]
    progs = [(k, p) for k, p in progs if not (isK(p.x.cur['err']) and p.x.cur['err'].v != 0)]
    lexes = {c: D.LexProg(data_base, c) for c in range(128)}
    lexes['x'] = D.LexProg(data_base)                      # characters >= 128
    NLP = max(p.nlports for _, p in progs)
    E = R.EMAX
    N = Names(short)
    css = []
    # ---- lexer, per character and parity
    for rd in 'AB':
        wr = OTH[rd]
        for c, lp in lexes.items():
            lout = set(lp.out)
            def ref(kind, n, rd=rd, wr=wr, lout=lout):
                if kind == 'S': return f'var(--s-{n}-{rd})'
                if kind == 'I': return f'var(--l-o_tkany-{rd})' if n == 'ptk' else f'var(--{n})'
                if n in lout: return f'var(--l-{n}-{wr})' if n in LEX_SUF else f'var(--l-{n})'
                return f'var(--l{c}-{n})'
            decl = []
            for n, node in lp.x.temps:
                if n in lout:
                    nm = f'l-{n}-{wr}' if n in LEX_SUF else f'l-{n}'; N.add(nm, True)
                else: nm = f'l{c}-{n}'; N.add(nm, False)
                decl.append(f'--{nm}: {tocss(node, ref)};')
            decl += [f'--s-{n}-{wr}: {tocss(lp.x.cur[n], ref)};' for n in lst]
            sel = f'.c{rd}{c}'
            css.append(f'{sel} {{ ' + ' '.join(decl) + ' }')
    for n in lst:
        for x in 'AB': N.add(f's-{n}-{x}', True)
    # ---- every level: resets, port copies, error state, variant selector
    cur = lambda n: f'if(style(--l-o_pp: 0): var(--p-{n}-0); else: var(--p-{n}-1))'
    for rd in 'AB':
        wr = OTH[rd]
        decl = [f'--q-o_v{s}: 0;' for s in range(E)] + ['--q-o_dv: 0;', '--q-ran: 0;'] + [f'--q-o_lv{k}: 0;' for k in range(NLP)]
        decl += ['--q-o_yw: 0;', '--q-o_fw: 0;', '--q-o_iw: 0;'] + [f'--q-{n}-{wr}: var(--q-{n});' for n in sorted(DELAYED_V)]
        decl += [f'--s-bad-{wr}: max(var(--s-bad-{rd}), var(--l-o_tkany-{rd}) * (1 - var(--q-ran)));',
                 f'--s-perr-{wr}: if(style(--s-perr-{rd}: 0): {cur("err")}; else: var(--s-perr-{rd}));',
                 f'--l-ce: max(var(--s-bad-{wr}), min(1, var(--s-perr-{wr})));',
                 f'--l-vh: calc({cur("mode")} + var(--l-ce) * (127 - {cur("mode")}));']
        css.append(f'.lv{rd} {{ ' + ' '.join(decl) + ' }')
        for x in ('bad', 'perr'): N.add(f's-{x}-{rd}', True)
        for n in DELAYED_V: N.add(f'q-{n}-{rd}', True)
    for n in ['q-ran', 'q-o_dv', 'l-ce', 'l-vh'] + [f'q-o_v{s}' for s in range(E)] + [f'q-o_lv{k}' for k in range(NLP)]:
        N.add(n, n.startswith('q-o'))
    # ---- token levels: parser state aliases in, new state out (by parser parity), token inputs (by char parity)
    for rd in 'AB':
        for p in '01':
            w = '1' if p == '0' else '0'
            decl = [f'--x-{n}: var(--p-{n}-{p});' for n in pst] + [f'--x-{n}: var(--l-o_{n}-{rd});' for n in TOKIN]
            decl += [f'--p-{n}-{w}: var(--q-new-{n});' for n in pst]
            css.append(f'@container style(--l-o_tkany-{rd}: 1) and style(--l-o_pp: {p}) {{ .lv{rd} {{ ' + ' '.join(decl) + ' } }')
    for n in pst:
        N.add(f'x-{n}', False); N.add(f'q-new-{n}', False)
        for x in '01': N.add(f'p-{n}-{x}', True)
    for n in TOKIN: N.add(f'x-{n}', False)
    # ---- delayed table writes
    wcats = set()
    for key, pg in progs:
        if any(not isK(r[0], 0) for r in pg.symw + pg.fnw):
            for tc in D.key_tcodes(key): wcats |= tc_cats(tc)
    for rd in 'AB':
        wsel = ', '.join(f'.g{rd}{c}' for c in sorted(wcats))
        for pre, nm, fl, cnt in (('y', ('sh1_', 'sh2_', 'sk_'), ('h1', 'h2', 'k'), R.NS), ('f', ('fh1_', 'fh2_', 'fl_'), ('h1', 'h2', 'l'), R.NF)):
            for j in range(cnt):
                css.append(f'@container style(--q-o_{pre}w: 1) and style(--q-o_{pre}i: {j}) {{ {wsel} {{ '
                           + ' '.join(f'--t-{a}{j}: var(--q-o_{pre}{b}-{rd});' for a, b in zip(nm, fl)) + ' } }')
    for n in tabs: N.add(f't-{n}', True)
    # ---- parser variants
    def pref(kind, n):
        if kind == 'S': return f'var(--x-{n})'
        if kind == 'I': return f'var(--t-{n})' if n in tset else f'var(--x-{n})'
        return f'var(--q-{n})'
    for key, pg in progs:
        X = pg.x; outs = set(pg.out)
        decl = [f'--q-{n}: {tocss(node, pref)};' for n, node in X.temps]
        decl += [f'--q-new-{n}: {tocss(X.cur[n], pref)};' for n in pst] + ['--q-ran: 1;']
        for n, _ in X.temps: N.add(f'q-{n}', n in outs and n not in PORTS)
        tcs = D.key_tcodes(key)
        sel = ', '.join(f'.p{c}' for c in sorted(set().union(*[tc_cats(t) for t in tcs])))
        tcond = f'style(--l-o_tc: {tcs[0]})' if len(tcs) == 1 else '(' + ' or '.join(f'style(--l-o_tc: {t})' for t in tcs) + ')'
        css.append(f'@container style(--l-vh: {key[0]}) and {tcond} {{ {sel} {{ ' + ' '.join(decl) + ' } }')
    init = {f's-{n}-A': v for n, v in D.initial_lex(data_base).items()}
    init.update({f'p-{n}-0': v for n, v in D.initial_parse(data_base).items()})
    init.update({'l-o_tkany-A': 0, 'l-o_pp': 0, 'l-o_tc': 0, 'l-vh': 0, 's-bad-A': 0, 's-perr-A': 0})
    css.append('#cc { ' + ' '.join(f'--{n}: {v};' for n, v in init.items()) + ' }')
    # ---- word overlays
    cb0 = code_base - 4096
    css.append('.ov, .ovd, .ovs { position: fixed; top: 0; left: 0; height: 1px; visibility: hidden; display: none; }')
    for s in range(E):
        a = f'q-o_a{s}'; N.add(f'{a}-h', False)
        body = (f'display: block; --{a}-h: round(down, (var(--{a}) - {cb0}) / 32);'
                f' anchor-name: {mux_shift(a, code_cells, cb0)}; --ln: {mux_lab(f"q-o_l{s}", R.NL)};'
                f' width: calc((var(--q-o_w{s}) + {WOFF}) * 1px + anchor-size(var(--ln) width, 0px));')
        css.append(f'@container style(--q-o_v{s}: 1) {{ .ov.k{s} {{ {body} }} }}')
    N.add('q-o_da-h', False); N.add('l-o_sa-h', False)
    css.append(f'@container style(--q-o_dv: 1) {{ .ovd {{ display: block; --q-o_da-h: round(down, var(--q-o_da) / 32);'
               f' anchor-name: {mux_shift("q-o_da", data_cells, 0, ishift)}; width: calc((var(--q-o_dw) + {WOFF}) * 1px); }} }}')
    css.append(f'@container style(--l-o_sv: 1) {{ .ovs {{ display: block; --l-o_sa-h: round(down, (var(--l-o_sa) - {data_cells}) / 32);'
               f' anchor-name: {mux_shift("l-o_sa", data_cells, data_cells)}; width: calc((var(--l-o_sw) + {WOFF}) * 1px); }} }}')
    # ---- label anchors
    css.append('.lp { display: none; height: 0; }')
    for k in range(NLP):
        css.append(f'@container style(--q-o_lv{k}: 1) {{ .lp{k} {{ display: block; anchor-name: {mux_lab(f"q-o_lj{k}", R.NL)};'
                   f' width: calc(max(0, var(--q-o_lx{k})) * 1px); }} }}')
    css.append('#cc, #cc div { height: 0; } #cc { contain: strict; position: relative; }')   # its layout never joins the CPU's per-frame layout
    # ---- chain
    s = [ord(ch) for ch in src_text] + [0, 0]
    nlev = len(s)
    fo = OTH['A' if (nlev - 1) % 2 == 0 else 'B']          # parity suffix written by the deepest level
    css.append(f'.ovn {{ position: fixed; top: 0; left: 0; height: 1px; visibility: hidden; anchor-name: --c{initw - 1 - data_base};'
               f' width: calc(({cur("dp")} - {data_base} + {WOFF}) * 1px); }}')
    css.append(f'.ccerr {{ --e: if(style(--s-perr-{fo}: 0): max(var(--s-bad-{fo}) * 99, clamp(0, var(--n) - {code_cells}, 1) * 62); else: var(--s-perr-{fo})); --n: {cur("cp")};'
               ' counter-set: e var(--e) n var(--n); } .ccerr::after { content: "compiled: " counter(n) " words, error " counter(e); }')
    for n in ('c', 'cn', 'e', 'n'): N.add(n, False)
    slots = (''.join(f'<b class="ov k{k}"></b>' for k in range(E)) + '<b class="ovd"></b><b class="ovs"></b>'
             + ''.join(f'<b class="lp lp{k}"></b>' for k in range(NLP)))
    par = lambda i: 'A' if i % 2 == 0 else 'B'
    ccls = lambda ch: str(ch) if ch < 128 else 'x'
    def cls(i):
        x = par(i)
        return (f'lv{x} c{x}{ccls(s[i])} p{cat(s[i - 1]) if i > 0 else "n"} g{x}{cat(s[i - 2]) if i > 1 else "n"}')
    opens = "".join(f'<div class="{cls(i)}" style="--cn:{s[i + 1] if i + 1 < nlev else 0}{";--c:" + str(s[i]) if s[i] >= 128 else ""}">{slots}' for i in range(nlev))
    body = f'<div id="cc">{opens}<b class="ovn"></b><p class="ccerr"></p>{"</div>" * nlev}</div>'
    css_text = N.rename('\n'.join(N.props() + css))
    if prefix:
        open(prefix + '.css', 'w').write(css_text)
        open(prefix + '.html', 'w').write(N.rename(body))
    info = dict(levels=nlev, variants=len(progs), parse_temps=sum(len(p.x.temps) for _, p in progs),
                lex_temps=sum(len(l.x.temps) for l in lexes.values()), lports=NLP, css_bytes=len(css_text))
    return css_text, N.rename(body), info

if __name__ == '__main__':
    src = open(sys.argv[1]).read(); lib = json.load(open(sys.argv[2]))
    print(build(src, lib, sys.argv[3], short=os.environ.get('SHORT', '1') == '1')[2])
