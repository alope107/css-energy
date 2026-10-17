"""cc_dsl.py — the CSS compiler's per-character step, written once in the DSL (dsl.py).

Mirrors cc_ref.Compiler exactly (same state, same limits, same code), but as predicated straight-line code so
it can become one nested element's CSS. Prog is the parser step (one token), LexProg the lexer step (one
character). Outputs: code-word candidates, label definitions, the data word, table write ports.

Table encodings: sk_j = (type + 4 * const) * 65536 + kind * 16384 + addr + 8192 (a parameter i is addr 4096 + i, resolved
against npar when read); fl_k = label + 64 * type (type: 0 number/unknown, 1 boolean, 2 string). Symbols 0..nsym-1 are
function / program level, NS-nlet..NS-1 block-scoped let / const. Control-stack entry k: csA = kind * 4096 + a * 64 + b,
csB = e * 4096 + c * 64 + d (e: nlet when pushed, restored when a body closes). Operator-stack entry: code * 8192 + value.
"""
from dsl import *
import cc_ref as R

OD, CD, NS, NF, NL = R.OD, R.CD, R.NS, R.NF, R.NL
H1M, H2M = R.H1M, R.H2M
KW = R.KW

LEX_STATE = ['lx', 'q', 'lt', 'tkc', 'acc', 'h1', 'h2', 'p2', 'sstart', 'sdp', 'pp']

def parse_state_names():
    s = ['dp', 'mode', 'pn1', 'pn2', 'osp', 'csp', 'nsym', 'nlet', 'nfn', 'nlab', 'cp', 'curf', 'cfn', 'nfdef', 'nloc', 'npar', 'fsym', 'pendLa',
         'err', 'arrstart', 'lb']
    s += [f'op{k}' for k in range(OD)]
    s += [f'csA{k}' for k in range(CD)] + [f'csB{k}' for k in range(CD)]
    return s

def table_names():
    """symbol and function tables: not parser state. Read as inputs; a step writes at most one entry of each
    (write ports o_y* / o_f*), applied by the next level. Labels are not state at all: definitions are outputs."""
    return [x for j in range(NS) for x in (f'sh1_{j}', f'sh2_{j}', f'sk_{j}')] + [x for k in range(NF) for x in (f'fh1_{k}', f'fh2_{k}', f'fl_{k}')]

def initial_lex(data_base):
    st = {n: 0 for n in LEX_STATE}; st['sdp'] = data_base + R.SDATA
    return st

def initial_parse(data_base):
    st = {n: 0 for n in parse_state_names()}
    st['dp'] = data_base + 1; st['mode'] = R.S_STMT
    return st

# punctuation codes the parser distinguishes (single chars and the lexer's two-char codes); others share a variant
PUNCT = sorted({41, 59, 93, 40, 44, 61, 123, 91, 45, 8, 7, 46, 125, 33, 58, 63, R.T_NL} | set(R.BIN) | set(R.COMPOUND))
import os
SPEC_LEVEL = os.environ.get('SPECK', 'mtv')     # m: mode only; mt: + token kind; mtv: + punctuation value
def variant_key(mode, tk, tv):
    if SPEC_LEVEL == 'm': return (mode, None, None)
    if SPEC_LEVEL == 'mt': return (mode, tk, None)
    return (mode, tk, tv if tk == 4 and tv in PUNCT else None)
def tcode(tk, tv):
    if tk == 4 and tv in PUNCT: return 6 + PUNCT.index(tv)
    return tk
def key_tcodes(key):
    """token codes a variant key covers"""
    m, tk, tv = key
    if tk is None: return list(range(1, 6 + len(PUNCT)))
    if tk == 4 and tv is None: return [4] if SPEC_LEVEL == 'mtv' else [4] + list(range(6, 6 + len(PUNCT)))
    return [tcode(tk, tv)]
def variant_keys():
    if SPEC_LEVEL == 'm': return [(m, None, None) for m in range(R.S_ERR + 1)]
    if SPEC_LEVEL == 'mt': return [(m, k, None) for m in range(R.S_ERR + 1) for k in range(1, 6)]
    return [(m, k, v) for m in range(R.S_ERR + 1) for k in range(1, 6) for v in ((PUNCT + [None]) if k == 4 else [None])]

ALPHA = set(range(65, 91)) | set(range(97, 123)) | {95, 36}
DIGIT = set(range(48, 58))

class Base:
    def named(self, n, node):
        self.x.temps.append((n, lift(node))); self.out.append(n)

