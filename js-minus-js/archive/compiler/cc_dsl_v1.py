"""cc_dsl.py — the CSS compiler's per-character step, written once in the DSL (dsl.py).

Mirrors cc_ref.Compiler exactly (same state, same limits, same code), but as predicated straight-line code so
it can become one nested element's CSS. build() returns the Ctx plus the step's outputs: code-word candidates,
label definitions and the data word.
"""
from dsl import *
import cc_ref as R

OD, CD, NS, NF, NL = R.OD, R.CD, R.NS, R.NF, R.NL
H1M, H2M = R.H1M, R.H2M
KW = R.KW

LEX_STATE = ['lx', 'tkc', 'acc', 'h1', 'h2', 'p2', 'sstart', 'sdp', 'pp']

def parse_state_names():
    s = ['dp', 'mode', 'pn1', 'pn2', 'osp', 'csp', 'nsym', 'nfn', 'nlab', 'cp', 'curf', 'nloc', 'npar', 'fsym', 'pendLa', 'err', 'arrstart']
    s += [f'op{k}' for k in range(OD)]
    s += [f'csA{k}' for k in range(CD)] + [f'csB{k}' for k in range(CD)]
    s += [x for j in range(NS) for x in (f'sh1_{j}', f'sh2_{j}', f'sk_{j}')]
    s += [x for k in range(NF) for x in (f'fh1_{k}', f'fh2_{k}', f'fl_{k}')]
    s += [f'lab{j}' for j in range(NL)]
    return s

def initial_lex(data_base):
    st = {n: 0 for n in LEX_STATE}; st['sdp'] = data_base + R.SDATA
    return st

def initial_parse(data_base):
    st = {n: 0 for n in parse_state_names()}
    st['dp'] = data_base; st['mode'] = R.S_STMT
    for j in range(NL): st[f'lab{j}'] = -1
    return st

class Base:
    def named(self, n, node):
        self.x.temps.append((n, lift(node))); self.out.append(n)

