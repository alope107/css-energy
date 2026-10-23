"""cc_dsl.py — the CSS compiler's per-character step, written once in the DSL (dsl.py).

Mirrors cc_ref.Compiler exactly (same state, same limits, same code), but as predicated straight-line code so
it can become one nested element's CSS. Prog is the parser step (one token), LexProg the lexer step (one
character). Outputs: instruction candidates, label definitions, the data word, table write ports.

Table encodings: sk_j = (type + 4 * const) * 65536 + kind * 16384 + addr + 8192 (a parameter i is addr PARAM0 + i, its frame
slot 1 + i, resolved when read); fl_k = label + 64 * type + 256 * (argument count + 1, or 0 while unknown) (type: 0
number/unknown, 1 boolean, 2 string); iv_k = an interned string's address. Symbols 0..nsym-1 are function / program level,
NS-nlet..NS-1 block-scoped let / const. Control-stack entry k: csA = kind * 4096 + a * 64 + b, csB = e * 4096 + c * 64 + d
(e: nlet when pushed, restored when a body closes). Operator-stack entry: code * 8192 + value. Operand-stack entry: tb * 16384 +
type * 4096 + descriptor (cc_ref's od). An operand is a pair (field, temp?): a temp's field gets the function's frame label added.
"""
from dsl import *
import os
import cc_ref as R

INLINE = os.environ.get('INLINE', '1') == '1'     # (dsl.Ctx.inline: single-use temps into their users)
OD, CD, NS, NF, NL, NI, ODN, TBMAX = R.OD, R.CD, R.NS, R.NF, R.NL, R.NI, R.ODN, R.TBMAX
H1M, H2M = R.H1M, R.H2M
KW = R.KW
OP = R.OP
KBIG, TMP, CND = R.KBIG, R.TMP, R.CND

LEX_STATE = ['lx', 'q', 'lt', 'tkc', 'acc', 'h1', 'h2', 'p2', 'sstart', 'sdp', 'pp', 'inul', 'icm', 'kpos', 'lcon', 'pnl']

def parse_state_names():
    s = ['dp', 'mode', 'pn1', 'pn2', 'osp', 'csp', 'nsym', 'nlet', 'nfn', 'nlab', 'cp', 'curf', 'cfn', 'nfdef', 'nloc', 'npar', 'fsym', 'pendLa',
         'err', 'nint', 'pm', 'nd', 'pk', 'tb', 'nimp', 'obase', 'dbase', 'fcsp', 'flab', 'sv0', 'sv1', 'sv2', 'sv3', 'fmark', 'clab', 'ca']
    s += [f'op{k}' for k in range(OD)]
    s += [f'csA{k}' for k in range(CD)] + [f'csB{k}' for k in range(CD)]
    s += [f'od{k}' for k in range(ODN)]
    return s

def table_names():
    """symbol and function tables: not parser state. Read as inputs; a step writes at most one entry of each
    (write ports o_y* / o_f*), applied by the next level. Labels are not state at all: definitions are outputs."""
    return ([x for j in range(NS) for x in (f'sh1_{j}', f'sh2_{j}', f'sk_{j}')] + [x for k in range(NF) for x in (f'fh1_{k}', f'fh2_{k}', f'fl_{k}')]
            + [x for k in range(NI) for x in (f'ih1_{k}', f'ih2_{k}', f'iv_{k}')])

def initial_lex(data_base):
    st = {n: 0 for n in LEX_STATE}; st['sdp'] = data_base + R.SDATA + 1 + NF     # (cc_ref: past the DONE marker and FTAB)
    return st

def initial_parse(data_base):
    st = {n: 0 for n in parse_state_names()}
    st['dp'] = R.SPCELL + 1; st['mode'] = R.S_STMT        # (global k: data_base + k; cc_ref.NIMP, FCACHE: the implicit globals', the functions')
    st['nsym'] = R.NIMP
    return st

# punctuation codes the parser distinguishes (single chars and the lexer's two-char codes); others share a variant.
# '?' and ':' are not among them: every variant costs some time on every token level, whether it applies or not, and
# only S_OPER (and the modes that fall into it) accepts them, so they share the 'other punctuation' variant there
PUNCT = sorted(({41, 59, 93, 40, 44, 61, 123, 91, 45, 8, 7, 46, 125, 33, R.T_NL, R.T_ARROW, R.T_THIS, R.T_NEW, R.T_PROTO, R.T_PTYPE} | set(R.BIN) | set(R.COMPOUND)) - set(R.BITTOK))     # (cc_ref.BITTOK)
import os
SPEC_LEVEL = os.environ.get('SPECK', 'mtv')     # m: mode only; mt: + token kind; mtv: + punctuation value
# at a statement's start ( [ ! - (cc_ref.XSTART) begin an expression statement: there they share the 'other punctuation'
# variant, which falls into S_OPND (one variant for the five, not one each)
STMTM = (R.S_STMT, R.S_ELSE)
def spec_p(mode, tv): return tv in PUNCT and not (mode in STMTM and tv in R.XSTART)
def variant_key(mode, tk, tv):
    if SPEC_LEVEL == 'm': return (mode, None, None)
    if SPEC_LEVEL == 'mt': return (mode, tk, None)
    return (mode, tk, tv if tk == 4 and spec_p(mode, tv) else None)
def tcode(tk, tv):
    if tk == 4 and tv in PUNCT: return 6 + PUNCT.index(tv)
    return tk
def key_tcodes(key):
    """token codes a variant key covers"""
    m, tk, tv = key
    if tk is None: return list(range(1, 6 + len(PUNCT)))
    if tk == 4 and tv is None:
        if SPEC_LEVEL != 'mtv': return [4] + list(range(6, 6 + len(PUNCT)))
        return [4] + [tcode(4, v) for v in R.XSTART if v in PUNCT and not spec_p(m, v)]
    return [tcode(tk, tv)]
def variant_keys():
    if SPEC_LEVEL == 'm': return [(m, None, None) for m in range(R.NMODES)]
    if SPEC_LEVEL == 'mt': return [(m, k, None) for m in range(R.NMODES) for k in range(1, 6)]
    return [(m, k, v) for m in range(R.NMODES) for k in range(1, 6) for v in (([p for p in PUNCT if spec_p(m, p)] + [None]) if k == 4 else [None])]

ALPHA = set(range(65, 91)) | set(range(97, 123)) | {95, 36}
DIGIT = set(range(48, 58))
NOP0 = (K(0), K(0))                     # the operand fields an instruction leaves unused
BOP0 = (K(512), K(0))

class Base:
    def named(self, n, node):
        self.x.temps.append((n, lift(node))); self.out.append(n)

