"""cmp_dsl.py files... — run the DSL steps (Python evaluation) level by level against cc_ref; compare state, tables, code, data.
SPEC=1: use the mode/token-specialised parser variants (as the page selects them by container query)."""
import sys, json, time, os, collections
import os, sys; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]  # repo root
import cc_ref as R, cc_dsl as D
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
SPEC = os.environ.get('SPEC') == '1'
DB, CB = R.LAYOUT['data_base'], R.LAYOUT['code_base']
gen = D.Prog(DB, CB, lib)
variants = {}
def prog_for(mode, tk, tv):
    if not SPEC: return gen
    key = D.variant_key(mode, tk, tv)
    if key not in variants: variants[key] = D.Prog(DB, CB, lib, *key)
    return variants[key]

def ref_state(c):
    st = dict(lx=c.lx, q=c.q, lt=c.lt, tkc=c.tkc, acc=c.acc, h1=c.h1, h2=c.h2, p2=c.p2, sstart=c.sstart, dp=c.dp, mode=c.mode, pn1=c.pn[0], pn2=c.pn[1],
              sdp=c.sdp, pnl=c.pnl, inul=c.inul, icm=c.icm, kpos=c.kpos, lcon=c.lcon, nint=c.nint, pm=c.pm,
              osp=c.osp, csp=c.csp, nsym=c.nsym, nlet=c.nlet, nfn=c.nfn, nlab=c.nlab, cp=c.cp, curf=c.curf, cfn=c.cfn, nfdef=c.nfdef, nloc=c.nloc, npar=c.npar, fsym=c.fsym,
              pendLa=c.pendLa, err=c.err, nd=c.nd)
    for k in range(R.ODN): st[f'od{k}'] = c.od[k] if k < c.nd else None
    st['pk'] = c.pk if c.nd and c.desc(c.nd - 1) >= R.KBIG and c.desc(c.nd - 1) != R.TMP else None     # (a big constant or comparison on top)
    for k in range(R.OD): st[f'op{k}'] = c.ops[k] * 8192 + c.opv[k] if k < c.osp else None
    for k in range(R.CD):
        e = c.cs[k]; st[f'csA{k}'] = e[0] * 4096 + e[1] * 64 + e[2] if k < c.csp else None; st[f'csB{k}'] = e[5] * 4096 + e[3] * 64 + e[4] if k < c.csp else None
    for j in range(R.NS):
        e = c.sym[j]
        live = j < c.nsym or j >= R.NS - c.nlet                    # function / program level, or block-scoped
        for nm, v in ((f'sh1_{j}', e[0]), (f'sh2_{j}', e[1]), (f'sk_{j}', (e[4] + 4 * e[5]) * 65536 + e[2] * 16384 + e[3] + 8192)):
            st[nm] = v if live else None
    for k in range(R.NF):
        e = c.fn[k]
        for nm, v in ((f'fh1_{k}', e[0]), (f'fh2_{k}', e[1]), (f'fl_{k}', e[2] + 64 * e[3] + 256 * e[4])): st[nm] = v if k < c.nfn else None
    for k in range(R.NI):
        e = c.itab[k]
        for nm, v in ((f'ih1_{k}', e[0]), (f'ih2_{k}', e[1]), (f'iv_{k}', e[2])): st[nm] = v if k < c.nint else None
    return st
allok = True
lexp = D.LexProg(DB)
if SPEC:                                         # class-specialised lexers, as the page picks them (ccpage5.CLASSES)
    import ccpage5 as C5
    lexes = [D.LexProg(DB, cset=cs) for cs in C5.CLASSES]
    def lex_for(c): return lexes[next(i for i, cs in enumerate(C5.CLASSES) if c in cs)]
else:
    def lex_for(c): return lexp
