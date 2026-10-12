#!/usr/bin/env python3
"""ccpage5.py — the compiler as CSS for TYPED input: a character chain and a token chain.

The source is read from the editor by the scan readback (latch cells, one per line x column). Each latch cell
carries a tiny view-timeline register (--ch<k>_<j>: the code, --cl<k>_<j>: its class), so any element can
animate a property from it. Slots: L lines x (P columns + newline), then two NULs; a column past the end of
its line reads as a space.

Character chain (#cc, one nested element per slot; display:none until Run):
  - --c / --cn / --ncl come from the registers of this slot and the next one (newline/NUL slots are static).
  - the lexer is specialised per character class and picked by the parent's --ncl (9 small rules).
  - a level that completes a token shows its token register .tr: a scroller whose four subjects are named
    --tk<t>c/v/h/g (t = tokens so far, chosen with an if() mux) and placed at tc / tv / th1 / th2 px.
  - string bytes become in-flow overlay words (.ovs) named after their RAM cell.
Token chain (#tcr, nested inside the deepest character level; levels past the token count are display:none):
  - level t animates token t's four values from --tk<t>*; level t+1 runs the parser on token t, picking the
    variant for (mode, token code) with @container style(--vh: m) and style(--tcq: tc) on its parent.
  - symbol/function tables: delayed writes as before; labels: in-flow anchors; code words: fixed overlays
    inside #tcr (contain: strict), anchor-name --c<RAM index>.
  - the last level shows .fin: the staged-data count word, and two in-flow anchors the CPU reads:
    --ccdone (width 1 when compiled without error) and --ccinfo (width = done + 2*err + 1024*words).
"""
import sys, json, re, os
from dsl import css2 as tocss, isK
import cc_dsl as D, cc_ref as R
from ccpage4 import Names, mux_shift, mux_lab, WOFF, OTH, DELAYED_V, PORTS

PR = set(range(32, 127))
CLASSES = [{32}, D.ALPHA, D.DIGIT, {34}, {92}, {47}, PR - D.ALPHA - D.DIGIT - {32, 34, 92, 47}, {10}, {0}]
CL_NL, CL_NUL = 7, 8
HC = 128                 # character register height
HT = 1 << 20             # token register height
TOKF = [('c', 'tc'), ('v', 'tv'), ('h', 'th1'), ('g', 'th2')]

def ccl_css(v):
    """class of a printable code (CSS expression over var(--v))"""
    al = f'clamp(0, {v} - 64, 1) * clamp(0, 91 - {v}, 1) + clamp(0, {v} - 96, 1) * clamp(0, 123 - {v}, 1)'
    dg = f'clamp(0, {v} - 47, 1) * clamp(0, 58 - {v}, 1)'
    return (f'if(style(--cv: 32): 0; style(--cv: 34): 3; style(--cv: 92): 4; style(--cv: 47): 5; style(--cv: 95): 1; style(--cv: 36): 1;'
            f' else: calc(6 - 5 * ({al}) - 4 * ({dg})))')

