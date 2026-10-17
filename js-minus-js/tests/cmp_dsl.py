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
              osp=c.osp, csp=c.csp, nsym=c.nsym, nlet=c.nlet, nfn=c.nfn, nlab=c.nlab, cp=c.cp, curf=c.curf, cfn=c.cfn, nfdef=c.nfdef, lb=c.lb, nloc=c.nloc, npar=c.npar, fsym=c.fsym,
              pendLa=c.pendLa, err=c.err, arrstart=c.arrstart)
    for k in range(R.OD): st[f'op{k}'] = c.ops[k] * 8192 + c.opv[k] if k < c.osp else None
    for k in range(R.CD):
        e = c.cs[k]; st[f'csA{k}'] = e[0] * 4096 + e[1] * 64 + e[2] if k < c.csp else None; st[f'csB{k}'] = e[5] * 4096 + e[3] * 64 + e[4] if k < c.csp else None
    for j in range(R.NS):
        e = c.sym[j]
        live = j < c.nsym or j >= R.NS - c.nlet                    # function / program level, or block-scoped
        for nm, v in ((f'sh1_{j}', e[0]), (f'sh2_{j}', e[1]), (f'sk_{j}', (e[4] + 4 * e[5]) * 65536 + e[2] * 16384 + e[3] + 8192)):
            st[nm] = v if live and not (nm.startswith('sk') and e[3] < 0) else None
    for k in range(R.NF):
        e = c.fn[k]
        for nm, v in ((f'fh1_{k}', e[0]), (f'fh2_{k}', e[1]), (f'fl_{k}', e[2] + 64 * e[3])): st[nm] = v if k < c.nfn else None
    return st
allok = True
lexp = D.LexProg(DB)
if SPEC:                                         # class-specialised lexers, as the page picks them (ccpage5.CLASSES)
    import ccpage5 as C5
    lexes = [D.LexProg(DB, cset=cs) for cs in C5.CLASSES]
    def lex_for(c): return lexes[next(i for i, cs in enumerate(C5.CLASSES) if c in cs)]
else:
    def lex_for(c): return lexp
print(f'lexer: {len(lexp.x.temps)} temps; parser: {len(gen.x.temps)} temps')
work = 0; steps = 0
for f in sys.argv[1:]:
    text = open(f).read().rstrip('\n') + '\n'
    src = [ord(ch) for ch in text] + [0, 0]
    ref = R.Compiler(DB, CB, lib)
    ls = D.initial_lex(DB); ps = D.initial_parse(DB); tab = {n: 0 for n in D.table_names()}; lab = {}; code = {}; data = {}
    prev = dict(o_tkany=0); pw = None
    for i in range(len(src)):
        c, cn = src[i], (src[i + 1] if i + 1 < len(src) else 0)
        if pw:                                   # delayed table writes from the previous level
            for pre, fl in (('y', ('sh1_', 'sh2_', 'sk_')), ('f', ('fh1_', 'fh2_', 'fl_'))):
                if pw[f'o_{pre}w']:
                    j = pw[f'o_{pre}i']
                    for nm, fld in zip(fl, ('h1', 'h2', 'k' if pre == 'y' else 'l')): tab[f'{nm}{j}'] = pw[f'o_{pre}{fld}']
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
                        w, l, a = e[('T', f'o_w{s}')], e[('T', f'o_l{s}')], e[('T', f'o_a{s}')] + DB - CB
                        code[a] = (w // 8192, l if l >= 0 else w % 8192, int(l >= 0))
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
    rcode = {a: (op, (lab_ if lab_ is not None else imm), int(lab_ is not None)) for a, (op, imm, lab_) in ref.code.items()}
    ok = not diff and code == rcode and data == ref.data and lab == rlab
    allok &= ok
    print(f, 'OK' if ok else f'MISMATCH {diff[:5]} code-eq {code == rcode} data-eq {data == ref.data} lab-eq {lab == rlab}')
print(f'parser steps {steps}, temps evaluated {work} ({work // max(steps, 1)}/step); variants {len(variants)}')
print('ALL OK' if allok else 'FAILURES')
