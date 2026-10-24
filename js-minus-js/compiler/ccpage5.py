#!/usr/bin/env python3
"""ccpage5.py — the compiler as CSS for TYPED input: a character chain and a token chain.

The source is read from the editor by the scan readback (ui_rb.py: one latch cell per line x column). Each latch
cell carries a tiny view-timeline register --ch<k>_<j> (its code), so any element can animate a property from it.
Slots: L lines x (P columns + newline), then one NUL; a column past the end of its line reads as a space.

Character chain (#cc inside #ccw; shown once the editor's scan says the text is complete, i.e. one sweep after Run):
  - one source element per line (.ls) animates the line's P codes into --lc<j> (names reused by every line); each
    level reads --c / --cn from its line's source and computes --ncl, the class of the next character. A line's source
    opens at the previous line's newline level, so that level's --cn is the line's first character.
  - the lexer is specialised per character class and picked by the parent's --ncl (9 small rules, class selectors).
  - a level that completes a token shows its token register .tr: a scroller whose four subjects are named
    --tk<t>c/v/h/g (t = tokens so far, chosen with an if() mux) and placed at tc / tv / th1 / th2 px.
  - string bytes become in-flow words (.ovs) named after their RAM cell.
  - levels are display: contents (XHTML: no 512-element nesting limit, no deep layout recursion).
Token chain (#tcr, nested inside the deepest character level; levels past the token count are display: none):
  - one source element per 32 tokens animates their four values (names alternate by group parity).
  - level t+1 runs the parser on token t, picking the variant for (mode, token code) with
    @container style(--vh: m) and style(--tcq: tc) on its parent; variants share one pool of temp names.
  - symbol/function tables: delayed writes; labels: in-flow anchors; code words: fixed overlays inside #tcr
    (contain: strict), anchor-name --c<RAM index>, two per instruction slot: word0 adds its label (a jump target, or the
    function's frame label for a temp in A), word1 the frame label times its multiplier (1024 for a temp in B, 1 in C).
  - the last level shows .fin: the globals' count word, and two in-flow anchors the CPU page reads:
    --ccdone (width 1 when compiled without error) and --ccinfo (width = done + 2*err + 1024*words).
"""
import sys, json, re, os
from dsl import css2 as tocss, isK, S
import cc_dsl as D, cc_ref as R
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'py'))
import csslabel as lbl     # section and group comments in the output (../../shared/README.md#labels-in-generated-css)

WOFF = 1 << 20
BSTRW = sorted(R.BSTRW.items())        # the built-in strings' words (cc_ref BSTRS; RAM holds the zeros)
OTH = {'A': 'B', 'B': 'A'}
DELAYED_V = {f'o_{pre}{f}' for pre, last in (('y', 'k'), ('f', 'l'), ('i', 'v')) for f in ('h1', 'h2', last)}   # read by var() one level down
PORTS = ['o_yw', 'o_yi', 'o_yh1', 'o_yh2', 'o_yk', 'o_fw', 'o_fi', 'o_fh1', 'o_fh2', 'o_fl', 'o_iw', 'o_ii', 'o_ih1', 'o_ih2', 'o_iv']

