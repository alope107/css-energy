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
import cc_ref as R

OD, CD, NS, NF, NL, NI, ODN, TBMAX = R.OD, R.CD, R.NS, R.NF, R.NL, R.NI, R.ODN, R.TBMAX
H1M, H2M = R.H1M, R.H2M
KW = R.KW
OP = R.OP
KBIG, TMP, CND = R.KBIG, R.TMP, R.CND

LEX_STATE = ['lx', 'q', 'lt', 'tkc', 'acc', 'h1', 'h2', 'p2', 'sstart', 'sdp', 'pp', 'inul', 'icm', 'kpos', 'lcon', 'pnl']

def parse_state_names():
    s = ['dp', 'mode', 'pn1', 'pn2', 'osp', 'csp', 'nsym', 'nlet', 'nfn', 'nlab', 'cp', 'curf', 'cfn', 'nfdef', 'nloc', 'npar', 'fsym', 'pendLa',
         'err', 'nint', 'pm', 'nd', 'pk', 'tb']
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
    st = {n: 0 for n in LEX_STATE}; st['sdp'] = data_base + R.SDATA + 1 + len(R.SEED)        # (cc_ref: past the DONE marker and SEED)
    return st

def initial_parse(data_base):
    st = {n: 0 for n in parse_state_names()}
    st['dp'] = data_base + 1; st['mode'] = R.S_STMT
    return st