if __name__ == '__main__': print(f'lexer: {len(lexp.x.temps)} temps; parser: {len(gen.x.temps)} temps')
work = 0; steps = 0
def check(text):
    """run the DSL level by level on one source text against cc_ref -> (ok, detail)"""
    global work, steps
    src = [ord(ch) for ch in text] + [0, 0]
    ref = R.Compiler(DB, CB, lib)
    ls = D.initial_lex(DB); ps = D.initial_parse(DB); tab = {n: 0 for n in D.table_names()}; lab = {}; code = {}; data = {}
    prev = dict(o_tkany=0); pw = None
    for i in range(len(src)):
        c, cn = src[i], (src[i + 1] if i + 1 < len(src) else 0)
        if pw:                                   # delayed table writes from the previous level
            for pre, fl, last in (('y', ('sh1_', 'sh2_', 'sk_'), 'k'), ('f', ('fh1_', 'fh2_', 'fl_'), 'l'), ('i', ('ih1_', 'ih2_', 'iv_'), 'v')):
                if pw[f'o_{pre}w']:
                    j = pw[f'o_{pre}i']
                    for nm, fld in zip(fl, ('h1', 'h2', last)): tab[f'{nm}{j}'] = pw[f'o_{pre}{fld}']
            pw = None
        if prev['o_tkany']:
            pg = prog_for(ps['mode'], prev['o_tk'], prev['o_tv']) if ps['err'] == 0 else None
            if pg is not None:
                env = {('S', n): v for n, v in ps.items()}
                for k in ('tk', 'tv', 'th1', 'th2'): env[('I', k)] = prev['o_' + k]
                for n, v in tab.items(): env[('I', n)] = v
                ps, e = pg.x.run_python(env); e = collections.defaultdict(int, e); work += len(pg.x.temps); steps += 1
                for s in range(R.EMAX):
                    if e[('T', f'o_v{s}')]:
                        a = e[('T', f'o_a{s}')] + DB; l, m = e[('T', f'o_l{s}')], e[('T', f'o_m{s}')]
                        code[a] = (e[('T', f'o_w{s}')], l if l >= 0 else None, 1)
                        code[a + 1] = (e[('T', f'o_x{s}')], e[('T', f'o_f{s}')] if m else None, m)
                if e[('T', 'o_dv')]: data[e[('T', 'o_da')] + DB] = e[('T', 'o_dw')]
                for k in range(pg.nlports):
                    if e[('T', f'o_lv{k}')]: lab[e[('T', f'o_lj{k}')]] = e[('T', f'o_lx{k}')]
                pw = collections.defaultdict(int, {n: e[('T', n)] for n in pg.out})
        env = {('S', n): v for n, v in ls.items()}; env[('I', 'c')] = c; env[('I', 'cn')] = cn; env[('I', 'ptk')] = prev['o_tkany']
        lx_ = lex_for(c); ls, e = lx_.x.run_python(env)
        prev = {n: e[('T', n)] for n in lx_.out}
        if prev['o_sv']: data[prev['o_sa'] + DB] = prev['o_sw']
    s0 = [ord(ch) for ch in text] + [0]
    for i in range(len(s0)): ref.char(s0[i], s0[i + 1] if i + 1 < len(s0) else 0)
    rs = ref_state(ref); st = dict(ps); st.update(tab); st.update(ls)
    diff = [k for k, v in rs.items() if v is not None and st.get(k) != v]
    rlab = {j: v for j, v in enumerate(ref.lab) if v != -1}
    rcode = {a: (w, l, m if l is not None else 0) for a, (w, l, m) in ref.words_ir().items()}
    code = {a: (w, l, m if l is not None else 0) for a, (w, l, m) in code.items()}
    lab = {j: v for j, v in lab.items() if j < R.NL}   # (labels past NL exist only after error 20)
    ok = not diff and code == rcode and data == ref.data and lab == rlab
    return ok, ('OK' if ok else f'MISMATCH {diff[:5]} code-eq {code == rcode} data-eq {data == ref.data} lab-eq {lab == rlab}')
if __name__ == '__main__':                       # (tests/fuzz/fuzz.py imports check())
    from par import pmap                         # one program per worker process; the counts come back with it
    def one(f):
        w, s, v = work, steps, set(variants); ok, msg = check(open(f).read().rstrip('\n') + '\n')
        return ok, msg, work - w, steps - s, set(variants) - v
    tw = ts = 0; used = set()
    for f, (ok, msg, w, s, v) in zip(sys.argv[1:], pmap(one, sys.argv[1:])):
        allok &= ok; tw += w; ts += s; used |= v
        print(f, msg)
    print(f'parser steps {ts}, temps evaluated {tw} ({tw // max(ts, 1)}/step); variants {len(used)}')
    print('ALL OK' if allok else 'FAILURES')