def mux_shift(prop, n, base, shift=0):
    """--c<v + shift> for v in [base, base+n): prop holds v, prop-h holds (v - base) // 32; shift may be a function of v"""
    hi = []
    sh = shift if callable(shift) else (lambda v: shift)
    for h in range((n + 31) // 32):
        lo = ' '.join(f'style(--{prop}: {base + h * 32 + l}): --c{base + h * 32 + l + sh(base + h * 32 + l)};' for l in range(32) if h * 32 + l < n)
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


PR = set(range(32, 127))
CLASSES = [{32}, D.ALPHA, D.DIGIT, {34}, {92}, {47}, PR - D.ALPHA - D.DIGIT - {32, 34, 92, 47}, {10}, {0}]
CL_NL, CL_NUL = 7, 8
HC = 128                 # character register height
HT = 1 << 20             # token register height
TOKF = [('c', 'tc'), ('v', 'tv'), ('h', 'th1'), ('g', 'th2')]

def ccl_css(prop):
    """class of the printable code held in the registered property prop (CSS expression)"""
    v = f'var(--{prop})'
    al = f'clamp(0, {v} - 64, 1) * clamp(0, 91 - {v}, 1) + clamp(0, {v} - 96, 1) * clamp(0, 123 - {v}, 1)'
    dg = f'clamp(0, {v} - 47, 1) * clamp(0, 58 - {v}, 1)'
    return (f'if(style(--{prop}: 32): 0; style(--{prop}: 34): 3; style(--{prop}: 92): 4; style(--{prop}: 47): 5; style(--{prop}: 95): 1; style(--{prop}: 36): 1;'
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
        '.row i { --cv: max(32, var(--lv)); }',
        f'.cr {{ position: absolute; left: 0; top: 0; width: 1px; height: {HC}px; overflow: hidden; visibility: hidden; display: block; }}',
        '.cr > b { position: absolute; left: 0; width: 1px; height: 1px; display: block; }',
        '.cr > .c1 { top: calc(var(--cv) * 1px); }',
        f'.cr > .cp {{ position: static; height: {HC}px; }}'])

def cell_html(k, j):
    return (f'<b class="cr"><b class="c1" style="view-timeline-name: --ch{k}_{j}"></b>'
            f'<b class="cp"></b></b>')

# A parser variant as the page uses it: its rule's declarations and the temp names they register. Building the variants
# is most of build()'s time (~70 ms each, ~1,000 of them), so worker processes build them (JOBS, default every CPU).
_vargs = None
def variant_rule(key):
    """-> None for a variant that only reports an error, else (key, label ports, is it a no-op, declarations,
    [(temp name, inherits)])"""
    data_base, code_base, lib = _vargs
    pg = D.Prog(data_base, code_base, lib, *key)
    if isK(pg.x.cur['err']) and pg.x.cur['err'].v != 0: return None
    pst, tset = D.parse_state_names(), set(D.table_names())
    X = pg.x; outs = set(pg.out)
    fixed = {'mode': pg.spec_mode, 'err': 0}     # a no-op: changes nothing (a newline token where it means nothing)
    noop = not pg.out and all(X.cur[n] == S(n) or (n in fixed and isK(X.cur[n], fixed[n])) for n in pst)
    pool = {}
    for n, _ in X.temps:
        pool[n] = f'q-{n}' if n in outs else f'qp{sum(1 for v in pool.values() if v.startswith("qp"))}'
    def pref(kind, n):
        if kind == 'S': return f'var(--x-{n})'
        if kind == 'I': return f'var(--t-{n})' if n in tset else f'var(--x-{n})'
        return f'var(--{pool[n]})'
    decl = [f'--{pool[n]}: {tocss(node, pref)};' for n, node in X.temps]
    decl += [f'--q-new-{n}: {tocss(X.cur[n], pref)};' for n in pst] + ['--q-ran: 1;']
    return key, pg.nlports, noop, ' '.join(decl), [(pool[n], n in outs and n not in PORTS) for n, _ in X.temps]

def variant_rules(data_base, code_base, lib):
    global _vargs
    _vargs = (data_base, code_base, lib); keys = D.variant_keys()
    n = min(int(os.environ.get('JOBS') or os.cpu_count() or 1), len(keys))
    if n <= 1: return [r for r in map(variant_rule, keys) if r]
    import multiprocessing as mp
    with mp.get_context('fork').Pool(n) as pool: return [r for r in pool.map(variant_rule, keys, chunksize=4) if r]