class Prog(Base):
    """per token (runs on the level after the character that completed it): parser step. inputs tk tv th1 th2"""
    def __init__(self, data_base, code_base, lib, mode=None, tk=None, tv=None):
        """mode / tk: specialise for a known starting mode and token kind (and err == 0) -- the page selects the
        variant with a container query, so each level evaluates only the code reachable from that mode"""
        self.db, self.cb = data_base, code_base
        self.ent = (lib or {}).get('entries', {})   # ROM routines (cc_ref)
        self.spec_mode, self.spec_tk, self.spec_tv = mode, tk, tv
        X = self.x = Ctx(parse_state_names(), ['tk', 'tv', 'th1', 'th2'])
        X.cur.update(live=K(1), f_expr=K(0), f_simple=K(0), f_compl=K(0), f_asic=K(0), f_compl2=K(0), f_imp=K(0))
        X.cur.update({f'sc{c}{f}': K(0) for c in 'AOT' for f in ('', 'l', 'x')}); X.cur['ptop'] = K(0); X.cur['psp'] = K(0)
        if mode is not None: X.cur['mode'] = K(mode); X.cur['err'] = K(0)
        self.code = []      # (valid, instruction index, word0 (op * 8192 + A), 0, word0's label or -1, word1, word1's multiplier, frame label)
        self.labs = []      # (valid, label, value)
        self.data = []      # (valid, addr, value)
        self.symw = []      # (valid, index, h1, h2, sk)
        self.fnw = []       # (valid, index, h1, h2, label)
        self.intw = []      # (valid, index, h1, h2, value)
        self.out = []
        self.parser()
        self.outputs()
        self.x.dce(self.out)
        if INLINE: self.x.inline(set(self.out))

    # ---------------- primitives
    def v(self, n): return self.x.v(n)
    def set(self, n, val): self.x.set(n, val)
    def setif(self, n, c, val):
        """n := val if c (and the current guard): one temp, where a when() block would add a guard temp"""
        X = self.x; X.cur[n] = X.mat(ite(and_(X.g, c), lift(val), X.cur[n]), n + '_')
    def when(self, c): return self.x.when(c)
    def m(self, e, h='t'): return self.x.mat(e, h)
    def frame_label(self): return self.m(self.v('flab'), 'frl')     # (cc_ref: the current function's; temps use it only inside one)
    def fn_enter(self, k):
        """cc_ref.fn_enter"""
        curf = self.m(self.v('curf'), 'fec'); deep = self.m(ge(curf, 2), 'fdeep')
        with self.when(deep): self.fail(41)
        with self.when(not_(deep)):
            with self.when(eq(curf, 0)): self.set('sv0', add(self.v('obase'), mul(self.v('dbase'), 8), mul(self.v('tb'), 128)))
            with self.when(eq(curf, 1)):
                self.set('sv1', add(self.v('nloc'), mul(self.v('npar'), 64), mul(self.v('obase'), 1024), mul(self.v('ca'), 8192)))
                self.set('sv2', add(self.v('dbase'), mul(self.v('tb'), 16), mul(self.v('fsym'), 512), mul(self.v('fmark'), 16384)))
                self.set('sv3', add(self.v('cfn'), mul(self.v('flab'), 16), mul(self.v('fcsp'), 1024)))
            with self.when(eq(curf, 1)): self.deflab(self.v('clab'), R.RETC)     # (the outer function makes closures: its RETs are RETC)
            self.set('curf', curf + 1); self.set('cfn', k); self.set('nloc', 0); self.set('npar', 0); self.set('tb', 0); self.set('ca', 0)
            self.set('fsym', self.v('nsym')); self.set('fmark', self.v('nlet'))
            self.set('obase', self.v('osp')); self.set('dbase', self.v('nd')); self.set('fcsp', self.v('csp'))
            le = self.newlab(); self.set('flab', le); self.set_topA(lambda A: add(sub(A, mod(A, 64)), le))     # (FUNC*'s b: its frame label)
            with self.when(eq(curf, 0)): self.set('clab', self.newlab())       # (its RETs' close label)
    def fn_exit(self):
        """cc_ref.fn_exit"""
        self.set('nsym', self.v('fsym')); c = self.m(self.v('curf') - 1, 'fxc'); self.set('curf', c)
        s0, s1, s2, s3 = (self.m(self.v(n), n + 'x') for n in ('sv0', 'sv1', 'sv2', 'sv3'))
        top = self.m(eq(c, 0), 'fxt')
        self.set('obase', ite(top, mod(s0, 8), mod(fdiv(s1, 1024), 8))); self.set('ca', mul(not_(top), fdiv(s1, 8192))); self.set('dbase', ite(top, mod(fdiv(s0, 8), 16), mod(s2, 16)))
        self.set('tb', ite(top, fdiv(s0, 128), mod(fdiv(s2, 16), 32)))
        self.set('nloc', mul(not_(top), mod(s1, 64))); self.set('npar', mul(not_(top), mod(fdiv(s1, 64), 16)))
        self.set('fsym', mul(not_(top), mod(fdiv(s2, 512), 32))); self.set('fmark', mul(not_(top), fdiv(s2, 16384))); self.set('cfn', mul(not_(top), mod(s3, 16)))
        self.set('flab', mul(not_(top), mod(fdiv(s3, 16), 64))); self.set('fcsp', mul(not_(top), fdiv(s3, 1024)))
    def captured(self, j, k):
        """cc_ref.captured (k: symbol j's kind)"""
        return self.m(and_(eq(k, 2), eq(self.v('curf'), 2), or_(and_(ge(j, R.NIMP), lt(j, self.v('fsym'))), ge(j, sub(NS, self.v('fmark'))))), 'capt')
    def envbase(self, t): self.emit(OP['LDI'], t, (add(258, self.v('npar')), 0), (R.K(0), 0))     # (local 1 past this and the parameters)
    def cread(self, o, t):
        """cc_ref.cread: the captured variable at operand o (its slot: o - 256) into temp t"""
        self.envbase(t); self.emit(OP['LDI'], t, t, (add(o, 640), 0))
    def fnnew(self, argc=0):
        """cc_ref.fnnew -> the new entry's index. argc: its parameters + 1 when end_params follows in this step (one table write)"""
        n = self.m(self.v('nfn'), 'fnn')
        with self.when(ge(n, NF)): self.fail(23)
        with self.when(lt(n, NF)):
            l = self.newlab()                          # (the count only if no label ran out: cc_ref skips end_params then)
            self.fnw.append((self.x.g, n, K(0), add(n, R.H2M), add(l, mul(argc * 256, eq(self.v('err'), 0))))); self.set('nfn', n + 1); self.set('nfdef', self.v('nfdef') + 1)
        return n
    def emit(self, op, a=NOP0, b=BOP0, c=NOP0, label=None, w1=None):
        """cc_ref.emit: op A, B, C with operands (field, temp?), or A and word1 whole (w1: a value, or (field, temp?)); label:
        A is that label's value at link time. Temps add the frame label: times 1 in A, 1024 in B, 1 in C or word1"""
        X = self.x; fl = self.frame_label()
        a, b, c = (lift(a[0]), lift(a[1])), (lift(b[0]), lift(b[1])), (lift(c[0]), lift(c[1]))
        if w1 is None: w, m = add(mul(sub(b[0], 512), 1024), c[0]), add(mul(b[1], 1024), c[1])
        elif isinstance(w1, tuple): w, m = lift(w1[0]), lift(w1[1])
        else: w, m = lift(w1), K(0)
        la = lift(label) if label is not None else ite(a[1], fl, -1)
        self.code.append((X.g, X.cur['cp'], self.m(add(mul(lift(op), 8192), a[0]), 'ew0'), K(0), self.m(la, 'ela'), self.m(w, 'ew'), self.m(m, 'em'), fl))
        self.set('cp', self.v('cp') + 1)
    def deflab(self, l, val): self.labs.append((self.x.g, lift(l), lift(val)))
    def datum(self, addr, val): self.data.append((self.x.g, lift(addr), lift(val)))
    def here(self): return self.m(add(self.v('cp'), self.cb // 2), 'here')     # (cc_ref.here: an instruction pair's index)
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
    def set_top(self, A, B):
        csp = self.m(self.v('csp'), 'csp')
        for k in range(CD):
            with self.when(eq(csp, k + 1)): self.set(f'csA{k}', A); self.set(f'csB{k}', B)
    def set_topB(self, f):
        """top entry's csB := f(old csB)"""
        csp = self.m(self.v('csp'), 'csp')
        for k in range(CD):
            with self.when(eq(csp, k + 1)): self.set(f'csB{k}', f(self.v(f'csB{k}')))
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
        osp = self.m(self.v('osp'), 'osp')       # (none above obase: a function expression's barrier is no operator of its body's)
        w = self.m(mul(gt(osp, self.v('obase')), add(*[mul(eq(osp, k + 1), self.v(f'op{k}')) for k in range(OD)])), 'topw')
        return self.m(fdiv(w, 8192), 'topc'), self.m(mod(w, 8192), 'topv')
    def prec(self, code):
        assert ((R.ADD, R.MUL, R.LT, R.EQ, R.LNE, R.BAND, R.BOR, R.BXOR, R.SHL, R.USHR, R.AND, R.OR, R.NOT, R.BNOT) ==
                (8, 10, 13, 17, 20, 21, 22, 23, 24, 26, 27, 28, 29, 32))
        return self.m(add(mul(inrange(code, 10, 12), 11), mul(inrange(code, 8, 9), 10), mul(inrange(code, 24, 26), 9), mul(inrange(code, 13, 16), 8),
                          mul(inrange(code, 17, 20), 7), mul(eq(code, 21), 6), mul(eq(code, 23), 5), mul(eq(code, 22), 4),
                          mul(eq(code, 27), 3), mul(eq(code, 28), 2), mul(inrange(code, 29, 32), 12),
                          mul(eq(code, R.M_CADD), 10), eq(code, R.M_TELSE)), 'prec')
    def tmerge(self, a, b): return self.m(ite(or_(eq(a, 1), eq(b, 1)), 1, mul(eq(a, b), b)), 'tmg')     # cc_ref.tmerge
    def lookup(self, h1, h2):
        """index of the symbol with this name, or -1 (cc_ref.lookup): scores 3NS+1..4NS the current function's block-scoped
        ones, 2NS+1..3NS its parameters and variables, NS+1..2NS other block-scoped ones, 1..NS other names (the latest first)"""
        n, lo = self.v('nsym'), self.m(sub(NS, self.v('nlet')), 'slo')
        ni = self.v('nimp')                             # (entries 0 ... NIMP - 1: the implicit globals, nimp of them)
        fs, fm = self.v('fsym'), self.m(sub(NS, self.v('fmark')), 'sfm')
        best = self.m(mx(*[mul(and_(eq(I(f'sh1_{j}'), h1), eq(I(f'sh2_{j}'), h2)),
                               add(mul(lt(j, ni if j < R.NIMP else n), j + 1 + mul(ge(j, fs), 2 * NS)), mul(ge(j, lo), 2 * NS - j + mul(lt(j, fm), 2 * NS))))
                           for j in range(NS)]), 'sbest')
        return self.m(ite(gt(best, 3 * NS), sub(4 * NS, best), ite(gt(best, 2 * NS), sub(best, 2 * NS + 1), ite(gt(best, NS), sub(2 * NS, best), sub(best, 1)))), 'sym')
    def sym_sel(self, j, f, h):
        return self.m(add(*[mul(eq(j, i), I(f'{f}{i}')) for i in range(NS)]), h)
    def symkind_addr(self, j):
        """kind, operand (cc_ref.var), static type, const flag of symbol j"""
        sk = self.sym_sel(j, 'sk_', 'sk')
        b = self.m(mod(fdiv(sk, 65536), 4), 'skb'); r = self.m(mod(sk, 65536), 'skr'); cst = self.m(fdiv(sk, 262144), 'skc')
        k, a = self.m(fdiv(r, 16384), 'skk'), self.m(sub(mod(r, 16384), 8192), 'ska')
        # parameter i is stored as kind 2, addr PARAM0 + i: its frame slot is 1 + i
        ispar = self.m(and_(eq(k, 2), ge(a, R.PARAM0)), 'spar')
        o = self.m(ite(eq(k, 2), add(257, ite(ispar, sub(a, R.PARAM0 - 1), a)), a), 'svar')     # (past this: cc_ref.th)
        return k, o, b, cst
    def set_symbool(self, j, b):
        """cc_ref.settype: symbol j's type := b (write port: the whole entry), unless this step wrote an implicit global's entry
        (f_imp): then the type stays, or error 61 if it was a string's"""
        sk = self.sym_sel(j, 'sk_', 'sk'); old = self.m(mod(fdiv(sk, 65536), 4), 'syo')
        fi = self.m(and_(self.v('f_imp'), ne(old, b)), 'syfi')
        with self.when(and_(fi, eq(old, 2))): self.fail(61)
        with self.when(not_(self.v('f_imp'))):
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
    def isres(self, h1, h2):
        """cc_ref.RESERVED: a reserved word's name"""
        return or_(*[and_(eq(h1, a), eq(h2, b)) for a, b in R.RESERVED])
    def implicit(self, h1, h2, assign):
        """cc_ref.implicit: an undeclared name's global -> its symbol index"""
        assign = lift(assign)
        top = self.m(and_(eq(self.v('curf'), 0), assign), 'itop')
        n, k = self.m(self.v('nsym'), 'ins'), self.m(self.v('nimp'), 'ink')
        with self.when(top):
            full = self.m(ge(self.v('dp'), R.SDATA), 'igf')
            with self.when(full): self.fail(25)
            with self.when(not_(full)): self.declare(h1, h2, 1, self.v('dp')); self.set('dp', self.v('dp') + 1)
        with self.when(not_(top)):
            with self.when(ge(k, R.NIMP)): self.fail(24)
            with self.when(lt(k, R.NIMP)):
                self.symw.append((self.x.g, k, lift(h1), lift(h2), self.m(add(mul(ite(assign, 1, 3), 16384), k, R.IMPC + 8192), 'isk')))
                self.set('nimp', k + 1); self.set('f_imp', 1)
        return self.m(ite(top, n, k), 'ij')
    def sym_kind(self, j, kind, cst):
        """symbol j's kind := kind, its const flag := cst (cc_ref: an implicit global assigned, a var of a global's name)"""
        sk = self.sym_sel(j, 'sk_', 'sk')
        self.symw.append((self.x.g, lift(j), self.sym_sel(j, 'sh1_', 'sy1'), self.sym_sel(j, 'sh2_', 'sy2'),
                          self.m(add(mod(sk, 16384), mul(mod(fdiv(sk, 65536), 4), 65536), mul(kind, 16384), mul(cst, 262144)), 'syk2')))
    def decl_blk(self):
        """cc_ref.decl_blk: let / const (pn1 1 / 2) below the function or program level"""
        return self.m(and_(gt(self.v('pn1'), 0), gt(self.v('csp'), self.v('fcsp'))), 'dblk')
    def fnlook(self, h1, h2):
        """cc_ref.fnlook: the function named h1 / h2's index, or -1"""
        n = self.m(self.v('nfn'), 'nf')
        return self.m(sub(mx(*[mul(and_(eq(I(f'fh1_{k}'), h1), eq(I(f'fh2_{k}'), h2), lt(k, n)), k + 1) for k in range(NF)]), 1), 'flk')
    def fnfind(self, h1, h2):
        """-> (index, label, type) of the function named h1/h2, adding it (with a new label) if absent"""
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
                self.m(ite(new, 0, mod(fdiv(oldl, 64), 4)), 'fnb'))
    def intern(self, h1, h2, vnew, ln):
        """cc_ref.intern: -> (address, ok) of the interned string h1 / h2, entering vnew if it is new (fail 68 when full); writes
        this copy's length word"""
        self.datum(sub(vnew, 1), ln)
        n = self.m(self.v('nint'), 'nin')
        found = self.m(mx(*[mul(and_(eq(I(f'ih1_{k}'), h1), eq(I(f'ih2_{k}'), h2), lt(k, n)), k + 1) for k in range(NI)]), 'ifd')
        oldv = self.m(add(*[mul(eq(found, k + 1), I(f'iv_{k}')) for k in range(NI)]), 'iov')
        new = self.m(eq(found, 0), 'inew'); full = self.m(and_(new, ge(n, NI)), 'ifull')
        with self.when(full): self.fail(68)
        with self.when(and_(new, not_(full))):
            self.intw.append((self.x.g, n, lift(h1), lift(h2), lift(vnew))); self.set('nint', n + 1)
        return self.m(ite(new, vnew, oldv), 'ival'), self.m(not_(full), 'iok')

    # ---------------- operands (cc_ref's operand stack)
    def odv(self, i): return self.m(add(*[mul(eq(i, k), self.v(f'od{k}')) for k in range(ODN)]), 'odv') if not isK(lift(i)) else self.v(f'od{lift(i).v}')
    def desc(self, i): return self.m(mod(self.odv(i), 4096), 'dsc')
    def otype(self, i): return self.m(mod(fdiv(self.odv(i), 4096), 4), 'oty')
    def set_od(self, i, d, t=None, c=K(1)):
        """entry i := descriptor d of type t at the current tb (t None: d is the whole entry), if c; a dynamic i selects inside each
        entry's update (no guard per entry)"""
        w = self.m(add(mul(self.v('tb'), 16384), mul(t, 4096), d) if t is not None else d, 'odw'); i = lift(i)
        if isK(i): self.setif(f'od{i.v}', c, w); return
        for k in range(ODN): self.setif(f'od{k}', and_(c, eq(i, k)), w)
    def tmp(self, i):
        inf = self.m(gt(self.v('curf'), 0), 'inf')     # (inside a function: past its this, and its frame label)
        return (self.m(add(257, inf, self.v('npar'), self.v('tb'), i, mul(self.v('dbase'), -1)), 'tmpf'), inf)
    def arg_end(self):
        """cc_ref.arg_end: the top into its temp, off the operand stack (tb past it)"""
        i = self.m(self.v('nd') - 1, 'aei'); self.to_temp(i); self.set('nd', i); self.set('tb', self.v('tb') + 1)
    def opnd(self, i, d=None):
        """descriptor i (d: its descriptor, if known) as an operand (field, temp?), where it can't be a big constant"""
        d = self.desc(i) if d is None else d; ist = self.m(eq(d, TMP), 'ist'); t = self.tmp(i)
        return self.m(ite(ist, t[0], d), 'opf'), self.m(mul(ist, t[1]), 'opt')
    def src(self, i):
        """cc_ref.src: a big constant is loaded into its temp first"""
        with self.when(eq(self.desc(i), KBIG)):
            self.emit(OP['LOADK'], self.tmp(i), w1=self.v('pk')); self.set_od(i, TMP, self.otype(i))
        return self.opnd(i)
    def put(self, dst, i):
        """cc_ref.put: the value of descriptor i into operand dst: LOADK, or MOV unless it is there"""
        kb = self.m(eq(self.desc(i), KBIG), 'pkb'); o = self.opnd(i)
        same = self.m(and_(not_(kb), eq(o[0], dst[0]), eq(o[1], dst[1])), 'psame')
        with self.when(not_(same)):
            self.emit(ite(kb, OP['LOADK'], OP['MOV']), dst, w1=(ite(kb, self.v('pk'), mul(sub(o[0], 512), 1024)), mul(not_(kb), mul(o[1], 1024))))
    def to_temp(self, i):
        self.put(self.tmp(i), i); self.set_od(i, TMP, self.otype(i))
    def push_od(self, d, t, k=None):
        """cc_ref.push_od: a big constant below the new entry goes to its temp first"""
        nd = self.m(self.v('nd'), 'pnd0'); full = self.m(or_(ge(nd, ODN), ge(add(nd, self.v('tb')), TBMAX)), 'pfull')
        with self.when(full): self.fail(22)
        with self.when(not_(full)):
            with self.when(gt(nd, 0)): self.src(nd - 1)
            self.set_od(nd, d, t); self.set('nd', nd + 1)
            if k is not None:
                with self.when(eq(lift(d), KBIG)): self.set('pk', k)
    def snapshot(self, hit, n=None):
        """cc_ref.snapshot: operands below n that are variables hit(descriptor) are copied to their temps"""
        n = self.v('nd') if n is None else n
        for k in range(ODN):
            w = self.v(f'od{k}'); d = self.m(mod(w, 4096), 'sdsc')
            with self.when(and_(lt(k, n), ge(k, self.v('dbase')), lt(d, 768), hit(d))):        # (its temp: at the tb it was pushed at)
                tbk = self.m(fdiv(w, 16384), 'stb')
                inf = self.m(gt(self.v('curf'), 0), 'inf')
                self.emit(OP['MOV'], (self.m(add(257, inf, self.v('npar'), tbk, k, mul(self.v('dbase'), -1)), 'stf'), inf), (d, 0))
                self.set_od(k, add(mul(tbk, 16384), mul(mod(fdiv(w, 4096), 4), 4096), TMP))
    def pend(self, i, ci, b, c):
        """cc_ref.pend: descriptor i := the pending comparison ci (CNDOPS' index) of b and c"""
        self.set_od(i, add(CND + 0, mul(ci, 4), mul(b[1], 2), c[1]), 1); self.set('pk', add(mul(sub(b[0], 512), 1024), c[0]))
    def branch(self, lab, sense):
        """cc_ref.branch: pop the top value and jump to lab if its truth is sense (a pending comparison fuses into the jump)"""
        sense = lift(sense); nd = self.m(self.v('nd'), 'bnd'); i = self.m(nd - 1, 'bi'); d = self.desc(i); t = self.otype(i)
        cnd = self.m(ge(d, CND), 'bcnd'); e = self.m(sub(d, CND), 'bce'); ci = self.m(fdiv(e, 4), 'bci')
        pk = self.v('pk')
        bF, cF = (self.m(add(fdiv(pk, 1024), 512), 'bbf'), self.m(mod(fdiv(e, 2), 2), 'bbt')), (self.m(mod(pk, 1024), 'bcf'), self.m(mod(e, 2), 'bct'))
        jn = lambda c: OP['J' + R.DYN[c][1:]]                                         # (user code: == / != are the loose jumps)
        jt = [jn(c) for c in R.CMPS] + [OP['JZ']]                                     # by CNDOPS' index, when sense (! b: b false)
        jf = [OP['JN' + R.NAME[c]] if c in (R.LT, R.GT, R.LE, R.GE) else jn(R.INV[c]) for c in R.CMPS] + [OP['JNZ']]     # (cc_ref.jname)
        jop = self.m(ite(sense, add(*[mul(eq(ci, k), v_) for k, v_ in enumerate(jt)]), add(*[mul(eq(ci, k), v_) for k, v_ in enumerate(jf)])), 'bjop')
        isk = self.m(and_(ge(d, 768), lt(d, 1024)), 'bisk')
        kbn = self.m(and_(eq(d, KBIG), ne(t, 2)), 'bkbn')
        ktrue = and_(ne(d, R.K(0)), not_(inrange(d, R.K(R.FALSE), R.K(R.MZERO))))     # (a constant's truth: the falsy specials)
        jumpc = self.m(or_(and_(isk, eq(ktrue, sense)), and_(kbn, eq(ne(pk, 0), sense))), 'bjc')
        other = self.m(not_(or_(cnd, isk, kbn)), 'both')
        with self.when(other): o = self.src(i)
        self.set('nd', i)
        with self.when(or_(cnd, jumpc, other)):
            op = ite(cnd, jop, ite(other, ite(sense, OP['JNZ'], OP['JZ']), OP['JMP']))
            self.emit(op, b=(ite(cnd, bF[0], ite(other, o[0], 512)), ite(cnd, bF[1], mul(other, o[1]))),
                      c=(mul(cnd, cF[0]), mul(cnd, cF[1])), label=lab)
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
        SEND = R.SEND                                  # the end of the string area (cc_ref.sbyte)
        # the NUL after an identifier's bytes (cc_ref.char)
        inul = self.m(self.v('inul'), 'inul')
        with self.when(and_(ne(inul, 0), lt(inul, SEND))): self.datum(inul, 0)
        self.set('inul', 0)
        def shash(x):
            self.set('h1', mod(add(mul(self.v('h1'), 31), x), H1M)); self.set('h2', mod(add(mul(self.v('h2'), 37), x), H2M))
        def tok(kind, v=0, a=0, b=0):
            self.set('tk', kind); self.set('tv', v); self.set('th1', a); self.set('th2', b)
        def adv(): self.set('sdp', self.v('sdp') + 1)
        def strtok(noroom, a, ln):
            """a string's or name's token value: its address - data_base (or 1024: it didn't fit) + 2048 * its length"""
            return add(ite(noroom, 1024, sub(a, self.db)), mul(ln, 2048))
        alc, dgc = self.m(cpred(isal, ALPHA), 'al'), self.m(cpred(isdg, DIGIT), 'dg')
        alcn, dgcn = self.m(isal(cn), 'aln'), self.m(isdg(cn), 'dgn')
        two = self.m(add(*[mul(and_(ceq(a), eq(cn, b)), code) for (a, b), code in R.TWO.items()]), 'two')
        cE = self.m(ceq(0), 'cE')
        eof = self.m(and_(cE, ne(lx, 0)), 'eofx')
        with self.when(eof): self.set('lx', 0); self.set('p2', 0); tok(5)
        L = lambda n: self.m(and_(not_(eof), eq(lx, n)), f'lx{n}_')
        with self.when(L(1)):
            cq = self.m(eq(c, self.v('q')), 'cq')
            with self.when(cq):                             # tv: strtok(); th1 / th2: its hash
                sdq = self.m(self.v('sdp'), 'sdq'); ss = self.m(self.v('sstart'), 'ss')
                self.datum(sdq, 0); self.set('sdp', sdq + 1); self.set('lx', 0)
                tok(3, strtok(gt(sdq + 1, SEND), ss, sub(sdq, ss)), self.v('h1'), self.v('h2'))
            with self.when(and_(not_(cq), ceq(92))): self.set('lx', 3)
            with self.when(and_(not_(cq), not_(ceq(92)))):
                self.datum(self.v('sdp'), c); adv(); shash(c)
        with self.when(L(3)):
            eb = self.m(ite(ceq(110), 10, ite(ceq(116), 9, ite(ceq(114), 13, c))), 'esc')
            self.datum(self.v('sdp'), eb); adv(); self.set('lx', 1); shash(eb)
        def newline():                                  # cc_ref.newline: after return a T_NL now, else pending
            with self.when(eq(ltk, 2)): tok(4, R.T_NL)
            with self.when(eq(ltk, 1)): self.set('pnl', 1)
        with self.when(L(2)):
            with self.when(ceq(10)): self.set('lx', 0); newline()
        with self.when(L(4)):
            with self.when(and_(ceq(42), eq(cn, 47))): self.set('lx', 5)
            with self.when(ceq(10)): newline()
        with self.when(L(5)): self.set('lx', 0)
        with self.when(L(6)): self.set('lx', 4)
        with self.when(L(0)):
            with self.when(ne(p2, 0)):                      # (c: a two-character token's second; < and > are punctuation)
                ext = self.m(and_(ceq(62), eq(p2, 16), eq(cn, 62)), 'p2x')                      # >> then >: >>> (or >>>=)
                asg = self.m(and_(or_(ceq(60), ceq(62)), inrange(p2, 15, 17), eq(cn, 61)), 'p2a')     # <<= >>= >>>=
                with self.when(ext): self.set('p2', 17)
                with self.when(not_(ext)):
                    tok(4, add(p2, mul(asg, 6)), and_(or_(eq(p2, 1), eq(p2, 2)), ne(cn, 61))); self.set('p2', 0)     # (== / !=: hash1 is the flag, cc_ref.tflag)
                    with self.when(or_(and_(or_(eq(p2, 1), eq(p2, 2)), eq(cn, 61)), asg)): self.set('lx', 5)
            with self.when(eq(p2, 0)):
                sp = self.m(or_(*[ceq(v) for v in R.BLANK]), 'spc')
                with self.when(ceq(10)): newline()
                cG = self.m(and_(not_(cE), not_(sp), ceq(47), eq(cn, 47)), 'cG')
                cB = self.m(and_(not_(cE), not_(sp), ceq(47), eq(cn, 42)), 'cB')
                cH = self.m(and_(not_(cE), not_(sp), or_(ceq(34), ceq(39))), 'cH')
                rest = self.m(and_(not_(cE), not_(sp), not_(cG), not_(cB), not_(cH)), 'rest')
                cJ = self.m(and_(rest, or_(ge(tkc, 2), and_(dgc, ne(tkc, 1)))), 'cJ')      # a number (cc_ref.char: tkc 2 3 4 5)
                cI = self.m(and_(rest, not_(cJ), or_(alc, and_(dgc, eq(tkc, 1)))), 'cI')
                cK = self.m(and_(rest, not_(cI), not_(cJ), ne(two, 0)), 'cK')
                cL = self.m(and_(rest, not_(cI), not_(cJ), eq(two, 0)), 'cL')
                with self.when(cE): tok(5)
                with self.when(cG): self.set('lx', 2)
                with self.when(cB): self.set('lx', 6)
                with self.when(cH):
                    sdp = self.m(self.v('sdp'), 'sdp0')
                    self.set('lx', 1); self.set('q', c); self.set('sdp', sdp + 1); self.set('sstart', sdp + 1)     # (sdp: the length word)
                    self.set('h1', 0); self.set('h2', 0)
                with self.when(cI):                         # an identifier: hashed, its bytes at sdp (acc: its length so far)
                    keep = self.m(eq(tkc, 1), 'kp')
                    nh1 = self.m(mod(add(mul(mul(keep, self.v('h1')), 31), c), H1M), 'nh1')
                    nh2 = self.m(mod(add(mul(mul(keep, self.v('h2')), 37), c), H2M), 'nh2')
                    self.set('h1', nh1); self.set('h2', nh2); self.set('tkc', 1)
                    sdp = self.m(self.v('sdp'), 'sdp1'); ln = self.m(mul(keep, self.v('acc')), 'iln')
                    kp = self.m(self.v('kpos'), 'kpos')        # maybe a property name: its bytes (cc_ref.char)
                    with self.when(and_(ne(kp, 0), lt(add(sdp, ln + 1), SEND))): self.datum(add(sdp, ln + 1), c)     # (sdp: the length word)
                    self.set('acc', ln + 1)
                    with self.when(not_(or_(alcn, dgcn))):     # tv: strtok()
                        pk = self.m(add(*[mul(and_(eq(nh1, h1), eq(nh2, h2)), code) for (h1, h2), code in R.PKW.items()]), 'npk')     # (this / new ...: punctuation, cc_ref.PKW)
                        tok(ite(ne(pk, 0), 4, 2), ite(ne(pk, 0), pk, add(strtok(ge(add(sdp, ln + 2), SEND), sdp + 1, ln + 1), mul(eq(cn, 40), 262144))), nh1, nh2)
                        self.set('tkc', 0)
                        with self.when(ne(kp, 0)): self.set('inul', add(sdp, ln + 2))
                        with self.when(eq(kp, 2)): self.set('sdp', add(sdp, ln + 3))
                        self.set('icm', mul(eq(kp, 1), ln + 3))
                with self.when(cJ):                         # its characters at sdp (a double's string), its integer value (acc)
                    fr = self.m(lt(tkc, 2), 'nfr'); st0 = self.m(ite(fr, 2, tkc), 'nst0')
                    acc0 = self.m(mul(not_(fr), self.v('acc')), 'nac0'); h10 = self.m(mul(not_(fr), self.v('h1')), 'nh10')
                    dg2 = self.m(and_(dgc, eq(st0, 2)), 'ndg2'); dot = self.m(ceq(46), 'ndot'); ee = self.m(or_(ceq(69), ceq(101)), 'nee')
                    nst = self.m(ite(dg2, 2, ite(dot, 3, ite(ee, 4, ite(eq(st0, 4), 5, st0)))), 'nst')
                    nacc = self.m(ite(dg2, add(mul(acc0, 10), sub(c, 48)), acc0), 'nacc')
                    nh2 = self.m(or_(and_(not_(fr), self.v('h2')), dot, ee), 'nh2'); nh1 = self.m(h10 + 1, 'nh1')
                    sdp = self.m(self.v('sdp'), 'sdp2')
                    with self.when(lt(add(sdp, h10 + 1), SEND)): self.datum(add(sdp, h10 + 1), c)
                    self.set('tkc', nst); self.set('acc', nacc); self.set('h1', nh1); self.set('h2', nh2)
                    more = self.m(or_(dgcn, and_(eq(nst, 2), anyeq(cn, (46, 69, 101))), and_(eq(nst, 3), anyeq(cn, (69, 101))),
                                      and_(eq(nst, 4), anyeq(cn, (43, 45)))), 'nmore')
                    with self.when(not_(more)):
                        nbad = self.m(or_(eq(nst, 4), and_(eq(nst, 5), not_(dgc))), 'nbad')     # cc_ref: an exponent without digits
                        with self.when(nbad): tok(4, 31)
                        isd = self.m(and_(not_(nbad), or_(nh2, gt(nacc, R.SMI_HI))), 'nisd')      # a double: its string, committed
                        with self.when(isd):
                            tok(1, strtok(gt(add(sdp, nh1 + 2), SEND), sdp + 1, nh1), 0, 1)
                            self.set('inul', add(sdp, nh1 + 1)); self.set('sdp', add(sdp, nh1 + 2))
                        with self.when(and_(not_(nbad), not_(isd))): tok(1, nacc)
                        self.set('tkc', 0)
                with self.when(cK): self.set('p2', two)
                with self.when(cL): tok(4, c)
        # the pending newline (cc_ref.char): decided at the blank before the next significant character, or on it (+ - /)
        pnl = self.m(self.v('pnl'), 'pnl')
        gap = self.m(or_(and_(L(2), ceq(10)), L(5), and_(L(0), eq(p2, 0), or_(*[ceq(v) for v in R.BLANK]))), 'gap')
        with self.when(and_(pnl, gap)):
            cont = self.m(anyeq(cn, R.CONT), 'cont'); wait = self.m(anyeq(cn, R.BLANK + (47, 43, 45)), 'wait')
            with self.when(cont): self.set('pnl', 0)
            with self.when(and_(not_(cont), not_(wait))): tok(4, R.T_NL); self.set('pnl', 0)
        with self.when(and_(pnl, not_(gap), L(0), eq(p2, 0))):
            with self.when(or_(ceq(43), ceq(45))):
                with self.when(eq(cn, c)): tok(4, R.T_NL)
                self.set('pnl', 0)
            with self.when(and_(ceq(47), ne(cn, 47), ne(cn, 42))): self.set('pnl', 0)


    def popops(self, minprec, br=K(0), dvalid=K(0), dfield=K(0)):
        """cc_ref.popops: pop and emit operators with precedence >= minprec (br: a comparison or ! popped last stays pending;
        dvalid: the last writes operand dfield). One instruction per pop at most: a big constant on top goes to its temp before
        the first. && / || and a ternary's M_TELSE define their join labels after their moves; at most one of each is popped
        (the stack's precedences increase upwards between markers, and cc_ref's M_TELSE chain rule keeps one M_TELSE per
        segment), so they are collected and defined afterwards. Every pop writes the new top entry of the operand stack (the
        left operand's for && || and binary operators, else the right one's): the top is kept in ptop through the pops and
        written once at the end."""
        minprec, br, dvalid, dfield = lift(minprec), lift(br), lift(dvalid), lift(dfield)
        c0, v0 = self.top_op(); p0 = self.prec(c0); nd0 = self.m(self.v('nd'), 'ppn'); osp0 = self.m(self.v('osp'), 'ppo')
        v1 = self.m(mod(add(*[mul(eq(osp0, k + 2), self.v(f'op{k}')) for k in range(OD - 1)]), 8192), 'ppv1')     # (M_PRINT below M_CADD)
        split0 = and_(eq(c0, R.M_CADD), or_(eq(v0, 2), eq(self.otype(nd0 - 1), 2)), lt(v1, 4 * (R.PIECES - 1)))
        with self.when(and_(gt(self.v('osp'), 0), gt(p0, 0), ge(p0, minprec), gt(nd0, 0), not_(split0))): self.src(nd0 - 1)
        self.set('ptop', self.odv(nd0 - 1)); popped = K(0)
        go = K(1); cap = R.popcap(minprec.v) if isK(minprec) else OD      # (a binary operator's variant: cc_ref.popcap)
        code, val = c0, v0; p = p0
        for _ in range(cap):
            go = self.m(and_(go, eq(self.v('err'), 0), gt(self.v('osp'), 0), gt(p, 0), ge(p, minprec)), 'pop')
            with self.when(go):
                self.set('osp', self.v('osp') - 1)
                c2, v2 = self.top_op(); p2 = self.prec(c2)
                last = self.m(not_(and_(gt(self.v('osp'), 0), gt(p2, 0), ge(p2, minprec))), 'plast')
                nd = self.m(self.v('nd'), 'pnd'); iR, iL = self.m(nd - 1, 'piR'), self.m(nd - 2, 'piL')
                ptop = self.v('ptop'); dR, tR, tL = self.m(mod(ptop, 4096), 'pdR'), self.m(mod(fdiv(ptop, 4096), 4), 'ptR'), self.otype(iL)
                oR, oL, TR, TL = self.opnd(iR, dR), self.opnd(iL), self.tmp(iR), self.tmp(iL)
                isAO = self.m(or_(eq(code, R.AND), eq(code, R.OR)), 'pao'); isTE = self.m(eq(code, R.M_TELSE), 'pte')
                isUN = self.m(inrange(code, R.NOT, R.BNOT), 'pun'); isCA = self.m(eq(code, R.M_CADD), 'pca')
                hasstr = self.m(or_(eq(val, 2), eq(tR, 2)), 'pstr')
                popped = self.m(or_(popped, go), 'ppd')
                ok = K(1)
                split = self.m(and_(isCA, hasstr, lt(v2, 4 * (R.PIECES - 1))), 'psplit')     # (past PIECES: the last two joined)
                isBIN = self.m(not_(or_(isAO, isTE, isUN, split)), 'pbin')            # (M_CADD that doesn't split: ADD)
                binc = self.m(ite(isCA, R.ADD, code), 'pbc')
                iscmp = self.m(inrange(code, R.LT, R.LNE), 'picmp')
                pnot = self.m(and_(eq(code, R.NOT), last, br), 'pnot')
                pcmp = self.m(and_(isBIN, last, br, iscmp), 'pcmp')               # (a branch takes it: the jump traps for non-integers)
                isd = self.m(and_(last, dvalid), 'pisd')
                # the one instruction: && / || MOV T(iL), right; M_TELSE MOV T(iR), right (if not there); ! / - (dest or T(iR));
                # binary (dest or T(iL)) left op right
                with self.when(and_(ok, or_(isAO, and_(isTE, ne(dR, TMP)), and_(isUN, not_(pnot)), and_(isBIN, not_(pcmp))))):
                    dopc, bs = self.dop(binc)
                    op = ite(or_(isAO, isTE), OP['MOV'], ite(isUN, ite(eq(code, R.NOT), OP['NOT'], ite(eq(code, R.NEG), OP['DNEG'],
                                                                    ite(eq(code, R.TYPEOF), OP['KIND'], OP['DBIT']))), dopc))
                    dst = add(ite(isAO, TL[0], ite(or_(isTE, and_(isUN, not_(isd))), TR[0], ite(isd, dfield, TL[0]))),
                              mul(1024, add(mul(isBIN, bs), mul(eq(code, R.BNOT), R.BXOR - R.BAND))))     # (DBIT's operator; ~x: x ^ -1)
                    dstt = mul(not_(and_(isd, not_(isAO), not_(isTE))), gt(self.v('curf'), 0))     # (a temp's frame flag: 0 / 1)
                    un = or_(isAO, isTE, isUN)
                    cU = ite(eq(code, R.NEG), R.K(0), ite(eq(code, R.TYPEOF), R.K(R.KINDS.index('typeof')), ite(eq(code, R.BNOT), R.K(-1), 0)))     # (DNEG: #0; KIND: typeof's test)
                    self.emit(op, (self.m(dst, 'pdst'), self.m(dstt, 'pdstt')), (ite(un, oR[0], oL[0]), ite(un, oR[1], oL[1])),
                              (ite(isBIN, oR[0], cU), mul(isBIN, oR[1])))
                here = self.here()
                for c_, cond in (('A', eq(code, R.AND)), ('O', eq(code, R.OR)), ('T', isTE)):
                    cond = self.m(and_(ok, cond), 'psc')
                    self.setif(f'sc{c_}', cond, 1); self.setif(f'sc{c_}l', cond, mod(val, 64)); self.setif(f'sc{c_}x', cond, here)
                self.setif('psp', and_(ok, split), 1)
                # the operand stack: one entry written per pop (cc_ref: the left operand's for && || and binary operators, else
                # the right one's), a pending comparison's operands in pk
                two = self.m(and_(ok, or_(isAO, isBIN)), 'ptwo')
                self.setif('nd', two, iR)
                ae = add(mul(16384, self.v('tb')), mul(4096, ite(or_(isAO, isTE), self.tmerge(fdiv(val, 64), tR),
                                                    ite(or_(pnot, pcmp, and_(isUN, eq(code, R.NOT)), iscmp), 1,
                                                        ite(isUN, ite(eq(code, R.TYPEOF), 2, 3), ite(isBIN, self.btype(binc, tL, tR), 3))))),
                         ite(pnot, add(CND + 4 * R.CNDOPS.index(R.NOT), mul(oR[1], 2)),
                             ite(pcmp, add(CND - 4 * R.LT, mul(code, 4), mul(oL[1], 2), oR[1]),
                             ite(and_(isd, or_(isUN, isBIN)), dfield, TMP))))
                self.setif('ptop', and_(ok, not_(split)), ae)
                self.setif('pk', and_(ok, or_(pnot, pcmp)), ite(pnot, mul(sub(oR[0], 512), 1024), add(mul(sub(oL[0], 512), 1024), oR[0])))
            code, val, p = c2, v2, p2                      # (the next top: read once)
        if cap < OD:                                       # more to pop than cc_ref.popcap allows
            with self.when(and_(go, eq(self.v('err'), 0), gt(self.v('osp'), 0), gt(p, 0), ge(p, minprec))): self.fail(22)
        self.set_od(self.v('nd') - 1, self.v('ptop'), c=popped)
        with self.when(self.v('psp')):                      # a + chain split (M_CADD is right above M_PRINT: at most one per call)
            _, pv = self.top_op(); self.set_top_op(R.M_PRINT, add(pv, 4)); self.set('psp', 0)
        for c in 'AOT':
            with self.when(self.v(f'sc{c}')): self.deflab(self.v(f'sc{c}l'), self.v(f'sc{c}x'))
            self.set(f'sc{c}', 0)

    def cond_dest(self):
        """cc_ref.cond_ctx / dest_ctx: (no markers on the operator stack, the control entry's kind, can the last operator write the
        assignment's target, its operand)"""
        osp = self.m(self.v('osp'), 'ospm')
        nomark = self.m(not_(or_(*[and_(lt(k, osp), ge(k, self.v('obase')), ge(self.v(f'op{k}'), 100 * 8192)) for k in range(OD)])), 'nomark')
        t = self.top()
        kd, o, _, _ = self.symkind_addr(t[1])
        return nomark, t[0], self.m(and_(nomark, eq(t[0], R.C_ASSIGN), eq(t[2], 0), not_(self.captured(t[1], kd))), 'dok'), o

    def print_call(self, sep):
        """cc_ref.print_call: the argument's pieces (M_PRINT's value // 4 + 1 of them, on top of the operand stack), one PRINT each
        (PRINTK for the big constant on top); the last with the separator"""
        _, pv = self.top_op(); c = self.m(fdiv(pv, 4), 'pcc'); nd = self.m(self.v('nd'), 'pnd'); d0 = self.m(sub(sub(nd, 1), c), 'pd0')
        for j in range(R.PIECES):                           # (at most PIECES of them)
            k = self.m(add(d0, j), 'prk')
            with self.when(lt(k, nd)):
                w = self.odv(k); d = self.m(mod(w, 4096), 'prd'); kb = self.m(eq(d, KBIG), 'prkb'); o = self.opnd(k, d)
                flags = add(mul(eq(k, nd - 1), 2 * R.SEP[sep]), mul(gt(c, 0), 8))
                self.emit(ite(kb, OP['PRINTK'], OP['PRINT']), (flags, 0), w1=(ite(kb, self.v('pk'), mul(sub(o[0], 512), 1024)), mul(not_(kb), mul(o[1], 1024))))
        self.set('nd', d0)

    # ---------------- the language past the PoC (cc_ref's helpers of the same names)
    def key_name(self, tv, th1, th2):
        """cc_ref.key_name: a property name -> (key, ok); tv: strtok()"""
        ta = self.m(mod(tv, 2048), 'kta'); big = self.m(ge(ta, 1024), 'kbig')
        with self.when(big): self.fail(26)
        with self.when(not_(big)): e, ok = self.intern(th1, th2, add(ta, self.db), mod(fdiv(tv, 2048), 128))
        return self.m(e, 'kname'), self.m(and_(not_(big), ok), 'kok')
    def stmt_level(self):
        return self.m(and_(eq(self.v('osp'), self.v('obase')), eq(self.top()[0], R.C_EXPR)), 'stl')
    def marker(self):
        """cc_ref.marker: the innermost marker on the operator stack (0: none)"""
        osp = self.m(self.v('osp'), 'mko')
        best = self.m(mx(*[mul(and_(lt(k, osp), ge(k, self.v('obase')), ge(self.v(f'op{k}'), 100 * 8192)), k + 1) for k in range(OD)]), 'mkb')
        return self.m(fdiv(add(*[mul(eq(best, k + 1), self.v(f'op{k}')) for k in range(OD)]), 8192), 'mkc')
    def num(self, t): return or_(eq(t, 1), eq(t, 3))
    def dop(self, code):
        """cc_ref.dynop: the dynamic operator of binary operator code (ADD ... LNE are in DADD ... DLNE's order, then BAND ... USHR
        are DBIT) and its A's 1024s (DBIT's operator, code - BAND)"""
        assert all(OP[R.DYN[c]] - OP['DADD'] == c - R.ADD for c in R.DYN) and R.CNDOPS.index(R.LNE) == R.LNE - R.LT
        assert OP['DBIT'] == OP['DLNE'] + 1 and R.BAND == R.LNE + 1
        bs = self.m(mx(sub(code, R.BAND), K(0)), 'dbs')
        return self.m(sub(add(OP['DADD'] - R.ADD, code), bs), 'dop'), bs
    def btype(self, code, tl, tr):
        """cc_ref.btype: a comparison 1; + 2 with a string side, else 0; the rest 3"""
        return self.m(ite(inrange(code, R.LT, R.LNE), 1, ite(eq(code, R.ADD), mul(2, or_(eq(tl, 2), eq(tr, 2))), 3)), 'bty')
    def join_pieces(self):
        """cc_ref.join_pieces: a + chain's pieces (M_PRINT on top) joined into one string, its first piece's temp"""
        tc, tv = self.top_op()
        with self.when(and_(eq(tc, R.M_PRINT), ge(tv, 4))):
            nd = self.m(self.v('nd'), 'jnd'); d0 = self.m(sub(sub(nd, 1), fdiv(tv, 4)), 'jd0')
            self.src(nd - 1)
            for j in range(1, R.PIECES):
                k = self.m(add(d0, j), 'jk')
                with self.when(lt(k, nd)):
                    self.emit(OP['DADD'], self.tmp(d0), self.opnd(d0), self.opnd(k)); self.set_od(d0, TMP, 2)
            self.set('nd', d0 + 1); self.set_top_op(R.M_PRINT, mod(tv, 4))
    def read_elem(self, dyn, key, keep):
        """cc_ref.index_read (dyn: [x, k] on top) / prop_read ([o], key): GETX / GETP into the first's temp, or (keep) pushed above"""
        keep = lift(keep); nd = self.m(self.v('nd'), 'rnd'); i = self.m(sub(nd, add(1, dyn)), 'rei')
        top = self.src(nd - 1)
        full = self.m(and_(keep, or_(ge(nd, ODN), ge(add(nd, self.v('tb')), TBMAX))), 'refull')
        with self.when(full): self.fail(22)
        with self.when(not_(full)):
            xo = self.opnd(i); d = self.m(ite(keep, nd, i), 'red')
            self.emit(ite(dyn, OP['GETX'], OP['GETP']), self.tmp(d), (ite(dyn, xo[0], top[0]), ite(dyn, xo[1], top[1])),
                      (ite(dyn, top[0], sub(key, self.db)), mul(dyn, top[1])))
            self.set_od(d, TMP, 0); self.set('nd', d + 1)
    def write_elem(self, dyn, key, val):
        """cc_ref.index_write ([x, k, v]) / prop_write ([o, v]): SETX / SETP with val v's operand; they are popped"""
        nd = self.m(self.v('nd'), 'wnd'); b = self.m(sub(nd, add(2, dyn)), 'web')
        xo = self.opnd(b); ko = self.opnd(b + 1)
        self.emit(ite(dyn, OP['SETX'], OP['SETP']), xo, (ite(dyn, ko[0], val[0]), ite(dyn, ko[1], val[1])),
                  (ite(dyn, val[0], sub(key, self.db)), mul(dyn, val[1])))
        self.set('nd', b)
    def forof(self, j, isin):
        """cc_ref.forof: for (x of / in: two temps for the loop, then e"""
        full = self.m(gt(self.v('tb') + 2, R.TBMAX), 'fofull')
        with self.when(full): self.fail(22)
        with self.when(not_(full)):
            t = self.pop_cs(); self.set('tb', self.v('tb') + 2)
            self.push_cs(R.C_FOROF, t[1], t[3], j, isin, t[5]); self.set('mode', R.S_OPND)
            with self.when(not_(isin)): self.emit(OP['MOV'], self.tmp(-1), (R.K(0), 0))
            self.done()
    def forof_end(self, t):
        """cc_ref.forof_end: the loop's head (C_FOROF), then its body"""
        self.pop_cs(); i = self.m(self.v('nd') - 1, 'foi'); a, ix = self.tmp(-2), self.tmp(-1); isin = self.m(ne(t[4], 0), 'foin')
        self.put((ite(isin, ix[0], a[0]), a[1]), i)
        with self.when(isin): self.emit(OP['CALL'], (self.ent.get('keys', 0) // 2, K(0)), w1=(sub(a[0], 256), a[1]))
        self.set('nd', i); self.deflab(t[1], self.here())
        n = self.tmp(0); kx, xo, _, _ = self.symkind_addr(t[3]); x = (xo, K(0))
        with self.when(self.captured(t[3], kx)): self.fail(80)     # (cc_ref: no outer function's variable as the target)
        # (one record per instruction slot: for of LDI JGE GETX MOV DSUB, for in GETX JEQ MOV DSUB)
        self.emit(ite(isin, OP['GETX'], OP['LDI']), n, a, (ite(isin, ix[0], R.K(-1)), mul(isin, ix[1])))
        self.emit(ite(isin, OP['JEQ'], OP['JGE']), b=(ite(isin, n[0], ix[0]), n[1]), c=(ite(isin, R.K(R.UNDEF), n[0]), mul(not_(isin), n[1])), label=t[2])
        self.emit(ite(isin, OP['MOV'], OP['GETX']), (ite(isin, xo, n[0]), mul(not_(isin), n[1])), (ite(isin, n[0], a[0]), a[1]), (ite(isin, 0, ix[0]), mul(not_(isin), ix[1])))
        self.emit(ite(isin, OP['DSUB'], OP['MOV']), (ite(isin, ix[0], xo), mul(isin, ix[1])), (ite(isin, ix[0], n[0]), n[1]), (ite(isin, R.K(-1), 0), 0))
        with self.when(not_(isin)): self.emit(OP['DSUB'], ix, ix, (R.K(-1), 0))
        self.push_cs(R.C_LOOPB, t[1], t[2], 0, 2, t[5]); self.set('mode', R.S_LBRACE); self.done()
    def compound(self, code, i, o, otemp):
        """cc_ref.compound: x op= e, the old value at i, e above it, into o -> the static type"""
        tl, tr = self.otype(i), self.otype(i + 1)
        r = self.src(i + 1); l = self.opnd(i); dopc, bs = self.dop(code)
        self.emit(dopc, (add(o[0], mul(1024, bs)), o[1]), l, r)
        return self.btype(code, tl, tr)
    def meth_end(self, tv, last):
        """cc_ref.meth_end: a method call's ')' (tv: the method + 64 * its commas; last: an argument just ended)"""
        mi = self.m(mod(tv, 64), 'mmi'); argc = self.m(add(fdiv(tv, 64), last), 'margc')
        pairs = [(i, a, e) for i, m in enumerate(R.ALLM) for a, e in m[1].items()]
        mk = self.m(add(mul(mi, 16), mn(argc, 15)), 'mkey')              # (one key per method and argument count)
        ok = self.m(or_(*[eq(mk, 16 * i + a) for i, a, e in pairs]), 'mok')
        with self.when(not_(ok)): self.fail(77)
        with self.when(ok):
            e = self.m(add(*[mul(eq(mk, 16 * i + a), self.ent.get(e, 0) // 2) for i, a, e in pairs]), 'ment')
            ty = self.m(add(*[mul(eq(mi, i), m[2]) for i, m in enumerate(R.ALLM)]), 'mty')
            if last: self.arg_end()
            self.set('tb', sub(self.v('tb'), argc + 1)); d0 = self.m(self.v('nd') - 1, 'md0'); f = self.tmp(d0)
            self.emit(OP['CALL'], (e, 0), w1=(sub(f[0], 256), f[1])); self.set_od(d0, TMP, ty)
            self.set('mode', R.S_OPER); self.done()
    def arr_make(self, n):
        """cc_ref.arr_make: mkarrN of the n collapsed elements above the slot"""
        self.set('tb', sub(self.v('tb'), n)); d0 = self.m(self.v('nd') - 1, 'amd'); f = self.tmp(d0)
        self.emit(OP['CALL'], (add(*[mul(eq(n, k), self.ent.get(f'mkarr{k}', 0) // 2) for k in range(9)]), 0), w1=(sub(f[0], 256), f[1]))
        self.set_od(d0, TMP, 0)
    def arr_store(self, k):
        """cc_ref.arr_store: element k (past the eighth, on top) into the array below it"""
        with self.when(ge(k, R.KLIM)): self.fail(22)
        with self.when(lt(k, R.KLIM)):
            i = self.m(self.v('nd') - 1, 'asi'); vo = self.src(i)
            self.emit(OP['SETX'], self.opnd(i - 1), (add(k, 896), 0), vo); self.set('nd', i)
    def okey_end(self, tv, close):
        """cc_ref.okey_end: an object literal's pair (tv: its key's offset, 0: a number key below the value)"""
        close = lift(close)
        self.set('osp', self.v('osp') - 1)
        i = self.m(self.v('nd') - 1, 'oki'); nk = self.m(eq(tv, 0), 'oknk'); vo = self.src(i)
        xo = self.opnd(sub(i, add(1, nk))); ko = self.opnd(i - 1)
        self.emit(ite(nk, OP['SETX'], OP['SETP']), xo, (ite(nk, ko[0], vo[0]), ite(nk, ko[1], vo[1])), (ite(nk, vo[0], tv), mul(nk, vo[1])))
        self.set('nd', sub(i, nk))
        with self.when(close): self.set('osp', self.v('osp') - 1)
        self.set('mode', ite(close, R.S_OPER, R.S_OKEY)); self.done()
    def case_end(self):
        """cc_ref.case_end: J!= Tnext, T(0), value  Bk:"""
        c = self.pop_cs(); tn = self.newlab()
        db_ = self.m(self.v('dbase'), 'cedb'); r = self.src(add(db_, 1)); l = self.opnd(db_)
        self.emit(OP['JNE'], b=l, c=r, label=tn)
        self.set('nd', db_)
        with self.when(c[2]): self.deflab(c[1], self.here())
        t = self.top()
        self.set_top(add(R.C_SWITCH * 4096, mul(tn, 64), t[2]), add(mul(t[5], 4096), mul(t[3], 64), t[4], sub(1, mod(t[4], 2))))
        self.set('mode', R.S_STMT); self.done()

    def fn_sel(self, k, f): return self.m(add(*[mul(eq(k, i), I(f'{f}{i}')) for i in range(NF)]), f)
    def callv_end(self, tv, last):
        """cc_ref.callv_end: CALLV A, its slot (tv % 64: 1 a method call, 2 f.call, 4 f.apply)"""
        argc = self.m(add(fdiv(tv, 64), last), 'cvc'); fl = self.m(mod(tv, 64), 'cvf')
        isap, isca = self.m(eq(fl, 4), 'cvap'), self.m(eq(fl, 2), 'cvca')
        if last: self.arg_end()
        bad = self.m(and_(isap, ne(argc, 2)), 'cvbad')
        with self.when(bad): self.fail(77)
        with self.when(not_(bad)):
            self.set('tb', sub(self.v('tb'), add(argc, not_(or_(isap, isca))))); d0 = self.m(self.v('nd') - 1, 'cvd'); f = self.tmp(d0)
            isnew = self.m(eq(fl, 8), 'cvnew')
            a = ite(isap, 63, ite(isca, mul(gt(argc, 0), add(argc, 31)), add(argc, mul(or_(eq(fl, 1), isnew), 32))))
            self.emit(OP['CALLV'], (a, 0), w1=(sub(f[0], 256), f[1]))
            with self.when(isnew): self.emit(OP['MOV'], f, self.tmp(add(d0, 1)))     # (new: the object)
            self.set_od(d0, TMP, 0); self.set('mode', R.S_OPER); self.done()
    def new_call(self, h1, h2):
        """cc_ref.new_call"""
        j = self.lookup(h1, h2); k, o, b, _ = self.symkind_addr(j); fk = self.fnlook(h1, h2)
        isv = self.m(ge(j, 0), 'nwv'); isf = self.m(and_(not_(isv), ge(fk, 0)), 'nwf'); ok = self.m(or_(isv, isf), 'nwok')
        with self.when(not_(ok)): self.fail(4)
        cap = self.m(and_(isv, self.captured(j, k)), 'nwcap')
        with self.when(cap): self.cread(o, self.tmp(self.v('nd')))
        with self.when(isf): self.emit(OP['NUMLIT'], (add(fk, R.FCACHE), 0), w1=fk)
        with self.when(ok): self.push_od(ite(cap, TMP, ite(isv, o, add(fk, R.FCACHE))), mul(cap, b))
        go = self.m(and_(ok, eq(self.v('err'), 0)), 'nwgo')
        with self.when(go):
            d0 = self.m(self.v('nd') - 1, 'nwd'); self.to_temp(d0); self.snapshot(lambda d: lt(d, 256))
            full = self.m(gt(add(self.v('nd'), self.v('tb'), 2), TBMAX), 'nwfull')
            with self.when(full): self.fail(22)
            with self.when(not_(full)):
                self.emit(OP['MOV'], self.tmp(add(d0, 2)), self.tmp(d0)); f = self.tmp(add(d0, 1))
                self.emit(OP['CALL'], (self.ent.get('mknew', 0) // 2, 0), w1=(sub(f[0], 256), f[1]))
                self.set('tb', self.v('tb') + 1); self.push_op(R.M_CALLV, 8); self.set('mode', R.S_OPND); self.done()
    def meth_call(self, dyn, key):
        """cc_ref.meth_call: o.f( / o[k]( : the callee into o's slot, o above it as its this"""
        nd = self.m(self.v('nd'), 'mcd'); i = self.m(sub(nd, add(1, dyn)), 'mci3')
        full = self.m(and_(dyn, ge(add(nd, self.v('tb')), TBMAX)), 'mcfull')
        with self.when(full): self.fail(22)
        with self.when(and_(dyn, not_(full))):
            xo = self.opnd(i); ko = self.src(nd - 1)
            self.emit(OP['GETX'], self.tmp(i + 2), xo, ko); self.put(self.tmp(i + 1), i); self.emit(OP['MOV'], self.tmp(i), self.tmp(i + 2))
        with self.when(not_(dyn)):
            self.put(self.tmp(i + 1), i); self.emit(OP['GETP'], self.tmp(i), self.tmp(i + 1), (sub(key, self.db), 0))
        with self.when(not_(full)):
            self.set('nd', i + 1); self.set_od(i, TMP, 0); self.snapshot(lambda d: lt(d, 256)); self.set('tb', self.v('tb') + 1)
            self.push_op(R.M_CALLV, 1); self.set('mode', R.S_OPND); self.done()
    def cs_dbit(self, idx):
        """the control entry idx's d |= 2 (its function uses this: cc_ref.this_val)"""
        for k in range(CD):
            with self.when(eq(idx, k)):
                B = self.v(f'csB{k}'); self.set(f'csB{k}', add(B, mul(2, sub(1, mod(fdiv(B, 2), 2)))))
    def this_val(self):
        """cc_ref.this_val"""
        curf = self.m(self.v('curf'), 'thc'); fi = self.m(sub(self.v('fcsp'), 1), 'thfi'); oi = self.m(sub(fdiv(self.v('sv3'), 1024), 1), 'thoi')
        dsel = lambda j: mod(add(*[mul(eq(j, k), self.v(f'csB{k}')) for k in range(CD)]), 2)     # (an arrow's entry: d's bit 0)
        own = self.m(and_(gt(curf, 0), not_(dsel(fi))), 'thown')
        cap = self.m(and_(not_(own), eq(curf, 2), not_(dsel(oi))), 'thcap')
        with self.when(own): self.cs_dbit(fi)
        with self.when(cap):
            self.cs_dbit(oi); t = self.tmp(self.v('nd')); self.envbase(t); self.emit(OP['LDI'], t, t, (R.K(1), 0))
        with self.when(not_(or_(own, cap))): self.emit(OP['NUMLIT'], (R.GCELL, 0), w1=R.GLOBK)
        self.push_od(ite(own, 257, ite(cap, TMP, R.GCELL)), 0); self.set('mode', R.S_OPER); self.done()
    def call_end(self, tv, last):
        """cc_ref.call_end: CALL, after checking (or recording) the function's argument count"""
        k = self.m(mod(tv, 16), 'cfk'); argc = self.m(add(fdiv(tv, 64), last), 'argc')
        if last: self.arg_end()
        fl = self.fn_sel(k, 'fl_'); exp = self.m(fdiv(fl, 256), 'cexp')
        bad = self.m(and_(ne(exp, 0), ne(exp, add(argc, 1))), 'cbad')
        with self.when(bad): self.fail(76)
        with self.when(not_(bad)):
            with self.when(eq(exp, 0)):
                self.fnw.append((self.x.g, k, self.fn_sel(k, 'fh1_'), self.fn_sel(k, 'fh2_'), add(mod(fl, 256), mul(add(argc, 1), 256))))
            self.set('tb', sub(self.v('tb'), argc + 1)); d0 = self.m(self.v('nd') - 1, 'cd0'); f = self.tmp(d0)     # (+ its this)
            self.emit(OP['CALL'], label=mod(fl, 64), w1=(sub(f[0], 256), f[1]))
            self.set_od(d0, TMP, mod(fdiv(tv, 16), 4))
            self.done()

    def print_end(self):
        """cc_ref.print_end: console.log(...) leaves no value; it ends its statement (C_EXPR), or a return's value is undefined
        (C_RETURN)"""
        t = self.top()[0]; isr = self.m(eq(t, R.C_RETURN), 'pret')
        ok = self.m(and_(eq(self.v('osp'), self.v('obase')), or_(eq(t, R.C_EXPR), isr)), 'pend')
        with self.when(not_(ok)): self.fail(30)
        with self.when(and_(ok, isr)): self.push_od(R.K(R.UNDEF), 0); self.set('mode', R.S_OPER); self.done()
        with self.when(and_(ok, not_(isr))): self.pop_cs(); self.set('mode', R.S_INC); self.done()

    def incdec(self, h1, h2, op, x=0, pre=None):
        """cc_ref.incdec. x: 0 statement, 1 ++x / 2 x++ in an expression; pre: the symbol (j, k, o, b, cst) if looked up"""
        if pre is None: j = self.lookup(h1, h2); k, o, b, cst = self.symkind_addr(j)
        else: j, k, o, b, cst = pre
        x = lift(x); x1, x2 = self.m(eq(x, 1), 'ix1'), self.m(eq(x, 2), 'ix2')
        with self.when(lt(j, 0)): self.fail(6)
        with self.when(and_(ge(j, 0), cst)): self.fail(64)
        with self.when(and_(ge(j, 0), not_(cst))):
            cap = self.captured(j, k)
            with self.when(cap):                               # cc_ref: through the env (base at T(nd + 1), the value at T(nd))
                nd_ = self.m(self.v('nd'), 'icn'); u, t, w = self.tmp(nd_), self.tmp(nd_ + 1), self.tmp(nd_ + 2); s_ = (add(o, 640), 0)
                nv = (ite(x2, w[0], u[0]), u[1])
                self.envbase(t); self.emit(OP['LDI'], u, t, s_); self.emit(OP['DSUB'], nv, u, (ite(eq(op, 7), R.K(-1), R.K(1)), 0))
                self.emit(OP['STI'], t, s_, nv)
                with self.when(ne(x, 0)): self.push_od(TMP, 3)
            with self.when(and_(not_(cap), ne(x, 0))): self.snapshot(lambda d: eq(d, o))
            with self.when(and_(not_(cap), x2)): self.push_od(o, 3); self.to_temp(self.v('nd') - 1)
            with self.when(not_(cap)): self.emit(OP['DSUB'], (o, 0), (o, 0), (ite(eq(op, 7), R.K(-1), R.K(1)), 0))     # (cc_ref.step1: x - -1)
            with self.when(and_(not_(cap), x1)): self.push_od(o, 3)
            with self.when(ne(x, 0)): self.set('pm', 3); self.set('mode', R.S_OPER)
            with self.when(eq(x, 0)): self.set('mode', R.S_INC)
            self.done()

    def jump_loop(self, isbreak, isID, th1, th2):
        """cc_ref S_BRK: break / continue: JMP to a loop's break (b) or continue (a) label: the labeled one (an identifier: its
        label's symbol holds the entry's index), else the innermost (break: or switch), and on into S_INC"""
        csp = self.m(self.v('csp'), 'csp')
        def loop(kind): return anyeq(kind, (R.C_LOOPB, R.C_LOOPB1, R.C_DOB, R.C_DOB1))
        best = self.m(mx(*[mul(and_(lt(k, csp), or_(loop(fdiv(self.v(f'csA{k}'), 4096)), and_(isbreak, eq(fdiv(self.v(f'csA{k}'), 4096), R.C_SWITCH)))), k + 1)
                           for k in range(CD)]), 'lpk')
        jl = self.lookup(th1, add(th2, R.H2M)); _, lc, _, _ = self.symkind_addr(jl)
        lab = self.m(mul(isID, ite(ge(jl, 0), add(lc, 1), 0)), 'lpl')          # (the labeled entry + 1, 0 for none)
        idx = self.m(ite(isID, lab, best), 'lpx')
        A = self.m(add(*[mul(eq(idx, k + 1), self.v(f'csA{k}')) for k in range(CD)]), 'lpA')
        bad = self.m(or_(eq(idx, 0), gt(idx, csp), and_(isID, not_(loop(fdiv(A, 4096))))), 'lpbad')
        with self.when(bad): self.fail(56)
        with self.when(not_(bad)):
            self.emit(OP['JMP'], label=ite(isbreak, mod(A, 64), mod(fdiv(A, 64), 64))); self.set('mode', R.S_INC)
            with self.when(isID): self.done()

    # ---------------- parser
    def parser(self):
        tk = I('tk') if self.spec_tk is None else K(self.spec_tk)
        with self.when(and_(ne(tk, 0), eq(self.v('err'), 0))):
            self.token(tk, I('tv') if self.spec_tv is None else K(self.spec_tv), I('th1'), I('th2'))

    def token(self, tk, tv, th1, th2):
        # a variant for 'other punctuation' (tk 4, no tv) only sees codes outside PUNCT
        other_p = self.spec_tk == 4 and self.spec_tv is None and SPEC_LEVEL == 'mtv'
        P = lambda ch: K(0) if other_p and spec_p(self.spec_mode, ch) else self.m(and_(eq(tk, 4), eq(tv, ch)), f'P{ch}_')
        isID = self.m(eq(tk, 2), 'isID'); isNUM = self.m(eq(tk, 1), 'isNUM'); isSTR = self.m(eq(tk, 3), 'isSTR'); isEOF = self.m(eq(tk, 5), 'isEOF')
        KWc = lambda k: self.m(and_(isID, eq(th1, KW[k][0]), eq(th2, KW[k][1])), 'kw_' + k)
        live = lambda: self.m(self.v('live'), 'live')
        mode = lambda: self.m(self.v('mode'), 'mode')
        # an arrow's expression body (cc_ref.CMODES): S_OPERC / S_NAMEEC are S_OPER / S_NAMEE with arrow_close
        if self.spec_mode is None:
            cc = self.m(anyeq(mode(), tuple(R.CMODES)), 'cc')
            with self.when(cc): self.set('mode', add(*[mul(eq(mode(), c), b) for c, b in R.CMODES.items()]))
        else:
            cc = K(int(self.spec_mode in R.CMODES))
            if self.spec_mode in R.CMODES: self.set('mode', R.CMODES[self.spec_mode])
        compound = self.m(add(*[mul(P(ch), op) for ch, op in R.COMPOUND.items()]), 'cmpd')
        # with a known starting mode, only the fallthrough chains below can run: other blocks are folded away
        # (after a dynamic mode change the analysis could not prove them unreachable)
        FALL = {R.S_NAMES: (R.S_NAMEE, R.S_OPER), R.S_NAMEE: (R.S_OPER,), R.S_ELSE: (R.S_DOWHILE, R.S_STMT), R.S_AFTERELSE: (R.S_STMT,),
                R.S_LBRACE: (R.S_STMT,), R.S_CONFIRST: (R.S_OPND,), R.S_SWCASE: (R.S_STMT,), R.S_BRK: (R.S_INC,), R.S_FNAME: (R.S_FPAREN,),
                R.S_OPERC: (R.S_OPER,), R.S_NAMEEC: (R.S_NAMEE, R.S_OPER), R.S_ABODY: (R.S_OPND,)}
        if self.spec_tk in (None, 1, 3) or (self.spec_tk == 4 and self.spec_tv is None):     # an expression statement's first token
            FALL[R.S_STMT] = (R.S_OPND,); FALL[R.S_ELSE] += (R.S_OPND,)
        reach = None if self.spec_mode is None else {self.spec_mode, *FALL.get(self.spec_mode, ())}
        def block(md):
            if reach is not None and md not in reach: return self.when(K(0))
            return self.when(and_(live(), eq(mode(), md)))
        PNL, PRB = P(R.T_NL), P(125)
        fallin = self.m(anyeq(mode(), (R.S_AFTERELSE, R.S_LBRACE)), 'fallin')     # (cc_ref: a braceless body's statement)
        lits = lambda: [(KWc(w), k, t) for w, (k, t) in R.LITERALS.items()]      # true false null undefined NaN Infinity
        def push_lit(ls):
            self.push_od(add(*[mul(c, k) for c, k, _ in ls]), add(*[mul(c, t) for c, _, t in ls if t])); self.set('mode', R.S_OPER); self.done()
        # a newline token means nothing outside the modes where it can end a statement
        with self.when(and_(PNL, not_(anyeq(mode(), (R.S_NAMES, R.S_NAMEE, R.S_OPER, R.S_VARAFTER, R.S_INC, R.S_OPND, R.S_BRK))))): self.done()
        # ---- S_NAMES
        isw = lambda p1, p2: self.m(and_(or_(*[and_(eq(p1, KW[w][0]), eq(p2, KW[w][1])) for w in ('window', 'globalThis')]), P(46)), 'isw')
        with block(R.S_NAMES):
            pn1, pn2 = self.v('pn1'), self.v('pn2')
            wd = isw(pn1, pn2)
            with self.when(wd): self.set('pn1', 1); self.set('pn2', 0); self.set('mode', R.S_WDOT); self.done()     # window.x: x
            fo = self.m(and_(not_(wd), or_(KWc('of'), KWc('in')), eq(self.top()[0], R.C_FORINIT)), 'nfo')
            with self.when(fo):                                # for (x of / in (cc_ref)
                fu = self.m(lt(self.lookup(pn1, pn2), 0), 'nfou')
                with self.when(fu): jf = self.implicit(pn1, pn2, K(1))
                jl = self.lookup(pn1, pn2); kl, _, _, cl = self.symkind_addr(jl)
                with self.when(and_(not_(fu), eq(kl, 3))): self.sym_kind(jl, 1, cl)
                with self.when(eq(self.v('err'), 0)): self.forof(ite(fu, jf, jl), KWc('in'))
            with self.when(P(58)):                             # a label (cc_ref): the next statement's control entry
                fh = self.m(or_(eq(self.top()[0], R.C_FORINIT), eq(self.top()[0], R.C_FORSTEP)), 'lfh')
                with self.when(fh): self.fail(67)              # (not in a for header)
                with self.when(not_(fh)): self.declare(pn1, add(pn2, R.H2M), 0, self.v('csp'), 0, K(1)); self.set('mode', R.S_STMT)
                self.done()
            j = self.lookup(pn1, pn2)
            k, o, b, cst = self.symkind_addr(j)
            asg = self.m(and_(not_(wd), not_(fo), not_(P(58)), or_(P(61), ne(compound, 0))), 'asg')
            with self.when(asg):
                undef = self.m(lt(j, 0), 'aund')
                with self.when(and_(undef, not_(P(61)))): self.fail(5)
                with self.when(and_(undef, P(61))): ja = self.implicit(pn1, pn2, K(1))      # cc_ref.implicit
                with self.when(and_(not_(undef), eq(k, 3))): self.sym_kind(j, 1, cst)     # (assigned)
                ccst = self.m(and_(not_(undef), cst), 'accst')
                with self.when(ccst): self.fail(64)
                with self.when(and_(or_(not_(undef), P(61)), not_(ccst))):
                    acap = self.captured(j, k)                  # x op= e: x is the left operand, read first
                    with self.when(and_(not_(P(61)), acap)): self.cread(o, self.tmp(self.v('nd')))
                    with self.when(not_(P(61))): self.push_od(ite(acap, TMP, o), b)
                    self.push_cs(R.C_ASSIGN, ite(undef, ja, j), compound); self.set('mode', R.S_OPND); self.done()
            with self.when(and_(not_(wd), or_(P(7), P(8)))): self.incdec(pn1, pn2, tv)
            with self.when(and_(not_(wd), P(91), lt(j, 0))): self.fail(7)      # NAME[e] = e: an expression statement (x[k])
            with self.when(not_(or_(wd, fo, P(58), asg, P(7), P(8), and_(P(91), lt(j, 0))))):
                self.push_cs(R.C_EXPR); self.set('mode', R.S_NAMEE)
        # ---- S_NAMEE
        with block(R.S_NAMEE):
            pn1, pn2 = self.m(self.v('pn1'), 'pn1'), self.m(self.v('pn2'), 'pn2')
            arw = P(R.T_ARROW)
            with self.when(arw):                               # x => / (x) => (cc_ref)
                self.arrow_start(pn1, pn2, 2)
                with self.when(eq(self.v('err'), 0)): self.end_params(True); self.arrow_body()
                self.done()
            tcn, _ = self.top_op()
            par = self.m(and_(or_(P(41), P(44)), eq(tcn, R.M_PAREN)), 'npar')     # (x): x, still pending; (x, : an arrow's
            with self.when(par):
                self.set('osp', self.v('osp') - 1)
                with self.when(P(44)): self.set('mode', R.S_APAR1)
                self.done()
            nx = self.m(not_(or_(arw, par)), 'nnx')
            wgn = self.m(or_(*[and_(eq(pn1, KW[w][0]), eq(pn2, KW[w][1])) for w in ('window', 'globalThis')]), 'wgn')
            wd = self.m(and_(wgn, P(46)), 'isw')
            with self.when(wd): self.set('pn1', 0); self.set('pn2', 0); self.set('mode', R.S_WDOT); self.done()     # window.x: x
            iscon = self.m(and_(nx, not_(wd), eq(pn1, KW['console'][0]), eq(pn2, KW['console'][1])), 'iscon')
            isputc = self.m(and_(eq(pn1, KW['putc'][0]), eq(pn2, KW['putc'][1])), 'isputc')
            with self.when(iscon):
                with self.when(not_(P(46))): self.fail(30)
                with self.when(P(46)): self.set('mode', R.S_CONLOG); self.done()
            with self.when(and_(not_(wd), not_(iscon), P(40))):
                gi = self.m(add(*[mul(and_(eq(pn1, KW[g[0]][0]), eq(pn2, KW[g[0]][1])), R.GLOBAL_INDEX[KW[g[0]]] + 1) for g in R.GLOBALS]), 'gi')
                with self.when(isputc): self.push_op(R.M_PUTC)
                with self.when(and_(not_(isputc), ne(gi, 0))):            # parseInt(s), ...: a method on a dummy receiver
                    self.push_od(TMP, 0); self.set('tb', self.v('tb') + 1); self.push_op(R.M_METH, sub(gi, 1))
                    tms = self.m(and_(anyeq(sub(gi, 1), tuple(R.GLOBAL_INDEX[KW[w]] for w in ('setTimeout', 'setInterval'))), lt(self.v('nfdef'), R.TIMERS)), 'tms')
                    with self.when(tms): self.set('nfdef', self.v('nfdef') + R.TIMERS)     # (cc_ref: the timers run at the end)
                jc = self.lookup(pn1, pn2); kc, oc, _, _ = self.symkind_addr(jc); dyn = self.m(ge(jc, 0), 'cdyn')
                with self.when(and_(not_(isputc), eq(gi, 0), dyn)):      # a variable's value: CALLV (cc_ref)
                    self.snapshot(lambda d: lt(d, 256)); i = self.m(self.v('nd'), 'cvi'); ccap = self.captured(jc, kc)
                    with self.when(ccap): self.cread(oc, self.tmp(i))
                    self.push_od(ite(ccap, TMP, oc), 0)
                    with self.when(not_(ccap)): self.to_temp(i)
                    self.push_op(R.M_CALLV); self.set('tb', self.v('tb') + 1)     # (its this)
                with self.when(and_(not_(isputc), eq(gi, 0), not_(dyn))):
                    self.snapshot(lambda d: lt(d, 256))                     # the callee may change a global still on the stack
                    fi, _, fb = self.fnfind(pn1, pn2); self.push_op(R.M_CALL, add(fi, mul(fb, 16))); self.push_od(TMP, 0)    # its slot
                    self.set('tb', self.v('tb') + 1)                 # (its this)
                self.set('mode', R.S_OPND); self.done()
            p78n = self.m(or_(P(7), P(8)), 'p78n')
            with self.when(and_(nx, not_(wd), not_(iscon), not_(P(40)))):
                j = self.lookup(pn1, pn2)
                k, o, b, cst = self.symkind_addr(j)
                with self.when(p78n): self.incdec(pn1, pn2, tv, 2, (j, k, o, b, cst))     # x++ in an expression
                ismath = self.m(and_(eq(pn1, KW['Math'][0]), eq(pn2, KW['Math'][1])), 'ismath')
                sdot = self.m(and_(not_(p78n), lt(j, 0), or_(ismath, *[and_(eq(pn1, KW[w][0]), eq(pn2, KW[w][1])) for w in ('String', 'Object')]), P(46)), 'sdot')
                isstrn = self.m(and_(eq(pn1, KW['String'][0]), eq(pn2, KW['String'][1])), 'isstrn')
                with self.when(sdot): self.push_od(R.K(0), 0); self.set('mode', ite(isstrn, R.S_DOT, R.S_MATHDOT)); self.done()     # String.fromCharCode
                tyo = self.m(eq(self.top_op()[0], R.TYPEOF), 'ntyo')       # typeof x, x undeclared: "undefined"
                undef = self.m(lt(j, 0), 'nund')
                rd = self.m(and_(not_(p78n), not_(sdot)), 'nrd')
                wgv = self.m(and_(rd, undef, or_(wgn, ismath)), 'nwgv')    # window / globalThis (Math alone): the global object (cc_ref)
                with self.when(wgv): self.emit(OP['NUMLIT'], (R.GCELL, 0), w1=R.GLOBK)
                fk = self.fnlook(pn1, pn2); isfv = self.m(and_(rd, undef, not_(wgv), ge(fk, 0)), 'nfv')      # a function's name: its value (cc_ref)
                with self.when(isfv): self.emit(OP['NUMLIT'], (add(fk, R.FCACHE), 0), w1=fk)
                newi = self.m(and_(rd, undef, not_(tyo), not_(isfv), not_(wgv)), 'nnew')
                with self.when(newi): ji = self.implicit(pn1, pn2, K(0))     # cc_ref.implicit: read first (its global)
                cap = self.m(and_(rd, not_(undef), self.captured(j, k)), 'ncap')
                with self.when(and_(cap, eq(self.v('err'), 0))): self.cread(o, self.tmp(self.v('nd')))     # (cc_ref.cread)
                with self.when(and_(rd, eq(self.v('err'), 0))):
                    dsc = self.m(ite(cap, TMP, ite(wgv, R.GCELL, ite(isfv, add(fk, R.FCACHE), ite(newi, add(ji, R.IMPC), ite(undef, R.K(R.UNDEF), o))))), 'ndsc')
                    self.push_od(dsc, mul(not_(undef), b)); self.set('mode', R.S_OPER)
        # ---- S_BRK: after break / continue (pn1: break)
        with block(R.S_BRK):
            bok = self.m(or_(isID, P(59), PNL, PRB), 'bok')
            with self.when(not_(bok)): self.fail(53)
            with self.when(bok): self.jump_loop(self.v('pn1'), isID, th1, th2)
        # ---- S_WDOT: window.x / globalThis.x is the global x (pn1: at a statement's start)
        with block(R.S_WDOT):
            with self.when(not_(isID)): self.fail(69)
            with self.when(isID):
                self.set('mode', ite(ne(self.v('pn1'), 0), R.S_NAMES, R.S_NAMEE)); self.set('pn1', th1); self.set('pn2', th2); self.done()
        # ---- S_ELSE
        with block(R.S_ELSE):
            with self.when(KWc('else')):
                t = self.top(); reuse = self.m(eq(t[0], R.C_ELSEB1), 'reuse')
                with self.when(not_(reuse)): nl = self.newlab()
                lb = self.m(ite(reuse, t[1], nl), 'elb')
                self.emit(OP['JMP'], label=lb); self.deflab(self.v('pendLa'), self.here())
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
            tkind = self.top()[0]
            with self.when(P(123)): self.set('mode', ite(eq(tkind, R.C_SWITCH), R.S_SWCASE, R.S_STMT)); self.done()
            with self.when(not_(P(123))):
                okb = self.m(anyeq(tkind, (R.C_IFB, R.C_LOOPB, R.C_DOB)), 'okb')
                with self.when(not_(okb)): self.fail(33)
                with self.when(okb): self.set_topA(lambda A: add(A, R.BRACELESS * 4096)); self.set('mode', R.S_STMT)
        # ---- S_SWCASE: a switch body's first token
        with block(R.S_SWCASE):
            okc = self.m(or_(KWc('case'), KWc('default'), PRB), 'okc')
            with self.when(not_(okc)): self.fail(74)
            with self.when(okc): self.set('mode', R.S_STMT)
        # ---- S_STMT
        with block(R.S_STMT):
            t0 = self.top()[0]
            with self.when(isEOF):
                with self.when(ne(self.v('csp'), 0)): self.fail(40)
                # a reserved word read or called (cc_ref: an implicit global, a function never declared)
                ni_, ns_, nf_ = self.v('nimp'), self.v('nsym'), self.v('nfn')
                eres = self.m(or_(*[and_(lt(j, ni_) if j < R.NIMP else lt(j, ns_), self.isres(I(f'sh1_{j}'), I(f'sh2_{j}'))) for j in range(NS)],
                                  *[and_(lt(k, ni_), eq(fdiv(mod(I(f'sk_{k}'), 65536), 16384), 3)) for k in range(R.NIMP)],     # read, never assigned
                                  *[and_(lt(k, nf_), self.isres(I(f'fh1_{k}'), I(f'fh2_{k}'))) for k in range(NF)]), 'eres')
                with self.when(and_(eq(self.v('csp'), 0), eres)): self.fail(4)
                with self.when(and_(eq(self.v('csp'), 0), not_(eres))):
                    with self.when(ge(self.v('nfdef'), R.TIMERS)):    # cc_ref.timer_loop
                        t = self.tmp(K(0)); l = self.here()
                        self.emit(OP['CALL'], (self.ent.get('nexttimer', 0) // 2, 0), w1=(sub(t[0], 256), t[1])); self.emit(OP['JZ'], (add(l, 4), 0), b=t)
                        self.emit(OP['CALLV'], (0, 0), w1=(sub(t[0], 256), t[1])); self.emit(OP['JMP'], (l, 0))
                    self.emit(OP['HALT']); self.done()
            with self.when(P(123)): self.push_cs(R.C_BLOCK); self.done()
            with self.when(P(125)): self.close_block()
            with self.when(P(59)): self.set('f_simple', 1)
            fstep = self.m(and_(P(41), eq(t0, R.C_FORSTEP)), 'fstep')
            with self.when(fstep): self.set('f_simple', 1)
            with self.when(or_(P(7), P(8))): self.set('pn1', tv); self.set('pn2', 0); self.set('mode', R.S_PREINC); self.done()
            other = self.m(and_(not_(isEOF), not_(P(123)), not_(P(125)), not_(P(59)), not_(fstep), not_(P(7)), not_(P(8))), 'oth')
            exs = self.m(and_(other, or_(isNUM, isSTR, *[P(c) for c in R.XSTART])), 'exs')     # an expression statement (cc_ref)
            with self.when(and_(exs, fallin)): self.fail(8)
            with self.when(and_(exs, not_(fallin))): self.push_cs(R.C_EXPR); self.set('mode', R.S_OPND)      # (into S_OPND)
            with self.when(and_(other, not_(isID), not_(exs))): self.fail(8)
            ls = lits(); tfs = self.m(or_(*[c for c, _, _ in ls]), 'tfs'); tys = KWc('typeof')
            with self.when(and_(other, or_(tfs, tys), fallin)): self.fail(8)
            with self.when(and_(other, or_(tfs, tys), not_(fallin))):       # a literal word or typeof: as S_OPND would take it
                self.push_cs(R.C_EXPR)
                with self.when(tfs): push_lit(ls)
                with self.when(tys): self.push_op(R.TYPEOF); self.set('mode', R.S_OPND); self.done()
            with self.when(and_(other, isID, not_(tfs), not_(tys))):
                kws = ['var', 'let', 'const', 'if', 'while', 'do', 'for', 'return', 'function', 'break', 'continue', 'switch', 'case', 'default']
                with self.when(or_(KWc('var'), KWc('let'), KWc('const'))):
                    self.set('pn1', add(KWc('let'), mul(KWc('const'), 2))); self.set('pn2', 0); self.set('mode', R.S_VAR); self.done()
                with self.when(KWc('if')): self.push_cs(R.C_IFC); self.set('mode', R.S_LPAREN); self.done()
                with self.when(KWc('switch')): self.push_cs(R.C_SWITCHC); self.set('mode', R.S_LPAREN); self.done()
                with self.when(or_(KWc('case'), KWc('default'))):         # cc_ref; one label, one JMP, one label port for both
                    t = self.top(); seen = self.m(mod(t[4], 2), 'swseen'); insw = self.m(eq(t[0], R.C_SWITCH), 'insw')
                    isc = KWc('case'); dup = self.m(and_(not_(isc), mod(fdiv(t[4], 2), 2)), 'swdup')
                    with self.when(not_(insw)): self.fail(73)
                    with self.when(and_(insw, dup)): self.fail(75)
                    with self.when(and_(insw, not_(dup))):
                        with self.when(or_(seen, not_(isc))): l = self.newlab()     # case: Bk (after a body); default: its label
                        with self.when(ite(isc, seen, not_(seen))): self.emit(OP['JMP'], label=ite(isc, l, t[1]))
                        self.deflab(ite(isc, t[1], l), self.here())
                        with self.when(isc):                       # the switch's value (T(0)), then this one's
                            self.push_od(TMP, fdiv(t[4], 4)); self.push_cs(R.C_CASE, mul(seen, l), seen); self.set('mode', R.S_OPND)
                        with self.when(not_(isc)):
                            self.set_top(add(R.C_SWITCH * 4096, mul(t[1], 64), t[2]), add(mul(t[5], 4096), mul(l, 64), sub(t[4], mod(t[4], 4)), 3))
                            self.set('mode', R.S_OCOLON)
                        self.done()
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
                    self.set('pn1', KWc('break')); self.set('pn2', 0); self.set('mode', R.S_BRK); self.done()
                with self.when(KWc('function')):                # (cc_ref FUNCS: inside a function, a local's value)
                    bad = self.m(ge(self.v('curf'), 2), 'fbad')
                    with self.when(bad): self.fail(41)
                    with self.when(not_(bad)):
                        lo = self.newlab(); self.emit(OP['JMP'], label=lo); self.set('mode', R.S_FNAME)
                        self.push_cs(ite(gt(self.v('curf'), 0), R.C_FUNCN, R.C_FUNCB), lo); self.done()
                with self.when(not_(or_(*[KWc(k) for k in kws]))):
                    self.set('pn1', th1); self.set('pn2', th2); self.set('mode', R.S_NAMES); self.done()
        # ---- S_PREINC
        with block(R.S_PREINC):
            with self.when(not_(isID)): self.fail(10)
            with self.when(isID): self.incdec(th1, th2, self.v('pn1'), self.v('pn2'))
        # ---- S_VAR
        with block(R.S_VAR):
            vres = self.m(or_(not_(isID), self.isres(th1, th2)), 'vres')
            with self.when(vres): self.fail(9)
            with self.when(not_(vres)):
                curf = self.m(self.v('curf'), 'curf')
                cst, blk = self.m(eq(self.v('pn1'), 2), 'dcst'), self.decl_blk()
                # cc_ref.redecl: a let / const of a name its scope declares already (error 78)
                nl_, e_ = self.m(self.v('nlet'), 'rnl'), self.top()[5]
                lo = self.m(ite(ne(curf, 0), self.v('fsym'), 0), 'rlo'); ns_ = self.m(self.v('nsym'), 'rns')
                inb = lambda j: and_(ge(j, sub(NS, nl_)), lt(j, sub(NS, e_)))
                inf = lambda j: and_(ge(j, lo), lt(j, ns_))
                ni_, var_ = self.m(self.v('nimp'), 'rni'), self.m(eq(self.v('pn1'), 0), 'rvar')
                same = lambda j: and_(eq(I(f'sh1_{j}'), th1), eq(I(f'sh2_{j}'), th2))
                ru = self.m(mul(and_(eq(curf, 0), not_(blk)), mx(*[mul(and_(same(j), lt(j, ni_) if j < R.NIMP else and_(lt(j, ns_), var_)), j + 1) for j in range(NS)])), 'vru')
                with self.when(ne(ru, 0)):                     # cc_ref: the same variable
                    self.sym_kind(sub(ru, 1), 1, cst); self.set('pn2', ru); self.set('mode', R.S_VARAFTER); self.done()
                rd = self.m(and_(eq(ru, 0), ne(self.v('pn1'), 0), or_(*[and_(same(j), ite(blk, inb(j), inf(j))) for j in range(NS)])), 'redecl')
                with self.when(rd): self.fail(78)
                with self.when(eq(ru, 0)): self.set('pn2', 0)
                go = self.m(and_(eq(ru, 0), not_(rd)), 'vgo')
                with self.when(and_(ne(curf, 0), go)):
                    nl = self.m(self.v('nloc') + 1, 'nl'); self.set('nloc', nl); self.declare(th1, th2, 2, add(self.v('npar'), nl), cst, blk)
                full = self.m(ge(self.v('dp'), R.SDATA), 'gfull')
                with self.when(and_(eq(curf, 0), full, go)): self.fail(25)
                with self.when(and_(eq(curf, 0), not_(full), go)):
                    self.declare(th1, th2, 1, self.v('dp'), cst, blk); self.set('dp', self.v('dp') + 1)
                with self.when(and_(or_(ne(curf, 0), not_(full)), go)): self.set('mode', R.S_VARAFTER); self.done()
        # ---- S_VARAFTER
        with block(R.S_VARAFTER):
            pn1 = self.m(self.v('pn1'), 'dk')
            pn2v = self.m(self.v('pn2'), 'vpn2')              # (a reused global's index + 1)
            jv = self.m(ite(ne(pn2v, 0), sub(pn2v, 1), ite(self.decl_blk(), sub(NS, self.v('nlet')), self.v('nsym') - 1)), 'vj')
            fo = self.m(and_(or_(KWc('of'), KWc('in')), eq(self.top()[0], R.C_FORINIT)), 'vfo')
            with self.when(fo): self.forof(jv, KWc('in'))       # for (var x of / in
            with self.when(P(61)):
                self.push_cs(R.C_ASSIGN, jv, 0, add(pn1, 1)); self.set('mode', R.S_OPND); self.done()
            with self.when(and_(not_(fo), not_(P(61)), eq(pn1, 2))): self.fail(65)
            with self.when(and_(not_(fo), not_(P(61)), ne(pn1, 2))):
                _, ov, _, _ = self.symkind_addr(jv)
                with self.when(and_(eq(pn2v, 0), or_(ne(self.v('curf'), 0), ne(pn1, 0)))): self.emit(OP['MOV'], (ov, 0), (R.K(R.UNDEF), 0))     # (cc_ref)
                with self.when(P(44)): self.set('mode', R.S_VAR); self.done()
                with self.when(not_(P(44))): self.simple_end(PNL, PRB)
        with block(R.S_INC):
            self.simple_end(PNL, PRB)
        with block(R.S_LPAREN):
            with self.when(not_(P(40))): self.fail(32)
            with self.when(P(40)):
                t = self.top()
                self.set('mode', ite(eq(t[0], R.C_FORINIT), R.S_STMT, R.S_OPND)); self.done()
        with block(R.S_FNAME):
            fk = self.m(self.top()[0], 'fnk')
            anon = self.m(and_(eq(fk, R.C_FUNCE), P(40)), 'fanon')     # an anonymous function expression (cc_ref)
            with self.when(anon):
                _, nm = self.top_op()                          # (M_FN's value: a key's name)
                self.emit(OP['MOV'], w1=mul(ne(nm, 0), add(nm, self.db - R.STRTAG))); ka = self.fnnew(); self.fn_enter(ka); self.set('mode', R.S_FPAREN)
            fres = self.m(and_(not_(anon), or_(not_(isID), self.isres(th1, th2))), 'fres')
            with self.when(fres): self.fail(34)
            ta = self.m(mod(tv, 2048), 'fta')                  # (its name, committed: cc_ref FTAB's descriptor [MOV][its name])
            with self.when(and_(not_(anon), not_(fres), ge(ta, 1024))): self.fail(26)
            with self.when(and_(not_(anon), not_(fres), lt(ta, 1024))):
                self.datum(add(ta, self.db - 1), mod(fdiv(tv, 2048), 128)); self.emit(OP['MOV'], w1=add(ta, self.db - R.STRTAG))
                isb = self.m(eq(fk, R.C_FUNCB), 'fisb')
                with self.when(isb):                           # its calls: CALL its label (defined at its end: close_block)
                    fi, l, _ = self.fnfind(th1, th2); self.set('nfdef', self.v('nfdef') + 1)
                with self.when(eq(fk, R.C_FUNCN)):             # the local variable that holds it
                    nl = self.m(self.v('nloc') + 1, 'fnl1'); ns_ = self.m(self.v('nsym'), 'fns'); self.set('nloc', nl)
                    self.declare(th1, th2, 2, add(self.v('npar'), nl)); self.set_topB(lambda B: add(sub(B, mod(B, 4096)), mul(ns_, 64), mod(B, 64)))
                with self.when(not_(isb)): kn = self.fnnew()
                with self.when(eq(self.v('err'), 0)):
                    self.fn_enter(ite(isb, fi, kn))
                    r = self.m(self.v('cp'), 'fbr')            # (its body: cc_ref, c / d of its entry)
                    with self.when(isb): self.set_topB(lambda B: add(sub(B, mod(B, 4096)), mul(mod(r, 64), 64), mul(fdiv(r, 64), 4)))
                    self.set('mode', R.S_FPAREN); self.done()
        with block(R.S_FPAREN):
            with self.when(not_(P(40))): self.fail(35)
            with self.when(P(40)): self.set('mode', R.S_FPARAM); self.done()
        with block(R.S_FPARAM):
            with self.when(P(41)): self.end_params()
            pres = self.m(or_(not_(isID), self.isres(th1, th2)), 'pres')
            with self.when(and_(not_(P(41)), pres)): self.fail(36)
            with self.when(and_(not_(P(41)), not_(pres))): self.set('pn1', th1); self.set('pn2', th2); self.set('mode', R.S_FPSEP); self.done()
        with block(R.S_FPSEP):                             # (cc_ref: the parameter in pn is declared here)
            sep = self.m(or_(P(44), P(41)), 'fsep')
            with self.when(not_(sep)): self.fail(37)
            with self.when(sep):
                self.declare(self.v('pn1'), self.v('pn2'), 2, add(self.v('npar'), R.PARAM0)); self.set('npar', self.v('npar') + 1)
                ok = self.m(eq(self.v('err'), 0), 'fsok')
                with self.when(and_(ok, P(44))): self.set('mode', R.S_FPARAM); self.done()
                with self.when(and_(ok, P(41))): self.end_params()
        with block(R.S_APAR1):                             # (a, b: an arrow's (cc_ref)
            pres = self.m(or_(not_(isID), self.isres(th1, th2)), 'apres')
            with self.when(pres): self.fail(36)
            with self.when(not_(pres)):
                self.arrow_start(self.v('pn1'), self.v('pn2')); self.set('pn1', th1); self.set('pn2', th2); self.set('mode', R.S_FPSEP); self.done()
        with block(R.S_MATHDOT):                           # Math. name (cc_ref)
            mm_ = [(KW[m[0]], R.MATH_INDEX[KW[m[0]]], m[0]) for m in R.MATHM]
            mi_ = self.m(add(*[mul(and_(eq(th1, h[0]), eq(th2, h[1])), ix + 1) for h, ix, _ in mm_]), 'mmi')     # (its ALLM index + 1)
            mv_ = self.m(add(*[mul(and_(eq(th1, h[0]), eq(th2, h[1])), R.MATHV.index(n) + 1) for h, ix, n in mm_ if n in R.MATHV]), 'mmv')
            mk_ = self.m(add(*[mul(and_(eq(th1, KW[c][0]), eq(th2, KW[c][1])), k + 1) for c, k in R.MATHK.items()]), 'mmk')
            tpar = self.m(ge(tv, 262144), 'mtp')
            meth = self.m(and_(isID, ne(mi_, 0), tpar), 'mmeth')
            with self.when(meth): self.set('pn1', 0); self.set('pn2', 0); self.set('pm', add(mi_, 3)); self.set('mode', R.S_OPER); self.done()
            val = self.m(and_(isID, not_(meth), or_(ne(mk_, 0), and_(ne(mi_, 0), ne(mv_, 0)))), 'mval')
            with self.when(and_(not_(meth), not_(val))): self.fail(69)
            with self.when(val):                               # (dummy[a hidden key], pending as x[k]: cc_ref)
                isk = self.m(ne(mk_, 0), 'misk')
                self.push_od(KBIG, 0, sub(R.PKSTAT, ite(isk, sub(mk_, 1), add(sub(mv_, 1), len(R.MATHK)))))
                self.set('pm', 2); self.set('mode', R.S_OPER); self.done()
        with block(R.S_NEW):                               # new F(...): F's name (cc_ref)
            nbad = self.m(or_(not_(isID), self.isres(th1, th2)), 'nbad')
            with self.when(nbad): self.fail(3)
            with self.when(not_(nbad)): self.set('pn1', th1); self.set('pn2', th2); self.set('mode', R.S_NEWN); self.done()
        with block(R.S_NEWN):
            with self.when(not_(P(40))): self.fail(35)
            nw = self.m(add(*[mul(and_(eq(self.v('pn1'), h[0]), eq(self.v('pn2'), h[1])), ix + 1) for h, ix in R.NEW_INDEX.items()]), 'nwi')
            with self.when(and_(P(40), ne(nw, 0))):            # new Number( ...: a wrapper (cc_ref)
                self.push_od(TMP, 0); self.set('tb', self.v('tb') + 1); self.push_op(R.M_METH, sub(nw, 1)); self.set('mode', R.S_OPND); self.done()
            with self.when(and_(P(40), eq(nw, 0))): self.new_call(self.v('pn1'), self.v('pn2'))
        for am in (R.S_AARROW0, R.S_AARROW):              # () => / (a, b) =>
            with block(am):
                with self.when(not_(P(R.T_ARROW))): self.fail(35)
                with self.when(P(R.T_ARROW)):
                    if am == R.S_AARROW0:
                        self.arrow_start(None, None, 1)
                        with self.when(eq(self.v('err'), 0)): self.end_params(True)
                    with self.when(eq(self.v('err'), 0)): self.arrow_body()
        with block(R.S_CONLOG):
            with self.when(not_(KWc('log'))): self.fail(38)
            with self.when(KWc('log')): self.set('mode', R.S_CONLP); self.done()
        with block(R.S_CONLP):
            with self.when(not_(P(40))): self.fail(39)
            with self.when(P(40)): self.push_op(R.M_PRINT); self.set('mode', R.S_CONFIRST); self.done()
        with block(R.S_CONFIRST):
            _, cfv = self.top_op()
            with self.when(and_(P(41), eq(cfv, 2))): self.fail(30)          # console.log(a, ) (cc_ref)
            with self.when(and_(P(41), ne(cfv, 2))):
                self.set('osp', self.v('osp') - 1); self.emit(OP['PUTC'], b=(R.K(10), 0)); self.print_end()
            with self.when(not_(P(41))):
                self.set_top_op(R.M_PRINT, 0); self.set('mode', R.S_OPND)
        # ---- objects (cc_ref)
        with block(R.S_DOT):
            dpt = self.m(or_(P(R.T_PROTO), P(R.T_PTYPE)), 'dpt')     # o.__proto__ / f.prototype: x[a hidden key] (cc_ref)
            with self.when(dpt): self.push_od(KBIG, 0, ite(P(R.T_PROTO), R.PKPROTO, R.PKPT)); self.set('pm', 2); self.set('mode', R.S_OPER); self.done()
            with self.when(and_(not_(isID), not_(dpt))): self.fail(69)
            isl = self.m(and_(isID, eq(th1, KW['length'][0]), eq(th2, KW['length'][1])), 'islen')
            mi = self.m(add(*[mul(and_(eq(th1, KW[m[0]][0]), eq(th2, KW[m[0]][1])), i + 1) for i, m in enumerate(R.METHODS)]), 'mi')
            fm = self.m(add(*[mul(and_(eq(th1, h[0]), eq(th2, h[1])), j + 1) for h, j in R.FMETH.items()]), 'fm')
            fdir = self.m(and_(isID, ne(fm, 0), ge(tv, 262144)), 'fdir')     # f.call( / f.apply( (cc_ref)
            with self.when(fdir): self.set('pn1', 0); self.set('pn2', 0); self.set('pm', add(fm, R.PMFN - 1)); self.set('mode', R.S_OPER); self.done()
            direct = self.m(and_(isID, not_(fdir), not_(isl), ne(mi, 0), ge(tv, 262144)), 'mdir')     # x.name( for a method's name
            with self.when(and_(or_(isl, direct), lt(mod(tv, 2048), 1024))): self.datum(add(mod(tv, 2048), self.db - 1), mod(fdiv(tv, 2048), 128))    # (its length word)
            with self.when(isl):                               # a string's or an array's length: the word before its value's address
                i = self.m(self.v('nd') - 1, 'lni'); o = self.src(i)
                self.emit(OP['LDI'], self.tmp(i), o, (R.K(-1), 0)); self.set_od(i, TMP, 3); self.set('mode', R.S_OPER); self.done()
            with self.when(direct): self.set('pn1', 0); self.set('pn2', 0); self.set('pm', add(mi, 3)); self.set('mode', R.S_OPER); self.done()
            with self.when(and_(isID, not_(fdir), not_(isl), not_(direct))):
                ks, ok = self.key_name(tv, th1, th2)
                with self.when(ok):
                    self.set('pn1', ks); self.set('pn2', 0); self.set('pm', ite(ne(fm, 0), add(fm, R.PMFN - 1), ite(eq(mi, 0), 1, add(mi, 3)))); self.set('mode', R.S_OPER); self.done()
        with block(R.S_OKEY):
            with self.when(P(125)): self.set('osp', self.v('osp') - 1); self.set('mode', R.S_OPER); self.done()     # {} or a trailing comma
            nk = self.m(not_(P(125)), 'onk')
            with self.when(and_(nk, not_(or_(isID, isSTR, and_(isNUM, eq(th2, 0)))))): self.fail(71)     # (a double's literal: no key)
            if self.spec_tk in (None, 2):
                with self.when(and_(nk, isID)): ksI, okI = self.key_name(tv, th1, th2)
            else: ksI, okI = K(0), K(0)
            if self.spec_tk in (None, 3):
                tsa = self.m(mod(tv, 2048), 'otsa'); bigS = self.m(and_(nk, isSTR, ge(tsa, 1024)), 'obig')
                with self.when(bigS): self.fail(26)
                with self.when(and_(nk, isSTR, not_(bigS))): eS, okS = self.intern(th1, th2, add(tsa, self.db), fdiv(tv, 2048))
                ksS = self.m(eS, 'oks'); okS = self.m(and_(not_(bigS), okS), 'okS')
            else: ksS, okS = K(0), K(0)
            nkey = self.m(and_(nk, isNUM, eq(th2, 0)), 'onkey')
            with self.when(nkey):                              # a number key: as o[n] = v
                v20 = self.m(sub(mod(add(tv, 1 << 19), 1 << 20), 1 << 19), 'kn20'); small = self.m(and_(ge(v20, -128), lt(v20, R.KLIM)), 'knsm')
                self.push_od(ite(small, add(v20, 896), KBIG), 3, v20)
            okk = self.m(or_(and_(isID, okI), and_(isSTR, okS), and_(isNUM, eq(th2, 0), eq(self.v('err'), 0))), 'okk')
            with self.when(and_(nk, okk)):
                self.push_op(R.M_OKEY, mul(not_(isNUM), sub(add(mul(isID, ksI), mul(isSTR, ksS)), self.db))); self.set('mode', R.S_OCOLON); self.done()
        with block(R.S_OCOLON):
            with self.when(P(58)): self.set('mode', ite(eq(self.top()[0], R.C_SWITCH), R.S_STMT, R.S_OPND)); self.done()     # (default's ':')
            with self.when(not_(P(58))): self.fail(72)
        # ---- S_OPND
        with block(R.S_ABODY):                             # => {: a block body (cc_ref)
            with self.when(P(123)):                            # (a frame label of its own, defined at its '}')
                self.pop_cs(); self.set('ca', 0); lf = self.newlab(); self.set('flab', lf); self.set_topA(lambda A: add(sub(A, mod(A, 64)), lf))
                self.set('mode', R.S_STMT); self.done()
            with self.when(not_(P(123))): self.set('mode', R.S_OPND)
        with block(R.S_OPND):
            dbl = self.m(and_(isNUM, eq(th2, 1)), 'ndbl')
            with self.when(dbl):                               # cc_ref.numlit
                tsa = self.m(mod(tv, 2048), 'ntsa'); gfull = self.m(ge(self.v('dp'), R.SDATA), 'ngf')
                with self.when(ge(tsa, 1024)): self.fail(26)
                with self.when(lt(tsa, 1024)):
                    self.datum(add(tsa, self.db - 1), fdiv(tv, 2048))
                    with self.when(gfull): self.fail(25)
                    with self.when(not_(gfull)):
                        g = self.m(self.v('dp'), 'ng'); self.set('dp', g + 1)
                        self.emit(OP['NUMLIT'], (g, 0), w1=add(tsa, self.db - R.STRTAG)); self.push_od(g, 3); self.set('mode', R.S_OPER); self.done()
            with self.when(and_(isNUM, not_(dbl))):
                v20 = self.m(sub(mod(add(tv, 1 << 19), 1 << 20), 1 << 19), 'n20')
                small = self.m(and_(ge(v20, -128), lt(v20, R.KLIM)), 'nsm')
                self.push_od(ite(small, add(v20, 896), KBIG), 3, v20); self.set('mode', R.S_OPER); self.done()
            with self.when(isSTR):                          # interned (cc_ref)
                tsa = self.m(mod(tv, 2048), 'tsa')
                with self.when(ge(tsa, 1024)): self.fail(26)
                with self.when(lt(tsa, 1024)):
                    e, ok = self.intern(th1, th2, add(tsa, self.db), fdiv(tv, 2048))
                    with self.when(ok): self.push_od(KBIG, 2, sub(e, R.STRTAG)); self.set('mode', R.S_OPER); self.done()
            ls = lits(); tf = self.m(or_(*[c for c, _, _ in ls]), 'tf')
            with self.when(tf): push_lit(ls)
            with self.when(KWc('function')):                   # a function expression (cc_ref): its value; a key gives it its name
                with self.when(ge(self.v('curf'), 2)): self.fail(41)
                with self.when(lt(self.v('curf'), 2)):
                    tc_, tv_ = self.top_op()
                    self.push_op(R.M_FN, mul(eq(tc_, R.M_OKEY), tv_)); lo = self.newlab(); self.emit(OP['JMP'], label=lo)
                    self.push_cs(R.C_FUNCE, lo); self.set('mode', R.S_FNAME); self.done()
            tyo = KWc('typeof')
            with self.when(tyo): self.push_op(R.TYPEOF); self.done()
            with self.when(P(R.T_THIS)): self.this_val()
            with self.when(P(R.T_NEW)): self.set('mode', R.S_NEW); self.done()
            with self.when(P(123)):                            # an object literal: NEW, then each pair as o.key = v
                i = self.m(self.v('nd'), 'obi'); self.push_od(TMP, 0)
                with self.when(eq(self.v('err'), 0)): self.emit(OP['NEW'], self.tmp(i)); self.push_op(R.M_OBJ); self.set('mode', R.S_OKEY); self.done()
            with self.when(P(91)): self.push_od(TMP, 0); self.push_op(R.M_ARR, 0); self.done()     # an array literal: its slot, the elements
            with self.when(P(40)): self.push_op(R.M_PAREN); self.done()
            with self.when(P(33)): self.push_op(R.NOT); self.done()
            with self.when(P(45)): self.push_op(R.NEG); self.done()
            with self.when(P(126)): self.push_op(R.BNOT); self.done()
            with self.when(or_(P(7), P(8))): self.set('pn1', tv); self.set('pn2', 1); self.set('mode', R.S_PREINC); self.done()
            with self.when(and_(isID, not_(tf), not_(tyo), not_(KWc('function')))): self.set('pn1', th1); self.set('pn2', th2); self.set('mode', R.S_NAMEE); self.done()
            rest = self.m(and_(live(), eq(mode(), R.S_OPND)), 'orest')
            with self.when(rest):
                tc, tvv = self.top_op()
                t = self.top()
                cP = self.m(and_(P(41), eq(tc, R.M_PAREN)), 'oP')     # () => (cc_ref)
                with self.when(cP): self.set('osp', self.v('osp') - 1); self.set('mode', R.S_AARROW0); self.done()
                cA = self.m(and_(P(41), gt(self.v('osp'), 0), anyeq(tc, (R.M_CALL, R.M_METH, R.M_CALLV))), 'oA')
                cR = self.m(and_(P(93), gt(self.v('osp'), 0), eq(tc, R.M_ARR)), 'oR')
                cB = self.m(and_(not_(cA), or_(P(59), PNL, PRB), eq(t[0], R.C_RETURN), eq(self.v('osp'), self.v('obase'))), 'oB')
                cC = self.m(and_(not_(cA), not_(cB), P(59), eq(t[0], R.C_FORCOND), eq(self.v('osp'), self.v('obase'))), 'oC')
                cN = self.m(and_(not_(cB), PNL), 'oN')
                with self.when(cN): self.done()
                with self.when(cA):
                    self.set('osp', self.v('osp') - 1); self.set('mode', R.S_OPER)
                    with self.when(eq(tc, R.M_CALL)): self.call_end(tvv, 0)
                    with self.when(eq(tc, R.M_METH)): self.meth_end(tvv, 0)
                    with self.when(eq(tc, R.M_CALLV)): self.callv_end(tvv, 0)
                with self.when(cR):                            # [] or a trailing comma
                    self.set('osp', self.v('osp') - 1)
                    with self.when(lt(tvv, 8)): self.arr_make(tvv)
                    self.set('mode', R.S_OPER); self.done()
                with self.when(cB):
                    self.push_od(R.K(R.UNDEF), 0); self.set('f_expr', 1)
                    with self.when(PRB): self.set('f_asic', 1)
                with self.when(cC): self.push_od(R.K(1), 1); self.set('f_expr', 1)
                with self.when(and_(not_(cA), not_(cB), not_(cC), not_(cN), not_(cR), not_(cP))): self.fail(3)
        # ---- S_OPER
        with block(R.S_OPER):
            # pm is set only on the way out of S_OPER (S_DOT, x[k]'s ']'): a variant starting in another mode knows it is 0
            pmr = self.m(self.v('pm'), 'pmr') if self.spec_mode in (None, R.S_OPER, R.S_OPERC) else K(0)
            pinc = self.m(eq(pmr, 3), 'pinc')                  # after x++ / ++x (cc_ref): no '.' or '[' may follow
            pbad = self.m(and_(pinc, or_(P(46), P(91))), 'pbad')
            with self.when(pinc): self.set('pm', 0)
            with self.when(pbad): self.fail(48)
            pm4 = self.m(ge(pmr, 4), 'pm4')                     # x.name for a method's name: a call, or else the property
            mcall = self.m(and_(pm4, P(40)), 'mcall')
            fcall = self.m(and_(mcall, ge(pmr, R.PMFN)), 'mfc')
            with self.when(fcall):                             # f.call( / f.apply( (cc_ref): f is the callee
                self.to_temp(self.m(self.v('nd') - 1, 'fct')); self.snapshot(lambda d: lt(d, 256))
                self.push_op(R.M_CALLV, add(2, mul(sub(pmr, R.PMFN), 2))); self.set('pm', 0); self.set('mode', R.S_OPND); self.done()
            with self.when(and_(mcall, not_(fcall))):          # the receiver: an argument above its slot
                i = self.m(self.v('nd') - 1, 'mci')
                self.put(self.tmp(i + 1), i); self.set_od(i, TMP, 0); self.set('tb', self.v('tb') + 1)
                self.push_op(R.M_METH, sub(pmr, 4)); self.set('pm', 0); self.set('mode', R.S_OPND); self.done()
            pmv = self.m(mul(not_(mcall), ite(pm4, 1, mul(pmr, not_(pinc)))), 'pmv')     # 1: o.x pending, 2: x[k]
            with self.when(ne(pmv, 0)):
                dyn = self.m(eq(pmv, 2), 'mdyn'); key = self.m(self.v('pn1'), 'mks')
                p78 = self.m(or_(P(7), P(8)), 'p78'); asgm = self.m(or_(P(61), ne(compound, 0), p78), 'masg')
                self.set('pm', 0)
                with self.when(asgm):
                    stl = self.stmt_level()
                    with self.when(not_(stl)): self.fail(70)
                    with self.when(stl):
                        with self.when(not_(P(61))): self.read_elem(dyn, key, 1)     # the old value, above [o] / [x, k]
                        go = self.m(eq(self.v('err'), 0), 'mgo')
                        with self.when(and_(go, p78)):         # o.x++ / x[k]--
                            i = self.m(self.v('nd') - 1, 'mpi'); t = self.tmp(i)
                            self.emit(OP['DSUB'], t, t, (ite(P(7), R.K(-1), R.K(1)), 0)); self.write_elem(dyn, key, t)
                            self.pop_cs(); self.set('mode', R.S_INC); self.done()
                        with self.when(and_(go, not_(p78))):
                            t = self.top(); off = self.m(mul(not_(dyn), sub(key, self.db)), 'koff')
                            self.set_top(add(R.C_PSET * 4096, mul(dyn, 64), compound), add(mul(t[5], 4096), mul(fdiv(off, 64), 64), mod(off, 64)))
                            self.set('mode', R.S_OPND); self.done()
                with self.when(and_(not_(asgm), P(40))): self.meth_call(dyn, key)     # o.f( (cc_ref)
                with self.when(and_(not_(asgm), not_(P(40)))): self.read_elem(dyn, key, 0)
            binop = self.m(add(*[mul(P(ch), op) for ch, op in R.BIN.items()], mul(and_(or_(P(1), P(2)), th1), 2)), 'binop')     # (== / !=: LEQ / LNE)
            def context():
                nomark, tk0, dok, dop = self.cond_dest()
                csp_ = self.m(self.v('csp'), 'cspa')        # the entry below the top: a for header takes no semicolon insertion
                k2 = self.m(add(*[mul(eq(csp_, k + 2), fdiv(self.v(f'csA{k}'), 4096)) for k in range(CD - 1)]), 'k2nd')
                asiok = self.m(and_(nomark, anyeq(tk0, (R.C_ASSIGN, R.C_EXPR, R.C_RETURN, R.C_PSET)), not_(anyeq(k2, (R.C_FORINIT, R.C_FORSTEP)))), 'asiok')
                semi = self.m(or_(P(59), and_(or_(PNL, PRB), asiok)), 'semi')
                okb = self.m(and_(PRB, eq(self.marker(), R.M_OKEY)), 'okb')     # '}' ending an object literal's value
                with self.when(and_(live(), PNL, not_(asiok))): self.done()
                return nomark, tk0, dok, dop, asiok, semi, okb
            nomark, tk0, dok, dop, asiok, semi, okb = context()
            closer = self.m(and_(live(), or_(ne(binop, 0), P(41), P(44), P(58), P(63), P(93), okb, semi)), 'closer')
            br = self.m(or_(P(63), and_(P(41), nomark, anyeq(tk0, (R.C_IFC, R.C_WHILEC, R.C_DOB, R.C_DOB1))),
                            and_(or_(P(59), PNL), nomark, eq(tk0, R.C_FORCOND))), 'pbr')
            dv = self.m(and_(not_(br), or_(P(41), P(44), semi), dok), 'pdv')
            with self.when(closer):
                self.popops(self.m(ite(ne(binop, 0), self.prec(binop), add(1, P(63))), 'minp'), br, dv, dop)
            atok = or_(*[P(c) for c in R.ACLOSE])
            if (self.spec_mode is None or self.spec_mode in R.CMODES) and not isK(atok, 0):    # an arrow's expression body ended (its
                acl = self.m(and_(live(), cc, atok, nomark), 'acl')     # operators popped above, as cc_ref's popops(1)): the function
                with self.when(acl):                           # first (cc_ref), then the token in the outer context. (Other
                    for _ in range(2):                         # tokens: S_OPER's CSS exactly.) x => y => x + y: both
                        with self.when(and_(eq(self.v('err'), 0), ne(self.v('ca'), 0), eq(self.v('osp'), self.v('obase')))): self.arrow_close()
                nomark, tk0, dok, dop, asiok, semi, okb = context()
            tc, tvv = self.top_op()
            osp0 = self.m(self.v('osp'), 'osp0')
            ob0 = self.m(self.v('obase'), 'ob0'); tc = self.m(mul(tc, gt(osp0, ob0)), 'tt')
            with self.when(and_(live(), P(46))): self.set('mode', R.S_DOT); self.done()                        # o.x
            with self.when(and_(live(), P(40))):               # e(...): a call of e's value (cc_ref)
                self.to_temp(self.m(self.v('nd') - 1, 'cvt')); self.snapshot(lambda d: lt(d, 256)); self.push_op(R.M_CALLV); self.set('tb', self.v('tb') + 1)
                self.set('mode', R.S_OPND); self.done()
            with self.when(and_(live(), P(91))): self.push_op(R.M_INDEX); self.set('mode', R.S_OPND); self.done()    # x[k]
            with self.when(and_(live(), P(93))):              # x[k]: the read is pending (pm 2); or an array literal's end
                with self.when(eq(tc, R.M_INDEX)): self.set('osp', osp0 - 1); self.set('pm', 2); self.done()
                with self.when(eq(tc, R.M_ARR)):
                    self.set('osp', osp0 - 1)
                    with self.when(ge(tvv, 8)): self.arr_store(tvv)
                    with self.when(lt(tvv, 8)): self.arg_end(); self.arr_make(tvv + 1)
                    self.set('mode', R.S_OPER); self.done()
                with self.when(not_(anyeq(tc, (R.M_INDEX, R.M_ARR)))): self.fail(45)
            with self.when(and_(live(), okb)): self.okey_end(tvv, 1)
            with self.when(and_(live(), ne(binop, 0))):
                nd = self.m(self.v('nd'), 'bnd'); ty = self.otype(nd - 1)
                inpr = self.m(eq(tc, R.M_PRINT), 'inpr'); npc = self.m(fdiv(tvv, 4), 'npc')
                piece = self.m(and_(eq(binop, R.ADD), inpr, or_(ne(npc, 0), eq(ty, 2)), lt(tvv, 4 * (R.PIECES - 1))), 'piece')     # a piece, kept on the stack
                with self.when(piece): self.set_top_op(R.M_PRINT, add(tvv, 4))
                full = self.m(and_(eq(binop, R.ADD), inpr, ge(tvv, 4 * (R.PIECES - 1))), 'pfull')     # (cc_ref: joined, then +)
                plus = self.m(and_(not_(piece), not_(full), eq(binop, R.ADD)), 'plus')
                with self.when(plus): self.push_op(ite(inpr, R.M_CADD, R.ADD), ty)
                rest = self.m(and_(not_(piece), not_(plus)), 'brest')
                with self.when(and_(rest, not_(gt(self.prec(binop), 10)))): self.join_pieces()     # (* / % bind tighter: they end no piece)
                nd2 = self.m(self.v('nd'), 'bnd2'); ty2 = self.otype(nd2 - 1)
                logic = self.m(and_(rest, or_(eq(binop, R.AND), eq(binop, R.OR))), 'logic')
                with self.when(logic):                         # a: tested in its temp; b joins it there (popops)
                    l = self.newlab(); i = self.m(nd2 - 1, 'li'); self.to_temp(i); self.snapshot(lambda d: K(1), i)
                    self.emit(ite(eq(binop, R.AND), OP['JZ'], OP['JNZ']), b=self.tmp(i), label=l)
                    self.push_op(binop, add(l, mul(ty2, 64)))
                with self.when(and_(rest, not_(logic))): self.push_op(ite(full, R.M_CADD, binop), ty2)     # (the left operand's type)
                self.set('mode', R.S_OPND); self.done()
            with self.when(and_(live(), P(63))):               # c ? ... (cc_ref)
                self.join_pieces(); self.snapshot(lambda d: K(1), self.v('nd') - 1)
                l = self.newlab(); self.branch(l, 0); self.push_op(R.M_TERN, add(l, mul(eq(tc, R.M_TELSE), 64)))
                self.set('mode', R.S_OPND); self.done()
            with self.when(and_(live(), P(58))):               # c ? a : ...; a case value's end
                cse = self.m(and_(ne(tc, R.M_TERN), eq(osp0, ob0), eq(self.top()[0], R.C_CASE)), 'cse')
                with self.when(cse): self.case_end()
                with self.when(and_(ne(tc, R.M_TERN), not_(cse))): self.fail(67)
                with self.when(eq(tc, R.M_TERN)):
                    reuse = self.m(ge(tvv, 64), 'treu')
                    self.set('osp', osp0 - 1)
                    i = self.m(self.v('nd') - 1, 'tei'); lbt = self.otype(i); self.to_temp(i); self.set('nd', i)
                    _, ev = self.top_op()                      # the enclosing M_TELSE, when reuse
                    with self.when(not_(reuse)): l2 = self.newlab()
                    self.emit(OP['JMP'], label=ite(reuse, mod(ev, 64), l2))
                    with self.when(reuse): self.set_top_op(R.M_TELSE, add(mod(ev, 64), mul(self.tmerge(fdiv(ev, 64), lbt), 64)))
                    with self.when(not_(reuse)): self.push_op(R.M_TELSE, add(l2, mul(lbt, 64)))
                    self.deflab(mod(tvv, 64), self.here()); self.set('mode', R.S_OPND); self.done()
            with self.when(and_(live(), P(44))):
                vasg = self.m(and_(eq(osp0, ob0), eq(self.top()[0], R.C_ASSIGN), ne(self.top()[3], 0)), 'vasg')
                with self.when(eq(tc, R.M_PRINT)): self.print_call(32); self.set_top_op(R.M_PRINT, 2); self.set('mode', R.S_CONFIRST); self.done()
                with self.when(eq(tc, R.M_OKEY)): self.okey_end(tvv, 0)
                with self.when(eq(tc, R.M_ARR)):              # cc_ref.arr_elem
                    with self.when(ge(tvv, 8)): self.arr_store(tvv)
                    with self.when(lt(tvv, 8)):
                        self.arg_end()
                        with self.when(eq(tvv, 7)): self.arr_make(8)
                    self.set_top_op(R.M_ARR, tvv + 1); self.set('mode', R.S_OPND); self.done()
                with self.when(anyeq(tc, (R.M_CALL, R.M_METH, R.M_CALLV))): self.arg_end(); self.set_top_op(tc, tvv + 64)       # count the arguments
                with self.when(anyeq(tc, (R.M_CALL, R.M_METH, R.M_PUTC, R.M_CALLV))): self.set('mode', R.S_OPND); self.done()
                known = anyeq(tc, (R.M_PRINT, R.M_OKEY, R.M_ARR, R.M_CALL, R.M_METH, R.M_PUTC, R.M_CALLV))
                with self.when(and_(not_(known), vasg)): self.set('f_expr', 1)
                with self.when(not_(or_(known, vasg))): self.fail(44)
            with self.when(and_(live(), P(41))):
                with self.when(eq(tc, R.M_PAREN)): self.set('osp', osp0 - 1); self.done()
                with self.when(eq(tc, R.M_CALL)): self.set('osp', osp0 - 1); self.call_end(tvv, 1)
                with self.when(eq(tc, R.M_CALLV)): self.set('osp', osp0 - 1); self.callv_end(tvv, 1)
                with self.when(eq(tc, R.M_METH)): self.set('osp', osp0 - 1); self.meth_end(tvv, 1)
                with self.when(eq(tc, R.M_PUTC)):
                    self.set('osp', osp0 - 1); o = self.src(self.v('nd') - 1); self.emit(OP['PUTC'], b=o)
                    self.set('nd', self.v('nd') - 1); self.push_od(R.K(0), 0); self.done()
                with self.when(eq(tc, R.M_PRINT)): self.print_call(10); self.set('osp', osp0 - 1); self.print_end()
                other = self.m(not_(anyeq(tc, (R.M_PAREN, R.M_CALL, R.M_METH, R.M_PUTC, R.M_PRINT, R.M_CALLV))), 'o41')
                with self.when(and_(other, gt(osp0, ob0))): self.fail(46)
                with self.when(and_(other, eq(osp0, ob0))): self.set('f_expr', 1)
            with self.when(and_(live(), eq(binop, 0), semi)):
                with self.when(gt(osp0, ob0)): self.fail(47)
                with self.when(eq(osp0, ob0)):
                    self.set('f_expr', 1)
                    with self.when(PRB): self.set('f_asic', 1)
            with self.when(and_(live(), eq(binop, 0), not_(or_(P(41), P(44), P(58), P(63), P(93), okb, semi, PNL)))): self.fail(48)
        # deferred tails (each is the last thing its path does)
        with self.when(self.v('f_expr')): self.end_expr_stmt(P)
        with self.when(self.v('f_simple')): self.end_simple_stmt(P)
        asic = self.m(self.v('f_asic'), 'asic')
        with self.when(self.v('f_compl')): self.complete_stmt(asic)
        with self.when(asic): self.close_block('f_compl2')        # '}' after a statement without ';'
        with self.when(self.v('f_compl2')): self.complete_stmt(K(0))
        # nothing handled it
        with self.when(self.v('live')): self.fail(99)
        # inside an arrow's expression body (cc_ref.token)
        md = self.m(self.v('mode'), 'mdf')
        with self.when(and_(ne(self.v('ca'), 0), eq(self.v('err'), 0))):
            self.set('mode', ite(eq(md, R.S_OPER), R.S_OPERC, ite(eq(md, R.S_NAMEE), R.S_NAMEEC, md)))

    def end_expr_stmt(self, P):
        t = self.top()
        k = t[0]
        c1 = self.m(and_(eq(k, R.C_IFC), P(41)), 'e1')
        c2 = self.m(and_(eq(k, R.C_WHILEC), P(41)), 'e2')
        c3 = self.m(and_(eq(k, R.C_FORCOND), P(59)), 'e3')
        c4 = self.m(eq(k, R.C_ASSIGN), 'e4')
        c6 = self.m(eq(k, R.C_EXPR), 'e6')
        c7 = self.m(and_(eq(k, R.C_RETURN), or_(P(59), P(R.T_NL), self.v('f_asic'))), 'e7')
        c8 = self.m(and_(anyeq(k, (R.C_DOB, R.C_DOB1)), P(41)), 'e8')
        c9 = self.m(eq(k, R.C_PSET), 'e9')
        c10 = self.m(and_(eq(k, R.C_SWITCHC), P(41)), 'e10')
        c11 = self.m(and_(eq(k, R.C_FOROF), P(41)), 'e11')
        with self.when(c11): self.forof_end(t)
        with self.when(or_(c1, c2, c3, c8)):               # a branch takes the value: if / while (out when false), for / do (in when true)
            self.pop_cs()
            with self.when(or_(c1, c2)): l1 = self.newlab()     # if: else label; while: end label
            self.branch(ite(or_(c1, c2), l1, t[3]), or_(c3, c8))
            with self.when(or_(c1, c2)):
                self.push_cs(ite(c1, R.C_IFB, R.C_LOOPB), ite(c2, t[1], l1), ite(c1, 0, l1)); self.set('mode', R.S_LBRACE); self.done()
            with self.when(c3):
                self.emit(OP['JMP'], label=t[2]); self.deflab(t[4], self.here())
                self.push_cs(R.C_FORSTEP, t[1], t[2], t[3], t[4], t[5]); self.set('mode', R.S_STMT); self.done()
            with self.when(c8): self.deflab(t[2], self.here()); self.set('f_compl', 1); self.done()
        with self.when(c4):                                  # t: symbol, compound op, from a declaration
            self.pop_cs()
            ka, o, _, _ = self.symkind_addr(t[1]); nd = self.m(self.v('nd'), 'and'); i = self.m(nd - 1, 'ai')
            cmp_ = self.m(ne(t[2], 0), 'acmp'); acap = self.captured(t[1], ka)
            with self.when(cmp_):                              # (a snapshot replaced x below e if e changed it)
                self.set_symbool(t[1], self.compound(t[2], i - 1, (ite(acap, self.tmp(i - 1)[0], o), mul(acap, self.tmp(i - 1)[1])), False))
            with self.when(and_(not_(cmp_), acap)): self.set_symbool(t[1], self.otype(i))
            with self.when(acap):                              # cc_ref: its value through the env (scratch: the temp above the top)
                vi = self.m(ite(cmp_, i - 1, i), 'acvi'); sc = self.tmp(add(vi, 1)); self.envbase(sc); self.emit(OP['STI'], sc, (add(o, 640), 0), self.src(vi))
            with self.when(cmp_): self.set('nd', i - 1)
            with self.when(and_(not_(cmp_), not_(acap))): self.put((o, 0), i); self.set_symbool(t[1], self.otype(i))
            with self.when(not_(cmp_)): self.set('nd', i)
            vdecl = self.m(and_(P(44), ne(t[3], 0)), 'vdecl')
            with self.when(self.m(self.v('live'), 'live')):
                with self.when(vdecl): self.set('pn1', sub(t[3], 1)); self.set('pn2', 0); self.set('mode', R.S_VAR); self.done()
                with self.when(not_(vdecl)): self.set('f_simple', 1)
        with self.when(c9):                                  # t: dynamic (x[k]), compound op, the key's offset (64 * c + d)
            self.pop_cs(); i = self.m(self.v('nd') - 1, 'qi'); cm = self.m(ne(t[2], 0), 'qcm'); ti = self.tmp(i - 1)
            with self.when(cm): self.compound(t[2], i - 1, ti, True); self.set('nd', i)
            with self.when(not_(cm)): vs = self.src(i)
            self.write_elem(t[1], add(self.db, mul(t[3], 64), t[4]), (ite(cm, ti[0], vs[0]), ite(cm, ti[1], vs[1])))
            self.set('f_simple', 1)
        with self.when(c10):                                 # the value into T(0), where the case tests read it
            db_ = self.m(self.v('dbase'), 'swdb'); self.pop_cs(); self.to_temp(db_); ty = self.otype(db_); self.set('nd', db_)
            l1 = self.newlab(); l2 = self.newlab()
            self.push_cs(R.C_SWITCH, l1, l2, 0, mul(4, ty)); self.set('mode', R.S_LBRACE); self.done()
        with self.when(c6):
            self.pop_cs(); self.set('nd', self.v('nd') - 1); self.set('f_simple', 1)
        with self.when(c7):
            self.pop_cs()
            i = self.m(self.v('nd') - 1, 'ri'); rty = self.otype(i)
            with self.when(ne(rty, 0)):                       # the function returns a boolean / a string
                cfn = self.v('cfn')
                fl = self.m(add(*[mul(eq(cfn, n_), I(f'fl_{n_}')) for n_ in range(NF)]), 'rfl')
                self.fnw.append((self.x.g, cfn, add(*[mul(eq(cfn, n_), I(f'fh1_{n_}')) for n_ in range(NF)]),
                                 add(*[mul(eq(cfn, n_), I(f'fh2_{n_}')) for n_ in range(NF)]), add(mod(fl, 64), mul(rty, 64), mul(fdiv(fl, 256), 256))))
            o = self.src(i); d1 = self.m(eq(self.v('curf'), 1), 'rd1')       # (a top-level function's: its close label, local 1)
            self.emit(OP['RET'], b=o, c=(mul(d1, add(258, self.v('npar'))), 0), label=ite(d1, self.v('clab'), -1)); self.set('nd', i); self.set('f_compl', 1); self.done()
        with self.when(not_(or_(c1, c2, c3, c4, c6, c7, c8, c9, c10, c11))): self.fail(50)

    def end_simple_stmt(self, P):
        t = self.top()
        with self.when(eq(t[0], R.C_FORINIT)):
            with self.when(not_(P(59))): self.fail(51)
            with self.when(P(59)):
                self.pop_cs(); self.deflab(t[1], self.here()); self.push_cs(R.C_FORCOND, t[1], t[2], t[3], t[4], t[5]); self.set('mode', R.S_OPND); self.done()
        with self.when(eq(t[0], R.C_FORSTEP)):
            with self.when(not_(P(41))): self.fail(52)
            with self.when(P(41)):
                self.pop_cs(); self.emit(OP['JMP'], label=t[1]); self.deflab(t[3], self.here())
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
                with self.when(isloop): self.emit(OP['JMP'], label=t[1]); self.set('tb', sub(self.v('tb'), t[4]))     # (d: a for of's temps)
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
            isfn, islp, issw = self.m(anyeq(k, R.FUNCS), 'cfn'), self.m(eq(k, R.C_LOOPB), 'clp'), self.m(eq(k, R.C_SWITCH), 'csw')
            hasd = self.m(and_(issw, mod(fdiv(t[4], 2), 2)), 'cswd')    # a switch: the last test failed: to default if there is one
            with self.when(hasd): self.emit(OP['JMP'], label=t[2])
            swh = self.here()
            with self.when(hasd): self.emit(OP['JMP'], label=t[3])
            # the code (one instruction slot for both): loop JMP top; function RET #0 (and its frame label := its count of locals)
            cd1 = self.m(and_(isfn, eq(self.v('curf'), 1)), 'ccd1')     # (a top-level function's RET: its close label, local 1)
            uth = self.m(and_(isfn, mod(fdiv(t[4], 2), 2)), 'cuth')     # (it uses this: RET's A 32, the library's mkfn)
            with self.when(or_(islp, isfn)): self.emit(ite(islp, OP['JMP'], OP['RET']), (mul(uth, 32), 0), b=(ite(islp, 512, R.K(R.UNDEF)), 0),
                                                       c=(mul(cd1, add(258, self.v('npar'))), 0), label=ite(islp, t[1], ite(cd1, self.v('clab'), -1)))
            isb = self.m(eq(k, R.C_FUNCB), 'cisb')         # a declaration's calls' entry (cc_ref): its body, or a thunk that makes this the global
            body = self.m(add(self.cb // 2, t[3], mul(fdiv(t[4], 4), 64)), 'cbody')     # object (sharing the switch's label port)
            thk = self.here()
            with self.when(and_(isb, uth)):
                self.emit(OP['NUMLIT'], (R.GCELL, 0), w1=R.GLOBK); self.emit(OP['MOV'], (257, 0), (R.GCELL, 0)); self.emit(OP['JMP'], (body, 0))
            with self.when(or_(issw, isb)): self.deflab(ite(issw, t[1], mod(self.fn_sel(self.v('cfn'), 'fl_'), 64)), ite(issw, swh, ite(uth, thk, body)))
            with self.when(isfn): self.deflab(t[2], self.v('nloc'))
            with self.when(islp): self.set('tb', sub(self.v('tb'), t[4]))     # (d: a for of's temps)
            # the end label of whichever body closed (one kind per call, so one label port serves them all)
            with self.when(anyeq(k, (R.C_ELSEB, R.C_DOB, R.C_LOOPB, R.C_SWITCH) + R.FUNCS)):
                self.deflab(ite(or_(islp, issw), t[2], t[1]), self.here())
            with self.when(anyeq(k, (R.C_ELSEB, R.C_LOOPB, R.C_SWITCH))): self.set(flag, 1); self.done()
            with self.when(eq(k, R.C_DOB)): self.set('csp', self.v('csp') + 1); self.set('mode', R.S_DOWHILE); self.done()
            with self.when(isfn):                              # cc_ref: the outer context back; C_FUNCN's local / C_FUNCE's value
                fkn = self.m(self.v('cfn'), 'cfk'); self.fn_exit(); ise = self.m(eq(k, R.C_FUNCE), 'cfe')
                with self.when(ise): self.set('osp', self.v('osp') - 1); i = self.m(self.v('nd'), 'cfi'); self.push_od(TMP, 0)
                _, lo_, _, _ = self.symkind_addr(t[3]); te = self.tmp(i)
                o = (self.m(ite(ise, te[0], lo_), 'cfo'), mul(ise, te[1]))
                inn = self.m(eq(self.v('curf'), 1), 'cfin')    # (an inner function's: cc_ref, with its env's slot and the frame's size)
                w1 = (ite(inn, add(self.v('npar'), 1, mul(fkn, 64), mul(add(self.v('npar'), 2), 1024)), add(fkn, 16)), inn)
                with self.when(ne(k, R.C_FUNCB)): self.emit(OP['NUMLIT'], o, w1=w1)
                self.set('mode', ite(ise, R.S_OPER, R.S_STMT)); self.done()
            with self.when(not_(anyeq(k, (R.C_BLOCK, R.C_IFB, R.C_ELSEB, R.C_DOB, R.C_LOOPB, R.C_SWITCH) + R.FUNCS))): self.fail(55)

    def end_params(self, fresh=False):
        """cc_ref.end_params. fresh: fnnew made the entry in this step (and wrote its count of parameters)"""
        cfn, npar = self.v('cfn'), self.v('npar')
        if fresh: bad = K(0)
        else:
            fl = self.fn_sel(cfn, 'fl_'); exp = self.m(fdiv(fl, 256), 'pexp')
            bad = self.m(and_(ne(exp, 0), ne(exp, add(npar, 1))), 'pbad')     # cc_ref.end_params: the calls so far must agree
        with self.when(bad): self.fail(76)
        with self.when(not_(bad)):
            if not fresh: self.fnw.append((self.x.g, cfn, self.fn_sel(cfn, 'fh1_'), self.fn_sel(cfn, 'fh2_'), add(mod(fl, 256), mul(add(npar, 1), 256))))
            self.set('nloc', 1)                                # (local 1: an env cell; an inner function's meta + 16: cc_ref)
            self.datum(add(cfn, R.FTAB), add(self.here(), mul(add(npar, mul(eq(self.v('curf'), 2), 16)), 8192)))
            t = self.top(); self.set('mode', ite(and_(eq(t[0], R.C_FUNCE), ne(t[4], 0)), R.S_AARROW, R.S_LBRACE)); self.done()

    def arrow_start(self, h1, h2, argc=0):
        """cc_ref.arrow_start (h1 None: no parameter). argc: as fnnew's"""
        curf = self.m(self.v('curf'), 'asc'); tc_, tv_ = self.top_op()
        with self.when(ge(curf, 2)): self.fail(41)
        ares = self.m(and_(lt(curf, 2), self.isres(h1, h2)), 'ares') if h1 is not None else K(0)
        with self.when(ares): self.fail(36)
        opd = self.m(and_(lt(curf, 2), not_(ares), gt(tc_, 0), lt(tc_, 100)), 'aopd')     # (an operator's operand: 1 + x => x)
        with self.when(opd): self.fail(48)
        with self.when(and_(lt(curf, 2), not_(ares), not_(opd))):
            nm = self.m(mul(eq(tc_, R.M_OKEY), tv_), 'anm')
            self.push_op(R.M_FN, nm); lo = self.newlab(); self.emit(OP['JMP'], label=lo); self.push_cs(R.C_FUNCE, lo, 0, 0, 1)
            self.emit(OP['MOV'], w1=mul(ne(nm, 0), add(nm, self.db - R.STRTAG))); ka = self.fnnew(argc); self.fn_enter(ka)
            if h1 is not None:
                with self.when(eq(self.v('err'), 0)):
                    self.declare(h1, h2, 2, add(self.v('npar'), R.PARAM0)); self.set('npar', self.v('npar') + 1)

    def arrow_body(self):
        """cc_ref.arrow_body"""
        self.deflab(self.v('flab'), 1); self.push_cs(R.C_RETURN); self.set('ca', 1); self.set('mode', R.S_ABODY); self.done()

    def arrow_close(self):
        """cc_ref.arrow_close: the body's RET; the function's end (close_block's)"""
        self.pop_cs(); i = self.m(self.v('nd') - 1, 'aci'); o = self.src(i)
        cd1 = self.m(eq(self.v('curf'), 1), 'acd1')     # (a top-level function's RET: its close label, local 1)
        self.emit(OP['RET'], b=o, c=(mul(cd1, add(258, self.v('npar'))), 0), label=ite(cd1, self.v('clab'), -1)); self.set('nd', i)
        t = self.pop_cs(); self.set('nlet', t[5]); self.deflab(t[1], self.here())     # (its frame label: 1, arrow_body)
        fkn = self.m(self.v('cfn'), 'acfk'); self.fn_exit()
        self.set('osp', self.v('osp') - 1); j = self.m(self.v('nd'), 'acj'); self.push_od(TMP, 0)
        inn = self.m(eq(self.v('curf'), 1), 'acin')
        self.emit(OP['NUMLIT'], self.tmp(j), w1=(ite(inn, add(self.v('npar'), 1, mul(fkn, 64), mul(add(self.v('npar'), 2), 1024)), add(fkn, 16)), inn))
        self.set('mode', R.S_OPER)

    def outputs(self):
        """per-level outputs for the overlay: EMAX instruction slots (word0: its base and label id or -1; word1: its base, the
        frame label and its multiplier; the RAM index of word0; valid) and one data word"""
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
            sels = [X.mat(and_(g, eq(ip, add(cp0, s))), 'sel') for g, ip, op, a, la, w, m, fl in code]
            group(f'o_v{s}', or_(*sels), [
                (f'o_w{s}', add(*[mul(sel, op) for sel, (g, ip, op, a, la, w, m, fl) in zip(sels, code)])),     # (op: word0, ew0)
                (f'o_l{s}', sub(add(*[mul(sel, add(la, 1)) for sel, (g, ip, op, a, la, w, m, fl) in zip(sels, code)]), 1)),
                (f'o_x{s}', add(*[mul(sel, w) for sel, (g, ip, op, a, la, w, m, fl) in zip(sels, code)])),
                (f'o_m{s}', add(*[mul(sel, m) for sel, (g, ip, op, a, la, w, m, fl) in zip(sels, code)])),
                (f'o_f{s}', add(*[mul(f, add(*[sel for sel, r in zip(sels, code) if r[7] == f])) for f in dict.fromkeys(r[7] for r in code)])),   # (by frame label: one per step in practice)
                (f'o_a{s}', add(mul(cp0, 2), self.cb + 2 * s - self.db))])      # RAM index (address - rom_size = data_base)
        self.nlports = len(labs)
        for k, (g, l, v) in enumerate(labs):               # label definitions: one anchor element per port
            group(f'o_lv{k}', g, [(f'o_lj{k}', l), (f'o_lx{k}', v)])
        def port(pre, recs, fields):
            recs = live(recs)
            group(f'o_{pre}w', or_(*[r[0] for r in recs]), [(f'o_{pre}{f}', add(*[mul(r[0], r[i + 1]) for r in recs])) for i, f in enumerate(fields)])
        port('y', self.symw, ('i', 'h1', 'h2', 'k'))
        port('f', self.fnw, ('i', 'h1', 'h2', 'l'))
        port('i', self.intw, ('i', 'h1', 'h2', 'v'))
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
        tk, tv = self.m(self.v('tk'), 'ptk_'), self.m(self.v('tv'), 'ptv_')
        # cc_ref.char's token tail: an object literal's key is committed at its ':'; console.log's log is no property name
        nl = self.m(and_(eq(tk, 4), eq(tv, R.T_NL)), 'isnl')
        icm = self.m(self.v('icm'), 'icm')
        with self.when(and_(eq(tk, 4), eq(tv, 58), ne(icm, 0))): self.set('sdp', add(self.v('sdp'), icm))
        with self.when(and_(ne(tk, 0), ne(tk, 2), not_(nl))): self.set('icm', 0)
        with self.when(and_(ne(tk, 0), not_(nl))):
            isfn = and_(eq(tk, 2), eq(self.v('th1'), KW['function'][0]), eq(self.v('th2'), KW['function'][1]))     # (a function's name: committed)
            self.set('kpos', add(mul(or_(and_(eq(tk, 4), eq(tv, 46), not_(self.v('lcon'))), isfn), 2), and_(eq(tk, 4), or_(eq(tv, 123), eq(tv, 44)))))
            self.set('lcon', and_(eq(tk, 2), eq(self.v('th1'), KW['console'][0]), eq(self.v('th2'), KW['console'][1])))
        isret = and_(eq(tk, 2), eq(self.v('th1'), KW['return'][0]), eq(self.v('th2'), KW['return'][1]))     # lt 2: restricted
        self.set('lt', ite(ne(tk, 0), add(or_(inrange(tk, 1, 3), and_(eq(tk, 4), anyeq(tv, (41, 93, 125, 7, 8)))), isret), self.v('lt')))
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
        if INLINE: self.x.inline(set(self.out))


# ---------------- compiled variants, cached on disk (the L2 levels: tests/cmp_dsl.py, the fuzzer)
# Building a parser variant takes ~70 ms and every L2 worker process needs a few hundred; its Python function
# (dsl.pyfn) marshals to ~15 KB and loads in ~0.1 ms. build/dslcache/<hash>/ holds them, the hash naming every input:
# the sources this module imports (sources_hash), layout.json, the ROM's entry points, the bases, INLINE, SPECK and
# Python's version (marshal's format). DSLCACHE=0 builds every variant in memory; DSLEVAL=interp or both
# (dsl.Ctx.run_python) bypasses it.
import sys, hashlib, marshal, shutil, dsl
class Compiled:
    """what the L2 levels use of a Prog: run(env) -> ({state: value}, env + {('T', temp): value}), out, nlports, ntemps"""
    def __init__(self, run, out, nlports, ntemps): self.run, self.out, self.nlports, self.ntemps = run, out, nlports, ntemps
_HERE = os.path.dirname(os.path.abspath(__file__))
def sources_hash(h, *mods):
    """h.update() with the source of every module of this repository that mods import, directly or not (found through
    their globals: imported modules, and the modules of imported functions and classes), and with compiler/layout.json,
    which cc_ref reads at import"""
    root = os.path.dirname(os.path.dirname(_HERE)); seen = {}; todo = list(mods)
    while todo:
        m = todo.pop(); f = getattr(m, '__file__', None)
        if not f or os.path.abspath(f) in seen or not os.path.abspath(f).startswith(root + os.sep): continue
        f = os.path.abspath(f)
        seen[f] = m
        for v in vars(m).values():
            d = v if type(v) is type(os) else sys.modules.get(getattr(v, '__module__', None) or '')
            if d is not None: todo.append(d)
    for f in sorted(seen) + [os.path.join(_HERE, 'layout.json')]: h.update(f.encode()); h.update(open(f, 'rb').read())
    return h
_cdir = {}
def _cache_dir(data_base, code_base, lib):
    k = (data_base, code_base, id(lib))
    if k not in _cdir:
        h = hashlib.sha256(repr((data_base, code_base, INLINE, SPEC_LEVEL, sys.version, sorted((lib or {}).get('entries', {}).items()))).encode())
        sources_hash(h, sys.modules[__name__])
        _cdir[k] = os.path.join(_HERE, '..', 'build', 'dslcache', h.hexdigest()[:16])
    return _cdir[k]
def compiled(data_base, code_base, lib, key=(None, None, None), lex=None):
    """the variant `key` of Prog (or LexProg(data_base, cset=lex) when lex is a set of characters), compiled"""
    use = os.environ.get('DSLCACHE', '1') == '1' and dsl.EVAL == 'py'
    path = os.path.join(_cache_dir(data_base, code_base, lib), ('lex_' + '_'.join(map(str, sorted(lex))) if lex is not None else '_'.join(map(str, key))) + '.bin')
    if use and os.path.exists(path):
        code, out, nl, nt = marshal.loads(open(path, 'rb').read()); g = {}; exec(code, g)
        return Compiled(g['f'], out, nl, nt)
    pg = LexProg(data_base, cset=lex) if lex is not None else Prog(data_base, code_base, lib, *key)
    if not use: return Compiled(pg.x.run_python, pg.out, getattr(pg, 'nlports', 0), len(pg.x.temps))
    src = dsl.pysrc(pg.x.temps, pg.x.cur, pg.x.state)
    d = os.path.dirname(path)
    if not os.path.isdir(d):                     # a new version of the sources: keep the 8 newest versions' caches
        os.makedirs(d, exist_ok=True); up = os.path.dirname(d)
        for old in sorted(os.listdir(up), key=lambda n: -os.path.getmtime(os.path.join(up, n)))[8:]: shutil.rmtree(os.path.join(up, old), ignore_errors=True)
    tmp = f'{path}.{os.getpid()}'
    with open(tmp, 'wb') as f: f.write(marshal.dumps((compile(src, '<dsl.pyfn>', 'exec'), pg.out, getattr(pg, 'nlports', 0), len(pg.x.temps))))
    os.replace(tmp, path)
    return compiled(data_base, code_base, lib, key, lex)
