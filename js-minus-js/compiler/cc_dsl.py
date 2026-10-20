"""cc_dsl.py — the CSS compiler's per-character step, written once in the DSL (dsl.py).

Mirrors cc_ref.Compiler exactly (same state, same limits, same code), but as predicated straight-line code so
it can become one nested element's CSS. Prog is the parser step (one token), LexProg the lexer step (one
character). Outputs: code-word candidates, label definitions, the data word, table write ports.

Table encodings: sk_j = (type + 4 * const) * 65536 + kind * 16384 + addr + 8192 (a parameter i is addr PARAM0 + i, resolved
against npar when read); fl_k = label + 64 * type + 256 * (argument count + 1, or 0 while unknown) (type: 0 number/unknown,
1 boolean, 2 string); iv_k = an interned string's
address + 4096 if it has no tag word (cc_ref.intern). Symbols 0..nsym-1 are
function / program level, NS-nlet..NS-1 block-scoped let / const. Control-stack entry k: csA = kind * 4096 + a * 64 + b,
csB = e * 4096 + c * 64 + d (e: nlet when pushed, restored when a body closes). Operator-stack entry: code * 8192 + value.
"""
from dsl import *
import cc_ref as R

OD, CD, NS, NF, NL, NI = R.OD, R.CD, R.NS, R.NF, R.NL, R.NI
H1M, H2M = R.H1M, R.H2M
KW = R.KW

LEX_STATE = ['lx', 'q', 'lt', 'tkc', 'acc', 'h1', 'h2', 'p2', 'sstart', 'sdp', 'pp', 'inul', 'icm', 'kpos', 'lcon', 'pnl']

def parse_state_names():
    s = ['dp', 'mode', 'pn1', 'pn2', 'osp', 'csp', 'nsym', 'nlet', 'nfn', 'nlab', 'cp', 'curf', 'cfn', 'nfdef', 'nloc', 'npar', 'fsym', 'pendLa',
         'err', 'lb', 'nint', 'pm']
    s += [f'op{k}' for k in range(OD)]
    s += [f'csA{k}' for k in range(CD)] + [f'csB{k}' for k in range(CD)]
    return s

def table_names():
    """symbol and function tables: not parser state. Read as inputs; a step writes at most one entry of each
    (write ports o_y* / o_f*), applied by the next level. Labels are not state at all: definitions are outputs."""
    return ([x for j in range(NS) for x in (f'sh1_{j}', f'sh2_{j}', f'sk_{j}')] + [x for k in range(NF) for x in (f'fh1_{k}', f'fh2_{k}', f'fl_{k}')]
            + [x for k in range(NI) for x in (f'ih1_{k}', f'ih2_{k}', f'iv_{k}')])

def initial_lex(data_base):
    st = {n: 0 for n in LEX_STATE}; st['sdp'] = data_base + R.SDATA + 1        # (cc_ref: past the DONE marker)
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

class Base:
    def named(self, n, node):
        self.x.temps.append((n, lift(node))); self.out.append(n)