class Prog(Base):
    """per token (runs on the level after the character that completed it): parser step. inputs tk tv th1 th2"""
    def __init__(self, data_base, code_base, lib, mode=None, tk=None, tv=None):
        """mode / tk: specialise for a known starting mode and token kind (and err == 0) -- the page selects the
        variant with a container query, so each level evaluates only the code reachable from that mode"""
        self.db, self.cb, self.addc_fn = data_base, code_base, lib['addc']
        self.spec_mode, self.spec_tk, self.spec_tv = mode, tk, tv
        X = self.x = Ctx(parse_state_names(), ['tk', 'tv', 'th1', 'th2'])
        X.cur.update(live=K(1), f_expr=K(0), f_simple=K(0), f_compl=K(0), f_asic=K(0), f_compl2=K(0), scA=K(0), scAl=K(0), scO=K(0), scOl=K(0),
                     scT=K(0), scTl=K(0))
        if mode is not None: X.cur['mode'] = K(mode); X.cur['err'] = K(0)
        self.code = []      # (valid, addr, op, imm, islab)  addr relative to code base
        self.labs = []      # (valid, label, value)
        self.data = []      # (valid, addr, value)
        self.symw = []      # (valid, index, h1, h2, sk)
        self.fnw = []       # (valid, index, h1, h2, label)
        self.out = []
        self.parser()
        self.outputs()
        self.x.dce(self.out)

    # ---------------- primitives
    def v(self, n): return self.x.v(n)
    def set(self, n, val): self.x.set(n, val)
    def when(self, c): return self.x.when(c)
    def m(self, e, h='t'): return self.x.mat(e, h)
    def emit(self, op, imm=0, lab=None, b=None):
        X = self.x
        islab = 0 if lab is None else 1
        self.code.append((X.g, X.cur['cp'], lift(op), lift(lab if lab is not None else imm), islab))
        self.set('cp', self.v('cp') + 1)
        if b is None:
            op = lift(op)
            if isK(op): b = K(1 if op.v in R.BOOLOPS else 3 if op.v in R.NUMOPS else 0)
            else: b = ite(or_(inrange(op, R.LT, R.NE), eq(op, R.NOT)), 1, mul(anyeq(op, R.NUMOPS), 3))
        self.set('lb', b)
    def deflab(self, l, val): self.labs.append((self.x.g, lift(l), lift(val)))
    def datum(self, addr, val): self.data.append((self.x.g, lift(addr), lift(val)))
    def here(self): return self.v('cp') + self.cb
    def fail(self, code):
        self.set('err', ite(eq(self.v('err'), 0), code, self.v('err'))); self.set('live', 0)
    def done(self): self.set('live', 0)
    def newlab(self):
        l = self.m(self.v('nlab'), 'L')
        with self.when(ge(l, NL)): self.fail(20)
        self.set('nlab', l + 1)
        return l
    # control stack: entry k = (csA: kind*4096 + a*64 + b, csB: c*64 + d)
    def push_cs(self, kind, a=0, b=0, c=0, d=0, e=None):
        csp = self.m(self.v('csp'), 'csp')
        with self.when(ge(csp, CD)): self.fail(21)
        with self.when(lt(csp, CD)):
            A = self.m(add(add(mul(kind, 4096), mul(a, 64)), b))
            B = self.m(add(mul(self.v('nlet') if e is None else e, 4096), mul(c, 64), d))
            for k in range(CD):
                with self.when(eq(csp, k)):
                    self.set(f'csA{k}', A); self.set(f'csB{k}', B)
            self.set('csp', csp + 1)
    def top(self):
        csp = self.m(self.v('csp'), 'csp')
        A = self.m(add(*[mul(eq(csp, k + 1), self.v(f'csA{k}')) for k in range(CD)]), 'topA')
        B = self.m(add(*[mul(eq(csp, k + 1), self.v(f'csB{k}')) for k in range(CD)]), 'topB')
        kind = self.m(fdiv(A, 4096), 'tk'); a = self.m(mod(fdiv(A, 64), 64), 'ta'); b = self.m(mod(A, 64), 'tb')
        c = self.m(mod(fdiv(B, 64), 64), 'tc'); d = self.m(mod(B, 64), 'td'); e = self.m(fdiv(B, 4096), 'te')
        return kind, a, b, c, d, e
    def set_topA(self, f):
        """top entry's csA := f(old csA)"""
        csp = self.m(self.v('csp'), 'csp')
        for k in range(CD):
            with self.when(eq(csp, k + 1)): self.set(f'csA{k}', f(self.v(f'csA{k}')))
    def pop_cs(self):
        t = self.top(); self.set('csp', self.v('csp') - 1); return t
    def push_op(self, code, val=0):
        osp = self.m(self.v('osp'), 'osp')
        with self.when(ge(osp, OD)): self.fail(22)
        with self.when(lt(osp, OD)):
            w = self.m(add(mul(code, 8192), val))
            for k in range(OD):
                with self.when(eq(osp, k)): self.set(f'op{k}', w)
            self.set('osp', osp + 1)
    def set_top_op(self, code, val):
        osp = self.m(self.v('osp'), 'osp'); w = self.m(add(mul(code, 8192), val))
        for k in range(OD):
            with self.when(eq(osp, k + 1)): self.set(f'op{k}', w)
    def top_op(self):
        osp = self.m(self.v('osp'), 'osp')
        w = self.m(add(*[mul(eq(osp, k + 1), self.v(f'op{k}')) for k in range(OD)]), 'topw')
        return self.m(fdiv(w, 8192), 'topc'), self.m(mod(w, 8192), 'topv')
    def prec(self, code):
        return self.m(add(mul(inrange(code, 10, 12), 7), mul(inrange(code, 8, 9), 6), mul(inrange(code, 13, 16), 5),
                          mul(inrange(code, 17, 18), 4), mul(eq(code, 19), 3), mul(eq(code, 20), 2), mul(inrange(code, 21, 22), 8),
                          mul(eq(code, R.M_CADD), 6), eq(code, R.M_TELSE)), 'prec')
    def popops(self, minprec):
        """pop operators with precedence >= minprec. && / || and a ternary's M_TELSE define their jump label
        instead of emitting; at most one of each is popped (the stack's precedences increase upwards between
        markers, and cc_ref's M_TELSE chain rule keeps one M_TELSE per segment), and all are defined at the
        address after the pops, so they are collected and defined afterwards."""
        go = K(1)
        for _ in range(OD):
            code, val = self.top_op()
            p = self.prec(code)
            go = self.m(and_(go, gt(self.v('osp'), 0), gt(p, 0), ge(p, minprec)), 'pop')
            with self.when(go):
                self.set('osp', self.v('osp') - 1)
                with self.when(eq(code, R.AND)): self.set('scA', 1); self.set('scAl', val)
                with self.when(eq(code, R.OR)): self.set('scO', 1); self.set('scOl', val)
                lb = self.m(self.v('lb'), 'plb')
                with self.when(eq(code, R.M_TELSE)):
                    self.set('scT', 1); self.set('scTl', mod(val, 64)); self.set('lb', self.tmerge(fdiv(val, 64), lb))
                with self.when(eq(code, R.ADD)):
                    with self.when(or_(eq(val, 2), eq(lb, 2))): self.fail(63)
                with self.when(eq(code, R.M_CADD)):
                    num = self.m(and_(eq(val, 3), eq(lb, 3)), 'cnum')
                    self.emit(ite(num, R.ADD, R.CALL), ite(num, 0, self.addc_fn), b=mul(num, 3))
                with self.when(not_(anyeq(code, (R.AND, R.OR, R.M_CADD, R.M_TELSE)))): self.emit(code)
        with self.when(self.v('scA')): self.deflab(self.v('scAl'), self.here())
        with self.when(self.v('scO')): self.deflab(self.v('scOl'), self.here())
        with self.when(self.v('scT')): self.deflab(self.v('scTl'), self.here())
    def tmerge(self, a, b): return self.m(mul(eq(a, b), b), 'tmg')
    def lookup(self, h1, h2):
        """index of the symbol with this name, or -1: the latest block-scoped one (scores NS+1..2NS), else the latest
        other one (1..NS)"""
        n, lo = self.v('nsym'), self.m(sub(NS, self.v('nlet')), 'slo')
        best = self.m(mx(*[mul(and_(eq(I(f'sh1_{j}'), h1), eq(I(f'sh2_{j}'), h2)), add(mul(lt(j, n), j + 1), mul(ge(j, lo), 2 * NS - j)))
                           for j in range(NS)]), 'sbest')
        return self.m(ite(gt(best, NS), sub(2 * NS, best), sub(best, 1)), 'sym')
    def sym_sel(self, j, f, h):
        return self.m(add(*[mul(eq(j, i), I(f'{f}{i}')) for i in range(NS)]), h)
    def symkind_addr(self, j):
        """kind, address, static type, const flag of symbol j"""
        sk = self.sym_sel(j, 'sk_', 'sk')
        b = self.m(mod(fdiv(sk, 65536), 4), 'skb'); r = self.m(mod(sk, 65536), 'skr'); cst = self.m(fdiv(sk, 262144), 'skc')
        k, a = self.m(fdiv(r, 16384), 'skk'), self.m(sub(mod(r, 16384), 8192), 'ska')
        # parameter i is stored as kind 2, addr 4096 + i; its frame slot is -1 - npar + i (npar of the current function)
        ispar = self.m(and_(eq(k, 2), ge(a, 4096)), 'spar')
        return k, self.m(ite(ispar, sub(add(a, -1 - 4096), self.v('npar')), a), 'ska2'), b, cst
    def set_symbool(self, j, b):
        """symbol j's type := b (write port: the whole entry)"""
        sk = self.sym_sel(j, 'sk_', 'sk')
        self.symw.append((self.x.g, lift(j), self.sym_sel(j, 'sh1_', 'sy1'), self.sym_sel(j, 'sh2_', 'sy2'),
                          self.m(add(mod(sk, 65536), mul(fdiv(sk, 262144), 262144), mul(b, 65536)), 'syk')))
    def declare(self, h1, h2, kind, addr, cst=0, blk=0):
        """blk: a block-scoped let / const (written at NS - 1 - nlet)"""
        n, nl = self.m(self.v('nsym'), 'ns'), self.m(self.v('nlet'), 'nlt')
        full = self.m(ge(add(n, nl), NS), 'sfull')
        with self.when(full): self.fail(24)
        with self.when(not_(full)):
            sk = self.m(add(mul(kind, 16384), add(addr, 8192), mul(cst, 262144)))
            blk = lift(blk)
            self.symw.append((self.x.g, self.m(ite(blk, sub(NS - 1, nl), n), 'sdi'), lift(h1), lift(h2), sk))
            with self.when(blk): self.set('nlet', nl + 1)
            with self.when(not_(blk)): self.set('nsym', n + 1)
    def decl_blk(self):
        """cc_ref.decl_blk: let / const (pn1 1 / 2) below the function or program level"""
        return self.m(and_(gt(self.v('pn1'), 0), gt(self.v('csp'), self.v('curf'))), 'dblk')
    def fnfind(self, h1, h2):
        """-> (index, label, bool) of the function named h1/h2, adding it (with a new label) if absent"""
        n = self.m(self.v('nfn'), 'nf')
        found = self.m(mx(*[mul(and_(eq(I(f'fh1_{k}'), h1), eq(I(f'fh2_{k}'), h2), lt(k, n)), k + 1) for k in range(NF)]), 'ff')
        oldl = self.m(add(*[mul(eq(found, k + 1), I(f'fl_{k}')) for k in range(NF)]), 'fol')
        with self.when(eq(found, 0)):
            with self.when(ge(n, NF)): self.fail(23)
            with self.when(lt(n, NF)):
                l = self.newlab()
                self.fnw.append((self.x.g, n, lift(h1), lift(h2), lift(l)))
                self.set('nfn', n + 1)
        new = self.m(eq(found, 0), 'fnew')
        return (self.m(ite(new, n, sub(found, 1)), 'fni'), self.m(ite(new, self.v('nlab') - 1, mod(oldl, 64)), 'fnl'),
                self.m(ite(new, 0, fdiv(oldl, 64)), 'fnb'))
    def load(self, k, a, b=0):
        self.emit(ite(eq(k, 2), R.LOADL, R.LOADG), mod(a, 8192), b=b)
    def store(self, k, a):
        self.emit(ite(eq(k, 2), R.STOREL, R.STOREG), mod(a, 8192))
    def print_call(self, sep):
        # one PRINT word (cc_ref.print_call): the B form when the static type is boolean
        self.emit(add(R.PRINT_OP[sep], eq(self.v('lb'), 1)), 0, b=0)

    # ---------------- lexer
    def lexer(self):
        c, cn = (I('c') if getattr(self, 'spec_c', None) is None else K(self.spec_c)), I('cn')
        isal = lambda x: or_(inrange(x, 65, 90), inrange(x, 97, 122), eq(x, 95), eq(x, 36))
        isdg = lambda x: inrange(x, 48, 57)
        cs = getattr(self, 'cset', None)        # the set of codes c can take (class-specialised lexer), or None
        def ceq(v):
            if cs is not None and v not in cs: return K(0)
            return eq(c, v)
        def cpred(pred, members):
            if cs is not None and cs <= members: return K(1)
            if cs is not None and not (cs & members): return K(0)
            return pred(c)
        lx, p2, tkc = self.m(self.v('lx'), 'lx'), self.m(self.v('p2'), 'p2'), self.m(self.v('tkc'), 'tkc')
        ltk = self.m(self.v('lt'), 'ltk')
        def tok(kind, v=0, a=0, b=0):
            self.set('tk', kind); self.set('tv', v); self.set('th1', a); self.set('th2', b)
        def adv(): self.set('sdp', self.v('sdp') + 1)
        alc, dgc = self.m(cpred(isal, ALPHA), 'al'), self.m(cpred(isdg, DIGIT), 'dg')
        alcn, dgcn = self.m(isal(cn), 'aln'), self.m(isdg(cn), 'dgn')
        two = self.m(add(*[mul(and_(ceq(a), eq(cn, b)), code) for (a, b), code in R.TWO.items()]), 'two')
        cE = self.m(ceq(0), 'cE')
        eof = self.m(and_(cE, ne(lx, 0)), 'eofx')
        with self.when(eof): self.set('lx', 0); self.set('p2', 0); tok(5)
        L = lambda n: self.m(and_(not_(eof), eq(lx, n)), f'lx{n}_')
        with self.when(L(1)):
            cq = self.m(eq(c, self.v('q')), 'cq')
            with self.when(cq):
                self.datum(self.v('sdp'), 0); adv(); self.set('lx', 0); tok(3, self.v('sstart'), self.v('sdp'))   # th1: end of the string data
            with self.when(and_(not_(cq), ceq(92))): self.set('lx', 3)
            with self.when(and_(not_(cq), not_(ceq(92)))):
                self.datum(self.v('sdp'), c); adv()
        with self.when(L(3)):
            self.datum(self.v('sdp'), ite(ceq(110), 10, ite(ceq(116), 9, ite(ceq(114), 13, c)))); adv(); self.set('lx', 1)
        with self.when(L(2)):
            with self.when(ceq(10)):
                self.set('lx', 0)
                with self.when(ltk): tok(4, R.T_NL)
        with self.when(L(4)):
            with self.when(and_(ceq(42), eq(cn, 47))): self.set('lx', 5)
        with self.when(L(5)): self.set('lx', 0)
        with self.when(L(6)): self.set('lx', 4)
        with self.when(L(0)):
            with self.when(ne(p2, 0)):
                tok(4, p2); self.set('p2', 0)
                with self.when(and_(or_(eq(p2, 1), eq(p2, 2)), eq(cn, 61))): self.set('lx', 5)
            with self.when(eq(p2, 0)):
                cN = self.m(and_(ceq(10), ltk), 'cN')
                sp = self.m(or_(cN, *[ceq(v) for v in (9, 10, 13, 32)]), 'spc')
                with self.when(cN): tok(4, R.T_NL)
                cG = self.m(and_(not_(cE), not_(sp), ceq(47), eq(cn, 47)), 'cG')
                cB = self.m(and_(not_(cE), not_(sp), ceq(47), eq(cn, 42)), 'cB')
                cH = self.m(and_(not_(cE), not_(sp), or_(ceq(34), ceq(39))), 'cH')
                rest = self.m(and_(not_(cE), not_(sp), not_(cG), not_(cB), not_(cH)), 'rest')
                cI = self.m(and_(rest, or_(alc, and_(dgc, eq(tkc, 1)))), 'cI')
                cJ = self.m(and_(rest, not_(cI), dgc), 'cJ')
                cK = self.m(and_(rest, not_(cI), not_(cJ), ne(two, 0)), 'cK')
                cL = self.m(and_(rest, not_(cI), not_(cJ), eq(two, 0)), 'cL')
                with self.when(cE): tok(5)
                with self.when(cG): self.set('lx', 2)
                with self.when(cB): self.set('lx', 6)
                with self.when(cH):
                    sdp = self.m(self.v('sdp'), 'sdp0')
                    self.set('lx', 1); self.set('q', c); self.datum(sdp, sdp + 1 - R.STRTAG); self.set('sdp', sdp + 1); self.set('sstart', sdp + 1)
                with self.when(cI):
                    keep = self.m(eq(tkc, 1), 'kp')
                    nh1 = self.m(mod(add(mul(mul(keep, self.v('h1')), 31), c), H1M), 'nh1')
                    nh2 = self.m(mod(add(mul(mul(keep, self.v('h2')), 37), c), H2M), 'nh2')
                    self.set('h1', nh1); self.set('h2', nh2); self.set('tkc', 1)
                    with self.when(not_(or_(alcn, dgcn))): tok(2, 0, nh1, nh2); self.set('tkc', 0)
                with self.when(cJ):
                    nacc = self.m(add(mul(mul(eq(tkc, 2), self.v('acc')), 10), sub(c, 48)), 'nacc')
                    self.set('acc', nacc); self.set('tkc', 2)
                    with self.when(not_(dgcn)): tok(1, nacc); self.set('tkc', 0)
                with self.when(cK): self.set('p2', two)
                with self.when(cL): tok(4, c)

    # ---------------- parser
    def parser(self):
        tk = I('tk') if self.spec_tk is None else K(self.spec_tk)
        with self.when(and_(ne(tk, 0), eq(self.v('err'), 0))):
            self.token(tk, I('tv') if self.spec_tv is None else K(self.spec_tv), I('th1'), I('th2'))

    def token(self, tk, tv, th1, th2):
        # a variant for 'other punctuation' (tk 4, no tv) only sees codes outside PUNCT
        other_p = self.spec_tk == 4 and self.spec_tv is None and SPEC_LEVEL == 'mtv'
        P = lambda ch: K(0) if other_p and ch in PUNCT else self.m(and_(eq(tk, 4), eq(tv, ch)), f'P{ch}_')
        isID = self.m(eq(tk, 2), 'isID'); isNUM = self.m(eq(tk, 1), 'isNUM'); isSTR = self.m(eq(tk, 3), 'isSTR'); isEOF = self.m(eq(tk, 5), 'isEOF')
        KWc = lambda k: self.m(and_(isID, eq(th1, KW[k][0]), eq(th2, KW[k][1])), 'kw_' + k)
        live = lambda: self.m(self.v('live'), 'live')
        mode = lambda: self.m(self.v('mode'), 'mode')
        compound = self.m(add(*[mul(P(ch), op) for ch, op in R.COMPOUND.items()]), 'cmpd')
        # with a known starting mode, only the fallthrough chains below can run: other blocks are folded away
        # (after a dynamic mode change the analysis could not prove them unreachable)
        FALL = {R.S_NAMES: (R.S_NAMEE, R.S_OPER), R.S_NAMEE: (R.S_OPER,), R.S_ELSE: (R.S_DOWHILE, R.S_STMT), R.S_AFTERELSE: (R.S_STMT,),
                R.S_LBRACE: (R.S_STMT,), R.S_CONFIRST: (R.S_OPND,)}
        reach = None if self.spec_mode is None else {self.spec_mode, *FALL.get(self.spec_mode, ())}
        def block(md):
            if reach is not None and md not in reach: return self.when(K(0))
            return self.when(and_(live(), eq(mode(), md)))
        PNL, PRB = P(R.T_NL), P(125)
        # a newline token means nothing outside the modes where it can end a statement
        with self.when(and_(PNL, not_(anyeq(mode(), (R.S_NAMES, R.S_NAMEE, R.S_OPER, R.S_VARAFTER, R.S_INC, R.S_OPND))))): self.done()
        # ---- S_NAMES
        with block(R.S_NAMES):
            pn1, pn2 = self.v('pn1'), self.v('pn2')
            j = self.lookup(pn1, pn2)
            k, a, b, cst = self.symkind_addr(j)
            asg = self.m(or_(P(61), ne(compound, 0)), 'asg')
            with self.when(asg):
                with self.when(lt(j, 0)): self.fail(5)
                with self.when(and_(ge(j, 0), cst)): self.fail(64)
                with self.when(and_(ge(j, 0), not_(cst))):
                    with self.when(not_(P(61))): self.load(k, a, b)
                    self.push_cs(R.C_ASSIGN, j, compound); self.set('mode', R.S_OPND); self.done()
            with self.when(or_(P(7), P(8))): self.incdec(pn1, pn2, tv)
            with self.when(P(91)):
                with self.when(lt(j, 0)): self.fail(7)
                with self.when(ge(j, 0)): self.load(k, a, b); self.push_cs(R.C_IDXA); self.push_op(R.M_IDXA); self.set('mode', R.S_OPND); self.done()
            with self.when(not_(or_(asg, P(7), P(8), P(91)))):
                self.push_cs(R.C_EXPR); self.set('mode', R.S_NAMEE)
        # ---- S_NAMEE
        with block(R.S_NAMEE):
            pn1, pn2 = self.m(self.v('pn1'), 'pn1'), self.m(self.v('pn2'), 'pn2')
            iscon = self.m(and_(eq(pn1, KW['console'][0]), eq(pn2, KW['console'][1])), 'iscon')
            isputc = self.m(and_(eq(pn1, KW['putc'][0]), eq(pn2, KW['putc'][1])), 'isputc')
            with self.when(iscon):
                with self.when(not_(P(46))): self.fail(30)
                with self.when(P(46)): self.set('mode', R.S_CONLOG); self.done()
            with self.when(and_(not_(iscon), P(40))):
                with self.when(isputc): self.push_op(R.M_PUTC)
                with self.when(not_(isputc)):
                    _, l, fb = self.fnfind(pn1, pn2); self.push_op(R.M_CALL, add(l, mul(fb, 64)))
                self.set('mode', R.S_OPND); self.done()
            with self.when(and_(not_(iscon), not_(P(40)))):
                j = self.lookup(pn1, pn2)
                k, a, b, _ = self.symkind_addr(j)
                with self.when(lt(j, 0)): self.fail(4)
                with self.when(ge(j, 0)):
                    with self.when(P(91)):
                        self.push_op(ite(eq(k, 2), R.M_IDXL, R.M_IDXG), mod(a, 8192)); self.set('mode', R.S_OPND); self.done()
                    with self.when(not_(P(91))):
                        self.load(k, a, b); self.set('mode', R.S_OPER)
        # ---- S_ELSE
        with block(R.S_ELSE):
            with self.when(KWc('else')):
                t = self.top(); reuse = self.m(eq(t[0], R.C_ELSEB1), 'reuse')
                with self.when(not_(reuse)): nl = self.newlab()
                lb = self.m(ite(reuse, t[1], nl), 'elb')
                self.emit(R.JMP, 0, lb); self.deflab(self.v('pendLa'), self.here())
                self.set('pendLa', add(lb, mul(reuse, 64))); self.set('mode', R.S_AFTERELSE); self.done()
            with self.when(not_(KWc('else'))):
                dook = self.m(or_(isID, isEOF, P(59), P(123), P(125), P(7), P(8), P(41)), 'dook')    # see cc_ref
                self.deflab(self.v('pendLa'), self.here()); self.complete_stmt(K(1), dook)
        # ---- S_DOWHILE
        with block(R.S_DOWHILE):
            with self.when(KWc('while')): self.set('mode', R.S_LPAREN); self.done()
            with self.when(P(59)): self.done()
            with self.when(not_(or_(KWc('while'), P(59)))): self.fail(66)
        # ---- S_AFTERELSE
        with block(R.S_AFTERELSE):
            pl = self.m(self.v('pendLa'), 'pla'); reuse = self.m(ge(pl, 64), 'reuse2')
            with self.when(P(123)):
                self.push_cs(ite(reuse, R.C_BLOCK, R.C_ELSEB), mul(not_(reuse), pl)); self.set('mode', R.S_STMT); self.done()
            with self.when(not_(P(123))):
                with self.when(not_(reuse)): self.push_cs(R.C_ELSEB1, pl)
                self.set('mode', R.S_STMT)
        # ---- S_LBRACE
        with block(R.S_LBRACE):
            with self.when(P(123)): self.set('mode', R.S_STMT); self.done()
            with self.when(not_(P(123))):
                tkind = self.top()[0]
                okb = self.m(anyeq(tkind, (R.C_IFB, R.C_LOOPB, R.C_DOB)), 'okb')
                with self.when(not_(okb)): self.fail(33)
                with self.when(okb): self.set_topA(lambda A: add(A, R.BRACELESS * 4096)); self.set('mode', R.S_STMT)
        # ---- S_STMT
        with block(R.S_STMT):
            t0 = self.top()[0]
            with self.when(isEOF):
                with self.when(ne(self.v('csp'), 0)): self.fail(40)
                undef = self.m(lt(self.v('nfdef'), self.v('nfn')), 'undef')
                with self.when(and_(eq(self.v('csp'), 0), undef)): self.fail(60)
                with self.when(and_(eq(self.v('csp'), 0), not_(undef))): self.emit(R.HALT); self.done()
            with self.when(P(123)): self.push_cs(R.C_BLOCK); self.done()
            with self.when(P(125)): self.close_block()
            with self.when(P(59)): self.set('f_simple', 1)
            fstep = self.m(and_(P(41), eq(t0, R.C_FORSTEP)), 'fstep')
            with self.when(fstep): self.set('f_simple', 1)
            with self.when(or_(P(7), P(8))): self.set('pn1', tv); self.set('pn2', 0); self.set('mode', R.S_PREINC); self.done()
            other = self.m(and_(not_(isEOF), not_(P(123)), not_(P(125)), not_(P(59)), not_(fstep), not_(P(7)), not_(P(8))), 'oth')
            with self.when(and_(other, not_(isID))): self.fail(8)
            with self.when(and_(other, isID)):
                kws = ['var', 'let', 'const', 'if', 'while', 'do', 'for', 'return', 'function', 'break', 'continue']
                with self.when(or_(KWc('var'), KWc('let'), KWc('const'))):
                    self.set('pn1', add(KWc('let'), mul(KWc('const'), 2))); self.set('pn2', 0); self.set('mode', R.S_VAR); self.done()
                with self.when(KWc('if')): self.push_cs(R.C_IFC); self.set('mode', R.S_LPAREN); self.done()
                with self.when(KWc('while')):
                    lh = self.newlab(); self.deflab(lh, self.here()); self.push_cs(R.C_WHILEC, lh); self.set('mode', R.S_LPAREN); self.done()
                with self.when(KWc('do')):
                    lt_ = self.newlab(); lc = self.newlab(); lb = self.newlab(); self.deflab(lt_, self.here())
                    self.push_cs(R.C_DOB, lc, lb, lt_); self.set('mode', R.S_LBRACE); self.done()
                with self.when(KWc('for')):
                    l1 = self.newlab(); le = self.newlab(); lb = self.newlab(); l2 = self.newlab()
                    self.push_cs(R.C_FORINIT, l1, le, lb, l2); self.set('mode', R.S_LPAREN); self.done()
                with self.when(KWc('return')):
                    with self.when(eq(self.v('curf'), 0)): self.fail(57)
                    with self.when(ne(self.v('curf'), 0)): self.push_cs(R.C_RETURN); self.set('mode', R.S_OPND); self.done()
                with self.when(or_(KWc('break'), KWc('continue'))):
                    self.jump_loop(KWc('break'))
                with self.when(KWc('function')):
                    bad = self.m(or_(ne(self.v('curf'), 0), ne(self.v('csp'), 0)), 'fbad')
                    with self.when(bad): self.fail(41)
                    with self.when(not_(bad)):
                        lo = self.newlab(); self.emit(R.JMP, 0, lo); self.set('mode', R.S_FNAME); self.push_cs(R.C_FUNCB, lo); self.done()
                with self.when(not_(or_(*[KWc(k) for k in kws]))):
                    self.set('pn1', th1); self.set('pn2', th2); self.set('mode', R.S_NAMES); self.done()
        # ---- S_PREINC
        with block(R.S_PREINC):
            with self.when(not_(isID)): self.fail(10)
            with self.when(isID): self.incdec(th1, th2, self.v('pn1'))
        # ---- S_VAR
        with block(R.S_VAR):
            with self.when(not_(isID)): self.fail(9)
            with self.when(isID):
                curf = self.m(self.v('curf'), 'curf')
                cst, blk = self.m(eq(self.v('pn1'), 2), 'dcst'), self.decl_blk()
                with self.when(ne(curf, 0)):
                    nl = self.m(self.v('nloc') + 1, 'nl'); self.set('nloc', nl); self.declare(th1, th2, 2, nl, cst, blk)
                full = self.m(ge(self.v('dp'), self.db + R.SDATA), 'gfull')
                with self.when(and_(eq(curf, 0), full)): self.fail(25)
                with self.when(and_(eq(curf, 0), not_(full))):
                    self.declare(th1, th2, 1, self.v('dp'), cst, blk); self.set('dp', self.v('dp') + 1)
                with self.when(or_(ne(curf, 0), not_(full))): self.set('mode', R.S_VARAFTER); self.done()
        # ---- S_VARAFTER
        with block(R.S_VARAFTER):
            pn1 = self.m(self.v('pn1'), 'dk')
            with self.when(P(61)):
                self.push_cs(R.C_ASSIGN, ite(self.decl_blk(), sub(NS, self.v('nlet')), self.v('nsym') - 1), 0, add(pn1, 1))
                self.set('mode', R.S_OPND); self.done()
            with self.when(and_(not_(P(61)), eq(pn1, 2))): self.fail(65)
            with self.when(and_(P(44), ne(pn1, 2))): self.set('mode', R.S_VAR); self.done()
            with self.when(not_(or_(P(61), P(44), eq(pn1, 2)))): self.simple_end(PNL, PRB)
        with block(R.S_INC):
            self.simple_end(PNL, PRB)
        with block(R.S_LPAREN):
            with self.when(not_(P(40))): self.fail(32)
            with self.when(P(40)):
                t = self.top()
                self.set('mode', ite(eq(t[0], R.C_FORINIT), R.S_STMT, R.S_OPND)); self.done()
        with block(R.S_FNAME):
            with self.when(not_(isID)): self.fail(34)
            with self.when(isID):
                fi, l, _ = self.fnfind(th1, th2); self.set('cfn', fi); self.deflab(l, self.here()); self.set('nfdef', self.v('nfdef') + 1)
                self.set('curf', 1); self.set('nloc', 0); self.set('npar', 0); self.set('fsym', self.v('nsym'))
                le = self.newlab()
                self.set_topA(lambda A: add(sub(A, mod(A, 64)), le))      # top entry's b field := le
                self.set('mode', R.S_FPAREN); self.done()
        with block(R.S_FPAREN):
            with self.when(not_(P(40))): self.fail(35)
            with self.when(P(40)): self.set('mode', R.S_FPARAM); self.done()
        with block(R.S_FPARAM):
            with self.when(P(41)): self.end_params()
            with self.when(and_(not_(P(41)), not_(isID))): self.fail(36)
            with self.when(and_(not_(P(41)), isID)):
                self.declare(th1, th2, 2, add(self.v('npar'), 4096)); self.set('npar', self.v('npar') + 1); self.set('mode', R.S_FPSEP); self.done()
        with block(R.S_FPSEP):
            with self.when(P(44)): self.set('mode', R.S_FPARAM); self.done()
            with self.when(P(41)): self.end_params()
            with self.when(and_(not_(P(44)), not_(P(41)))): self.fail(37)
        with block(R.S_CONLOG):
            with self.when(not_(KWc('log'))): self.fail(38)
            with self.when(KWc('log')): self.set('mode', R.S_CONLP); self.done()
        with block(R.S_CONLP):
            with self.when(not_(P(40))): self.fail(39)
            with self.when(P(40)): self.push_op(R.M_PRINT); self.set('mode', R.S_CONFIRST); self.done()
        with block(R.S_CONFIRST):
            with self.when(P(41)):
                self.set('osp', self.v('osp') - 1); self.emit(R.PUSHI, 10); self.emit(R.PUTC); self.emit(R.PUSHI, 0)
                self.set('mode', R.S_OPER); self.done()
            with self.when(not_(P(41))):
                self.set_top_op(R.M_PRINT, 0); self.set('mode', R.S_OPND)
        with block(R.S_ARR):
            with self.when(P(93)): self.end_array()
            with self.when(and_(not_(P(93)), P(45))): self.set('mode', R.S_ARRNEG); self.done()
            with self.when(and_(not_(P(93)), not_(P(45)), not_(isNUM))): self.fail(42)
            full = self.m(ge(self.v('dp'), self.db + R.SDATA), 'afull')
            with self.when(and_(not_(P(93)), not_(P(45)), isNUM, full)): self.fail(25)
            with self.when(and_(not_(P(93)), not_(P(45)), isNUM, not_(full))):
                self.datum(self.v('dp'), tv); self.set('dp', self.v('dp') + 1); self.set('mode', R.S_ARRSEP); self.done()
        with block(R.S_ARRNEG):
            full = self.m(ge(self.v('dp'), self.db + R.SDATA), 'afull')
            with self.when(not_(isNUM)): self.fail(42)
            with self.when(and_(isNUM, full)): self.fail(25)
            with self.when(and_(isNUM, not_(full))):
                self.datum(self.v('dp'), sub(0, tv)); self.set('dp', self.v('dp') + 1); self.set('mode', R.S_ARRSEP); self.done()
        with block(R.S_ARRSEP):
            with self.when(P(44)): self.set('mode', R.S_ARR); self.done()
            with self.when(P(93)): self.end_array()
            with self.when(and_(not_(P(44)), not_(P(93)))): self.fail(43)
        # ---- S_OPND
        with block(R.S_OPND):
            with self.when(isNUM):
                with self.when(lt(tv, 8192)): self.emit(R.PUSHI, tv)
                with self.when(ge(tv, 8192)):
                    self.emit(R.PUSHI, fdiv(tv, 8192)); self.emit(R.SHL13); self.emit(R.PUSHI, mod(tv, 8192)); self.emit(R.ADD)
                self.set('mode', R.S_OPER); self.done()
            with self.when(isSTR):
                with self.when(gt(th1, self.db + 2 * R.SDATA)): self.fail(26)
                with self.when(lt(th1, self.db + 2 * R.SDATA + 1)): self.emit(R.LOADG, mod(sub(tv, 1), 8192), b=2); self.set('mode', R.S_OPER); self.done()
            tf = self.m(or_(KWc('true'), KWc('false')), 'tf')
            with self.when(tf): self.emit(R.PUSHI, KWc('true'), b=1); self.set('mode', R.S_OPER); self.done()
            with self.when(P(40)): self.push_op(R.M_PAREN); self.done()
            with self.when(P(33)): self.push_op(R.NOT); self.done()
            with self.when(P(45)): self.push_op(R.NEG); self.done()
            with self.when(P(91)): self.set('arrstart', self.v('dp')); self.set('mode', R.S_ARR); self.done()
            with self.when(and_(isID, not_(tf))): self.set('pn1', th1); self.set('pn2', th2); self.set('mode', R.S_NAMEE); self.done()
            rest = self.m(and_(live(), eq(mode(), R.S_OPND)), 'orest')
            with self.when(rest):
                tc, tvv = self.top_op()
                t = self.top()
                cA = self.m(and_(P(41), gt(self.v('osp'), 0), eq(tc, R.M_CALL)), 'oA')
                cB = self.m(and_(not_(cA), or_(P(59), PNL, PRB), eq(t[0], R.C_RETURN), eq(self.v('osp'), 0)), 'oB')
                cC = self.m(and_(not_(cA), not_(cB), P(59), eq(t[0], R.C_FORCOND), eq(self.v('osp'), 0)), 'oC')
                cN = self.m(and_(not_(cB), PNL), 'oN')
                with self.when(cN): self.done()
                with self.when(cA):
                    self.set('osp', self.v('osp') - 1); self.emit(R.CALL, 0, mod(tvv, 64), b=fdiv(tvv, 64)); self.set('mode', R.S_OPER); self.done()
                with self.when(cB):
                    self.emit(R.PUSHI, 0); self.set('f_expr', 1)
                    with self.when(PRB): self.set('f_asic', 1)
                with self.when(cC): self.emit(R.PUSHI, 1); self.set('f_expr', 1)
                with self.when(and_(not_(cA), not_(cB), not_(cC), not_(cN))): self.fail(3)
        # ---- S_OPER
        with block(R.S_OPER):
            binop = self.m(add(*[mul(P(ch), op) for ch, op in R.BIN.items()]), 'binop')
            osp_ = self.m(self.v('osp'), 'ospa')
            nomark = self.m(not_(or_(*[and_(lt(k, osp_), ge(self.v(f'op{k}'), 100 * 8192)) for k in range(OD)])), 'nomark')
            tk0 = self.top()[0]
            asiok = self.m(and_(nomark, anyeq(tk0, (R.C_ASSIGN, R.C_IDXA, R.C_EXPR, R.C_RETURN))), 'asiok')
            semi = self.m(or_(P(59), and_(or_(PNL, PRB), asiok)), 'semi')
            with self.when(and_(PNL, not_(asiok))): self.done()
            closer = self.m(or_(ne(binop, 0), P(41), P(44), P(93), P(58), P(63), semi), 'closer')
            with self.when(closer):
                self.popops(self.m(ite(ne(binop, 0), self.prec(binop), add(1, P(63))), 'minp'))
            tc, tvv = self.top_op()
            osp0 = self.m(self.v('osp'), 'osp0')
            tc = self.m(mul(tc, gt(osp0, 0)), 'tt')
            with self.when(ne(binop, 0)):
                lb0 = self.m(self.v('lb'), 'lb0')
                cat = self.m(and_(eq(binop, R.ADD), eq(tc, R.M_PRINT), or_(eq(tvv, 1), eq(lb0, 2))), 'cat')
                logic = self.m(and_(not_(cat), or_(eq(binop, R.AND), eq(binop, R.OR))), 'logic')
                plus = self.m(and_(not_(cat), eq(binop, R.ADD)), 'plus')
                with self.when(cat): self.print_call(0); self.set_top_op(R.M_PRINT, 1)
                with self.when(plus): self.push_op(ite(eq(tc, R.M_PRINT), R.M_CADD, R.ADD), lb0)
                with self.when(logic):
                    l = self.newlab(); self.emit(R.DUP); self.emit(ite(eq(binop, R.AND), R.JZ, R.JNZ), 0, l); self.emit(R.POP)
                    self.push_op(binop, l)
                with self.when(and_(not_(cat), not_(logic), not_(plus))): self.push_op(binop)
                self.set('mode', R.S_OPND); self.done()
            with self.when(P(63)):                             # c ? ... (cc_ref)
                l = self.newlab(); self.emit(R.JZ, 0, l); self.push_op(R.M_TERN, add(l, mul(eq(tc, R.M_TELSE), 64)))
                self.set('mode', R.S_OPND); self.done()
            with self.when(P(58)):                             # c ? a : ...
                with self.when(ne(tc, R.M_TERN)): self.fail(67)
                with self.when(eq(tc, R.M_TERN)):
                    lbt = self.m(self.v('lb'), 'lbt'); reuse = self.m(ge(tvv, 64), 'treu')
                    self.set('osp', osp0 - 1)
                    _, ev = self.top_op()                      # the enclosing M_TELSE, when reuse
                    with self.when(not_(reuse)): l2 = self.newlab()
                    self.emit(R.JMP, 0, ite(reuse, mod(ev, 64), l2))
                    with self.when(reuse): self.set_top_op(R.M_TELSE, add(mod(ev, 64), mul(self.tmerge(fdiv(ev, 64), lbt), 64)))
                    with self.when(not_(reuse)): self.push_op(R.M_TELSE, add(l2, mul(lbt, 64)))
                    self.deflab(mod(tvv, 64), self.here()); self.set('mode', R.S_OPND); self.done()
            cl = self.m(and_(eq(binop, 0), or_(P(41), P(44), P(93))), 'cl')
            with self.when(cl):
                t = tc
                with self.when(P(44)):
                    vasg = self.m(and_(eq(osp0, 0), eq(self.top()[0], R.C_ASSIGN), ne(self.top()[3], 0)), 'vasg')
                    with self.when(eq(t, R.M_PRINT)): self.print_call(32); self.set('mode', R.S_CONFIRST); self.done()
                    with self.when(anyeq(t, (R.M_CALL, R.M_PUTC))): self.set('mode', R.S_OPND); self.done()
                    with self.when(vasg): self.set('f_expr', 1)
                    with self.when(not_(or_(anyeq(t, (R.M_PRINT, R.M_CALL, R.M_PUTC)), vasg))): self.fail(44)
                with self.when(P(93)):
                    with self.when(anyeq(t, (R.M_IDXG, R.M_IDXL))):
                        self.set('osp', osp0 - 1); self.emit(ite(eq(t, R.M_IDXL), R.IDXL, R.IDX), tvv); self.done()
                    with self.when(eq(t, R.M_IDXA)): self.set('osp', osp0 - 1); self.emit(R.ADD); self.set('mode', R.S_IDXEQ); self.done()
                    with self.when(not_(anyeq(t, (R.M_IDXG, R.M_IDXL, R.M_IDXA)))): self.fail(45)
                with self.when(P(41)):
                    with self.when(eq(t, R.M_PAREN)): self.set('osp', osp0 - 1); self.done()
                    with self.when(eq(t, R.M_CALL)): self.set('osp', osp0 - 1); self.emit(R.CALL, 0, mod(tvv, 64), b=fdiv(tvv, 64)); self.done()
                    with self.when(eq(t, R.M_PUTC)): self.set('osp', osp0 - 1); self.emit(R.PUTC); self.emit(R.PUSHI, 0); self.done()
                    with self.when(eq(t, R.M_PRINT)): self.set('osp', osp0 - 1); self.print_call(10); self.done()
                    other = self.m(not_(anyeq(t, (R.M_PAREN, R.M_CALL, R.M_PUTC, R.M_PRINT))), 'o41')
                    with self.when(and_(other, gt(osp0, 0))): self.fail(46)
                    with self.when(and_(other, eq(osp0, 0))): self.set('f_expr', 1)
            with self.when(and_(eq(binop, 0), semi)):
                with self.when(gt(osp0, 0)): self.fail(47)
                with self.when(eq(osp0, 0)):
                    self.set('f_expr', 1)
                    with self.when(PRB): self.set('f_asic', 1)
            with self.when(and_(eq(binop, 0), not_(or_(P(41), P(44), P(93), P(58), P(63), semi, PNL)))): self.fail(48)
        with block(R.S_IDXEQ):
            with self.when(P(61)): self.set('mode', R.S_OPND); self.done()
            with self.when(ne(compound, 0)):
                self.emit(R.DUP); self.emit(R.LOADI); self.set_topA(lambda A: add(sub(A, mod(fdiv(A, 64), 64) * 64), compound * 64))
                self.set('mode', R.S_OPND); self.done()
            with self.when(and_(not_(P(61)), eq(compound, 0))): self.fail(49)
        # deferred tails (each is the last thing its path does)
        with self.when(self.v('f_expr')): self.end_expr_stmt(P)
        with self.when(self.v('f_simple')): self.end_simple_stmt(P)
        asic = self.m(self.v('f_asic'), 'asic')
        with self.when(self.v('f_compl')): self.complete_stmt(asic)
        with self.when(asic): self.close_block('f_compl2')        # '}' after a statement without ';'
        with self.when(self.v('f_compl2')): self.complete_stmt(K(0))
        # nothing handled it
        with self.when(self.v('live')): self.fail(99)

    def incdec(self, h1, h2, op):
        j = self.lookup(h1, h2)
        k, a, b, cst = self.symkind_addr(j)
        with self.when(lt(j, 0)): self.fail(6)
        with self.when(and_(ge(j, 0), cst)): self.fail(64)
        with self.when(and_(ge(j, 0), not_(cst))):
            with self.when(eq(op, 7)): self.emit(ite(eq(k, 2), R.INCL, R.INCG), mod(a, 8192))
            with self.when(eq(op, 8)): self.load(k, a, b); self.emit(R.PUSHI, 1); self.emit(R.SUB); self.store(k, a)
            self.set('mode', R.S_INC); self.done()

    def jump_loop(self, isbreak):
        """break / continue: JMP to the innermost loop's break (b) or continue (a) label"""
        csp = self.m(self.v('csp'), 'csp')
        best = self.m(mx(*[mul(and_(lt(k, csp), anyeq(fdiv(self.v(f'csA{k}'), 4096), (R.C_LOOPB, R.C_LOOPB1, R.C_DOB, R.C_DOB1))), k + 1)
                           for k in range(CD)]), 'lpk')
        A = self.m(add(*[mul(eq(best, k + 1), self.v(f'csA{k}')) for k in range(CD)]), 'lpA')
        with self.when(eq(best, 0)): self.fail(56)
        with self.when(ne(best, 0)):
            self.emit(R.JMP, 0, ite(isbreak, mod(A, 64), mod(fdiv(A, 64), 64))); self.set('mode', R.S_INC); self.done()

    def end_expr_stmt(self, P):
        t = self.top()
        k = t[0]
        c1 = self.m(and_(eq(k, R.C_IFC), P(41)), 'e1')
        c2 = self.m(and_(eq(k, R.C_WHILEC), P(41)), 'e2')
        c3 = self.m(and_(eq(k, R.C_FORCOND), P(59)), 'e3')
        c4 = self.m(eq(k, R.C_ASSIGN), 'e4')
        c5 = self.m(eq(k, R.C_IDXA), 'e5')
        c6 = self.m(eq(k, R.C_EXPR), 'e6')
        c7 = self.m(and_(eq(k, R.C_RETURN), or_(P(59), P(R.T_NL), self.v('f_asic'))), 'e7')
        c8 = self.m(and_(anyeq(k, (R.C_DOB, R.C_DOB1)), P(41)), 'e8')
        with self.when(c8):
            self.pop_cs(); self.emit(R.JNZ, 0, t[3]); self.deflab(t[2], self.here()); self.set('f_compl', 1); self.done()
        with self.when(c1):
            self.pop_cs(); la = self.newlab(); self.emit(R.JZ, 0, la); self.push_cs(R.C_IFB, la); self.set('mode', R.S_LBRACE); self.done()
        with self.when(c2):
            self.pop_cs(); le = self.newlab(); self.emit(R.JZ, 0, le); self.push_cs(R.C_LOOPB, t[1], le); self.set('mode', R.S_LBRACE); self.done()
        with self.when(c3):
            self.pop_cs(); self.emit(R.JZ, 0, t[2]); self.emit(R.JMP, 0, t[3]); self.deflab(t[4], self.here())
            self.push_cs(R.C_FORSTEP, t[1], t[2], t[3], t[4], t[5]); self.set('mode', R.S_STMT); self.done()
        with self.when(c4):                                  # t: symbol, compound op, from a declaration
            self.pop_cs()
            with self.when(ne(t[2], 0)): self.emit(t[2])
            self.set_symbool(t[1], self.m(self.v('lb'), 'alb'))
            kk, aa, _, _ = self.symkind_addr(t[1]); self.store(kk, aa)
            vdecl = self.m(and_(P(44), ne(t[3], 0)), 'vdecl')
            with self.when(vdecl): self.set('pn1', sub(t[3], 1)); self.set('pn2', 0); self.set('mode', R.S_VAR); self.done()
            with self.when(not_(vdecl)): self.set('f_simple', 1)
        with self.when(c5):
            self.pop_cs()
            with self.when(ne(t[1], 0)): self.emit(t[1])
            self.emit(R.STOREI); self.set('f_simple', 1)
        with self.when(c6):
            self.pop_cs(); self.emit(R.POP); self.set('f_simple', 1)
        with self.when(c7):
            self.pop_cs()
            rty = self.m(self.v('lb'), 'rty')
            with self.when(ne(rty, 0)):                       # the function returns a boolean / a string
                cfn = self.v('cfn')
                fl = self.m(add(*[mul(eq(cfn, i), I(f'fl_{i}')) for i in range(NF)]), 'rfl')
                self.fnw.append((self.x.g, cfn, add(*[mul(eq(cfn, i), I(f'fh1_{i}')) for i in range(NF)]),
                                 add(*[mul(eq(cfn, i), I(f'fh2_{i}')) for i in range(NF)]), add(mod(fl, 64), mul(rty, 64))))
            self.emit(R.RET, self.v('npar')); self.set('f_compl', 1); self.done()
        with self.when(not_(or_(c1, c2, c3, c4, c5, c6, c7, c8))): self.fail(50)

    def end_simple_stmt(self, P):
        t = self.top()
        with self.when(eq(t[0], R.C_FORINIT)):
            with self.when(not_(P(59))): self.fail(51)
            with self.when(P(59)):
                self.pop_cs(); self.deflab(t[1], self.here()); self.push_cs(R.C_FORCOND, t[1], t[2], t[3], t[4], t[5]); self.set('mode', R.S_OPND); self.done()
        with self.when(eq(t[0], R.C_FORSTEP)):
            with self.when(not_(P(41))): self.fail(52)
            with self.when(P(41)):
                self.pop_cs(); self.emit(R.JMP, 0, t[1]); self.deflab(t[3], self.here())
                self.push_cs(R.C_LOOPB, t[4], t[2], e=t[5]); self.set('mode', R.S_LBRACE); self.done()
        with self.when(and_(ne(t[0], R.C_FORINIT), ne(t[0], R.C_FORSTEP))):
            semi = self.m(or_(P(59), P(R.T_NL), self.v('f_asic')), 'ssemi')
            with self.when(not_(semi)): self.fail(53)
            with self.when(semi): self.set('f_compl', 1); self.done()

    def complete_stmt(self, nonelse, dook=K(1)):
        """close the braceless bodies the finished statement was the body of (see cc_ref)"""
        self.set('mode', R.S_STMT)
        go = K(1); dhit = K(0)
        for _ in range(CD):
            t = self.top(); k = t[0]
            on = self.m(and_(go, gt(self.v('csp'), 0)), 'cso')
            isloop, isdo = self.m(eq(k, R.C_LOOPB1), 'csl'), self.m(and_(eq(k, R.C_DOB1), dook), 'csd')
            close = self.m(and_(on, or_(eq(k, R.C_ELSEB1), isloop, isdo, and_(eq(k, R.C_IFB1), nonelse))), 'csc')
            wait = self.m(and_(on, eq(k, R.C_IFB1), not_(nonelse)), 'csw')
            with self.when(or_(close, wait)): self.set('nlet', t[5])
            with self.when(close):
                self.pop_cs()
                with self.when(isloop): self.emit(R.JMP, 0, t[1])
                self.deflab(ite(isloop, t[2], t[1]), self.here())
            with self.when(wait):
                self.pop_cs(); self.set('pendLa', t[1]); self.set('mode', R.S_ELSE)
            dhit = self.m(or_(dhit, and_(close, isdo)), 'csdh')
            go = self.m(and_(close, not_(isdo)), 'csg')
        with self.when(dhit):                                # the chain stopped at a braceless do body: it stays
            self.set('csp', self.v('csp') + 1); self.set('mode', R.S_DOWHILE)

    def simple_end(self, PNL, PRB):
        """S_VARAFTER / S_INC: the statement ends here (';', a newline, or '}' without ';')"""
        tk0 = self.top()[0]
        forx = self.m(anyeq(tk0, (R.C_FORINIT, R.C_FORSTEP)), 'forx')
        with self.when(and_(PNL, forx)): self.done()
        with self.when(and_(PRB, forx)): self.fail(53)
        with self.when(not_(and_(or_(PNL, PRB), forx))):
            self.set('f_simple', 1)
            with self.when(PRB): self.set('f_asic', 1)

    def close_block(self, flag='f_compl'):
        with self.when(eq(self.v('csp'), 0)): self.fail(54)
        with self.when(gt(self.v('csp'), 0)):
            t = self.pop_cs(); k = t[0]; self.set('nlet', t[5])
            with self.when(eq(k, R.C_BLOCK)): self.set(flag, 1); self.done()
            with self.when(eq(k, R.C_IFB)): self.set('pendLa', t[1]); self.set('mode', R.S_ELSE); self.done()
            with self.when(anyeq(k, (R.C_ELSEB, R.C_DOB))): self.deflab(t[1], self.here())
            with self.when(eq(k, R.C_ELSEB)): self.set(flag, 1); self.done()
            with self.when(eq(k, R.C_DOB)): self.set('csp', self.v('csp') + 1); self.set('mode', R.S_DOWHILE); self.done()
            with self.when(eq(k, R.C_LOOPB)):
                self.emit(R.JMP, 0, t[1]); self.deflab(t[2], self.here()); self.set(flag, 1); self.done()
            with self.when(eq(k, R.C_FUNCB)):
                self.emit(R.PUSHI, 0); self.emit(R.RET, self.v('npar')); self.deflab(t[2], self.v('nloc')); self.deflab(t[1], self.here())
                self.set('curf', 0); self.set('nsym', self.v('fsym')); self.set('mode', R.S_STMT); self.done()
            with self.when(not_(anyeq(k, (R.C_BLOCK, R.C_IFB, R.C_ELSEB, R.C_DOB, R.C_LOOPB, R.C_FUNCB)))): self.fail(55)

    def end_params(self):
        csp = self.m(self.v('csp'), 'csp')
        le = self.m(add(*[mul(eq(csp, k + 1), mod(self.v(f'csA{k}'), 64)) for k in range(CD)]), 'fle')
        self.emit(R.ENTER, 0, le); self.set('mode', R.S_LBRACE); self.done()

    def end_array(self):
        self.emit(R.PUSHI, self.v('arrstart')); self.set('mode', R.S_OPER); self.done()

    def outputs(self):
        """per-level outputs for the overlay: E code slots (word base, label id or -1, RAM index, valid) and one data word"""
        X = self.x; cp0 = S('cp'); E = R.EMAX
        with self.when(gt(sub(self.v('cp'), cp0), E)): self.fail(61)
        self.out = []
        def named(n, node):
            X.temps.append((n, lift(node))); self.out.append(n)
        live = lambda recs: [r for r in recs if not isK(r[0], 0)]
        code, labs, data = live(self.code), live(self.labs), live(self.data)
        def group(valid, vnode, fields):                   # a group whose valid flag is constant 0 is not declared at all
            if isK(vnode, 0): return
            named(valid, vnode)
            for n, node in fields: named(n, node)
        for s in range(E):
            sels = [X.mat(and_(g, eq(addr, add(cp0, s))), 'sel') for g, addr, op, imm, islab in code]
            group(f'o_v{s}', or_(*sels), [
                (f'o_w{s}', add(*[mul(sel, add(mul(op, 8192), mul(1 - islab, imm))) for sel, (g, addr, op, imm, islab) in zip(sels, code)])),
                (f'o_l{s}', sub(add(*[mul(sel, add(imm, 1)) for sel, (g, addr, op, imm, islab) in zip(sels, code) if islab]), 1)),
                (f'o_a{s}', add(cp0, self.cb + s - self.db))])      # RAM index (address - rom_size = data_base)
        self.nlports = len(labs)
        for k, (g, l, v) in enumerate(labs):               # label definitions: one anchor element per port
            group(f'o_lv{k}', g, [(f'o_lj{k}', l), (f'o_lx{k}', v)])
        def port(pre, recs, fields):
            recs = live(recs)
            group(f'o_{pre}w', or_(*[r[0] for r in recs]), [(f'o_{pre}{f}', add(*[mul(r[0], r[i + 1]) for r in recs])) for i, f in enumerate(fields)])
        port('y', self.symw, ('i', 'h1', 'h2', 'k'))
        port('f', self.fnw, ('i', 'h1', 'h2', 'l'))
        group('o_dv', or_(*[g for g, a, v in data]), [('o_da', sub(add(*[mul(g, a) for g, a, v in data]), self.db)),
                                                     ('o_dw', add(*[mul(g, v) for g, a, v in data]))])