# punctuation codes the parser distinguishes (single chars and the lexer's two-char codes); others share a variant.
# '?' and ':' are not among them: every variant costs some time on every token level, whether it applies or not, and
# only S_OPER (and the modes that fall into it) accepts them, so they share the 'other punctuation' variant there
PUNCT = sorted({41, 59, 93, 40, 44, 61, 123, 91, 45, 8, 7, 46, 125, 33, R.T_NL} | set(R.BIN) | set(R.COMPOUND))
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
        X.cur.update(live=K(1), f_expr=K(0), f_simple=K(0), f_compl=K(0), f_asic=K(0), f_compl2=K(0))
        X.cur.update({f'sc{c}{f}': K(0) for c in 'AOT' for f in ('', 'l', 'x')}); X.cur['ptop'] = K(0); X.cur['psp'] = K(0)
        if mode is not None: X.cur['mode'] = K(mode); X.cur['err'] = K(0)
        self.code = []      # (valid, instruction index, op, A, word0's label or -1, word1, word1's multiplier, frame label)
        self.labs = []      # (valid, label, value)
        self.data = []      # (valid, addr, value)
        self.symw = []      # (valid, index, h1, h2, sk)
        self.fnw = []       # (valid, index, h1, h2, label)
        self.intw = []      # (valid, index, h1, h2, value)
        self.out = []
        self.parser()
        self.outputs()
        self.x.dce(self.out)

    # ---------------- primitives
    def v(self, n): return self.x.v(n)
    def set(self, n, val): self.x.set(n, val)
    def setif(self, n, c, val):
        """n := val if c (and the current guard): one temp, where a when() block would add a guard temp"""
        X = self.x; X.cur[n] = X.mat(ite(and_(X.g, c), lift(val), X.cur[n]), n + '_')
    def when(self, c): return self.x.when(c)
    def m(self, e, h='t'): return self.x.mat(e, h)
    def frame_label(self): return self.m(mul(self.v('curf'), mod(self.v('csA0'), 64)), 'frl')     # (a function's FUNCB is entry 0)
    def emit(self, op, a=NOP0, b=BOP0, c=NOP0, label=None, w1=None):
        """cc_ref.emit: op A, B, C with operands (field, temp?), or A and word1 whole (w1: a value, or (field, temp?)); label:
        A is that label's value at link time. Temps add the frame label: times 1 in A, 1024 in B, 1 in C or word1"""
        X = self.x; fl = self.frame_label()
        a, b, c = (lift(a[0]), lift(a[1])), (lift(b[0]), lift(b[1])), (lift(c[0]), lift(c[1]))
        if w1 is None: w, m = add(mul(sub(b[0], 512), 1024), c[0]), add(mul(b[1], 1024), c[1])
        elif isinstance(w1, tuple): w, m = lift(w1[0]), lift(w1[1])
        else: w, m = lift(w1), K(0)
        la = lift(label) if label is not None else ite(a[1], fl, -1)
        self.code.append((X.g, X.cur['cp'], lift(op), a[0], self.m(la, 'ela'), self.m(w, 'ew'), self.m(m, 'em'), fl))
        self.set('cp', self.v('cp') + 1)
    def deflab(self, l, val): self.labs.append((self.x.g, lift(l), lift(val)))
    def datum(self, addr, val): self.data.append((self.x.g, lift(addr), lift(val)))
    def here(self): return self.m(add(mul(self.v('cp'), 2), self.cb), 'here')
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
    def tmerge(self, a, b): return self.m(ite(or_(eq(a, 1), eq(b, 1)), 1, mul(eq(a, b), b)), 'tmg')     # cc_ref.tmerge
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
        """kind, operand (cc_ref.var), static type, const flag of symbol j"""
        sk = self.sym_sel(j, 'sk_', 'sk')
        b = self.m(mod(fdiv(sk, 65536), 4), 'skb'); r = self.m(mod(sk, 65536), 'skr'); cst = self.m(fdiv(sk, 262144), 'skc')
        k, a = self.m(fdiv(r, 16384), 'skk'), self.m(sub(mod(r, 16384), 8192), 'ska')
        # parameter i is stored as kind 2, addr PARAM0 + i: its frame slot is 1 + i
        ispar = self.m(and_(eq(k, 2), ge(a, R.PARAM0)), 'spar')
        o = self.m(ite(eq(k, 2), add(256, ite(ispar, sub(a, R.PARAM0 - 1), a)), sub(a, self.db)), 'svar')
        return k, o, b, cst
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
    def tmp(self, i): return (self.m(add(257, mul(self.v('npar'), self.v('curf')), self.v('tb'), i), 'tmpf'), self.v('curf'))
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
            with self.when(and_(lt(k, n), lt(d, 768), hit(d))):        # (its temp: at the tb it was pushed at)
                tbk = self.m(fdiv(w, 16384), 'stb')
                self.emit(OP['MOV'], (self.m(add(257, mul(self.v('npar'), self.v('curf')), tbk, k), 'stf'), self.v('curf')), (d, 0))
                self.set_od(k, add(mul(tbk, 16384), mul(mod(fdiv(w, 4096), 4), 4096), TMP))
    def pend(self, i, ci, b, c):
        """cc_ref.pend: descriptor i := the pending comparison ci (CNDOPS' index) of b and c"""
        self.set_od(i, add(CND + 0, mul(ci, 4), mul(b[1], 2), c[1]), 1); self.set('pk', add(mul(sub(b[0], 512), 1024), c[0]))
    def branch(self, lab, sense):
        """cc_ref.branch: pop the top value and jump to lab if its truth is sense (a pending comparison fuses into the jump)"""
        sense = lift(sense); nd = self.m(self.v('nd'), 'bnd'); i = self.m(nd - 1, 'bi'); d = self.desc(i); t = self.otype(i)
        self.set('nd', i)
        cnd = self.m(ge(d, CND), 'bcnd'); e = self.m(sub(d, CND), 'bce'); ci = self.m(fdiv(e, 4), 'bci')
        pk = self.v('pk')
        bF, cF = (self.m(add(fdiv(pk, 1024), 512), 'bbf'), self.m(mod(fdiv(e, 2), 2), 'bbt')), (self.m(mod(pk, 1024), 'bcf'), self.m(mod(e, 2), 'bct'))
        jt = [OP['J' + R.NAME[c]] for c in R.CMPS] + [OP['JZ']]                        # by CNDOPS' index, when sense (! b: b false)
        jf = [OP['J' + R.NAME[R.INV[c]]] for c in R.CMPS] + [OP['JNZ']]
        jop = self.m(ite(sense, add(*[mul(eq(ci, k), v_) for k, v_ in enumerate(jt)]), add(*[mul(eq(ci, k), v_) for k, v_ in enumerate(jf)])), 'bjop')
        isk = self.m(and_(ge(d, 768), lt(d, 1024)), 'bisk')
        kbn = self.m(and_(eq(d, KBIG), ne(t, 2)), 'bkbn')
        jumpc = self.m(or_(and_(isk, eq(ne(d, R.K(0)), sense)), and_(kbn, eq(ne(pk, 0), sense))), 'bjc')
        other = self.m(not_(or_(cnd, isk, kbn)), 'both')
        with self.when(other): o = self.src(i)
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
            with self.when(ne(p2, 0)):
                tok(4, p2); self.set('p2', 0)
                with self.when(and_(or_(eq(p2, 1), eq(p2, 2)), eq(cn, 61))): self.set('lx', 5)
            with self.when(eq(p2, 0)):
                sp = self.m(or_(*[ceq(v) for v in R.BLANK]), 'spc')
                with self.when(ceq(10)): newline()
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
                        tok(2, add(strtok(ge(add(sdp, ln + 2), SEND), sdp + 1, ln + 1), mul(eq(cn, 40), 262144)), nh1, nh2); self.set('tkc', 0)
                        with self.when(ne(kp, 0)): self.set('inul', add(sdp, ln + 2))
                        with self.when(eq(kp, 2)): self.set('sdp', add(sdp, ln + 3))
                        self.set('icm', mul(eq(kp, 1), ln + 3))
                with self.when(cJ):
                    nacc = self.m(add(mul(mul(eq(tkc, 2), self.v('acc')), 10), sub(c, 48)), 'nacc')
                    self.set('acc', nacc); self.set('tkc', 2)
                    with self.when(not_(dgcn)): tok(1, nacc); self.set('tkc', 0)
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
        go = K(1)
        for _ in range(OD):
            code, val = self.top_op(); p = self.prec(code)
            go = self.m(and_(go, eq(self.v('err'), 0), gt(self.v('osp'), 0), gt(p, 0), ge(p, minprec)), 'pop')
            with self.when(go):
                self.set('osp', self.v('osp') - 1)
                c2, v2 = self.top_op(); p2 = self.prec(c2)
                last = self.m(not_(and_(gt(self.v('osp'), 0), gt(p2, 0), ge(p2, minprec))), 'plast')
                nd = self.m(self.v('nd'), 'pnd'); iR, iL = self.m(nd - 1, 'piR'), self.m(nd - 2, 'piL')
                ptop = self.v('ptop'); dR, tR, tL = self.m(mod(ptop, 4096), 'pdR'), self.m(mod(fdiv(ptop, 4096), 4), 'ptR'), self.otype(iL)
                oR, oL, TR, TL = self.opnd(iR, dR), self.opnd(iL), self.tmp(iR), self.tmp(iL)
                isAO = self.m(or_(eq(code, R.AND), eq(code, R.OR)), 'pao'); isTE = self.m(eq(code, R.M_TELSE), 'pte')
                isUN = self.m(or_(eq(code, R.NOT), eq(code, R.NEG)), 'pun'); isCA = self.m(eq(code, R.M_CADD), 'pca')
                hasstr = self.m(or_(eq(val, 2), eq(tR, 2)), 'pstr')
                popped = self.m(or_(popped, go), 'ppd')
                ok = K(1)
                split = self.m(and_(isCA, hasstr, lt(v2, 4 * (R.PIECES - 1))), 'psplit')     # (past PIECES: the last two joined)
                isBIN = self.m(not_(or_(isAO, isTE, isUN, split)), 'pbin')            # (M_CADD that doesn't split: ADD)
                binc = self.m(ite(isCA, R.ADD, code), 'pbc')
                num = lambda t: or_(eq(t, 1), eq(t, 3))                         # cc_ref.isdyn: a string, array or object possible
                dyn = self.m(and_(isBIN, ite(eq(binc, R.ADD), not_(and_(num(tL), num(tR))), and_(inrange(binc, R.LT, R.NE), not_(or_(num(tL), num(tR)))))), 'pdyn')
                pnot = self.m(and_(eq(code, R.NOT), last, br), 'pnot')
                pcmp = self.m(and_(isBIN, not_(dyn), last, br, inrange(code, R.LT, R.NE)), 'pcmp')
                isd = self.m(and_(last, dvalid, not_(dyn)), 'pisd')               # (a dynamic operator's destination is its temp)
                # the one instruction: && / || MOV T(iL), right; M_TELSE MOV T(iR), right (if not there); ! / - (dest or T(iR));
                # binary (dest or T(iL)) left op right
                with self.when(and_(ok, or_(isAO, and_(isTE, ne(dR, TMP)), and_(isUN, not_(pnot)), and_(isBIN, not_(pcmp))))):
                    dop = ite(eq(binc, R.ADD), ite(eq(tL, 1), OP['DADDL'], ite(eq(tR, 1), OP['DADDR'], OP['DADD'])), add(OP['DLT'] - R.LT, binc))
                    op = ite(or_(isAO, isTE), OP['MOV'], ite(isUN, ite(eq(code, R.NOT), OP['NOT'], OP['NEG']), ite(dyn, dop, sub(binc, R.ADD))))
                    dst = ite(isAO, TL[0], ite(or_(isTE, and_(isUN, not_(isd))), TR[0], ite(isd, dfield, TL[0])))
                    dstt = mul(not_(and_(isd, not_(isAO), not_(isTE))), self.v('curf'))
                    un = or_(isAO, isTE, isUN)
                    self.emit(op, (self.m(dst, 'pdst'), self.m(dstt, 'pdstt')), (ite(un, oR[0], oL[0]), ite(un, oR[1], oL[1])),
                              (mul(isBIN, oR[0]), mul(isBIN, oR[1])))
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
                                                    ite(or_(pnot, pcmp, and_(isUN, eq(code, R.NOT)), inrange(code, R.LT, R.NE)), 1,
                                                        ite(dyn, mul(2, or_(eq(tL, 2), eq(tR, 2))), 3)))),
                         ite(pnot, add(CND + 24, mul(oR[1], 2)), ite(pcmp, add(CND - 4 * R.LT, mul(code, 4), mul(oL[1], 2), oR[1]),
                             ite(and_(isd, or_(isUN, isBIN)), dfield, TMP))))
                self.setif('ptop', and_(ok, not_(split)), ae)
                self.setif('pk', and_(ok, or_(pnot, pcmp)), ite(pnot, mul(sub(oR[0], 512), 1024), add(mul(sub(oL[0], 512), 1024), oR[0])))
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
        nomark = self.m(not_(or_(*[and_(lt(k, osp), ge(self.v(f'op{k}'), 100 * 8192)) for k in range(OD)])), 'nomark')
        t = self.top()
        _, o, _, _ = self.symkind_addr(t[1])
        return nomark, t[0], self.m(and_(nomark, eq(t[0], R.C_ASSIGN), eq(t[2], 0)), 'dok'), o

    def print_call(self, sep):
        """cc_ref.print_call: the argument's pieces (M_PRINT's value // 4 + 1 of them, on top of the operand stack), one PRINT each
        (PRINTK for the big constant on top); the last with the separator"""
        _, pv = self.top_op(); c = self.m(fdiv(pv, 4), 'pcc'); nd = self.m(self.v('nd'), 'pnd'); d0 = self.m(sub(sub(nd, 1), c), 'pd0')
        for k in range(ODN):
            with self.when(and_(ge(k, d0), lt(k, nd))):
                d = self.m(mod(self.v(f'od{k}'), 4096), 'prd'); kb = self.m(eq(d, KBIG), 'prk'); o = self.opnd(K(k))
                flags = add(mul(eq(k, nd - 1), 2 * R.SEP[sep]), eq(mod(fdiv(self.v(f'od{k}'), 4096), 4), 1), mul(gt(c, 0), 8))
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
        return self.m(and_(eq(self.v('osp'), 0), eq(self.top()[0], R.C_EXPR)), 'stl')
    def marker(self):
        """cc_ref.marker: the innermost marker on the operator stack (0: none)"""
        osp = self.m(self.v('osp'), 'mko')
        best = self.m(mx(*[mul(and_(lt(k, osp), ge(self.v(f'op{k}'), 100 * 8192)), k + 1) for k in range(OD)]), 'mkb')
        return self.m(fdiv(add(*[mul(eq(best, k + 1), self.v(f'op{k}')) for k in range(OD)]), 8192), 'mkc')
    def num(self, t): return or_(eq(t, 1), eq(t, 3))
    def daddop(self, tl, tr): return ite(eq(tl, 1), OP['DADDL'], ite(eq(tr, 1), OP['DADDR'], OP['DADD']))     # cc_ref.dynop(ADD)
    def join_pieces(self):
        """cc_ref.join_pieces: a + chain's pieces (M_PRINT on top) joined into one string, its first piece's temp"""
        tc, tv = self.top_op()
        with self.when(and_(eq(tc, R.M_PRINT), ge(tv, 4))):
            nd = self.m(self.v('nd'), 'jnd'); d0 = self.m(sub(sub(nd, 1), fdiv(tv, 4)), 'jd0')
            self.src(nd - 1)
            for j in range(1, R.PIECES):
                k = self.m(add(d0, j), 'jk')
                with self.when(lt(k, nd)):
                    self.emit(self.daddop(self.otype(d0), self.otype(k)), self.tmp(d0), self.opnd(d0), self.opnd(k)); self.set_od(d0, TMP, 2)
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
    def compound(self, code, i, o, otemp):
        """cc_ref.compound: x op= e, the old value at i, e above it, into o (otemp: o is i's temp) -> the static type"""
        tl, tr = self.otype(i), self.otype(i + 1)
        dyn = self.m(and_(eq(code, R.ADD), not_(and_(self.num(tl), self.num(tr)))), 'cdyn')
        r = self.src(i + 1); l = self.opnd(i); t = self.tmp(i)
        self.emit(ite(dyn, self.daddop(tl, tr), sub(code, R.ADD)), (ite(dyn, t[0], o[0]), ite(dyn, t[1], o[1])), l, r)
        if not otemp:
            with self.when(dyn): self.emit(OP['MOV'], o, t)
        return self.m(ite(dyn, mul(2, or_(eq(tl, 2), eq(tr, 2))), 3), 'cty')
    def meth_end(self, tv, last):
        """cc_ref.meth_end: a method call's ')' (tv: the method + 64 * its commas; last: an argument just ended)"""
        mi = self.m(mod(tv, 64), 'mmi'); argc = self.m(add(fdiv(tv, 64), last), 'margc')
        pairs = [(i, a, e) for i, m in enumerate(R.ALLM) for a, e in m[1].items()]
        ok = self.m(or_(*[and_(eq(mi, i), eq(argc, a)) for i, a, e in pairs]), 'mok')
        with self.when(not_(ok)): self.fail(77)
        with self.when(ok):
            sb = self.m(and_(eq(mi, R.GLOBAL_INDEX[KW['String']]), eq(self.otype(self.v('nd') - 1), 1)), 'msb')    # String(a boolean)
            e = self.m(ite(sb, self.ent.get('tostringb', 0), add(*[mul(and_(eq(mi, i), eq(argc, a)), self.ent.get(e, 0)) for i, a, e in pairs])), 'ment')
            ty = self.m(add(*[mul(eq(mi, i), m[2]) for i, m in enumerate(R.ALLM)]), 'mty')
            if last: self.arg_end()
            self.set('tb', sub(self.v('tb'), argc + 1)); d0 = self.m(self.v('nd') - 1, 'md0'); f = self.tmp(d0)
            self.emit(OP['CALL'], (e, 0), w1=(sub(f[0], 256), f[1])); self.set_od(d0, TMP, ty)
            self.set('mode', R.S_OPER); self.done()
    def arr_make(self, n):
        """cc_ref.arr_make: mkarrN of the n collapsed elements above the slot"""
        self.set('tb', sub(self.v('tb'), n)); d0 = self.m(self.v('nd') - 1, 'amd'); f = self.tmp(d0)
        self.emit(OP['CALL'], (add(*[mul(eq(n, k), self.ent.get(f'mkarr{k}', 0)) for k in range(9)]), 0), w1=(sub(f[0], 256), f[1]))
        self.set_od(d0, TMP, 0)
    def arr_store(self, k):
        """cc_ref.arr_store: element k (past the eighth, on top) into the array below it"""
        with self.when(gt(k, 127)): self.fail(22)
        with self.when(le(k, 127)):
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
        """cc_ref.case_end: J!= Tnext, T(0), value (DEQ + JZ when either may be a string)  Bk:"""
        c = self.pop_cs(); tn = self.newlab()
        dyn = self.m(not_(or_(self.num(self.otype(K(0))), self.num(self.otype(K(1))))), 'ksdyn')
        r = self.src(K(1)); l = self.opnd(K(0)); t1 = self.tmp(K(1)); fl = self.frame_label()
        self.emit(ite(dyn, OP['DEQ'], OP['JNE']), (mul(dyn, t1[0]), mul(dyn, t1[1])), l, r, label=ite(dyn, ite(t1[1], fl, -1), tn))
        with self.when(dyn): self.emit(OP['JZ'], b=t1, label=tn)
        self.set('nd', 0)
        with self.when(c[2]): self.deflab(c[1], self.here())
        t = self.top()
        self.set_top(add(R.C_SWITCH * 4096, mul(tn, 64), t[2]), add(mul(t[5], 4096), mul(t[3], 64), t[4], sub(1, mod(t[4], 2))))
        self.set('mode', R.S_STMT); self.done()

    def fn_sel(self, k, f): return self.m(add(*[mul(eq(k, i), I(f'{f}{i}')) for i in range(NF)]), f)
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
            self.set('tb', sub(self.v('tb'), argc)); d0 = self.m(self.v('nd') - 1, 'cd0'); f = self.tmp(d0)
            self.emit(OP['CALL'], label=mod(fl, 64), w1=(sub(f[0], 256), f[1]))
            self.set_od(d0, TMP, mod(fdiv(tv, 16), 4))
            self.done()

    def print_end(self):
        """cc_ref.print_end: console.log(...) leaves no value; it ends its statement (C_EXPR)"""
        ok = self.m(and_(eq(self.v('osp'), 0), eq(self.top()[0], R.C_EXPR)), 'pend')
        with self.when(not_(ok)): self.fail(30)
        with self.when(ok): self.pop_cs(); self.set('mode', R.S_INC); self.done()

    def incdec(self, h1, h2, op, x=0, pre=None):
        """cc_ref.incdec. x: 0 statement, 1 ++x / 2 x++ in an expression; pre: the symbol (j, k, o, b, cst) if looked up"""
        if pre is None: j = self.lookup(h1, h2); k, o, b, cst = self.symkind_addr(j)
        else: j, k, o, b, cst = pre
        x = lift(x); x1, x2 = self.m(eq(x, 1), 'ix1'), self.m(eq(x, 2), 'ix2')
        with self.when(lt(j, 0)): self.fail(6)
        with self.when(and_(ge(j, 0), cst)): self.fail(64)
        with self.when(and_(ge(j, 0), not_(cst))):
            with self.when(ne(x, 0)): self.snapshot(lambda d: eq(d, o))
            with self.when(x2): self.push_od(o, 3); self.to_temp(self.v('nd') - 1)
            self.emit(ite(eq(op, 7), OP['ADD'], OP['SUB']), (o, 0), (o, 0), (R.K(1), 0))
            with self.when(x1): self.push_od(o, 3)
            with self.when(ne(x, 0)): self.set('pm', 3); self.set('mode', R.S_OPER)
            with self.when(eq(x, 0)): self.set('mode', R.S_INC)
            self.done()

    def jump_loop(self, isbreak):
        """break / continue: JMP to the innermost loop's break (b) or continue (a) label"""
        csp = self.m(self.v('csp'), 'csp')
        def target(kind): return or_(anyeq(kind, (R.C_LOOPB, R.C_LOOPB1, R.C_DOB, R.C_DOB1)), and_(isbreak, eq(kind, R.C_SWITCH)))
        best = self.m(mx(*[mul(and_(lt(k, csp), target(fdiv(self.v(f'csA{k}'), 4096))), k + 1) for k in range(CD)]), 'lpk')
        A = self.m(add(*[mul(eq(best, k + 1), self.v(f'csA{k}')) for k in range(CD)]), 'lpA')
        with self.when(eq(best, 0)): self.fail(56)
        with self.when(ne(best, 0)):
            self.emit(OP['JMP'], label=ite(isbreak, mod(A, 64), mod(fdiv(A, 64), 64))); self.set('mode', R.S_INC); self.done()

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
                R.S_LBRACE: (R.S_STMT,), R.S_CONFIRST: (R.S_OPND,), R.S_SWCASE: (R.S_STMT,)}
        reach = None if self.spec_mode is None else {self.spec_mode, *FALL.get(self.spec_mode, ())}
        def block(md):
            if reach is not None and md not in reach: return self.when(K(0))
            return self.when(and_(live(), eq(mode(), md)))
        PNL, PRB = P(R.T_NL), P(125)
        NOTSUB = R.NOTSUB
        # a newline token means nothing outside the modes where it can end a statement
        with self.when(and_(PNL, not_(anyeq(mode(), (R.S_NAMES, R.S_NAMEE, R.S_OPER, R.S_VARAFTER, R.S_INC, R.S_OPND))))): self.done()
        # ---- S_NAMES
        with block(R.S_NAMES):
            pn1, pn2 = self.v('pn1'), self.v('pn2')
            j = self.lookup(pn1, pn2)
            k, o, b, cst = self.symkind_addr(j)
            asg = self.m(or_(P(61), ne(compound, 0)), 'asg')
            with self.when(asg):
                with self.when(lt(j, 0)): self.fail(5)
                with self.when(and_(ge(j, 0), cst)): self.fail(64)
                with self.when(and_(ge(j, 0), not_(cst))):
                    with self.when(not_(P(61))): self.push_od(o, b)        # x op= e: x is the left operand, read first
                    self.push_cs(R.C_ASSIGN, j, compound); self.set('mode', R.S_OPND); self.done()
            with self.when(or_(P(7), P(8))): self.incdec(pn1, pn2, tv)
            with self.when(and_(P(91), lt(j, 0))): self.fail(7)      # NAME[e] = e: an expression statement (x[k])
            with self.when(not_(or_(asg, P(7), P(8), and_(P(91), lt(j, 0))))):
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
                gi = self.m(add(*[mul(and_(eq(pn1, KW[g[0]][0]), eq(pn2, KW[g[0]][1])), R.GLOBAL_INDEX[KW[g[0]]] + 1) for g in R.GLOBALS]), 'gi')
                with self.when(isputc): self.push_op(R.M_PUTC)
                with self.when(and_(not_(isputc), ne(gi, 0))):            # parseInt(s), ...: a method on a dummy receiver
                    self.push_od(TMP, 0); self.set('tb', self.v('tb') + 1); self.push_op(R.M_METH, sub(gi, 1))
                with self.when(and_(not_(isputc), eq(gi, 0))):
                    self.snapshot(lambda d: lt(d, 256))                     # the callee may change a global still on the stack
                    fi, _, fb = self.fnfind(pn1, pn2); self.push_op(R.M_CALL, add(fi, mul(fb, 16))); self.push_od(TMP, 0)    # its slot
                self.set('mode', R.S_OPND); self.done()
            p78n = self.m(or_(P(7), P(8)), 'p78n')
            with self.when(and_(not_(iscon), not_(P(40)))):
                j = self.lookup(pn1, pn2)
                k, o, b, cst = self.symkind_addr(j)
                with self.when(p78n): self.incdec(pn1, pn2, tv, 2, (j, k, o, b, cst))     # x++ in an expression
                sdot = self.m(and_(not_(p78n), lt(j, 0), eq(pn1, KW['String'][0]), eq(pn2, KW['String'][1]), P(46)), 'sdot')
                with self.when(sdot): self.push_od(R.K(0), 0); self.set('mode', R.S_DOT); self.done()     # String.fromCharCode
                with self.when(and_(not_(p78n), lt(j, 0), not_(sdot))): self.fail(4)
                with self.when(and_(not_(p78n), ge(j, 0))): self.push_od(o, b); self.set('mode', R.S_OPER)
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
                undef = self.m(lt(self.v('nfdef'), self.v('nfn')), 'undef')
                with self.when(and_(eq(self.v('csp'), 0), undef)): self.fail(60)
                with self.when(and_(eq(self.v('csp'), 0), not_(undef))): self.emit(OP['HALT']); self.done()
            with self.when(P(123)): self.push_cs(R.C_BLOCK); self.done()
            with self.when(P(125)): self.close_block()
            with self.when(P(59)): self.set('f_simple', 1)
            fstep = self.m(and_(P(41), eq(t0, R.C_FORSTEP)), 'fstep')
            with self.when(fstep): self.set('f_simple', 1)
            with self.when(or_(P(7), P(8))): self.set('pn1', tv); self.set('pn2', 0); self.set('mode', R.S_PREINC); self.done()
            other = self.m(and_(not_(isEOF), not_(P(123)), not_(P(125)), not_(P(59)), not_(fstep), not_(P(7)), not_(P(8))), 'oth')
            with self.when(and_(other, not_(isID))): self.fail(8)
            with self.when(and_(other, isID)):
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
                    self.jump_loop(KWc('break'))
                with self.when(KWc('function')):
                    bad = self.m(or_(ne(self.v('curf'), 0), ne(self.v('csp'), 0)), 'fbad')
                    with self.when(bad): self.fail(41)
                    with self.when(not_(bad)):
                        lo = self.newlab(); self.emit(OP['JMP'], label=lo); self.set('mode', R.S_FNAME); self.push_cs(R.C_FUNCB, lo); self.done()
                with self.when(not_(or_(*[KWc(k) for k in kws]))):
                    self.set('pn1', th1); self.set('pn2', th2); self.set('mode', R.S_NAMES); self.done()
        # ---- S_PREINC
        with block(R.S_PREINC):
            with self.when(not_(isID)): self.fail(10)
            with self.when(isID): self.incdec(th1, th2, self.v('pn1'), self.v('pn2'))
        # ---- S_VAR
        with block(R.S_VAR):
            with self.when(not_(isID)): self.fail(9)
            with self.when(isID):
                curf = self.m(self.v('curf'), 'curf')
                cst, blk = self.m(eq(self.v('pn1'), 2), 'dcst'), self.decl_blk()
                # cc_ref.redecl: a let / const of a name its scope declares already (error 78)
                nl_, e_ = self.m(self.v('nlet'), 'rnl'), self.top()[5]
                lo = self.m(ite(ne(curf, 0), self.v('fsym'), 0), 'rlo'); ns_ = self.m(self.v('nsym'), 'rns')
                inb = lambda j: and_(ge(j, sub(NS, nl_)), lt(j, sub(NS, e_)))
                inf = lambda j: and_(ge(j, lo), lt(j, ns_))
                rd = self.m(and_(ne(self.v('pn1'), 0), or_(*[and_(eq(I(f'sh1_{j}'), th1), eq(I(f'sh2_{j}'), th2), ite(blk, inb(j), inf(j))) for j in range(NS)])), 'redecl')
                with self.when(rd): self.fail(78)
                with self.when(and_(ne(curf, 0), not_(rd))):
                    nl = self.m(self.v('nloc') + 1, 'nl'); self.set('nloc', nl); self.declare(th1, th2, 2, add(self.v('npar'), nl), cst, blk)
                full = self.m(ge(self.v('dp'), self.db + R.SDATA), 'gfull')
                with self.when(and_(eq(curf, 0), full, not_(rd))): self.fail(25)
                with self.when(and_(eq(curf, 0), not_(full), not_(rd))):
                    self.declare(th1, th2, 1, self.v('dp'), cst, blk); self.set('dp', self.v('dp') + 1)
                with self.when(and_(or_(ne(curf, 0), not_(full)), not_(rd))): self.set('mode', R.S_VARAFTER); self.done()
        # ---- S_VARAFTER
        with block(R.S_VARAFTER):
            pn1 = self.m(self.v('pn1'), 'dk')
            jv = self.m(ite(self.decl_blk(), sub(NS, self.v('nlet')), self.v('nsym') - 1), 'vj')
            with self.when(P(61)):
                self.push_cs(R.C_ASSIGN, jv, 0, add(pn1, 1)); self.set('mode', R.S_OPND); self.done()
            with self.when(and_(not_(P(61)), eq(pn1, 2))): self.fail(65)
            with self.when(and_(not_(P(61)), ne(pn1, 2))):
                with self.when(ne(self.v('curf'), 0)):                 # a local without a value: 0
                    _, ov, _, _ = self.symkind_addr(jv); self.emit(OP['MOV'], (ov, 0), (R.K(0), 0))
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
            with self.when(not_(isID)): self.fail(34)
            with self.when(isID):
                fi, l, _ = self.fnfind(th1, th2); self.set('cfn', fi); self.deflab(l, self.here()); self.set('nfdef', self.v('nfdef') + 1)
                self.set('curf', 1); self.set('nloc', 0); self.set('npar', 0); self.set('fsym', self.v('nsym'))
                le = self.newlab()
                self.set_topA(lambda A: add(sub(A, mod(A, 64)), le))      # top entry's b field := le (the frame label)
                self.set('mode', R.S_FPAREN); self.done()
        with block(R.S_FPAREN):
            with self.when(not_(P(40))): self.fail(35)
            with self.when(P(40)): self.set('mode', R.S_FPARAM); self.done()
        with block(R.S_FPARAM):
            with self.when(P(41)): self.end_params()
            with self.when(and_(not_(P(41)), not_(isID))): self.fail(36)
            with self.when(and_(not_(P(41)), isID)):
                self.declare(th1, th2, 2, add(self.v('npar'), R.PARAM0)); self.set('npar', self.v('npar') + 1); self.set('mode', R.S_FPSEP); self.done()
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
            _, cfv = self.top_op()
            with self.when(and_(P(41), eq(cfv, 2))): self.fail(30)          # console.log(a, ) (cc_ref)
            with self.when(and_(P(41), ne(cfv, 2))):
                self.set('osp', self.v('osp') - 1); self.emit(OP['PUTC'], b=(R.K(10), 0)); self.print_end()
            with self.when(not_(P(41))):
                self.set_top_op(R.M_PRINT, 0); self.set('mode', R.S_OPND)
        # ---- objects (cc_ref)
        with block(R.S_DOT):
            with self.when(not_(isID)): self.fail(69)
            isl = self.m(and_(isID, eq(th1, KW['length'][0]), eq(th2, KW['length'][1])), 'islen')
            mi = self.m(add(*[mul(and_(eq(th1, KW[m[0]][0]), eq(th2, KW[m[0]][1])), i + 1) for i, m in enumerate(R.METHODS)]), 'mi')
            direct = self.m(and_(isID, not_(isl), ne(mi, 0), ge(tv, 262144)), 'mdir')     # x.name( for a method's name
            with self.when(and_(or_(isl, direct), lt(mod(tv, 2048), 1024))): self.datum(add(mod(tv, 2048), self.db - 1), mod(fdiv(tv, 2048), 128))    # (its length word)
            with self.when(isl):                               # a string's or an array's length: the word before its value's address
                i = self.m(self.v('nd') - 1, 'lni'); o = self.src(i)
                self.emit(OP['LDI'], self.tmp(i), o, (R.K(-1), 0)); self.set_od(i, TMP, 3); self.set('mode', R.S_OPER); self.done()
            with self.when(direct): self.set('pn1', 0); self.set('pn2', 0); self.set('pm', add(mi, 3)); self.set('mode', R.S_OPER); self.done()
            with self.when(and_(isID, not_(isl), not_(direct))):
                ks, ok = self.key_name(tv, th1, th2)
                with self.when(ok):
                    self.set('pn1', ks); self.set('pn2', 0); self.set('pm', ite(eq(mi, 0), 1, add(mi, 3))); self.set('mode', R.S_OPER); self.done()
        with block(R.S_OKEY):
            with self.when(P(125)): self.set('osp', self.v('osp') - 1); self.set('mode', R.S_OPER); self.done()     # {} or a trailing comma
            nk = self.m(not_(P(125)), 'onk')
            with self.when(and_(nk, not_(or_(isID, isSTR, isNUM)))): self.fail(71)
            if self.spec_tk in (None, 2):
                with self.when(and_(nk, isID)): ksI, okI = self.key_name(tv, th1, th2)
            else: ksI, okI = K(0), K(0)
            if self.spec_tk in (None, 3):
                tsa = self.m(mod(tv, 2048), 'otsa'); bigS = self.m(and_(nk, isSTR, ge(tsa, 1024)), 'obig')
                with self.when(bigS): self.fail(26)
                with self.when(and_(nk, isSTR, not_(bigS))): eS, okS = self.intern(th1, th2, add(tsa, self.db), fdiv(tv, 2048))
                ksS = self.m(eS, 'oks'); okS = self.m(and_(not_(bigS), okS), 'okS')
            else: ksS, okS = K(0), K(0)
            with self.when(and_(nk, isNUM)):                  # a number key: as o[n] = v
                v20 = self.m(sub(mod(add(tv, 1 << 19), 1 << 20), 1 << 19), 'kn20'); small = self.m(and_(ge(v20, -128), lt(v20, 128)), 'knsm')
                self.push_od(ite(small, add(v20, 896), KBIG), 3, v20)
            okk = self.m(or_(and_(isID, okI), and_(isSTR, okS), and_(isNUM, eq(self.v('err'), 0))), 'okk')
            with self.when(and_(nk, okk)):
                self.push_op(R.M_OKEY, mul(not_(isNUM), sub(add(mul(isID, ksI), mul(isSTR, ksS)), self.db))); self.set('mode', R.S_OCOLON); self.done()
        with block(R.S_OCOLON):
            with self.when(P(58)): self.set('mode', ite(eq(self.top()[0], R.C_SWITCH), R.S_STMT, R.S_OPND)); self.done()     # (default's ':')
            with self.when(not_(P(58))): self.fail(72)
        # ---- S_OPND
        with block(R.S_OPND):
            with self.when(isNUM):
                v20 = self.m(sub(mod(add(tv, 1 << 19), 1 << 20), 1 << 19), 'n20')
                small = self.m(and_(ge(v20, -128), lt(v20, 128)), 'nsm')
                self.push_od(ite(small, add(v20, 896), KBIG), 3, v20); self.set('mode', R.S_OPER); self.done()
            with self.when(isSTR):                          # interned (cc_ref)
                tsa = self.m(mod(tv, 2048), 'tsa')
                with self.when(ge(tsa, 1024)): self.fail(26)
                with self.when(lt(tsa, 1024)):
                    e, ok = self.intern(th1, th2, add(tsa, self.db), fdiv(tv, 2048))
                    with self.when(ok): self.push_od(KBIG, 2, sub(e, R.STRTAG)); self.set('mode', R.S_OPER); self.done()
            tf = self.m(or_(KWc('true'), KWc('false'), KWc('null')), 'tf')
            with self.when(tf): self.push_od(add(896, KWc('true')), not_(KWc('null'))); self.set('mode', R.S_OPER); self.done()
            with self.when(P(123)):                            # an object literal: NEW, then each pair as o.key = v
                i = self.m(self.v('nd'), 'obi'); self.push_od(TMP, 0)
                with self.when(eq(self.v('err'), 0)): self.emit(OP['NEW'], self.tmp(i)); self.push_op(R.M_OBJ); self.set('mode', R.S_OKEY); self.done()
            with self.when(P(91)): self.push_od(TMP, 0); self.push_op(R.M_ARR, 0); self.done()     # an array literal: its slot, the elements
            with self.when(P(40)): self.push_op(R.M_PAREN); self.done()
            with self.when(P(33)): self.push_op(R.NOT); self.done()
            with self.when(P(45)): self.push_op(R.NEG); self.done()
            with self.when(or_(P(7), P(8))): self.set('pn1', tv); self.set('pn2', 1); self.set('mode', R.S_PREINC); self.done()
            with self.when(and_(isID, not_(tf))): self.set('pn1', th1); self.set('pn2', th2); self.set('mode', R.S_NAMEE); self.done()
            rest = self.m(and_(live(), eq(mode(), R.S_OPND)), 'orest')
            with self.when(rest):
                tc, tvv = self.top_op()
                t = self.top()
                cA = self.m(and_(P(41), gt(self.v('osp'), 0), anyeq(tc, (R.M_CALL, R.M_METH))), 'oA')
                cR = self.m(and_(P(93), gt(self.v('osp'), 0), eq(tc, R.M_ARR)), 'oR')
                cB = self.m(and_(not_(cA), or_(P(59), PNL, PRB), eq(t[0], R.C_RETURN), eq(self.v('osp'), 0)), 'oB')
                cC = self.m(and_(not_(cA), not_(cB), P(59), eq(t[0], R.C_FORCOND), eq(self.v('osp'), 0)), 'oC')
                cN = self.m(and_(not_(cB), PNL), 'oN')
                with self.when(cN): self.done()
                with self.when(cA):
                    self.set('osp', self.v('osp') - 1); self.set('mode', R.S_OPER)
                    with self.when(eq(tc, R.M_CALL)): self.call_end(tvv, 0)
                    with self.when(eq(tc, R.M_METH)): self.meth_end(tvv, 0)
                with self.when(cR):                            # [] or a trailing comma
                    self.set('osp', self.v('osp') - 1)
                    with self.when(lt(tvv, 8)): self.arr_make(tvv)
                    self.set('mode', R.S_OPER); self.done()
                with self.when(cB):
                    self.push_od(R.K(0), 0); self.set('f_expr', 1)
                    with self.when(PRB): self.set('f_asic', 1)
                with self.when(cC): self.push_od(R.K(1), 1); self.set('f_expr', 1)
                with self.when(and_(not_(cA), not_(cB), not_(cC), not_(cN), not_(cR))): self.fail(3)
        # ---- S_OPER
        with block(R.S_OPER):
            # pm is set only on the way out of S_OPER (S_DOT, x[k]'s ']'): a variant starting in another mode knows it is 0
            pmr = self.m(self.v('pm'), 'pmr') if self.spec_mode in (None, R.S_OPER) else K(0)
            pinc = self.m(eq(pmr, 3), 'pinc')                  # after x++ / ++x (cc_ref): no '.' or '[' may follow
            pbad = self.m(and_(pinc, or_(P(46), P(91))), 'pbad')
            with self.when(pinc): self.set('pm', 0)
            with self.when(pbad): self.fail(48)
            pm4 = self.m(ge(pmr, 4), 'pm4')                     # x.name for a method's name: a call, or else the property
            mcall = self.m(and_(pm4, P(40)), 'mcall')
            with self.when(mcall):                             # the receiver: an argument above its slot
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
                            self.emit(ite(P(7), OP['ADD'], OP['SUB']), t, t, (R.K(1), 0)); self.write_elem(dyn, key, t)
                            self.pop_cs(); self.set('mode', R.S_INC); self.done()
                        with self.when(and_(go, not_(p78))):
                            t = self.top(); off = self.m(mul(not_(dyn), sub(key, self.db)), 'koff')
                            self.set_top(add(R.C_PSET * 4096, mul(dyn, 64), compound), add(mul(t[5], 4096), mul(fdiv(off, 64), 64), mod(off, 64)))
                            self.set('mode', R.S_OPND); self.done()
                with self.when(not_(asgm)): self.read_elem(dyn, key, 0)
            binop = self.m(add(*[mul(P(ch), op) for ch, op in R.BIN.items()]), 'binop')
            nomark, tk0, dok, dop = self.cond_dest()
            csp_ = self.m(self.v('csp'), 'cspa')            # the entry below the top: a for header takes no semicolon insertion
            k2 = self.m(add(*[mul(eq(csp_, k + 2), fdiv(self.v(f'csA{k}'), 4096)) for k in range(CD - 1)]), 'k2nd')
            asiok = self.m(and_(nomark, anyeq(tk0, (R.C_ASSIGN, R.C_EXPR, R.C_RETURN, R.C_PSET)), not_(anyeq(k2, (R.C_FORINIT, R.C_FORSTEP)))), 'asiok')
            semi = self.m(or_(P(59), and_(or_(PNL, PRB), asiok)), 'semi')
            okb = self.m(and_(PRB, eq(self.marker(), R.M_OKEY)), 'okb')       # '}' ending an object literal's value
            with self.when(and_(live(), PNL, not_(asiok))): self.done()
            closer = self.m(and_(live(), or_(ne(binop, 0), P(41), P(44), P(58), P(63), P(93), okb, semi)), 'closer')
            br = self.m(or_(P(63), and_(P(41), nomark, anyeq(tk0, (R.C_IFC, R.C_WHILEC, R.C_DOB, R.C_DOB1))),
                            and_(or_(P(59), PNL), nomark, eq(tk0, R.C_FORCOND))), 'pbr')
            dv = self.m(and_(not_(br), or_(P(41), P(44), semi), dok), 'pdv')
            with self.when(closer):
                self.popops(self.m(ite(ne(binop, 0), self.prec(binop), add(1, P(63))), 'minp'), br, dv, dop)
            tc, tvv = self.top_op()
            osp0 = self.m(self.v('osp'), 'osp0')
            tc = self.m(mul(tc, gt(osp0, 0)), 'tt')
            with self.when(and_(live(), P(46))): self.set('mode', R.S_DOT); self.done()                        # o.x
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
                plus = self.m(and_(not_(piece), eq(binop, R.ADD)), 'plus')
                with self.when(plus): self.push_op(ite(inpr, R.M_CADD, R.ADD), ty)
                rest = self.m(and_(not_(piece), not_(plus)), 'brest')
                with self.when(and_(rest, not_(gt(self.prec(binop), 6)))): self.join_pieces()     # (* / % bind tighter: they end no piece)
                nd2 = self.m(self.v('nd'), 'bnd2'); ty2 = self.otype(nd2 - 1)
                logic = self.m(and_(rest, or_(eq(binop, R.AND), eq(binop, R.OR))), 'logic')
                with self.when(logic):                         # a: tested in its temp; b joins it there (popops)
                    l = self.newlab(); i = self.m(nd2 - 1, 'li'); self.to_temp(i); self.snapshot(lambda d: K(1), i)
                    self.emit(ite(eq(binop, R.AND), OP['JZ'], OP['JNZ']), b=self.tmp(i), label=l)
                    self.push_op(binop, add(l, mul(ty2, 64)))
                with self.when(and_(rest, not_(logic))): self.push_op(binop, ty2)     # (the left operand's type)
                self.set('mode', R.S_OPND); self.done()
            with self.when(and_(live(), P(63))):               # c ? ... (cc_ref)
                self.join_pieces(); self.snapshot(lambda d: K(1), self.v('nd') - 1)
                l = self.newlab(); self.branch(l, 0); self.push_op(R.M_TERN, add(l, mul(eq(tc, R.M_TELSE), 64)))
                self.set('mode', R.S_OPND); self.done()
            with self.when(and_(live(), P(58))):               # c ? a : ...; a case value's end
                cse = self.m(and_(ne(tc, R.M_TERN), eq(osp0, 0), eq(self.top()[0], R.C_CASE)), 'cse')
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
                vasg = self.m(and_(eq(osp0, 0), eq(self.top()[0], R.C_ASSIGN), ne(self.top()[3], 0)), 'vasg')
                with self.when(eq(tc, R.M_PRINT)): self.print_call(32); self.set_top_op(R.M_PRINT, 2); self.set('mode', R.S_CONFIRST); self.done()
                with self.when(eq(tc, R.M_OKEY)): self.okey_end(tvv, 0)
                with self.when(eq(tc, R.M_ARR)):              # cc_ref.arr_elem
                    with self.when(ge(tvv, 8)): self.arr_store(tvv)
                    with self.when(lt(tvv, 8)):
                        self.arg_end()
                        with self.when(eq(tvv, 7)): self.arr_make(8)
                    self.set_top_op(R.M_ARR, tvv + 1); self.set('mode', R.S_OPND); self.done()
                with self.when(anyeq(tc, (R.M_CALL, R.M_METH))): self.arg_end(); self.set_top_op(tc, tvv + 64)       # count the arguments
                with self.when(anyeq(tc, (R.M_CALL, R.M_METH, R.M_PUTC))): self.set('mode', R.S_OPND); self.done()
                known = anyeq(tc, (R.M_PRINT, R.M_OKEY, R.M_ARR, R.M_CALL, R.M_METH, R.M_PUTC))
                with self.when(and_(not_(known), vasg)): self.set('f_expr', 1)
                with self.when(not_(or_(known, vasg))): self.fail(44)
            with self.when(and_(live(), P(41))):
                with self.when(eq(tc, R.M_PAREN)): self.set('osp', osp0 - 1); self.done()
                with self.when(eq(tc, R.M_CALL)): self.set('osp', osp0 - 1); self.call_end(tvv, 1)
                with self.when(eq(tc, R.M_METH)): self.set('osp', osp0 - 1); self.meth_end(tvv, 1)
                with self.when(eq(tc, R.M_PUTC)):
                    self.set('osp', osp0 - 1); o = self.src(self.v('nd') - 1); self.emit(OP['PUTC'], b=o)
                    self.set('nd', self.v('nd') - 1); self.push_od(R.K(0), 0); self.done()
                with self.when(eq(tc, R.M_PRINT)): self.print_call(10); self.set('osp', osp0 - 1); self.print_end()
                other = self.m(not_(anyeq(tc, (R.M_PAREN, R.M_CALL, R.M_METH, R.M_PUTC, R.M_PRINT))), 'o41')
                with self.when(and_(other, gt(osp0, 0))): self.fail(46)
                with self.when(and_(other, eq(osp0, 0))): self.set('f_expr', 1)
            with self.when(and_(live(), eq(binop, 0), semi)):
                with self.when(gt(osp0, 0)): self.fail(47)
                with self.when(eq(osp0, 0)):
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
            _, o, _, _ = self.symkind_addr(t[1]); nd = self.m(self.v('nd'), 'and'); i = self.m(nd - 1, 'ai')
            cmp_ = self.m(ne(t[2], 0), 'acmp')
            with self.when(cmp_):                              # (a snapshot replaced x below e if e changed it)
                self.set_symbool(t[1], self.compound(t[2], i - 1, (o, 0), False)); self.set('nd', i - 1)
            with self.when(not_(cmp_)): self.put((o, 0), i); self.set_symbool(t[1], self.otype(i)); self.set('nd', i)
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
            self.pop_cs(); self.to_temp(K(0)); ty = self.otype(K(0)); self.set('nd', 0)
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
            o = self.src(i); self.emit(OP['RET'], b=o); self.set('nd', i); self.set('f_compl', 1); self.done()
        with self.when(not_(or_(c1, c2, c3, c4, c6, c7, c8, c9, c10))): self.fail(50)

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
                with self.when(isloop): self.emit(OP['JMP'], label=t[1])
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
            isfn, islp, issw = self.m(eq(k, R.C_FUNCB), 'cfn'), self.m(eq(k, R.C_LOOPB), 'clp'), self.m(eq(k, R.C_SWITCH), 'csw')
            hasd = self.m(and_(issw, mod(fdiv(t[4], 2), 2)), 'cswd')    # a switch: the last test failed: to default if there is one
            with self.when(hasd): self.emit(OP['JMP'], label=t[2])
            with self.when(issw): self.deflab(t[1], self.here())
            with self.when(hasd): self.emit(OP['JMP'], label=t[3])
            # the code (one instruction slot for both): loop JMP top; function RET #0 (and its frame label := its count of locals)
            with self.when(or_(islp, isfn)): self.emit(ite(islp, OP['JMP'], OP['RET']), b=(ite(islp, 512, 896), 0), label=ite(islp, t[1], -1))
            with self.when(isfn): self.deflab(t[2], self.v('nloc'))
            # the end label of whichever body closed (one kind per call, so one label port serves them all)
            with self.when(anyeq(k, (R.C_ELSEB, R.C_DOB, R.C_LOOPB, R.C_FUNCB, R.C_SWITCH))):
                self.deflab(ite(or_(islp, issw), t[2], t[1]), self.here())
            with self.when(anyeq(k, (R.C_ELSEB, R.C_LOOPB, R.C_SWITCH))): self.set(flag, 1); self.done()
            with self.when(eq(k, R.C_DOB)): self.set('csp', self.v('csp') + 1); self.set('mode', R.S_DOWHILE); self.done()
            with self.when(isfn):
                self.set('curf', 0); self.set('nsym', self.v('fsym')); self.set('mode', R.S_STMT); self.done()
            with self.when(not_(anyeq(k, (R.C_BLOCK, R.C_IFB, R.C_ELSEB, R.C_DOB, R.C_LOOPB, R.C_FUNCB, R.C_SWITCH)))): self.fail(55)

    def end_params(self):
        cfn, npar = self.v('cfn'), self.v('npar'); fl = self.fn_sel(cfn, 'fl_'); exp = self.m(fdiv(fl, 256), 'pexp')
        bad = self.m(and_(ne(exp, 0), ne(exp, add(npar, 1))), 'pbad')     # cc_ref.end_params: the calls so far must agree
        with self.when(bad): self.fail(76)
        with self.when(not_(bad)):
            self.fnw.append((self.x.g, cfn, self.fn_sel(cfn, 'fh1_'), self.fn_sel(cfn, 'fh2_'), add(mod(fl, 256), mul(add(npar, 1), 256))))
            self.set('mode', R.S_LBRACE); self.done()

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
                (f'o_w{s}', add(*[mul(sel, add(mul(op, 8192), a)) for sel, (g, ip, op, a, la, w, m, fl) in zip(sels, code)])),
                (f'o_l{s}', sub(add(*[mul(sel, add(la, 1)) for sel, (g, ip, op, a, la, w, m, fl) in zip(sels, code)]), 1)),
                (f'o_x{s}', add(*[mul(sel, w) for sel, (g, ip, op, a, la, w, m, fl) in zip(sels, code)])),
                (f'o_m{s}', add(*[mul(sel, m) for sel, (g, ip, op, a, la, w, m, fl) in zip(sels, code)])),
                (f'o_f{s}', add(*[mul(sel, fl) for sel, (g, ip, op, a, la, w, m, fl) in zip(sels, code)])),
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
            self.set('kpos', add(mul(and_(eq(tk, 4), eq(tv, 46), not_(self.v('lcon'))), 2), and_(eq(tk, 4), or_(eq(tv, 123), eq(tv, 44)))))
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