class Prog(Base):
    """per token (runs on the level after the character that completed it): parser step. inputs tk tv th1 th2"""
    def __init__(self, data_base, code_base, lib, mode=None, tk=None, tv=None):
        """mode / tk: specialise for a known starting mode and token kind (and err == 0) -- the page selects the
        variant with a container query, so each level evaluates only the code reachable from that mode"""
        self.db, self.cb = data_base, code_base
        self.ent = lib['entries']                    # ROM routines: mkarr, the methods (cc_ref)
        self.spec_mode, self.spec_tk, self.spec_tv = mode, tk, tv
        X = self.x = Ctx(parse_state_names(), ['tk', 'tv', 'th1', 'th2'])
        X.cur.update(live=K(1), f_expr=K(0), f_simple=K(0), f_compl=K(0), f_asic=K(0), f_compl2=K(0), scA=K(0), scAl=K(0), scO=K(0), scOl=K(0))
        if mode is not None: X.cur['mode'] = K(mode); X.cur['err'] = K(0)
        self.code = []      # (valid, addr, op, imm, islab)  addr relative to code base
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
    def popops(self, minprec):
        """pop operators with precedence >= minprec. && / || and a ternary's M_TELSE define their jump label
        instead of emitting; at most one of each is popped (the stack's precedences increase upwards between
        markers, and cc_ref's M_TELSE chain rule keeps one M_TELSE per segment), and all are defined at the
        address after the pops, so they are collected and defined afterwards."""
        go = K(1); osp_in = self.m(self.v('osp'), 'ospi')
        for _ in range(OD):
            code, val = self.top_op()
            p = self.prec(code)
            go = self.m(and_(go, gt(self.v('osp'), 0), gt(p, 0), ge(p, minprec)), 'pop')
            with self.when(go):
                self.set('osp', self.v('osp') - 1)
                with self.when(eq(code, R.AND)): self.set('scA', 1); self.set('scAl', mod(val, 64))
                with self.when(eq(code, R.OR)): self.set('scO', 1); self.set('scOl', mod(val, 64))
                with self.when(or_(eq(code, R.AND), eq(code, R.OR))): self.set('lb', self.tmerge(fdiv(val, 64), self.v('lb')))   # cc_ref
                lb = self.m(self.v('lb'), 'plb')
                # one word for an operator (cc_ref: emit_dyn for + and the comparisons, else the opcode); M_CADD after the loop
                isd = self.m(anyeq(code, R.DYNOPS), 'pisd')
                dop, dimm, db = self.dyn_word(code, val, lb)
                with self.when(not_(anyeq(code, (R.AND, R.OR, R.M_CADD, R.M_TELSE)))):
                    self.emit(ite(isd, dop, code), mul(isd, dimm), b=ite(isd, db, ite(eq(code, R.NOT), 1, 3)))
        with self.when(self.v('scA')): self.deflab(self.v('scAl'), self.here())
        with self.when(self.v('scO')): self.deflab(self.v('scOl'), self.here())
        # an M_TELSE or M_CADD is the bottom of its segment, so if one was popped it was the last: the entry at the new osp
        osp = self.m(self.v('osp'), 'ospo')
        w = self.m(add(*[mul(eq(osp, k), self.v(f'op{k}')) for k in range(OD)]), 'lastw')
        popped = self.m(lt(osp, osp_in), 'ppd')
        with self.when(and_(popped, eq(fdiv(w, 8192), R.M_TELSE))):
            val = self.m(mod(w, 8192), 'tev')
            self.deflab(mod(val, 64), self.here()); self.set('lb', self.tmerge(fdiv(val, 64), self.v('lb')))
        with self.when(and_(popped, eq(fdiv(w, 8192), R.M_CADD))):        # cc_ref: numbers ADD; a string (not after a boolean) two pieces; else DYN
            val = self.m(mod(w, 8192), 'cav'); lb = self.m(self.v('lb'), 'calb')
            nm = lambda t: or_(eq(t, 1), eq(t, 3))
            num = self.m(and_(nm(val), nm(lb)), 'cnum')
            pcs = self.m(and_(not_(num), or_(eq(val, 2), eq(lb, 2)), ne(val, 1)), 'cpcs')
            dop, dimm, db = self.dyn_word(R.ADD, val, lb)
            with self.when(not_(pcs)): self.emit(dop, dimm, b=db)
            with self.when(and_(pcs, eq(lb, 1))): self.emit(R.CALL, self.ent['b2s'], b=2)
            with self.when(pcs): _, pv = self.top_op(); self.set_top_op(R.M_PRINT, add(pv, 4))
    def dyn_word(self, code, lt, rt):
        """cc_ref.emit_dyn's word: (opcode, immediate, static type): the plain instruction for known numbers, else DYN"""
        code, lt, rt = lift(code), lift(lt), lift(rt)
        num = lambda t: or_(eq(t, 1), eq(t, 3))
        isadd = self.m(eq(code, R.ADD), 'dadd')
        plain = self.m(ite(isadd, and_(num(lt), num(rt)), or_(num(lt), num(rt))), 'dpl')
        imm = add(code, mul(eq(lt, 1), 64), mul(eq(rt, 1), 128))
        return (self.m(ite(plain, code, R.DYN), 'dop'), self.m(mul(not_(plain), imm), 'dimm'),
                self.m(ite(isadd, ite(plain, 3, mul(or_(eq(lt, 2), eq(rt, 2)), 2)), 1), 'dtb'))
    def emit_dyn(self, code, lt, rt):
        """cc_ref.emit_dyn: the plain instruction for known numbers, else DYN (boolean operands flagged in its immediate)"""
        op, imm, b = self.dyn_word(code, lt, rt); self.emit(op, imm, b=b)
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
        """kind, address, static type, const flag of symbol j"""
        sk = self.sym_sel(j, 'sk_', 'sk')
        b = self.m(mod(fdiv(sk, 65536), 4), 'skb'); r = self.m(mod(sk, 65536), 'skr'); cst = self.m(fdiv(sk, 262144), 'skc')
        k, a = self.m(fdiv(r, 16384), 'skk'), self.m(sub(mod(r, 16384), 8192), 'ska')
        # parameter i is stored as kind 2, addr PARAM0 + i; its frame slot is -1 - npar + i (npar of the current function)
        ispar = self.m(and_(eq(k, 2), ge(a, R.PARAM0)), 'spar')
        return k, self.m(ite(ispar, sub(add(a, -1 - R.PARAM0), self.v('npar')), a), 'ska2'), b, cst
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
    def key_name(self, tv, th1, th2):
        """cc_ref.key_name: a property name -> (key, ok); tv: strtok()"""
        ta = self.m(mod(tv, 2048), 'kta'); big = self.m(ge(ta, 1024), 'kbig')
        with self.when(big): self.fail(26)
        with self.when(not_(big)): e, ok = self.intern(th1, th2, add(ta, self.db), mod(fdiv(tv, 2048), 128))
        return self.m(e, 'kname'), self.m(and_(not_(big), ok), 'kok')
    def stmt_level(self):
        return self.m(and_(eq(self.v('osp'), 0), eq(self.top()[0], R.C_EXPR)), 'stl')
    def load(self, k, a, b=0):
        self.emit(ite(eq(k, 2), R.LOADL, R.LOADG), mod(a, 8192), b=b)
    def store(self, k, a):
        self.emit(ite(eq(k, 2), R.STOREL, R.STOREG), mod(a, 8192))
    def print_call(self, sep, pv):
        """cc_ref.print_call: one PRINT word (the B form for a boolean), or a + chain's pieces (pv: M_PRINT's value) by pnK"""
        c = self.m(fdiv(pv, 4), 'pcc'); lbp = self.m(self.v('lb'), 'lbp')
        with self.when(eq(c, 0)): self.emit(add(R.PRINT_OP[sep], eq(lbp, 1)), 0, b=0)
        with self.when(ne(c, 0)):
            with self.when(eq(lbp, 1)): self.emit(R.CALL, self.ent['b2s'], b=2)
            self.emit(R.PUSHI, sep); self.emit(R.CALL, add(*[mul(eq(c, k - 1), self.ent[f'pn{k}']) for k in range(2, R.PIECES + 1)])); self.emit(R.POP, b=0)
    def catn(self, c):
        """the ROM's catnK for c + 1 pieces (c >= 1)"""
        self.emit(R.CALL, add(*[mul(eq(c, k - 1), self.ent[f'catn{k}']) for k in range(2, R.PIECES + 1)]), b=2)

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
            with self.when(and_(P(91), lt(j, 0))): self.fail(7)    # NAME[e] = e: an expression statement (cc_ref)
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
                with self.when(and_(not_(isputc), ne(gi, 0))): self.emit(R.PUSHI, 0); self.push_op(R.M_METH, sub(gi, 1))   # parseInt(s), ...
                with self.when(and_(not_(isputc), eq(gi, 0))):
                    fi, _, fb = self.fnfind(pn1, pn2); self.push_op(R.M_CALL, add(fi, mul(fb, 16)))
                self.set('mode', R.S_OPND); self.done()
            p78n = self.m(or_(P(7), P(8)), 'p78n')
            with self.when(and_(not_(iscon), not_(P(40)))):
                j = self.lookup(pn1, pn2)
                k, a, b, cst = self.symkind_addr(j)
                with self.when(p78n): self.incdec(pn1, pn2, tv, 2, (j, k, a, b, cst))     # x++ in an expression
                sdot = self.m(and_(not_(p78n), lt(j, 0), eq(pn1, KW['String'][0]), eq(pn2, KW['String'][1]), P(46)), 'sdot')
                with self.when(sdot): self.emit(R.PUSHI, 0); self.set('mode', R.S_DOT); self.done()     # String.fromCharCode
                with self.when(and_(not_(p78n), lt(j, 0), not_(sdot))): self.fail(4)
                with self.when(and_(not_(p78n), ge(j, 0))): self.load(k, a, b); self.set('mode', R.S_OPER)
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
                kws = ['var', 'let', 'const', 'if', 'while', 'do', 'for', 'return', 'function', 'break', 'continue', 'switch', 'case', 'default']
                with self.when(or_(KWc('var'), KWc('let'), KWc('const'))):
                    self.set('pn1', add(KWc('let'), mul(KWc('const'), 2))); self.set('pn2', 0); self.set('mode', R.S_VAR); self.done()
                with self.when(KWc('if')): self.push_cs(R.C_IFC); self.set('mode', R.S_LPAREN); self.done()
                with self.when(KWc('switch')): self.push_cs(R.C_SWITCHC); self.set('mode', R.S_LPAREN); self.done()
                with self.when(or_(KWc('case'), KWc('default'))):         # cc_ref; one label, one JMP, one label port for both
                    t = self.top(); seen = self.m(mod(t[4], 2), 'swseen'); insw = self.m(eq(t[0], R.C_SWITCH), 'insw')
                    isc = KWc('case'); dup = self.m(and_(not_(isc), ge(t[4], 2)), 'swdup')
                    with self.when(not_(insw)): self.fail(73)
                    with self.when(and_(insw, dup)): self.fail(75)
                    with self.when(and_(insw, not_(dup))):
                        with self.when(or_(seen, not_(isc))): l = self.newlab()     # case: Bk (after a body); default: its label
                        with self.when(ite(isc, seen, not_(seen))): self.emit(R.JMP, 0, ite(isc, l, t[1]))
                        self.deflab(ite(isc, t[1], l), self.here())
                        with self.when(isc): self.emit(R.DUP); self.push_cs(R.C_CASE, mul(seen, l), seen); self.set('mode', R.S_OPND)
                        with self.when(not_(isc)):
                            self.set_top(add(R.C_SWITCH * 4096, mul(t[1], 64), t[2]), add(mul(t[5], 4096), mul(l, 64), 3)); self.set('mode', R.S_OCOLON)
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
                        lo = self.newlab(); self.emit(R.JMP, 0, lo); self.set('mode', R.S_FNAME); self.push_cs(R.C_FUNCB, lo); self.done()
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
                    nl = self.m(self.v('nloc') + 1, 'nl'); self.set('nloc', nl); self.declare(th1, th2, 2, nl, cst, blk)
                full = self.m(ge(self.v('dp'), self.db + R.SDATA), 'gfull')
                with self.when(and_(eq(curf, 0), full, not_(rd))): self.fail(25)
                with self.when(and_(eq(curf, 0), not_(full), not_(rd))):
                    self.declare(th1, th2, 1, self.v('dp'), cst, blk); self.set('dp', self.v('dp') + 1)
                with self.when(and_(or_(ne(curf, 0), not_(full)), not_(rd))): self.set('mode', R.S_VARAFTER); self.done()
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
                self.set('osp', self.v('osp') - 1); self.emit(R.PUSHI, 10); self.emit(R.PUTC); self.print_end()
            with self.when(not_(P(41))):
                self.set_top_op(R.M_PRINT, 0); self.set('mode', R.S_OPND)
        # ---- objects (cc_ref)
        with block(R.S_DOT):
            with self.when(not_(isID)): self.fail(69)
            isl = self.m(and_(isID, eq(th1, KW['length'][0]), eq(th2, KW['length'][1])), 'islen')
            with self.when(isl):                               # an array's length
                self.emit(R.PUSHI, 1); self.emit(R.SUB); self.emit(R.LOADI, b=3); self.set('mode', R.S_OPER); self.done()
            mi = self.m(add(*[mul(and_(eq(th1, KW[m[0]][0]), eq(th2, KW[m[0]][1])), i + 1) for i, m in enumerate(R.METHODS)]), 'mi')
            direct = self.m(and_(isID, not_(isl), ne(mi, 0), ge(tv, 262144)), 'mdir')     # x.name( for a method's name
            with self.when(direct): self.set('pn1', 0); self.set('pn2', 0); self.set('pm', add(mi, 3)); self.set('mode', R.S_OPER); self.done()
            with self.when(and_(isID, not_(isl), not_(direct))):
                ks, ok = self.key_name(tv, th1, th2)
                with self.when(ok):
                    with self.when(eq(mi, 0)): self.emit(R.SCANI, ks)
                    self.set('pn1', ks); self.set('pn2', 0); self.set('pm', ite(eq(mi, 0), 1, add(mi, 3))); self.set('mode', R.S_OPER); self.done()
        with block(R.S_OKEY):
            _, ov = self.top_op(); ov = self.m(ov, 'okv')
            with self.when(P(125)):                            # {} or a trailing comma
                with self.when(lt(ov, 4)): self.emit(R.ENDK, mul(ov, 2))
                self.set('osp', self.v('osp') - 1); self.set('lb', 0); self.set('mode', R.S_OPER); self.done()
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
            skok = self.m(or_(and_(isID, okI), and_(isSTR, okS)), 'skok'); ksv = self.m(add(mul(isID, ksI), mul(isSTR, ksS)), 'ksv')
            setf = self.m(and_(nk, skok, lt(ov, 3)), 'osetf')
            gen = self.m(and_(nk, or_(and_(skok, ge(ov, 3)), isNUM)), 'ogen')
            with self.when(setf):                              # one of the first pairs, all string keys: stored in place
                self.emit(R.PUSHI, ksv); self.emit(R.SETF, mul(ov, 2)); self.push_op(R.M_OKEY, 0); self.set('mode', R.S_OCOLON); self.done()
            with self.when(gen):
                with self.when(lt(ov, 4)): self.emit(R.ENDK, mul(ov, 2)); self.set_top_op(R.M_OBJ, add(ov, 4))
                self.emit(R.DUP)
                with self.when(skok): self.emit(R.SCANI, ksv); self.push_op(R.M_OKEY, ksv)
                with self.when(isNUM):
                    with self.when(lt(tv, 8192)): self.emit(R.PUSHI, tv)
                    with self.when(ge(tv, 8192)):
                        self.emit(R.PUSHI, fdiv(tv, 8192)); self.emit(R.SHL13); self.emit(R.PUSHI, mod(tv, 8192)); self.emit(R.ADD)
                    self.push_op(R.M_OKEY, 1)
                self.set('mode', R.S_OCOLON); self.done()
        with block(R.S_OCOLON):
            with self.when(P(58)): self.set('mode', ite(eq(self.top()[0], R.C_SWITCH), R.S_STMT, R.S_OPND)); self.done()     # (default's ':')
            with self.when(not_(P(58))): self.fail(72)
        # ---- S_OPND
        with block(R.S_OPND):
            with self.when(isNUM):
                with self.when(lt(tv, 8192)): self.emit(R.PUSHI, tv)
                with self.when(ge(tv, 8192)):
                    self.emit(R.PUSHI, fdiv(tv, 8192)); self.emit(R.SHL13); self.emit(R.PUSHI, mod(tv, 8192)); self.emit(R.ADD)
                self.set('mode', R.S_OPER); self.done()
            with self.when(isSTR):                          # interned (cc_ref)
                tsa = self.m(mod(tv, 2048), 'tsa')
                with self.when(ge(tsa, 1024)): self.fail(26)
                with self.when(lt(tsa, 1024)):
                    e, ok = self.intern(th1, th2, add(tsa, self.db), fdiv(tv, 2048))
                    with self.when(ok): self.emit(R.PUSHS, e, b=2); self.set('mode', R.S_OPER); self.done()
            tf = self.m(or_(KWc('true'), KWc('false'), KWc('null')), 'tf')
            with self.when(and_(tf, not_(KWc('null')))): self.emit(R.PUSHI, KWc('true'), b=1); self.set('mode', R.S_OPER); self.done()
            with self.when(KWc('null')): self.emit(R.PUSHI, 0, b=0); self.set('mode', R.S_OPER); self.done()
            with self.when(P(123)): self.emit(R.NEW); self.push_op(R.M_OBJ, 0); self.set('mode', R.S_OKEY); self.done()
            with self.when(P(40)): self.push_op(R.M_PAREN); self.done()
            with self.when(P(33)): self.push_op(R.NOT); self.done()
            with self.when(P(45)): self.push_op(R.NEG); self.done()
            with self.when(or_(P(7), P(8))): self.set('pn1', tv); self.set('pn2', 1); self.set('mode', R.S_PREINC); self.done()
            with self.when(P(91)): self.push_op(R.M_ARR, 0); self.done()        # an array literal: its elements, then mkarr
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
                with self.when(cR): self.set('osp', self.v('osp') - 1); self.arr_end(tvv)
                with self.when(cB):
                    self.emit(R.PUSHI, 0); self.set('f_expr', 1)
                    with self.when(PRB): self.set('f_asic', 1)
                with self.when(cC): self.emit(R.PUSHI, 1); self.set('f_expr', 1)
                with self.when(and_(not_(cA), not_(cB), not_(cC), not_(cN), not_(cR))): self.fail(3)
        # ---- S_OPER
        with block(R.S_OPER):
            # pm is set only on the way out of S_OPER (S_DOT, x[k]'s ']'): a variant starting in another mode knows it is 0
            pmr = self.m(self.v('pm'), 'pmr') if self.spec_mode in (None, R.S_OPER) else K(0)
            pm4 = self.m(ge(pmr, 4), 'pm4')                     # x.name for a method's name: a call, or else the property
            mcall = self.m(and_(pm4, P(40)), 'mcall')
            with self.when(mcall): self.push_op(R.M_METH, sub(pmr, 4)); self.set('pm', 0); self.set('mode', R.S_OPND); self.done()
            with self.when(and_(pm4, not_(P(40)))): self.emit(R.SCANI, self.v('pn1')); self.set('pm', 1)
            pm0 = self.m(self.v('pm'), 'pm0') if self.spec_mode in (None, R.S_OPER) else K(0)
            pinc = self.m(eq(pm0, 3), 'pinc')                  # after x++ / ++x (cc_ref): no '.' or '[' may follow
            pbad = self.m(and_(pinc, or_(P(46), P(91))), 'pbad')
            with self.when(pbad): self.fail(48)
            with self.when(pinc): self.set('pm', 0)
            pmv = self.m(mul(pm0, not_(pinc)), 'pmv')
            with self.when(ne(pmv, 0)):                       # after o.x (cursor on the stack) or x[k] ([x, k]): cc_ref
                mks, dyn = self.m(self.v('pn1'), 'mks'), self.m(eq(pmv, 2), 'mdyn')
                p78 = self.m(or_(P(7), P(8)), 'p78')
                asgm = self.m(or_(P(61), ne(compound, 0), p78), 'masg')
                with self.when(asgm):
                    stl = self.stmt_level()
                    with self.when(not_(stl)): self.fail(70)
                    with self.when(stl):
                        with self.when(not_(P(61))):
                            with self.when(dyn): self.emit(R.OVER); self.emit(R.OVER); self.emit(R.IDXA, 0, b=0)
                            with self.when(not_(dyn)): self.emit(R.DUP); self.emit(R.LDF, 1)
                        with self.when(p78):
                            self.emit(R.PUSHI, 1); self.emit(ite(P(7), R.ADD, R.SUB))
                            self.emit(ite(dyn, R.STOREX, R.PUTV), mul(not_(dyn), mks), b=0)
                            self.pop_cs(); self.set('pm', 0); self.set('mode', R.S_INC); self.done()
                        with self.when(not_(p78)):
                            t = self.top(); off = self.m(mul(not_(dyn), sub(mks, self.db + R.SDATA)), 'koff')
                            self.set_top(add(R.C_PSET * 4096, mul(dyn, 64), compound), add(mul(t[5], 4096), mul(fdiv(off, 64), 64), mod(off, 64)))
                            self.set('pm', 0); self.set('mode', R.S_OPND); self.done()
                with self.when(not_(asgm)):
                    self.emit(ite(dyn, R.IDXA, R.LDF), not_(dyn), b=0); self.set('pm', 0)
            pmasg = self.m(and_(ne(pmv, 0), or_(P(61), ne(compound, 0), P(7), P(8))), 'pmasg')   # handled above (done)
            binop = self.m(add(*[mul(P(ch), op) for ch, op in R.BIN.items()]), 'binop')
            osp_ = self.m(self.v('osp'), 'ospa')
            nomark = self.m(not_(or_(*[and_(lt(k, osp_), ge(self.v(f'op{k}'), 100 * 8192)) for k in range(OD)])), 'nomark')
            tk0 = self.top()[0]
            csp_ = self.m(self.v('csp'), 'cspa')            # the entry below the top: a for header takes no semicolon insertion
            k2 = self.m(add(*[mul(eq(csp_, k + 2), fdiv(self.v(f'csA{k}'), 4096)) for k in range(CD - 1)]), 'k2nd')
            asiok = self.m(and_(nomark, anyeq(tk0, (R.C_ASSIGN, R.C_EXPR, R.C_RETURN, R.C_PSET)),
                                not_(anyeq(k2, (R.C_FORINIT, R.C_FORSTEP)))), 'asiok')
            semi = self.m(or_(P(59), and_(or_(PNL, PRB), asiok)), 'semi')
            with self.when(and_(PNL, not_(asiok))): self.done()
            closer = self.m(or_(ne(binop, 0), P(41), P(44), P(93), P(58), P(63), semi, PRB), 'closer')
            with self.when(closer):
                self.popops(self.m(ite(ne(binop, 0), self.prec(binop), add(1, P(63))), 'minp'))
            tc, tvv = self.top_op()
            osp0 = self.m(self.v('osp'), 'osp0')
            tc = self.m(mul(tc, gt(osp0, 0)), 'tt')
            with self.when(and_(P(46), not_(pbad))): self.set('mode', R.S_DOT); self.done()                         # o.x
            with self.when(and_(P(91), not_(pbad))): self.push_op(R.M_INDEX); self.set('mode', R.S_OPND); self.done()     # x[k]
            okend = self.m(and_(eq(tc, R.M_OKEY), or_(PRB, P(44))), 'okend')                # an object literal's value ended
            with self.when(okend): self.okey_end(tvv, PRB)
            ixend = self.m(and_(P(93), eq(tc, R.M_INDEX)), 'ixend')
            with self.when(ixend): self.set('osp', osp0 - 1); self.set('pm', 2); self.done()
            with self.when(ne(binop, 0)):
                lb0 = self.m(self.v('lb'), 'lb0')
                inpr = self.m(eq(tc, R.M_PRINT), 'inpr'); npc = self.m(fdiv(tvv, 4), 'npc')
                cat = self.m(and_(eq(binop, R.ADD), inpr, or_(ne(npc, 0), eq(lb0, 2))), 'cat')     # a piece, kept on the stack (cc_ref)
                join = self.m(and_(ne(binop, R.ADD), lt(self.prec(binop), 7), inpr, ne(npc, 0)), "join")   # the pieces joined
                with self.when(cat):
                    with self.when(eq(lb0, 1)): self.emit(R.CALL, self.ent['b2s'], b=2)
                    full = self.m(eq(npc, R.PIECES - 1), 'pfull')
                    with self.when(full): self.catn(npc)
                    self.set_top_op(R.M_PRINT, add(ite(full, mod(tvv, 4), tvv), 4))
                with self.when(join): self.catn(npc); self.set_top_op(R.M_PRINT, mod(tvv, 4))
                lb1 = self.m(self.v('lb'), 'lb1')
                logic = self.m(and_(not_(cat), or_(eq(binop, R.AND), eq(binop, R.OR))), 'logic')
                plus = self.m(and_(not_(cat), eq(binop, R.ADD)), 'plus')
                with self.when(plus): self.push_op(ite(inpr, R.M_CADD, R.ADD), lb0)
                with self.when(logic):
                    l = self.newlab(); self.emit(R.DUP); self.emit(ite(eq(binop, R.AND), R.JZ, R.JNZ), 0, l); self.emit(R.POP)
                    self.push_op(binop, add(l, mul(lb1, 64)))
                with self.when(and_(not_(cat), not_(logic), not_(plus))): self.push_op(binop, lb1)     # (the left operand's type)
                self.set('mode', R.S_OPND); self.done()
            with self.when(P(63)):                             # c ? ... (cc_ref)
                with self.when(and_(eq(tc, R.M_PRINT), ge(tvv, 4))): self.catn(fdiv(tvv, 4)); self.set_top_op(R.M_PRINT, mod(tvv, 4))
                l = self.newlab(); self.emit(R.JZ, 0, l); self.push_op(R.M_TERN, add(l, mul(eq(tc, R.M_TELSE), 64)))
                self.set('mode', R.S_OPND); self.done()
            with self.when(P(58)):                             # c ? a : ...
                cse = self.m(and_(ne(tc, R.M_TERN), eq(osp0, 0), eq(self.top()[0], R.C_CASE)), 'cse')
                with self.when(cse): self.case_end()
                with self.when(and_(ne(tc, R.M_TERN), not_(cse))): self.fail(67)
                with self.when(eq(tc, R.M_TERN)):
                    lbt = self.m(self.v('lb'), 'lbt'); reuse = self.m(ge(tvv, 64), 'treu')
                    self.set('osp', osp0 - 1)
                    _, ev = self.top_op()                      # the enclosing M_TELSE, when reuse
                    with self.when(not_(reuse)): l2 = self.newlab()
                    self.emit(R.JMP, 0, ite(reuse, mod(ev, 64), l2))
                    with self.when(reuse): self.set_top_op(R.M_TELSE, add(mod(ev, 64), mul(self.tmerge(fdiv(ev, 64), lbt), 64)))
                    with self.when(not_(reuse)): self.push_op(R.M_TELSE, add(l2, mul(lbt, 64)))
                    self.deflab(mod(tvv, 64), self.here()); self.set('mode', R.S_OPND); self.done()
            cl = self.m(and_(eq(binop, 0), or_(P(41), P(44), P(93)), not_(okend), not_(ixend)), 'cl')
            with self.when(cl):
                t = tc
                with self.when(P(44)):
                    vasg = self.m(and_(eq(osp0, 0), eq(self.top()[0], R.C_ASSIGN), ne(self.top()[3], 0)), 'vasg')
                    with self.when(eq(t, R.M_PRINT)): self.print_call(32, tvv); self.set_top_op(R.M_PRINT, 2); self.set('mode', R.S_CONFIRST); self.done()
                    with self.when(anyeq(t, (R.M_CALL, R.M_METH))): self.set_top_op(t, tvv + 64)       # count the arguments
                    with self.when(eq(t, R.M_ARR)): self.set_top_op(R.M_ARR, tvv + 1)
                    with self.when(anyeq(t, (R.M_CALL, R.M_METH, R.M_PUTC, R.M_ARR))): self.set('mode', R.S_OPND); self.done()
                    with self.when(vasg): self.set('f_expr', 1)
                    with self.when(not_(or_(anyeq(t, (R.M_PRINT, R.M_CALL, R.M_METH, R.M_PUTC, R.M_ARR)), vasg))): self.fail(44)
                with self.when(P(93)):
                    with self.when(eq(t, R.M_ARR)): self.set('osp', osp0 - 1); self.arr_end(tvv + 1)
                    with self.when(ne(t, R.M_ARR)): self.fail(45)
                with self.when(P(41)):
                    with self.when(eq(t, R.M_PAREN)): self.set('osp', osp0 - 1); self.done()
                    with self.when(eq(t, R.M_CALL)): self.set('osp', osp0 - 1); self.call_end(tvv, 1)
                    with self.when(eq(t, R.M_METH)): self.set('osp', osp0 - 1); self.meth_end(tvv, 1)
                    with self.when(eq(t, R.M_PUTC)): self.set('osp', osp0 - 1); self.emit(R.PUTC); self.emit(R.PUSHI, 0); self.done()
                    with self.when(eq(t, R.M_PRINT)): self.print_call(10, tvv); self.set('osp', osp0 - 1); self.print_end()
                    other = self.m(not_(anyeq(t, (R.M_PAREN, R.M_CALL, R.M_METH, R.M_PUTC, R.M_PRINT))), 'o41')
                    with self.when(and_(other, gt(osp0, 0))): self.fail(46)
                    with self.when(and_(other, eq(osp0, 0))): self.set('f_expr', 1)
            with self.when(and_(eq(binop, 0), semi, not_(okend))):
                with self.when(gt(osp0, 0)): self.fail(47)
                with self.when(eq(osp0, 0)):
                    self.set('f_expr', 1)
                    with self.when(PRB): self.set('f_asic', 1)
            with self.when(and_(eq(binop, 0), not_(or_(P(41), P(44), P(93), P(58), P(63), semi, PNL, P(46), P(91), okend, pmasg, mcall)))): self.fail(48)
        # deferred tails (each is the last thing its path does)
        with self.when(self.v('f_expr')): self.end_expr_stmt(P)
        with self.when(self.v('f_simple')): self.end_simple_stmt(P)
        asic = self.m(self.v('f_asic'), 'asic')
        with self.when(self.v('f_compl')): self.complete_stmt(asic)
        with self.when(asic): self.close_block('f_compl2')        # '}' after a statement without ';'
        with self.when(self.v('f_compl2')): self.complete_stmt(K(0))
        # nothing handled it
        with self.when(self.v('live')): self.fail(99)

    def okey_end(self, tvv, close):
        """cc_ref.okey_end: store the pair whose value ended (close: the literal ended too)"""
        self.set('osp', self.v('osp') - 1)
        _, o = self.top_op(); o = self.m(o, 'oko')
        with self.when(eq(tvv, 0)): self.emit(R.SETF, add(mul(o, 2), 1)); self.set_top_op(R.M_OBJ, o + 1)
        with self.when(eq(tvv, 1)): self.emit(R.STOREX)
        with self.when(gt(tvv, 1)): self.emit(R.PUTV, tvv)
        o2 = self.m(add(o, eq(tvv, 0)), 'oko2'); close = lift(close)
        with self.when(close):
            with self.when(lt(o2, 4)): self.emit(R.ENDK, mul(o2, 2))
            self.set('osp', self.v('osp') - 1); self.set('lb', 0); self.set('mode', R.S_OPER)
        with self.when(not_(close)): self.set('mode', R.S_OKEY)
        self.done()

    def fn_sel(self, k, f): return self.m(add(*[mul(eq(k, i), I(f'{f}{i}')) for i in range(NF)]), f)
    def call_end(self, tv, last):
        """cc_ref.call_end: CALL, after checking (or recording) the function's argument count"""
        k = self.m(mod(tv, 16), 'cfk'); argc = self.m(add(fdiv(tv, 64), last), 'argc')
        fl = self.fn_sel(k, 'fl_'); exp = self.m(fdiv(fl, 256), 'cexp')
        bad = self.m(and_(ne(exp, 0), ne(exp, add(argc, 1))), 'cbad')
        with self.when(bad): self.fail(76)
        with self.when(not_(bad)):
            with self.when(eq(exp, 0)):
                self.fnw.append((self.x.g, k, self.fn_sel(k, 'fh1_'), self.fn_sel(k, 'fh2_'), add(mod(fl, 256), mul(add(argc, 1), 256))))
            self.emit(R.CALL, 0, mod(fl, 64), b=mod(fdiv(tv, 16), 4)); self.done()

    def print_end(self):
        """cc_ref.print_end: console.log(...) leaves no value; it ends its statement (C_EXPR) without a POP"""
        ok = self.m(and_(eq(self.v('osp'), 0), eq(self.top()[0], R.C_EXPR)), 'pend')
        with self.when(not_(ok)): self.fail(30)
        with self.when(ok): self.pop_cs(); self.set('mode', R.S_INC); self.done()

    def case_end(self):
        """cc_ref.case_end: EQ JZ Tnext POP Bk:, the switch's pending test := Tnext"""
        c = self.pop_cs()
        self.emit_dyn(R.EQ, 0, self.v('lb')); tn = self.newlab(); self.emit(R.JZ, 0, tn); self.emit(R.POP)
        with self.when(ne(c[2], 0)): self.deflab(c[1], self.here())
        t = self.top()
        self.set_top(add(R.C_SWITCH * 4096, mul(tn, 64), t[2]), add(mul(t[5], 4096), mul(t[3], 64), t[4], sub(1, mod(t[4], 2))))
        self.set('mode', R.S_STMT); self.done()

    def incdec(self, h1, h2, op, x=0, pre=None):
        """cc_ref.incdec. x: 0 statement, 1 ++x / 2 x++ in an expression; pre: the symbol (j, k, a, b, cst) if looked up"""
        if pre is None: j = self.lookup(h1, h2); k, a, b, cst = self.symkind_addr(j)
        else: j, k, a, b, cst = pre
        x = lift(x); x1, x2 = self.m(eq(x, 1), 'ix1'), self.m(eq(x, 2), 'ix2')
        with self.when(lt(j, 0)): self.fail(6)
        with self.when(and_(ge(j, 0), cst)): self.fail(64)
        with self.when(and_(ge(j, 0), not_(cst))):
            with self.when(x2): self.load(k, a, b)
            with self.when(eq(op, 7)): self.emit(ite(eq(k, 2), R.INCL, R.INCG), mod(a, 8192))
            with self.when(eq(op, 8)):
                self.load(k, a, b); self.emit(R.PUSHI, 1); self.emit(R.SUB)
                with self.when(x1): self.emit(R.DUP)
                self.store(k, a)
            with self.when(and_(x1, eq(op, 7))): self.load(k, a, b)
            with self.when(ne(x, 0)): self.set('lb', 3); self.set('pm', 3); self.set('mode', R.S_OPER)
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
            self.emit(R.JMP, 0, ite(isbreak, mod(A, 64), mod(fdiv(A, 64), 64))); self.set('mode', R.S_INC); self.done()

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
        with self.when(or_(c1, c2, c10)):                    # if / while / switch (cond): one push for the three
            self.pop_cs(); l1 = self.newlab()                # if: else label; while: end label; switch: first test's label
            with self.when(c10): l2 = self.newlab()          # switch: end label
            with self.when(or_(c1, c2)): self.emit(R.JZ, 0, l1)
            self.push_cs(ite(c1, R.C_IFB, ite(c2, R.C_LOOPB, R.C_SWITCH)), ite(c2, t[1], l1), ite(c1, 0, ite(c2, l1, l2)))
            self.set('mode', R.S_LBRACE); self.done()
        with self.when(c9):                                  # a property assignment (cc_ref)
            self.pop_cs()
            with self.when(eq(t[2], R.ADD)): self.emit_dyn(R.ADD, 0, self.v('lb'))       # (the old value's type is not known)
            with self.when(and_(ne(t[2], 0), ne(t[2], R.ADD))): self.emit(t[2])
            with self.when(ne(t[1], 0)): self.emit(R.STOREX)
            with self.when(eq(t[1], 0)): self.emit(R.PUTV, add(self.db + R.SDATA, mul(t[3], 64), t[4]))
            self.set('f_simple', 1)
        with self.when(c8):
            self.pop_cs(); self.emit(R.JNZ, 0, t[3]); self.deflab(t[2], self.here()); self.set('f_compl', 1); self.done()
        with self.when(c3):
            self.pop_cs(); self.emit(R.JZ, 0, t[2]); self.emit(R.JMP, 0, t[3]); self.deflab(t[4], self.here())
            self.push_cs(R.C_FORSTEP, t[1], t[2], t[3], t[4], t[5]); self.set('mode', R.S_STMT); self.done()
        with self.when(c4):                                  # t: symbol, compound op, from a declaration
            self.pop_cs()
            with self.when(eq(t[2], R.ADD)): self.emit_dyn(R.ADD, self.symkind_addr(t[1])[2], self.v('lb'))
            with self.when(and_(ne(t[2], 0), ne(t[2], R.ADD))): self.emit(t[2])
            self.set_symbool(t[1], self.m(self.v('lb'), 'alb'))
            kk, aa, _, _ = self.symkind_addr(t[1]); self.store(kk, aa)
            vdecl = self.m(and_(P(44), ne(t[3], 0)), 'vdecl')
            with self.when(vdecl): self.set('pn1', sub(t[3], 1)); self.set('pn2', 0); self.set('mode', R.S_VAR); self.done()
            with self.when(not_(vdecl)): self.set('f_simple', 1)
        with self.when(c6):
            self.pop_cs(); self.emit(R.POP); self.set('f_simple', 1)
        with self.when(c7):
            self.pop_cs()
            rty = self.m(self.v('lb'), 'rty')
            with self.when(ne(rty, 0)):                       # the function returns a boolean / a string
                cfn = self.v('cfn')
                fl = self.m(add(*[mul(eq(cfn, i), I(f'fl_{i}')) for i in range(NF)]), 'rfl')
                self.fnw.append((self.x.g, cfn, add(*[mul(eq(cfn, i), I(f'fh1_{i}')) for i in range(NF)]),
                                 add(*[mul(eq(cfn, i), I(f'fh2_{i}')) for i in range(NF)]), add(mod(fl, 64), mul(rty, 64), mul(fdiv(fl, 256), 256))))
            self.emit(R.RET, self.v('npar')); self.set('f_compl', 1); self.done()
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
            # the code (shared code slots): loop JMP top; function PUSHI 0 RET; switch [JMP end] T: POP [JMP default]
            isfn, issw, islp = self.m(eq(k, R.C_FUNCB), 'cfn'), self.m(eq(k, R.C_SWITCH), 'csw'), self.m(eq(k, R.C_LOOPB), 'clp')
            with self.when(isfn): self.emit(R.PUSHI, 0)
            with self.when(or_(islp, and_(issw, mod(t[4], 2)))): self.emit(R.JMP, 0, ite(islp, t[1], t[2]))
            # a function's frame size, or a switch's no-match label T: one label port for both
            with self.when(or_(isfn, issw)):
                self.deflab(ite(isfn, t[2], t[1]), ite(isfn, self.v('nloc'), self.here()))
                self.emit(ite(isfn, R.RET, R.POP), mul(isfn, self.v('npar')), b=0)
            with self.when(and_(issw, ge(t[4], 2))): self.emit(R.JMP, 0, t[3])
            # the end label of whichever body closed (one kind per call, so one label port serves them all)
            with self.when(anyeq(k, (R.C_ELSEB, R.C_DOB, R.C_LOOPB, R.C_FUNCB, R.C_SWITCH))):
                self.deflab(ite(or_(eq(k, R.C_LOOPB), issw), t[2], t[1]), self.here())
            with self.when(anyeq(k, (R.C_ELSEB, R.C_LOOPB, R.C_SWITCH))): self.set(flag, 1); self.done()
            with self.when(eq(k, R.C_DOB)): self.set('csp', self.v('csp') + 1); self.set('mode', R.S_DOWHILE); self.done()
            with self.when(eq(k, R.C_FUNCB)):
                self.set('curf', 0); self.set('nsym', self.v('fsym')); self.set('mode', R.S_STMT); self.done()
            with self.when(not_(anyeq(k, (R.C_BLOCK, R.C_IFB, R.C_ELSEB, R.C_DOB, R.C_LOOPB, R.C_FUNCB, R.C_SWITCH)))): self.fail(55)

    def end_params(self):
        csp = self.m(self.v('csp'), 'csp')
        le = self.m(add(*[mul(eq(csp, k + 1), mod(self.v(f'csA{k}'), 64)) for k in range(CD)]), 'fle')
        cfn, npar = self.v('cfn'), self.v('npar'); fl = self.fn_sel(cfn, 'fl_'); exp = self.m(fdiv(fl, 256), 'pexp')
        bad = self.m(and_(ne(exp, 0), ne(exp, add(npar, 1))), 'pbad')     # cc_ref.end_params: the calls so far must agree
        with self.when(bad): self.fail(76)
        with self.when(not_(bad)):
            self.fnw.append((self.x.g, cfn, self.fn_sel(cfn, 'fh1_'), self.fn_sel(cfn, 'fh2_'), add(mod(fl, 256), mul(add(npar, 1), 256))))
            self.emit(R.ENTER, 0, le); self.set('mode', R.S_LBRACE); self.done()

    def arr_end(self, n):
        """cc_ref.arr_end: the n elements are on the stack"""
        self.emit(R.PUSHI, n); self.emit(R.CALL, self.ent['mkarr'], b=0); self.set('mode', R.S_OPER); self.done()

    def meth_end(self, tv, last):
        """cc_ref.meth_end: the routine for (method, argument count), or error 77"""
        mid = self.m(mod(tv, 64), 'mid'); argc = self.m(add(fdiv(tv, 64), last), 'margc')
        pairs = [(i, n, e) for i, (nm, ents, ty) in enumerate(R.ALLM) for n, e in ents.items()]
        hit = [self.m(and_(eq(mid, i), eq(argc, n)), 'mh') for i, n, e in pairs]
        ok = self.m(or_(*hit), 'mok')
        with self.when(not_(ok)): self.fail(77)
        with self.when(ok):
            sid = next(i for i, m in enumerate(R.ALLM) if m[0] == 'String')
            strb = and_(eq(mid, sid), eq(self.v('lb'), 1))          # String(a boolean)
            addr = ite(strb, self.ent.get('tostringb', 0), add(*[mul(h, self.ent.get(e, 0)) for h, (i, n, e) in zip(hit, pairs)]))
            ty = add(*[mul(eq(mid, i), m[2]) for i, m in enumerate(R.ALLM) if m[2]])
            self.emit(R.CALL, addr, b=ty); self.set('mode', R.S_OPER); self.done()

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