class LexProg(Prog):
    """per character: lexer step. inputs c, cn (this and next character), ptk (did the parent level complete a token)"""
    def __init__(self, data_base, c=None, cset=None):
        if cset is not None and len(cset) == 1: c = next(iter(cset)); cset = None
        self.spec_c = c; self.cset = cset; self.db = data_base
        X = self.x = Ctx(LEX_STATE, ['c', 'cn', 'ptk'])
        X.cur.update(tk=K(0), tv=K(0), th1=K(0), th2=K(0))
        self.data = []; self.out = []
        self.lexer()
        tk, tv = self.v('tk'), self.v('tv')
        self.set('lt', ite(ne(tk, 0), or_(inrange(tk, 1, 3), and_(eq(tk, 4), anyeq(tv, (41, 93, 7, 8)))), self.v('lt')))
        self.set('pp', mod(add(self.v('pp'), I('ptk')), 2))
        self.named('o_tk', self.v('tk')); self.named('o_tv', self.v('tv')); self.named('o_th1', self.v('th1')); self.named('o_th2', self.v('th2'))
        self.named('o_tkany', ne(self.v('tk'), 0))
        # token code for variant dispatch: 1 2 3 5 = kinds; 4 = other punctuation; 6 + i = PUNCT[i]
        tk, tv = self.m(self.v('tk'), 'tk'), self.m(self.v('tv'), 'tv')
        self.named('o_tc', add(tk, mul(eq(tk, 4), add(*[mul(eq(tv, v), i + 2) for i, v in enumerate(PUNCT)]))))
        self.named('o_pp', self.v('pp'))
        self.named('o_sv', or_(*[g for g, a, v in self.data]))
        self.named('o_sa', sub(add(*[mul(g, a) for g, a, v in self.data]), self.db))
        self.named('o_sw', add(*[mul(g, v) for g, a, v in self.data]))
        self.x.dce(self.out)