# build()'s output is a function of its arguments (of the ROM, its entry points and init) and the sources it imports:
# build/ccpage5/<hash>.json keeps the last few, so a page whose compiler didn't change (a machine change, the L3 page
# after the editor page) skips the chain. CCCACHE=0 always builds.
def build(lib, L, P, TMAX, code_base=None, data_base=None, short=True):
    import hashlib
    lib = {k: lib[k] for k in ('init', 'entries') if k in lib}      # all the chain reads of the ROM
    h = hashlib.sha256(json.dumps([lib, L, P, TMAX, code_base, data_base, short, D.INLINE, D.SPEC_LEVEL], sort_keys=True).encode())
    here = os.path.dirname(os.path.abspath(__file__))
    D.sources_hash(h, sys.modules[__name__])
    d = os.path.join(here, '..', 'build', 'ccpage5'); path = os.path.join(d, h.hexdigest()[:16] + '.json')
    if os.environ.get('CCCACHE', '1') == '1' and os.path.exists(path):
        os.utime(path); return tuple(json.load(open(path)))
    r = build_chain(lib, L, P, TMAX, code_base, data_base, short)
    os.makedirs(d, exist_ok=True); tmp = f'{path}.{os.getpid()}'
    json.dump(r, open(tmp, 'w')); os.replace(tmp, path)
    for old in sorted((f for f in os.listdir(d) if f.endswith('.json')), key=lambda f: -os.path.getmtime(os.path.join(d, f)))[4:]:
        os.remove(os.path.join(d, old))
    return r