class Prog(Base):
    """per token (runs on the level after the character that completed it): parser step. inputs tk tv th1 th2"""
    def __init__(self, data_base, code_base, print_fn, puts_fn, mode=None, tk=None):
        """mode / tk: specialise for a known starting mode and token kind (and err == 0) -- the page selects the
        variant with a container query, so each level evaluates only the code reachable from that mode"""
        self.db, self.cb, self.print_fn, self.puts_fn = data_base, code_base, print_fn, puts_fn
        self.spec_mode, self.spec_tk = mode, tk
        X = self.x = Ctx(parse_state_names(), ['tk', 'tv', 'th1', 'th2'])
        X.cur.update(live=K(1), f_expr=K(0), f_simple=K(0), f_compl=K(0))
        if mode is not None: X.cur['mode'] = K(mode); X.cur['err'] = K(0)
        self.code = []      # (valid, addr, op, imm, islab)  addr relative to code base
        self.labs = []      # (valid, label, value)
        self.data = []      # (valid, addr, value)
        self.out = []
        self.parser()
        self.finish()
        self.outputs()

    # ---------------- primitives
    def v(self, n): return self.x.v(n)
    def set(self, n, val): self.x.set(n, val)
    def when(self, c): return self.x.when(c)
    def m(self, e, h='t'): return self.x.mat(e, h)
    def emit(self, op, imm=0, lab=None):
        X = self.x
        islab = 0 if lab is None else 1
        self.code.append((X.g, X.cur['cp'], lift(op), lift(lab if lab is not None else imm), islab))
        self.set('cp', self.v('cp') + 1)
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
    def push_cs(self, kind, a=0, b=0, c=0, d=0):
        csp = self.m(self.v('csp'), 'csp')
        with self.when(ge(csp, CD)): self.fail(21)
        with self.when(lt(csp, CD)):
            A = self.m(add(add(mul(kind, 4096), mul(a, 64)), b)); B = self.m(add(mul(c, 64), d))
            for k in range(CD):
                with self.when(eq(csp, k)):
                    self.set(f'csA{k}', A); self.set(f'csB{k}', B)
            self.set('csp', csp + 1)
    def top(self):
        csp = self.m(self.v('csp'), 'csp')
        A = self.m(add(*[mul(eq(csp, k + 1), self.v(f'csA{k}')) for k in range(CD)]) if CD > 1 else self.v('csA0'), 'topA')
        B = self.m(add(*[mul(eq(csp, k + 1), self.v(f'csB{k}')) for k in range(CD)]), 'topB')
        kind = self.m(fdiv(A, 4096), 'tk'); a = self.m(mod(fdiv(A, 64), 64), 'ta'); b = self.m(mod(A, 64), 'tb')
        c = self.m(fdiv(B, 64), 'tc'); d = self.m(mod(B, 64), 'td')
        return kind, a, b, c, d
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
    def top_op(self):
        osp = self.m(self.v('osp'), 'osp')
        w = self.m(add(*[mul(eq(osp, k + 1), self.v(f'op{k}')) for k in range(OD)]), 'topw')
        return self.m(fdiv(w, 8192), 'topc'), self.m(mod(w, 8192), 'topv')
    def prec(self, code):
        return self.m(add(mul(inrange(code, 10, 12), 6), mul(inrange(code, 8, 9), 5), mul(inrange(code, 13, 16), 4),
                          mul(inrange(code, 17, 18), 3), mul(eq(code, 19), 2), eq(code, 20), mul(inrange(code, 21, 22), 7)), 'prec')
    def popops(self, minprec):
        go = K(1)
        for _ in range(OD):
            code, _v = self.top_op()
            p = self.prec(code)
            go = self.m(and_(go, gt(self.v('osp'), 0), gt(p, 0), ge(p, minprec)), 'pop')
            with self.when(go):
                self.set('osp', self.v('osp') - 1); self.emit(code)
    def lookup(self, h1, h2):
        """index of the latest symbol with this name, or -1"""
        n = self.v('nsym')
        best = mx(*[mul(and_(eq(self.v(f'sh1_{j}'), h1), eq(self.v(f'sh2_{j}'), h2), lt(j, n)), j + 1) for j in range(NS)])
        return self.m(sub(best, 1), 'sym')
    def symkind_addr(self, j):
        sk = self.m(add(*[mul(eq(j, i), self.v(f'sk_{i}')) for i in range(NS)]), 'sk')
        return self.m(fdiv(sk, 16384), 'skk'), self.m(sub(mod(sk, 16384), 8192), 'ska')
    def declare(self, h1, h2, kind, addr):
        n = self.m(self.v('nsym'), 'ns')
        with self.when(ge(n, NS)): self.fail(24)
        with self.when(lt(n, NS)):
            sk = self.m(add(mul(kind, 16384), add(addr, 8192)))
            for j in range(NS):
                with self.when(eq(n, j)):
                    self.set(f'sh1_{j}', h1); self.set(f'sh2_{j}', h2); self.set(f'sk_{j}', sk)
            self.set('nsym', n + 1)
    def fnlab(self, h1, h2):
        n = self.m(self.v('nfn'), 'nf')
        found = self.m(mx(*[mul(and_(eq(self.v(f'fh1_{k}'), h1), eq(self.v(f'fh2_{k}'), h2), lt(k, n)), k + 1) for k in range(NF)]), 'ff')
        oldl = self.m(add(*[mul(eq(found, k + 1), self.v(f'fl_{k}')) for k in range(NF)]), 'fol')
        with self.when(eq(found, 0)):
            with self.when(ge(n, NF)): self.fail(23)
            with self.when(lt(n, NF)):
                l = self.newlab()
                for k in range(NF):
                    with self.when(eq(n, k)):
                        self.set(f'fh1_{k}', h1); self.set(f'fh2_{k}', h2); self.set(f'fl_{k}', l)
                self.set('nfn', n + 1)
        return self.m(ite(eq(found, 0), self.v('nlab') - 1, oldl), 'fnl')
    def load(self, k, a):
        self.emit(ite(eq(k, 2), R.LOADL, R.LOADG), mod(a, 8192))
    def store(self, k, a):
        self.emit(ite(eq(k, 2), R.STOREL, R.STOREG), mod(a, 8192))

    # ---------------- lexer
    def lexer(self):
        c, cn = I('c'), I('cn')
        isal = lambda x: or_(inrange(x, 65, 90), inrange(x, 97, 122), eq(x, 95), eq(x, 36))
        isdg = lambda x: inrange(x, 48, 57)
        lx, p2, tkc = self.m(self.v('lx'), 'lx'), self.m(self.v('p2'), 'p2'), self.m(self.v('tkc'), 'tkc')
        def tok(kind, v=0, a=0, b=0):
            self.set('tk', kind); self.set('tv', v); self.set('th1', a); self.set('th2', b)
        alc, dgc = self.m(isal(c), 'al'), self.m(isdg(c), 'dg')
        alcn, dgcn = self.m(isal(cn), 'aln'), self.m(isdg(cn), 'dgn')
        two = self.m(add(*[mul(and_(eq(c, a), eq(cn, b)), code) for (a, b), code in R.TWO.items()]), 'two')
        with self.when(eq(lx, 1)):
            with self.when(eq(c, 34)):
                self.datum(self.v('sdp'), 0); self.set('sdp', self.v('sdp') + 1); self.set('lx', 0); tok(3, self.v('sstart'))
            with self.when(eq(c, 92)): self.set('lx', 3)
            with self.when(and_(ne(c, 34), ne(c, 92))):
                self.datum(self.v('sdp'), c); self.set('sdp', self.v('sdp') + 1)
        with self.when(eq(lx, 3)):
            self.datum(self.v('sdp'), ite(eq(c, 110), 10, c)); self.set('sdp', self.v('sdp') + 1); self.set('lx', 1)
        with self.when(eq(lx, 2)):
            with self.when(eq(c, 10)): self.set('lx', 0)
        with self.when(eq(lx, 0)):
            with self.when(ne(p2, 0)):
                tok(4, p2); self.set('p2', 0)
            with self.when(eq(p2, 0)):
                sp = self.m(anyeq(c, (9, 10, 13, 32)), 'spc')
                cE = self.m(eq(c, 0), 'cE')
                cG = self.m(and_(not_(cE), not_(sp), eq(c, 47), eq(cn, 47)), 'cG')
                cH = self.m(and_(not_(cE), not_(sp), not_(cG), eq(c, 34)), 'cH')
                rest = self.m(and_(not_(cE), not_(sp), not_(cG), not_(cH)), 'rest')
                cI = self.m(and_(rest, or_(alc, and_(dgc, eq(tkc, 1)))), 'cI')
                cJ = self.m(and_(rest, not_(cI), dgc), 'cJ')
                cK = self.m(and_(rest, not_(cI), not_(cJ), ne(two, 0)), 'cK')
                cL = self.m(and_(rest, not_(cI), not_(cJ), eq(two, 0)), 'cL')
                with self.when(cE): tok(5)
                with self.when(cG): self.set('lx', 2)
                with self.when(cH): self.set('lx', 1); self.set('sstart', self.v('sdp'))
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
            self.token(tk, I('tv'), I('th1'), I('th2'))

    def token(self, tk, tv, th1, th2):
        P = lambda ch: self.m(and_(eq(tk, 4), eq(tv, ch)), f'P{ch}_')
        isID = self.m(eq(tk, 2), 'isID'); isNUM = self.m(eq(tk, 1), 'isNUM'); isSTR = self.m(eq(tk, 3), 'isSTR'); isEOF = self.m(eq(tk, 5), 'isEOF')
        KWc = lambda k: self.m(and_(isID, eq(th1, KW[k][0]), eq(th2, KW[k][1])), 'kw_' + k)
        live = lambda: self.m(self.v('live'), 'live')
        mode = lambda: self.m(self.v('mode'), 'mode')
        def block(md):
            return self.when(and_(live(), eq(mode(), md)))
        # ---- S_NAMES
        with block(R.S_NAMES):
            pn1, pn2 = self.v('pn1'), self.v('pn2')
            j = self.lookup(pn1, pn2)
            k, a = self.symkind_addr(j)
            with self.when(P(61)):
                with self.when(lt(j, 0)): self.fail(5)
                with self.when(ge(j, 0)): self.push_cs(R.C_ASSIGN, j); self.set('mode', R.S_OPND); self.done()
            with self.when(or_(P(7), P(8))):
                with self.when(lt(j, 0)): self.fail(6)
                with self.when(ge(j, 0)):
                    with self.when(P(7)): self.emit(ite(eq(k, 2), R.INCL, R.INCG), mod(a, 8192))
                    with self.when(P(8)): self.load(k, a); self.emit(R.PUSHI, 1); self.emit(R.SUB); self.store(k, a)
                    self.set('mode', R.S_INC); self.done()
            with self.when(P(91)):
                with self.when(lt(j, 0)): self.fail(7)
                with self.when(ge(j, 0)): self.load(k, a); self.push_cs(R.C_IDXA); self.push_op(R.M_IDXA); self.set('mode', R.S_OPND); self.done()
            with self.when(not_(or_(P(61), P(7), P(8), P(91)))):
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
                    l = self.fnlab(pn1, pn2); self.push_op(R.M_CALL, l)
                self.set('mode', R.S_OPND); self.done()
            with self.when(and_(not_(iscon), not_(P(40)))):
                j = self.lookup(pn1, pn2)
                k, a = self.symkind_addr(j)
                with self.when(lt(j, 0)): self.fail(4)
                with self.when(ge(j, 0)):
                    with self.when(P(91)):
                        self.push_op(ite(eq(k, 2), R.M_IDXL, R.M_IDXG), mod(a, 8192)); self.set('mode', R.S_OPND); self.done()
                    with self.when(not_(P(91))):
                        self.load(k, a); self.set('mode', R.S_OPER)
        # ---- S_ELSE
        with block(R.S_ELSE):
            with self.when(KWc('else')):
                lb = self.newlab(); self.emit(R.JMP, 0, lb); self.deflab(self.v('pendLa'), self.here())
                self.push_cs(R.C_ELSEIF, lb); self.set('mode', R.S_AFTERELSE); self.done()
            with self.when(not_(KWc('else'))):
                self.deflab(self.v('pendLa'), self.here()); self.complete_stmt(); self.set('mode', R.S_STMT)
        # ---- S_AFTERELSE
        with block(R.S_AFTERELSE):
            t = self.pop_cs()
            with self.when(KWc('if')):
                self.push_cs(R.C_ELSEIF, t[1]); self.push_cs(R.C_IFC); self.set('mode', R.S_LPAREN); self.done()
            with self.when(and_(not_(KWc('if')), P(123))):
                self.push_cs(R.C_ELSEB, t[1]); self.set('mode', R.S_STMT); self.done()
            with self.when(and_(not_(KWc('if')), not_(P(123)))): self.fail(31)
        # ---- S_STMT
        with block(R.S_STMT):
            with self.when(isEOF):
                with self.when(ne(self.v('csp'), 0)): self.fail(40)
                with self.when(eq(self.v('csp'), 0)): self.emit(R.HALT); self.done()
            with self.when(P(123)): self.push_cs(R.C_BLOCK); self.done()
            with self.when(P(125)): self.close_block()
            with self.when(P(59)): self.done()
            other = self.m(and_(not_(isEOF), not_(P(123)), not_(P(125)), not_(P(59))), 'oth')
            with self.when(and_(other, not_(isID))): self.fail(8)
            with self.when(and_(other, isID)):
                kws = ['var', 'if', 'while', 'for', 'return', 'function']
                with self.when(KWc('var')): self.set('mode', R.S_VAR); self.done()
                with self.when(KWc('if')): self.push_cs(R.C_IFC); self.set('mode', R.S_LPAREN); self.done()
                with self.when(KWc('while')):
                    lh = self.newlab(); self.deflab(lh, self.here()); self.push_cs(R.C_WHILEC, lh); self.set('mode', R.S_LPAREN); self.done()
                with self.when(KWc('for')):
                    l1 = self.newlab(); le = self.newlab(); lb = self.newlab(); l2 = self.newlab()
                    self.push_cs(R.C_FORINIT, l1, le, lb, l2); self.set('mode', R.S_LPAREN); self.done()
                with self.when(KWc('return')): self.push_cs(R.C_RETURN); self.set('mode', R.S_OPND); self.done()
                with self.when(KWc('function')):
                    with self.when(ne(self.v('curf'), 0)): self.fail(41)
                    with self.when(eq(self.v('curf'), 0)):
                        lo = self.newlab(); self.emit(R.JMP, 0, lo); self.set('mode', R.S_FNAME); self.push_cs(R.C_FUNCB, lo); self.done()
                with self.when(not_(or_(*[KWc(k) for k in kws]))):
                    self.set('pn1', th1); self.set('pn2', th2); self.set('mode', R.S_NAMES); self.done()
        # ---- S_VAR
        with block(R.S_VAR):
            with self.when(not_(isID)): self.fail(9)
            with self.when(isID):
                curf = self.m(self.v('curf'), 'curf')
                with self.when(ne(curf, 0)):
                    nl = self.m(self.v('nloc') + 1, 'nl'); self.set('nloc', nl); self.declare(th1, th2, 2, nl)
                with self.when(eq(curf, 0)):
                    self.declare(th1, th2, 1, self.v('dp')); self.set('dp', self.v('dp') + 1)
                self.set('mode', R.S_VARAFTER); self.done()
        # ---- S_VARAFTER
        with block(R.S_VARAFTER):
            with self.when(P(61)): self.push_cs(R.C_ASSIGN, self.v('nsym') - 1); self.set('mode', R.S_OPND); self.done()
            with self.when(not_(P(61))): self.set('f_simple', 1)
        with block(R.S_INC):
            self.set('f_simple', 1)
        with block(R.S_LPAREN):
            with self.when(not_(P(40))): self.fail(32)
            with self.when(P(40)):
                t = self.top()
                self.set('mode', ite(eq(t[0], R.C_FORINIT), R.S_STMT, R.S_OPND)); self.done()
        with block(R.S_LBRACE):
            with self.when(not_(P(123))): self.fail(33)
            with self.when(P(123)): self.set('mode', R.S_STMT); self.done()
        with block(R.S_FNAME):
            with self.when(not_(isID)): self.fail(34)
            with self.when(isID):
                l = self.fnlab(th1, th2); self.deflab(l, self.here())
                self.set('curf', 1); self.set('nloc', 0); self.set('npar', 0); self.set('fsym', self.v('nsym'))
                le = self.newlab()
                csp = self.m(self.v('csp'), 'csp')        # top entry's b field := le
                for k in range(CD):
                    with self.when(eq(csp, k + 1)):
                        A = self.v(f'csA{k}'); self.set(f'csA{k}', add(sub(A, mod(A, 64)), le))
                self.set('mode', R.S_FPAREN); self.done()
        with block(R.S_FPAREN):
            with self.when(not_(P(40))): self.fail(35)
            with self.when(P(40)): self.set('mode', R.S_FPARAM); self.done()
        with block(R.S_FPARAM):
            with self.when(P(41)): self.end_params()
            with self.when(and_(not_(P(41)), not_(isID))): self.fail(36)
            with self.when(and_(not_(P(41)), isID)):
                self.declare(th1, th2, 2, self.v('npar')); self.set('npar', self.v('npar') + 1); self.set('mode', R.S_FPSEP); self.done()
        with block(R.S_FPSEP):
            with self.when(P(44)): self.set('mode', R.S_FPARAM); self.done()
            with self.when(P(41)): self.end_params()
            with self.when(and_(not_(P(44)), not_(P(41)))): self.fail(37)
        with block(R.S_CONLOG):
            with self.when(not_(KWc('log'))): self.fail(38)
            with self.when(KWc('log')): self.set('mode', R.S_CONLP); self.done()
        with block(R.S_CONLP):
            with self.when(not_(P(40))): self.fail(39)
            with self.when(P(40)): self.set('mode', R.S_CONFIRST); self.done()
        with block(R.S_CONFIRST):
            self.push_op(ite(isSTR, R.M_PUTS, R.M_PRINT)); self.set('mode', R.S_OPND)
        with block(R.S_ARR):
            with self.when(P(93)): self.end_array()
            with self.when(and_(not_(P(93)), P(45))): self.set('mode', R.S_ARRNEG); self.done()
            with self.when(and_(not_(P(93)), not_(P(45)), not_(isNUM))): self.fail(42)
            with self.when(and_(not_(P(93)), not_(P(45)), isNUM)):
                self.datum(self.v('dp'), tv); self.set('dp', self.v('dp') + 1); self.set('mode', R.S_ARRSEP); self.done()
        with block(R.S_ARRNEG):
            with self.when(not_(isNUM)): self.fail(42)
            with self.when(isNUM):
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
            with self.when(isSTR): self.emit(R.PUSHI, tv); self.set('mode', R.S_OPER); self.done()
            with self.when(P(40)): self.push_op(R.M_PAREN); self.done()
            with self.when(P(33)): self.push_op(R.NOT); self.done()
            with self.when(P(45)): self.push_op(R.NEG); self.done()
            with self.when(P(91)): self.set('arrstart', self.v('dp')); self.set('mode', R.S_ARR); self.done()
            with self.when(isID): self.set('pn1', th1); self.set('pn2', th2); self.set('mode', R.S_NAMEE); self.done()
            rest = self.m(and_(live(), eq(mode(), R.S_OPND)), 'orest')
            with self.when(rest):
                tc, tvv = self.top_op()
                t = self.top()
                cA = self.m(and_(P(41), gt(self.v('osp'), 0), eq(tc, R.M_CALL)), 'oA')
                cB = self.m(and_(not_(cA), P(59), eq(t[0], R.C_RETURN), eq(self.v('osp'), 0)), 'oB')
                cC = self.m(and_(not_(cA), not_(cB), P(59), eq(t[0], R.C_FORCOND), eq(self.v('osp'), 0)), 'oC')
                with self.when(cA): self.set('osp', self.v('osp') - 1); self.emit(R.CALL, 0, tvv); self.set('mode', R.S_OPER); self.done()
                with self.when(cB): self.emit(R.PUSHI, 0); self.set('f_expr', 1)
                with self.when(cC): self.emit(R.PUSHI, 1); self.set('f_expr', 1)
                with self.when(and_(not_(cA), not_(cB), not_(cC))): self.fail(3)
        # ---- S_OPER
        with block(R.S_OPER):
            binop = self.m(add(*[mul(and_(eq(tk, 4), eq(tv, ch)), op) for ch, op in R.BIN.items()]), 'binop')
            closer = self.m(or_(ne(binop, 0), P(41), P(44), P(93), P(59)), 'closer')
            with self.when(closer):
                self.popops(self.m(ite(ne(binop, 0), self.prec(binop), 1), 'minp'))
            with self.when(ne(binop, 0)):
                self.push_op(binop); self.set('mode', R.S_OPND); self.done()
            cl = self.m(and_(eq(binop, 0), or_(P(41), P(44), P(93))), 'cl')
            with self.when(cl):
                t, tvv = self.top_op()
                osp0 = self.m(self.v('osp'), 'osp0')
                t = self.m(mul(t, gt(osp0, 0)), 'tt')
                with self.when(P(44)):
                    with self.when(not_(anyeq(t, (R.M_CALL, R.M_PUTC, R.M_PRINT, R.M_PUTS)))): self.fail(44)
                    with self.when(anyeq(t, (R.M_CALL, R.M_PUTC, R.M_PRINT, R.M_PUTS))): self.set('mode', R.S_OPND); self.done()
                with self.when(P(93)):
                    with self.when(anyeq(t, (R.M_IDXG, R.M_IDXL))):
                        self.set('osp', osp0 - 1); self.emit(ite(eq(t, R.M_IDXL), R.IDXL, R.IDX), tvv); self.done()
                    with self.when(eq(t, R.M_IDXA)): self.set('osp', osp0 - 1); self.emit(R.ADD); self.set('mode', R.S_IDXEQ); self.done()
                    with self.when(not_(anyeq(t, (R.M_IDXG, R.M_IDXL, R.M_IDXA)))): self.fail(45)
                with self.when(P(41)):
                    with self.when(eq(t, R.M_PAREN)): self.set('osp', osp0 - 1); self.done()
                    with self.when(eq(t, R.M_CALL)): self.set('osp', osp0 - 1); self.emit(R.CALL, 0, tvv); self.done()
                    with self.when(eq(t, R.M_PUTC)): self.set('osp', osp0 - 1); self.emit(R.PUTC); self.emit(R.PUSHI, 0); self.done()
                    with self.when(eq(t, R.M_PRINT)): self.set('osp', osp0 - 1); self.emit(R.CALL, self.print_fn); self.done()
                    with self.when(eq(t, R.M_PUTS)): self.set('osp', osp0 - 1); self.emit(R.CALL, self.puts_fn); self.done()
                    other = self.m(not_(anyeq(t, (R.M_PAREN, R.M_CALL, R.M_PUTC, R.M_PRINT, R.M_PUTS))), 'o41')
                    with self.when(and_(other, gt(osp0, 0))): self.fail(46)
                    with self.when(and_(other, eq(osp0, 0))): self.set('f_expr', 1)
            with self.when(and_(eq(binop, 0), P(59))):
                with self.when(gt(self.v('osp'), 0)): self.fail(47)
                with self.when(eq(self.v('osp'), 0)): self.set('f_expr', 1)
            with self.when(and_(eq(binop, 0), not_(or_(P(41), P(44), P(93), P(59))))): self.fail(48)
        with block(R.S_IDXEQ):
            with self.when(not_(P(61))): self.fail(49)
            with self.when(P(61)): self.set('mode', R.S_OPND); self.done()
        # deferred tails (each is the last thing its path does)
        with self.when(self.v('f_expr')): self.end_expr_stmt(P)
        with self.when(self.v('f_simple')): self.end_simple_stmt(P)
        with self.when(self.v('f_compl')): self.complete_stmt()
        # nothing handled it
        with self.when(self.v('live')): self.fail(99)

    def end_expr_stmt(self, P):
        t = self.top()
        k = t[0]
        c1 = self.m(and_(eq(k, R.C_IFC), P(41)), 'e1')
        c2 = self.m(and_(eq(k, R.C_WHILEC), P(41)), 'e2')
        c3 = self.m(and_(eq(k, R.C_FORCOND), P(59)), 'e3')
        c4 = self.m(eq(k, R.C_ASSIGN), 'e4')
        c5 = self.m(eq(k, R.C_IDXA), 'e5')
        c6 = self.m(eq(k, R.C_EXPR), 'e6')
        c7 = self.m(and_(eq(k, R.C_RETURN), P(59)), 'e7')
        with self.when(c1):
            self.pop_cs(); la = self.newlab(); self.emit(R.JZ, 0, la); self.push_cs(R.C_IFB, la); self.set('mode', R.S_LBRACE); self.done()
        with self.when(c2):
            self.pop_cs(); le = self.newlab(); self.emit(R.JZ, 0, le); self.push_cs(R.C_WHILEB, t[1], le); self.set('mode', R.S_LBRACE); self.done()
        with self.when(c3):
            self.pop_cs(); self.emit(R.JZ, 0, t[2]); self.emit(R.JMP, 0, t[3]); self.deflab(t[4], self.here())
            self.push_cs(R.C_FORSTEP, t[1], t[2], t[3], t[4]); self.set('mode', R.S_STMT); self.done()
        with self.when(c4):
            self.pop_cs(); kk, aa = self.symkind_addr(t[1]); self.store(kk, aa)
            self.set('f_simple', 1)
        with self.when(c5):
            self.pop_cs(); self.emit(R.STOREI); self.set('f_simple', 1)
        with self.when(c6):
            self.pop_cs(); self.emit(R.POP); self.set('f_simple', 1)
        with self.when(c7):
            self.pop_cs(); self.emit(R.RET, self.v('npar')); self.set('f_compl', 1); self.set('mode', R.S_STMT); self.done()
        with self.when(not_(or_(c1, c2, c3, c4, c5, c6, c7))): self.fail(50)

    def end_simple_stmt(self, P):
        t = self.top()
        with self.when(eq(t[0], R.C_FORINIT)):
            with self.when(not_(P(59))): self.fail(51)
            with self.when(P(59)):
                self.pop_cs(); self.deflab(t[1], self.here()); self.push_cs(R.C_FORCOND, t[1], t[2], t[3], t[4]); self.set('mode', R.S_OPND); self.done()
        with self.when(eq(t[0], R.C_FORSTEP)):
            with self.when(not_(P(41))): self.fail(52)
            with self.when(P(41)):
                self.pop_cs(); self.emit(R.JMP, 0, t[1]); self.deflab(t[3], self.here())
                self.push_cs(R.C_FORB, t[2], t[4]); self.set('mode', R.S_LBRACE); self.done()
        with self.when(and_(ne(t[0], R.C_FORINIT), ne(t[0], R.C_FORSTEP))):
            with self.when(not_(P(59))): self.fail(53)
            with self.when(P(59)): self.set('f_compl', 1); self.set('mode', R.S_STMT); self.done()

    def complete_stmt(self):
        go = K(1)
        for _ in range(CD):
            t = self.top()
            go = self.m(and_(go, gt(self.v('csp'), 0), eq(t[0], R.C_ELSEIF)), 'cs')
            with self.when(go):
                self.pop_cs(); self.deflab(t[1], self.here())

    def close_block(self):
        with self.when(eq(self.v('csp'), 0)): self.fail(54)
        with self.when(gt(self.v('csp'), 0)):
            t = self.pop_cs(); k = t[0]
            with self.when(eq(k, R.C_BLOCK)): self.set('f_compl', 1); self.set('mode', R.S_STMT); self.done()
            with self.when(eq(k, R.C_IFB)): self.set('pendLa', t[1]); self.set('mode', R.S_ELSE); self.done()
            with self.when(eq(k, R.C_ELSEB)): self.deflab(t[1], self.here()); self.set('f_compl', 1); self.set('mode', R.S_STMT); self.done()
            with self.when(eq(k, R.C_WHILEB)):
                self.emit(R.JMP, 0, t[1]); self.deflab(t[2], self.here()); self.set('f_compl', 1); self.set('mode', R.S_STMT); self.done()
            with self.when(eq(k, R.C_FORB)):
                self.emit(R.JMP, 0, t[2]); self.deflab(t[1], self.here()); self.set('f_compl', 1); self.set('mode', R.S_STMT); self.done()
            with self.when(eq(k, R.C_FUNCB)):
                self.emit(R.PUSHI, 0); self.emit(R.RET, self.v('npar')); self.deflab(t[2], self.v('nloc')); self.deflab(t[1], self.here())
                self.set('curf', 0); self.set('nsym', self.v('fsym')); self.set('mode', R.S_STMT); self.done()
            with self.when(not_(anyeq(k, (R.C_BLOCK, R.C_IFB, R.C_ELSEB, R.C_WHILEB, R.C_FORB, R.C_FUNCB)))): self.fail(55)

    def end_params(self):
        npar, fsym = self.m(self.v('npar'), 'npar'), self.m(self.v('fsym'), 'fsym')
        for j in range(NS):                                # param i at symbol fsym+i: addr = -1 - npar + i
            with self.when(and_(ge(j, fsym), lt(j, add(fsym, npar)))):
                sk = self.v(f'sk_{j}')
                self.set(f'sk_{j}', add(mul(2, 16384), add(sub(sub(-1, npar), fsym), j + 8192)))
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
        for s in range(E):
            sels = [X.mat(and_(g, eq(addr, add(cp0, s))), 'sel') for g, addr, op, imm, islab in self.code]
            named(f'o_v{s}', or_(*sels))
            named(f'o_w{s}', add(*[mul(sel, add(mul(op, 8192), mul(1 - islab, imm))) for sel, (g, addr, op, imm, islab) in zip(sels, self.code)]))
            named(f'o_l{s}', sub(add(*[mul(sel, add(imm, 1)) for sel, (g, addr, op, imm, islab) in zip(sels, self.code) if islab]), 1))
            named(f'o_a{s}', add(cp0, self.cb + s - 4096))
        named('o_dv', or_(*[g for g, a, v in self.data]))
        named('o_da', sub(add(*[mul(g, a) for g, a, v in self.data]), 4096))
        named('o_dw', add(*[mul(g, v) for g, a, v in self.data]))

    def finish(self):
        """label table update from this step's definitions"""
        for j in range(NL):
            hit = or_(*[and_(g, eq(l, j)) for g, l, _ in self.labs])
            val = add(*[mul(and_(g, eq(l, j)), v) for g, l, v in self.labs])
            with self.when(self.x.mat(hit, 'lh')):
                self.set(f'lab{j}', val)



class LexProg(Prog):
    """per character: lexer step. inputs c, cn (this and next character), ptk (did the parent level complete a token)"""
    def __init__(self, data_base):
        X = self.x = Ctx(LEX_STATE, ['c', 'cn', 'ptk'])
        X.cur.update(tk=K(0), tv=K(0), th1=K(0), th2=K(0))
        self.data = []; self.out = []
        self.lexer()
        self.set('pp', mod(add(self.v('pp'), I('ptk')), 2))
        self.named('o_tk', self.v('tk')); self.named('o_tv', self.v('tv')); self.named('o_th1', self.v('th1')); self.named('o_th2', self.v('th2'))
        self.named('o_tkany', ne(self.v('tk'), 0))
        self.named('o_pp', self.v('pp'))
        self.named('o_sv', or_(*[g for g, a, v in self.data]))
        self.named('o_sa', sub(add(*[mul(g, a) for g, a, v in self.data]), 4096))
        self.named('o_sw', add(*[mul(g, v) for g, a, v in self.data]))