def mux_name(prop, n, fmt):
    hi = []
    for h in range((n + 31) // 32):
        lo = ' '.join(f'style(--{prop}: {h * 32 + l}): {fmt(h * 32 + l)};' for l in range(32) if h * 32 + l < n)
        hi.append(f'style(--{prop}-h: {h}): if({lo} else: none);')
    return f'if({" ".join(hi)} else: none)'

def cell_css():
    """CSS for the per-latch-cell registers (the cell holds the latched code in --v)"""
    return '\n'.join([
        '@property --cv { syntax: "<integer>"; inherits: true; initial-value: 32; }',
        '@property --ccl { syntax: "<integer>"; inherits: true; initial-value: 0; }',
        f'.row i {{ --cv: max(32, var(--v)); --ccl: {ccl_css("var(--cv)")}; }}',
        f'.cr {{ position: absolute; left: 0; top: 0; width: 1px; height: {HC}px; overflow: hidden; visibility: hidden; display: block; }}',
        '.cr > b { position: absolute; left: 0; width: 1px; height: 1px; display: block; }',
        '.cr > .c1 { top: calc(var(--cv) * 1px); } .cr > .c2 { top: calc(var(--ccl) * 1px); }',
        f'.cr > .cp {{ position: static; height: {HC}px; }}'])

def cell_html(k, j):
    return (f'<b class="cr"><b class="c1" style="view-timeline-name: --ch{k}_{j}"></b>'
            f'<b class="c2" style="view-timeline-name: --cl{k}_{j}"></b><b class="cp"></b></b>')

def build(lib, L, P, TMAX, code_base=4608, data_base=4096, short=True, static_src=None):
    initw = lib.get('init', 5120)
    code_cells = initw - 1 - code_base; data_cells = R.SDATA; ishift = initw - data_base
    lst = [n for n in D.LEX_STATE if n != 'pp']
    pst, tabs = D.parse_state_names(), D.table_names(); tset = set(tabs)
    progs = [(k, D.Prog(data_base, code_base, lib['print'], lib['puts'], *k)) for k in D.variant_keys()]
    progs = [(k, p) for k, p in progs if not (isK(p.x.cur['err']) and p.x.cur['err'].v != 0)]
    lexes = [D.LexProg(data_base, cset=cs) for cs in CLASSES]
    NLP = max(p.nlports for _, p in progs)
    E = R.EMAX
    N = Names(short)
    css = []
    # ================= character chain
    # slots: (k, j) columns, ('nl', k) newlines, ('nul',) x 2
    slots = []
    for k in range(L):
        slots += [('col', k, j) for j in range(P)] + [('nl', k)]
    slots += [('nul',), ('nul',)]
    NC = len(slots)
    css.append('@keyframes kc { from { --c: 128; } to { --c: -1; } } @keyframes kcn { from { --cn: 128; } to { --cn: -1; } }'
               ' @keyframes kcl { from { --ncl: 128; } to { --ncl: -1; } }')
    for n in ('c', 'cn', 'ncl'): N.add(n, False)
    css.append('#cc { display: none; contain: strict; position: relative; height: 0; } body:has(#run:checked) #cc { display: block; }'
               ' #cc div { height: 0; }'
               ' .lvA, .lvB, #cc { animation-duration: auto; animation-timing-function: linear; animation-fill-mode: both; --c: 32; --cn: 32; --ncl: 0; }')
    # lexer variants per class (picked by the parent's --ncl), per parity
    lex_sel = {}
    for ci, lp in enumerate(lexes):
        lout = set(lp.out)
        for rd in 'AB':
            wr = OTH[rd]
            def ref(kind, n, rd=rd, lout=lout, ci=ci):
                if kind == 'S': return f'var(--s-{n}-{rd})'
                if kind == 'I': return '0' if n == 'ptk' else f'var(--{n})'
                if n in lout: return f'var(--l-{n})'
                return f'var(--l{ci}-{n})'
            decl = []
            for n, node in lp.x.temps:
                if n in lout: nm = f'l-{n}'; N.add(nm, True)
                else: nm = f'l{ci}-{n}'; N.add(nm, False)
                decl.append(f'--{nm}: {tocss(node, ref)};')
            decl += [f'--s-{n}-{wr}: {tocss(lp.x.cur[n], ref)};' for n in lst]
            body = ' '.join(decl)
            if ci == CL_NL: css.append(f'.kn{rd} {{ {body} }}')
            elif ci == CL_NUL: css.append(f'.kz{rd} {{ {body} }}')
            else: css.append(f'@container style(--ncl: {ci}) {{ .kc{rd} {{ {body} }} }}')
    for n in lst + ['nt']:
        for x in 'AB': N.add(f's-{n}-{x}', True)
    for rd in 'AB':
        wr = OTH[rd]
        css.append(f'.lv{rd} {{ --s-nt-{wr}: calc(var(--s-nt-{rd}) + var(--l-o_tkany)); --l-tix: var(--s-nt-{rd});'
                   f' --l-tix-h: round(down, var(--s-nt-{rd}) / 32); }}')
    N.add('l-tix', True); N.add('l-tix-h', True)
    # token registers
    css.append(f'.tr {{ display: none; position: relative; width: 1px; height: {HT}px; overflow: hidden; visibility: hidden; }}'
               f' .tr > b {{ position: absolute; left: 0; width: 1px; height: 1px; display: block; }} .tr > .tp {{ position: static; height: {HT}px; }}'
               ' @container style(--l-o_tkany: 1) { .tr { display: block; } }')
    for f, src in TOKF:
        css.append(f'.tr > .t{f} {{ top: calc(var(--l-o_{src}) * 1px); view-timeline-name: {mux_name("l-tix", TMAX, lambda t, f=f: f"--tk{t}{f}")}; }}')
    # string bytes: in-flow words
    N.add('l-o_sa-h', False)
    css.append(f'.ovs {{ display: none; height: 0; }} @container style(--l-o_sv: 1) {{ .ovs {{ display: block; --l-o_sa-h: round(down, (var(--l-o_sa) - {data_cells}) / 32);'
               f' anchor-name: {mux_shift("l-o_sa", data_cells, data_cells)}; width: calc((var(--l-o_sw) + {WOFF}) * 1px); }} }}')
    init = {f's-{n}-A': v for n, v in D.initial_lex(data_base).items() if n != 'pp'}
    init['s-nt-A'] = 0
    ch_html = []
    def tl_of(slot, kind):
        if slot[0] != 'col': return None
        return f'--{kind}{slot[1]}_{slot[2]}'
    for i, sl in enumerate(slots):
        x = 'A' if i % 2 == 0 else 'B'
        kcls = {'col': 'kc', 'nl': 'kn', 'nul': 'kz'}[sl[0]] + x
        nxt = slots[i + 1] if i + 1 < NC else ('nul',)
        names, tls, st = [], [], []
        if sl[0] == 'col': names.append('kc'); tls.append(tl_of(sl, 'ch'))
        else: st.append(f'--c: {10 if sl[0] == "nl" else 0}')
        if nxt[0] == 'col': names += ['kcn', 'kcl']; tls += [tl_of(nxt, 'ch'), tl_of(nxt, 'cl')]
        else: st.append(f'--cn: {10 if nxt[0] == "nl" else 0}; --ncl: {CL_NL if nxt[0] == "nl" else CL_NUL}')
        if names and static_src is None: st.append(f'animation-name: {", ".join(names)}; animation-timeline: {", ".join(tls)}')
        if static_src is not None:      # experiment: characters as inline constants instead of timelines
            cc = static_src[i]; cn_ = static_src[i + 1] if i + 1 < NC else 0
            st.append(f'--c: {cc}; --cn: {cn_}; --ncl: {next(ci for ci, cs in enumerate(CLASSES) if cn_ in cs)}')
        ch_html.append(f'<div class="lv{x} {kcls}" style="{"; ".join(st)}"><b class="ovs"></b>'
                       f'<div class="tr"><b class="tc"></b><b class="tv"></b><b class="th"></b><b class="tg"></b><b class="tp"></b></div>')
    root_st = ''
    if slots[0][0] == 'col': root_st = f'animation-name: kcl; animation-timeline: {tl_of(slots[0], "cl")}'
    if static_src is not None: root_st = f'--ncl: {next(ci for ci, cs in enumerate(CLASSES) if static_src[0] in cs)}'
    fo = OTH['A' if (NC - 1) % 2 == 0 else 'B']      # suffix written by the deepest character level
    css.append('#cc { ' + ' '.join(f'--{n}: {v};' for n, v in init.items()) + ' }')
    # ================= token chain
    css.append(f'#tcr {{ contain: strict; position: relative; height: 0; --ntf: var(--s-nt-{fo}); }} #tcr div {{ height: 0; }}')
    N.add('ntf', True)
    for f, src in TOKF:
        for y in 'AB':
            css.append(f'@keyframes k{f}{y} {{ from {{ --k-{src}-{y}: {HT}; }} to {{ --k-{src}-{y}: -1; }} }}')
            N.add(f'k-{src}-{y}', True)
    css.append('.tlA, .tlB { animation-duration: auto; animation-timing-function: linear; animation-fill-mode: both;'
               ' --tlive: clamp(0, var(--ntf) - var(--ti) + 1, 1); --tlast: calc(1 - min(1, abs(var(--ntf) - var(--ti))));'
               ' display: if(style(--tlive: 0): none; else: block); }')
    css.append('.tlA { --tcq: var(--k-tc-A); } .tlB { --tcq: var(--k-tc-B); }')
    for n, i in (('ti', False), ('tlive', False), ('tlast', True), ('tcq', False), ('vh', False)): N.add(n, i)
    # level 0: initial parser state
    css.append('.t0 { ' + ' '.join(f'--p-{n}-A: {v};' for n, v in D.initial_parse(data_base).items())
               + ' --s-bad-A: 0; --s-perr-A: 0; --s-nr-A: 0; --vh: 0; }')
    TOKIN = ['tv', 'th1', 'th2']
    for y in 'AB':
        yp = OTH[y]
        decl = [f'--x-{n}: var(--p-{n}-{yp});' for n in pst] + [f'--x-{n}: var(--k-{n}-{yp});' for n in TOKIN] + ['--x-tk: 0;']
        decl += [f'--p-{n}-{y}: var(--q-new-{n});' for n in pst]
        decl += [f'--q-o_v{s}: 0;' for s in range(E)] + ['--q-o_dv: 0;', '--q-ran: 0;'] + [f'--q-o_lv{k}: 0;' for k in range(NLP)]
        decl += ['--q-o_yw: 0;', '--q-o_fw: 0;'] + [f'--q-{n}-{y}: var(--q-{n});' for n in sorted(DELAYED_V)]
        has = f'min(1, var(--k-tc-{yp}))'
        decl += [f'--s-bad-{y}: max(var(--s-bad-{yp}), {has} * (1 - var(--q-ran)));',
                 f'--s-nr-{y}: max(var(--s-nr-{yp}), 1 - {has});',
                 f'--s-perr-{y}: if(style(--s-perr-{yp}: 0): var(--p-err-{y}); else: var(--s-perr-{yp}));',
                 f'--stop: max(var(--s-bad-{y}), var(--s-nr-{y}), min(1, var(--s-perr-{y})));',
                 f'--vh: calc(var(--p-mode-{y}) + var(--stop) * (127 - var(--p-mode-{y})));']
        css.append(f'.tp{y} {{ ' + ' '.join(decl) + ' }')
        for xx in ('bad', 'perr', 'nr'): N.add(f's-{xx}-{y}', True)
        for n in DELAYED_V: N.add(f'q-{n}-{y}', True)
    N.add('stop', False)
    for n in ['q-ran', 'q-o_dv'] + [f'q-o_v{s}' for s in range(E)] + [f'q-o_lv{k}' for k in range(NLP)]:
        N.add(n, n.startswith('q-o'))
    for n in pst:
        N.add(f'x-{n}', False); N.add(f'q-new-{n}', False)
        for x in 'AB': N.add(f'p-{n}-{x}', True)
    for n in TOKIN + ['tk']: N.add(f'x-{n}', False)
    # delayed table writes
    for y in 'AB':
        yp = OTH[y]
        for pre, nm, fl, cnt in (('y', ('sh1_', 'sh2_', 'sk_'), ('h1', 'h2', 'k'), R.NS), ('f', ('fh1_', 'fh2_', 'fl_'), ('h1', 'h2', 'l'), R.NF)):
            for j in range(cnt):
                css.append(f'@container style(--q-o_{pre}w: 1) and style(--q-o_{pre}i: {j}) {{ .tp{y} {{ '
                           + ' '.join(f'--t-{a}{j}: var(--q-o_{pre}{b}-{yp});' for a, b in zip(nm, fl)) + ' } }')
    for n in tabs: N.add(f't-{n}', True)
    # parser variants
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
        tcond = f'style(--tcq: {tcs[0]})' if len(tcs) == 1 else '(' + ' or '.join(f'style(--tcq: {t})' for t in tcs) + ')'
        css.append(f'@container style(--vh: {key[0]}) and {tcond} {{ .tpA, .tpB {{ ' + ' '.join(decl) + ' } }')
    # code / data overlays (fixed, contained by #tcr)
    cb0 = code_base - 4096
    css.append('.ov, .ovd { position: fixed; top: 0; left: 0; height: 1px; visibility: hidden; display: none; }')
    for s in range(E):
        a = f'q-o_a{s}'; N.add(f'{a}-h', False)
        body = (f'display: block; --{a}-h: round(down, (var(--{a}) - {cb0}) / 32);'
                f' anchor-name: {mux_shift(a, code_cells, cb0)}; --ln: {mux_lab(f"q-o_l{s}", R.NL)};'
                f' width: calc((var(--q-o_w{s}) + {WOFF}) * 1px + anchor-size(var(--ln) width, 0px));')
        css.append(f'@container style(--q-o_v{s}: 1) {{ .ov.k{s} {{ {body} }} }}')
    N.add('q-o_da-h', False)
    css.append(f'@container style(--q-o_dv: 1) {{ .ovd {{ display: block; --q-o_da-h: round(down, var(--q-o_da) / 32);'
               f' anchor-name: {mux_shift("q-o_da", data_cells, 0, ishift)}; width: calc((var(--q-o_dw) + {WOFF}) * 1px); }} }}')
    css.append('.lp { display: none; height: 0; }')
    for k in range(NLP):
        css.append(f'@container style(--q-o_lv{k}: 1) {{ .lp{k} {{ display: block; anchor-name: {mux_lab(f"q-o_lj{k}", R.NL)};'
                   f' width: calc(max(0, var(--q-o_lx{k})) * 1px); }} }}')
    # final group on the last live level
    css.append('.fin { display: if(style(--tlast: 1): block; else: none); }')
    for y in 'AB':
        err = (f'if(style(--s-perr-{y}: 0): max(var(--s-bad-{y}) * 99, clamp(0, var(--p-cp-{y}) - {code_cells}, 1) * 62);'
               f' else: var(--s-perr-{y}))')
        css.append(f'.tl{y} > .fin {{ --e: {err}; --done: calc(1 - var(--s-nr-{y})); --n: var(--p-cp-{y}); --dpf: var(--p-dp-{y}); }}')
    css.append(f'.fin > .ovn {{ position: fixed; top: 0; left: 0; height: 1px; visibility: hidden; anchor-name: --c{initw - 1 - data_base};'
               f' width: calc((var(--dpf) - {data_base} + {WOFF}) * 1px); }}'
               ' .fin > .dn { display: block; height: 0; anchor-name: --ccdone; width: calc(var(--done) * (1 - min(1, var(--e))) * 1px); }'
               ' .fin > .di { display: block; height: 0; anchor-name: --ccinfo; width: calc((var(--done) + 2 * var(--e) + 1024 * var(--n)) * 1px); }')
    css.append(f'#tcr > .big {{ display: block; height: 0; anchor-name: --cctoo; width: calc(clamp(0, var(--ntf) - {TMAX}, 1) * 1px); }}')
    for n in ('e', 'done', 'n', 'dpf'): N.add(n, False)
    # html
    oslots = (''.join(f'<b class="ov k{k}"></b>' for k in range(E)) + '<b class="ovd"></b>'
              + ''.join(f'<b class="lp lp{k}"></b>' for k in range(NLP)) + '<div class="fin"><b class="ovn"></b><b class="dn"></b><b class="di"></b></div>')
    tl_html = []
    for t in range(TMAX + 1):
        y = 'A' if t % 2 == 0 else 'B'
        cls = f'tl{y}' + (' t0' if t == 0 else f' tp{y}')
        tl_html.append(f'<div class="{cls}" style="--ti: {t}; animation-name: {", ".join(f"k{f}{y}" for f, _ in TOKF)};'
                       f' animation-timeline: {", ".join(f"--tk{t}{f}" for f, _ in TOKF)}">{oslots}')
    tok = f'<div id="tcr"><b class="big"></b>{"".join(tl_html)}{"</div>" * (TMAX + 1)}</div>'
    body = f'<div id="cc" style="{root_st}">{"".join(ch_html)}{tok}{"</div>" * NC}</div>'
    timelines = ([f'--ch{k}_{j}' for k in range(L) for j in range(P)] + [f'--cl{k}_{j}' for k in range(L) for j in range(P)]
                 + [f'--tk{t}{f}' for t in range(TMAX + 1) for f, _ in TOKF])
    css_text = N.rename('\n'.join(N.props() + css))
    info = dict(char_levels=NC, token_levels=TMAX + 1, variants=len(progs), lports=NLP, css_bytes=len(css_text))
    return css_text, N.rename(body), timelines, info

def padded_source(text, L, P):
    """what the chain sees for a given editor text"""
    lines = text.split('\n')
    out = []
    for k in range(L):
        ln = lines[k] if k < len(lines) else ''
        ln = ''.join(ch if 32 <= ord(ch) < 127 else ' ' for ch in ln[:P])
        out.append(ln.ljust(P))
    return '\n'.join(out) + '\n'

if __name__ == '__main__':
    lib = json.load(open(sys.argv[1])); L, P, T = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    css, html, tls, info = build(lib, L, P, T)
    open(sys.argv[5] + '.css', 'w').write(css); open(sys.argv[5] + '.html', 'w').write(html)
    json.dump(tls, open(sys.argv[5] + '.tl.json', 'w'))
    print(info)