def build_chain(lib, L, P, TMAX, code_base=None, data_base=None, short=True):
    code_base = R.LAYOUT['code_base'] if code_base is None else code_base; data_base = R.LAYOUT['data_base'] if data_base is None else data_base
    initw = lib.get('init', R.LAYOUT['init'])
    code_cells = initw - 1 - code_base; data_cells = R.SDATA; ishift = initw - data_base
    lst = [n for n in D.LEX_STATE if n != 'pp']
    pst, tabs = D.parse_state_names(), D.table_names(); tset = set(tabs)
    progs = variant_rules(data_base, code_base, lib)
    lexes = [D.LexProg(data_base, cset=cs) for cs in CLASSES]
    NLP = max(r[1] for r in progs)
    E = R.EMAX
    N = Names(short)
    css = []
    # ================= character chain
    # slots: (k, j) columns, ('nl', k) newlines, ('nul',) x 2
    slots = []
    for k in range(L):
        slots += [('col', k, j) for j in range(P)] + [('nl', k)]
    slots += [('nul',)]              # the parser chain is separate, so one end-of-input level is enough
    NC = len(slots)
    # every character's code and class are animated on the chain root (#cc) from its register; levels read them by var().
    # (an animation on each level made every timeline update restyle the chain: ~3 ms per level)
    # one source element per line, nested in the chain just before the line's first level; it animates the line's
    # P codes and classes into --lc<j> / --ll<j> (names reused by every line, so each level inherits only one line's)
    css.append(lbl.group('Character chain: line sources', f'each line\'s source animates its {P} character codes from the editor scan\'s registers'))
    for j in range(P):
        css.append(f'@keyframes ka{j} {{ from {{ --lc{j}: {HC}; }} to {{ --lc{j}: -1; }} }}'
                   )
        N.reg[f'lc{j}'] = True
    css.append(f'.ls {{ animation-duration: auto; animation-timing-function: linear; animation-fill-mode: both;'
               f' animation-name: {", ".join(f"ka{j}" for j in range(P))}; --ncl: {ccl_css("lc0")};'
               # base values: a line whose probe is hidden (past the end of the text) has no registers, so its
               # animations are inactive; it must read as spaces, not inherit the previous line's characters
               + ''.join(f' --lc{j}: 32;' for j in range(P)) + ' }')
    # every level: the class of the next character, for its child's lexer dispatch (static slots set it inline)
    css.append(f'.lvA, .lvB {{ --ncl: {ccl_css("cn")}; }}')
    for n in ('c', 'cn', 'ncl'): N.add(n, False)
    # the chain exists only once the editor's scan says the text is complete (--rbrdT, raised one sweep after Run)
    # (the sources keep running: an animation created paused does not reliably take its timeline's value, and a pause
    # driven by an animated flag is ignored, since Blink reads animation-play-state from the base style)
    # (a pause driven by an animated flag does not work: Blink reads animation-play-state from the base style)
    css.append(lbl.group('Chain switch', 'the chain exists only once the editor scan is complete'))
    css.append('@property --ccgo { syntax: "<integer>"; inherits: true; initial-value: 0; } @keyframes kccgo { from { --ccgo: 4096; } to { --ccgo: -1; } }'
               ' #ccw { display: contents; animation: kccgo auto linear both; animation-timeline: --rbrdT; --repl: 0; --x-repl: var(--repl); }'
               ' #cc { display: if(style(--ccgo: 1): block; else: none); contain: strict; position: relative; height: 0; }'
               ' .ls, .lvA, .lvB, .gs0, .gs1 { display: contents; }'
               )
    # lexer variants per class (picked by the parent's --ncl), per parity
    css.append(lbl.group('Lexer: one rule per character class and level parity', 'picked by the class of the level\'s character'))
    lex_sel = {}
    for ci, lp in enumerate(lexes):
        lout = set(lp.out)
        for rd in 'AB':
            wr = OTH[rd]
            # temps share one pool of names across the class variants (only one applies per level): every
            # registered property costs something on each animated element, so keep their number small
            pool = {}
            for n, _ in lp.x.temps:
                pool[n] = f'l-{n}' if n in lout else f'lp{len(pool)}'
            def ref(kind, n, rd=rd, pool=pool):
                if kind == 'S': return f'var(--s-{n}-{rd})'
                if kind == 'I': return '0' if n == 'ptk' else f'var(--{n})'
                return f'var(--{pool[n]})'
            decl = []
            for n, node in lp.x.temps:
                N.add(pool[n], n in lout)
                decl.append(f'--{pool[n]}: {tocss(node, ref)};')
            decl += [f'--s-{n}-{wr}: {tocss(lp.x.cur[n], ref)};' for n in lst]
            body = ' '.join(decl)
            if ci == CL_NL: css.append(f'.kn{rd} {{ {body} }}')
            elif ci == CL_NUL: css.append(f'.kz{rd} {{ {body} }}')
            else: css.append(f'@container style(--ncl: {ci}) {{ .kc{rd} {{ {body} }} }}')
    for n in lst + ['nt']:
        for x in 'AB': N.add(f's-{n}-{x}', True)
    css.append(lbl.group('Character levels: token count and index'))
    for rd in 'AB':
        wr = OTH[rd]
        css.append(f'.lv{rd} {{ --s-nt-{wr}: calc(var(--s-nt-{rd}) + var(--l-o_tkany)); --l-tix: var(--s-nt-{rd});'
                   f' --l-tix-h: round(down, var(--s-nt-{rd}) / 32); }}')
    N.add('l-tix', True); N.add('l-tix-h', True)
    # token registers
    css.append(lbl.group('Token registers', 'each finished token is written into view-timeline registers the token chain reads'))
    css.append(f'.tr {{ display: none; position: absolute; top: 0; left: 0; width: 1px; height: {HT}px; overflow: hidden; visibility: hidden; }}'
               f' .tr > b {{ position: absolute; left: 0; width: 1px; height: 1px; display: block; }} .tr > .tp {{ position: static; height: {HT}px; }}'
               ' @container style(--l-o_tkany: 1) { .tr { display: block; } }')
    for f, src in TOKF:
        css.append(f'.tr > .t{f} {{ top: calc(var(--l-o_{src}) * 1px); view-timeline-name: {mux_name("l-tix", TMAX, lambda t, f=f: f"--tk{t}{f}")}; }}')
    # string bytes: in-flow words
    css.append(lbl.group('String bytes: in-flow words'))
    N.add('l-o_sa-h', False)
    css.append(f'.ovs {{ display: none; height: 0; }} @container style(--l-o_sv: 1) {{ .ovs {{ display: block; --l-o_sa-h: round(down, (var(--l-o_sa) - {data_cells}) / 32);'
               f' anchor-name: {mux_shift("l-o_sa", R.LAYOUT['str_size'], data_cells)}; width: calc((var(--l-o_sw) + {WOFF}) * 1px); }} }}')
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
        st = []
        if sl[0] == 'col': st.append(f'--c: var(--lc{sl[2]})')
        else: st.append(f'--c: {10 if sl[0] == "nl" else 0}')
        # the line a level reads (the lexer's lnum: a T_NL's line), inherited down the chain from a line's first level and its newline's
        if sl[0] == 'nl' or (sl[0] == 'col' and sl[2] == 0): st.append(f'--lnum: {sl[1]}')
        if nxt[0] == 'col': st.append(f'--cn: var(--lc{nxt[2]})')
        else: st.append(f'--cn: {10 if nxt[0] == "nl" else 0}; --ncl: {CL_NL if nxt[0] == "nl" else CL_NUL}')
        # a line's source opens just before the previous line's newline level, whose --cn must be this line's first
        # character (the lexer's lookahead at a newline decides semicolon insertion; that level's own --c is 10)
        nk = 0 if sl == ('col', 0, 0) else sl[1] + 1 if sl[0] == 'nl' and sl[1] + 1 < L else None
        if nk is not None:
            ch_html.append(f'<div class="ls" style="animation-timeline: {", ".join(f"--ch{nk}_{j}" for j in range(P))}">')
        ch_html.append(f'<div class="lv{x} {kcls}" style="{"; ".join(st)}"><b class="ovs"></b>'
                       f'<div class="tr"><b class="tc"></b><b class="tv"></b><b class="th"></b><b class="tg"></b><b class="tp"></b></div>')
    root_st = ''
    fo = OTH['A' if (NC - 1) % 2 == 0 else 'B']      # suffix written by the deepest character level
    css.append(lbl.group('Lexer start state (#cc)'))
    css.append('#cc { ' + ' '.join(f'--{n}: {v};' for n, v in init.items()) + ' }')
    # ================= token chain
    css.append(lbl.group('Token chain: group sources', 'one source per group of 32 tokens animates their fields from the token registers'))
    css.append(f'#tcr {{ contain: strict; position: relative; height: 0; --ntf: var(--s-nt-{fo}); --sdf: var(--s-sdp-{fo}); }}')
    N.add('ntf', True)
    # one source element per group of G tokens (names alternate by group parity, so the previous group's last
    # token stays visible to the first level of the next group). It also passes on what the next level's
    # container queries ask of its parent.
    G = 32
    for gp in '01':
        for i in range(G):
            for f, src in TOKF:
                css.append(f'@keyframes k{f}{gp}_{i} {{ from {{ --k{f}{gp}_{i}: {HT}; }} to {{ --k{f}{gp}_{i}: -1; }} }}')
                N.reg[f'k{f}{gp}_{i}'] = True
        css.append(f'.gs{gp} {{ animation-duration: auto; animation-timing-function: linear; animation-fill-mode: both;'
                   f' animation-name: {", ".join(f"k{f}{gp}_{i}" for i in range(G) for f, _ in TOKF)};'
                   + ''.join(f' --k{f}{gp}_{i}: 0;' for i in range(G) for f, _ in TOKF) +
                   f' --vh: inherit; --q-o_yw: inherit; --q-o_yi: inherit; --q-o_fw: inherit; --q-o_fi: inherit; --q-o_iw: inherit; --q-o_ii: inherit;'
                   f' --tcq: var(--kc{1 - int(gp)}_{G - 1}); }}')
    tref = lambda f, t: f'var(--k{f}{(t // G) % 2}_{t % G})'
    css.append('.tlA, .tlB {'
               ' --tlive: clamp(0, var(--ntf) - var(--ti) + 1, 1); --tlast: calc(1 - min(1, abs(var(--ntf) - var(--ti))));'
               ' display: if(style(--tlive: 0): none; else: contents); }')

    for n, i in (('ti', False), ('tlive', False), ('tlast', True), ('tcq', False), ('vh', False), ('has', False)): N.add(n, i)
    # level 0: initial parser state
    css.append(lbl.group('Parser: start state and the step on every token level'))
    css.append('.t0 { ' + ' '.join(f'--p-{n}-A: {v};' for n, v in D.initial_parse(data_base).items())
               + ' --s-bad-A: 0; --s-perr-A: 0; --s-nr-A: 0; --vh: 0; }')
    TOKIN = ['tv', 'th1', 'th2']
    for y in 'AB':
        yp = OTH[y]
        decl = [f'--x-{n}: var(--p-{n}-{yp});' for n in pst] + ['--x-tk: 0;']
        decl += [f'--p-{n}-{y}: var(--q-new-{n});' for n in pst]
        decl += [f'--q-o_v{s}: 0;' for s in range(E)] + ['--q-o_dv: 0;', '--q-ran: 0;'] + [f'--q-o_lv{k}: 0;' for k in range(NLP)]
        decl += ['--q-o_yw: 0;', '--q-o_fw: 0;', '--q-o_iw: 0;'] + [f'--q-{n}-{y}: var(--q-{n});' for n in sorted(DELAYED_V)]
        has = 'var(--has)'
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
    css.append(lbl.group('Parser: delayed table writes (names, functions, identifiers)'))
    for y in 'AB':
        yp = OTH[y]
        for pre, nm, fl, cnt in (('y', ('sh1_', 'sh2_', 'sk_'), ('h1', 'h2', 'k'), R.NS), ('f', ('fh1_', 'fh2_', 'fl_'), ('h1', 'h2', 'l'), R.NF),
                                 ('i', ('ih1_', 'ih2_', 'iv_'), ('h1', 'h2', 'v'), R.NI)):
            for j in range(cnt):
                css.append(f'@container style(--q-o_{pre}w: 1) and style(--q-o_{pre}i: {j}) {{ .tp{y} {{ '
                           + ' '.join(f'--t-{a}{j}: var(--q-o_{pre}{b}-{yp});' for a, b in zip(nm, fl)) + ' } }')
    for n in tabs: N.add(f't-{n}', True)
    # parser variants. A variant that changes nothing (a newline token where it means nothing) is folded into one
    # pass-through rule per token code, placed first so a mode-specific variant (later in the sheet) overrides it;
    # only when every reachable mode has a variant for that code (else a mode without one must stay 'bad').
    allm = set(range(R.NMODES)) - {R.S_ERR}
    noop_tc = []
    for tc in sorted({c for r in progs for c in D.key_tcodes(r[0])}):
        ks = [r for r in progs if D.key_tcodes(r[0]) == [tc]]
        if {r[0][0] for r in ks} >= allm and any(r[2] for r in ks): noop_tc.append(tc)
    css.append(lbl.group('Parser variants', 'one rule per parser mode and set of token codes; the first rules are the tokens that change nothing'))
    for tc in noop_tc:
        css.append(f'@container style(--tcq: {tc}) {{ .tpA, .tpB {{ ' + ' '.join(f'--q-new-{n}: var(--x-{n});' for n in pst) + ' --q-ran: 1; } }')
    progs = [r for r in progs if not (D.key_tcodes(r[0])[0] in noop_tc and len(D.key_tcodes(r[0])) == 1 and r[2])]
    # variants whose CSS is identical (a third of them: mostly modes that treat many punctuation tokens alike; and the
    # modes that only rename another, cc_ref.CMODES / S_ABODY, outside the tokens they handle) share one rule whose
    # condition lists all their modes and token codes. Every rule costs time on every token level whether it applies or
    # not (docs/BENCHMARKS.md §4c), so fewer rules is faster.
    rules = {}                                         # declarations -> {mode: token codes}, in first-seen order
    for key, _, _, decl, names in progs:
        for n, inh in names: N.add(n, inh)
        rules.setdefault(decl, {}).setdefault(key[0], []).extend(D.key_tcodes(key))
    def anyof(name, vs): return f'style(--{name}: {vs[0]})' if len(vs) == 1 else '(' + ' or '.join(f'style(--{name}: {v})' for v in vs) + ')'
    for body, bym in rules.items():
        byt = {}                                       # token codes -> the modes with exactly those
        for mode, tcs in bym.items(): byt.setdefault(tuple(tcs), []).append(mode)
        conds = [f'{anyof("vh", ms)} and {anyof("tcq", tcs)}' for tcs, ms in byt.items()]
        cond = conds[0] if len(conds) == 1 else ' or '.join(f'({c})' for c in conds)
        css.append(f'@container {cond} {{ .tpA, .tpB {{ {body} }} }}')
    # code / data overlays (fixed, contained by #tcr)
    css.append(lbl.group('Code and data overlays', 'each emitted word is an element anchored as its RAM cell'))
    cb0 = code_base - R.LAYOUT['rom_size']          # RAM index of the first code word (--c<index> names RAM cells)
    css.append('.ov, .ovd { position: fixed; top: 0; left: 0; height: 1px; visibility: hidden; display: none; }')
    for s in range(E):
        a = f'q-o_a{s}'; N.add(f'{a}-h', False)
        body = (f'display: block; --{a}-h: round(down, (var(--{a}) - {cb0}) / 32);'
                f' anchor-name: {mux_shift(a, code_cells, cb0)}; --ln: {mux_lab(f"q-o_l{s}", R.NL)};'
                f' width: calc((var(--q-o_w{s}) + {WOFF}) * 1px + anchor-size(var(--ln) width, 0px));')
        css.append(f'@container style(--q-o_v{s}: 1) {{ .ov.k{s} {{ {body} }} }}')
        body = (f'display: block; --{a}-h: round(down, (var(--{a}) - {cb0}) / 32);'
                f' anchor-name: {mux_shift(a, code_cells, cb0, 1)}; --ln: {mux_lab(f"q-o_f{s}", R.NL)};'
                f' width: calc((var(--q-o_x{s}) + {WOFF}) * 1px + var(--q-o_m{s}) * anchor-size(var(--ln) width, 0px));')
        css.append(f'@container style(--q-o_v{s}: 1) {{ .ov.j{s} {{ {body} }} }}')
    N.add('q-o_da-h', False)
    css.append(f'@container style(--q-o_dv: 1) {{ .ovd {{ display: block; --q-o_da-h: round(down, var(--q-o_da) / 32);'
               f' anchor-name: {mux_shift("q-o_da", data_cells + R.LAYOUT['str_size'], 0, lambda v: ishift if v < data_cells else 0)}; width: calc((var(--q-o_dw) + {WOFF}) * 1px); }} }}')
    css.append('.lp { display: none; height: 0; }')
    for k in range(NLP):
        css.append(f'@container style(--q-o_lv{k}: 1) {{ .lp{k} {{ display: block; anchor-name: {mux_lab(f"q-o_lj{k}", R.NL)};'
                   f' width: calc(max(0, var(--q-o_lx{k})) * 1px); }} }}')
    # final group on the last live level
    css.append(lbl.group('Result: error code, word count, done flag'))
    css.append('.fin { display: if(style(--tlast: 1): block; else: none); }')
    for y in 'AB':
        err = (f'if(style(--s-perr-{y}: 0): max(var(--s-bad-{y}) * 99, clamp(0, 2 * var(--p-cp-{y}) - {code_cells}, 1) * 62);'
               f' else: var(--s-perr-{y}))')
        css.append(f'.tl{y} > .fin {{ --e: {err}; --done: calc(1 - var(--s-nr-{y})); --n: calc(2 * var(--p-cp-{y})); --dpf: var(--p-dp-{y}); }}')
    css.append(f'.fin > .ovn {{ position: fixed; top: 0; left: 0; height: 1px; visibility: hidden; anchor-name: --c{initw - 1 - data_base};'
               f' width: calc((var(--dpf) + {WOFF}) * 1px); }}'
               # the string untag constant at data_base (the program never writes it)
               f' .fin > .ovk {{ position: fixed; top: 0; left: 0; height: 1px; visibility: hidden; anchor-name: --c0; width: {R.STRTAG + WOFF}px; }}'
               + ''.join(f' .fin > .sd{i} {{ position: fixed; top: 0; left: 0; height: 1px; visibility: hidden; anchor-name: --c{a - data_base}; width: {w + WOFF}px; }}' for i, (a, w) in enumerate(BSTRW))
               # the string area's end, for the runtime's key lookups
               + f' .fin > .ovt {{ position: fixed; top: 0; left: 0; height: 1px; visibility: hidden; anchor-name: --c{R.LAYOUT["strend"] - data_base}; width: calc((var(--sdf) + {WOFF}) * 1px); }}'
               + ' .fin > .dn { display: block; height: 0; anchor-name: --ccdone; width: calc(var(--done) * (1 - min(1, var(--e))) * 1px); }'
               ' .fin > .di { display: block; height: 0; anchor-name: --ccinfo; width: calc((var(--done) + 2 * var(--e) + 1024 * var(--n)) * 1px); }')
    css.append(f'#tcr > .big {{ display: block; height: 0; anchor-name: --cctoo; width: calc(clamp(0, var(--ntf) - {TMAX}, 1) * 1px); }}')
    for n in ('e', 'done', 'n', 'dpf', 'sdf'): N.add(n, True)
    # html
    oslots = (''.join(f'<b class="ov k{k}"></b><b class="ov j{k}"></b>' for k in range(E)) + '<b class="ovd"></b>'
              + ''.join(f'<b class="lp lp{k}"></b>' for k in range(NLP)) + '<div class="fin"><b class="ovn"></b><b class="ovk"></b><b class="ovt"></b>' + ''.join(f'<b class="sd{i}"></b>' for i in range(len(BSTRW))) + '<b class="dn"></b><b class="di"></b></div>')
    tl_html = []
    for t in range(TMAX + 1):
        y = 'A' if t % 2 == 0 else 'B'
        cls = f'tl{y}' + (' t0' if t == 0 else f' tp{y}')
        tin = '' if t == 0 else f' --x-tv: {tref("v", t - 1)}; --x-th1: {tref("h", t - 1)}; --x-th2: {tref("g", t - 1)}; --has: min(1, {tref("c", t - 1)});'
        if t % G == 0:
            g = t // G
            tl_html.append(f'<div class="gs{g % 2}" style="animation-timeline: {", ".join(f"--tk{g * G + i}{f}" for i in range(G) for f, _ in TOKF)}">')
        tl_html.append(f'<div class="{cls}" style="--ti: {t}; --tcq: {tref("c", t)};{tin}">{oslots}')
    tok = f'<div id="tcr"><b class="big"></b>{"".join(tl_html)}{"</div>" * (TMAX + 1 + (TMAX + G) // G)}</div>'
    body = f'<div id="ccw"><div id="cc" style="{root_st}">{"".join(ch_html)}{tok}{"</div>" * (NC + L)}</div></div>'
    timelines = ([f'--ch{k}_{j}' for k in range(L) for j in range(P)]
                 + [f'--tk{t}{f}' for t in range((TMAX // G + 1) * G) for f, _ in TOKF])
    css_text = N.rename('\n'.join([lbl.group('Registered properties')] + N.props() + css))
    info = dict(char_levels=NC, token_levels=TMAX + 1, variants=len(progs), rules=len(rules), noop_codes=noop_tc, lports=NLP, css_bytes=len(css_text))
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
