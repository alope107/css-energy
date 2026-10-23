#!/usr/bin/env python3
"""rc_ref.py — the register machine's reference compiler and simulator (a proof of concept: exp/regvm/README.md).
python3 exp/regvm/rc_ref.py prog.js [-d] compiles and runs one program (-d: the code).

The lexer, the tables and the statement structure are cc_ref.py's (a subclass): one token per step, fixed-size stacks, no
lookahead, so the parser can become CSS as cc_dsl.py did. Only code generation differs. cc_ref emits stack code as each
token arrives; here an operand is a descriptor on an operand stack (a variable, a constant, a temp), and code is emitted
when an operator pops (shunting-yard, as before), as one three-address instruction reading the operands where they are.

Instructions are two words, at even addresses (both words in one 4-word cache block, so one fetch):
  word0 = op * 8192 + A        A: a destination operand, a jump target, or flags
  word1 = (B - 512) * 1024 + C B, C: source operands (10 bits each); LOADK, PRINTK and CALL use word1 whole (a value / an offset)
An operand o (10 bits) is a cell or a constant:
  0 ... 255    global, address data_base + o
  256 ... 767  frame slot, address fp + o - 256
  768 ... 1023 the constant o - 896 (-128 ... 127)
A frame is [return word] fp, parameters fp + 1 ..., locals, then the temps: the operand stack's slot d is T(d) = fp + 1 + npar +
nloc + d, where nloc is the function's final count of locals, a label the linker adds (as ENTER's count was in cc_ref). A
call's slot T(d0) takes the return word and its arguments go to T(d0 + 1) ...: CALL target, off (fp + off = T(d0)) writes
off * 8192 + the return address there and adds off to fp; RET v writes v over the return word, the caller's T(d0), and
subtracts off again. One register, fp, so no ENTER and no saved fp. Top-level code runs with fp = sp0 (globals are absolute).
No ROM: the subset needs no runtime library (no heap strings, arrays or objects).

The subset (error 90 outside it): integers, booleans, string literals as values (printed, compared by identity), var / let /
const, functions, if / else, while, do / while, for, break, continue, return, + - * / % < > <= >= == != === !== && || ! unary -
?:, = op= ++ --, console.log (a + chain with a string prints its pieces, as main's pnK does), putc."""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(ROOT, 'compiler')]
import cc_ref as R
from cc_ref import (ADD, SUB, MUL, DIV, MOD, LT, GT, LE, GE, EQ, NE, AND, OR, NOT, NEG, BIN, COMPOUND, KW, NS, NL, SDATA, STRTAG,
                    NOROOM, PARAM0, LAYOUT, T_NL, M_CADD, M_TELSE, M_PAREN, M_CALL, M_PUTC, M_PRINT, M_TERN, prec, tmerge, truthy,
                    C_BLOCK, C_IFB, C_ELSEB, C_DOB, C_LOOPB, C_FUNCB, C_IFC, C_WHILEC, C_FORINIT, C_FORCOND, C_FORSTEP, C_ASSIGN,
                    C_EXPR, C_RETURN, C_DOB1, C_ELSEB1, C_IFB1, C_LOOPB1, BRACELESS,
                    S_STMT, S_OPND, S_OPER, S_NAMES, S_NAMEE, S_VAR, S_VARAFTER, S_LPAREN, S_LBRACE, S_ELSE, S_FNAME, S_FPAREN,
                    S_FPARAM, S_FPSEP, S_CONLOG, S_CONLP, S_CONFIRST, S_INC, S_AFTERELSE, S_PREINC, S_DOWHILE)

OPN = ('ADD SUB MUL DIV MOD LT GT LE GE EQ NE  MOV NEG LOADK  JMP JLT JGT JLE JGE JEQ JNE HALT  JZ JNZ  CALL RET NOT '
       ' PRINT PRINTK PUTC').split()                  # in class order (gen_rcss.py's classes alu, mov, jump, test, call, out)
OP = {n: i for i, n in enumerate(OPN)}
CMPS = (LT, GT, LE, GE, EQ, NE)
NAME = {ADD: 'ADD', SUB: 'SUB', MUL: 'MUL', DIV: 'DIV', MOD: 'MOD', LT: 'LT', GT: 'GT', LE: 'LE', GE: 'GE', EQ: 'EQ', NE: 'NE',
        NOT: 'NOT', NEG: 'NEG'}
INV = {LT: GE, GE: LT, GT: LE, LE: GT, EQ: NE, NE: EQ}
ODN = 16                                # the operand stack (its temps T(0) ... T(15))
LOOPCOPY = int(os.environ.get('LOOPCOPY', 0))   # experiment: a loop's one-instruction test (1, and a for's one-instruction step: 2)
                                                # emitted again at its bottom instead of a jump back to it
NOTSUB = 90                             # a construct outside the subset
CODE0 = LAYOUT['code_base']; CODESZ = R.CODESZ
def G(a, db): return a - db             # operand encodings
def L(off): return 256 + off
def K(v): return 896 + v
def isK(o): return 768 <= o < 1024
def T(d): return 2048 + d               # descriptors: temp d (an fp slot past the locals: enc), a constant LOADK must load first,
KBIG, CND = 1024, 1025                  # a pending comparison (pcnd)
SEP = {0: 0, 32: 1, 10: 2}              # PRINT / PRINTK's A: separator * 2 + boolean

class Compiler(R.Compiler):
    def __init__(self, data_base, code_base, lib=None):
        super().__init__(data_base, code_base, lib or {'entries': {}})
        self.od = [0] * ODN; self.odt = [0] * ODN; self.odk = [0] * ODN; self.nd = 0     # operand descriptors, types, big constants
        self.pcnd = None                # the pending comparison (op, B, C) a branch takes as it is
        self.maxstep = 0

    # ---------------- code
    def enc(self, o):
        """an operand's field and whether it needs the function's count of locals added (a temp in a function)"""
        if o < 2048: return o, 0
        return L(1 + self.npar * self.curf + o - 2048), self.curf
    def emit(self, op, a=0, b=0, c=0, label=None, w1=None, off=None):
        """one instruction: op A, B, C (or A and word1 whole; off: CALL's frame offset T(d0), a temp); label: A is that label's
        value at link time. Temps add the count of locals (the function's label) times 1 in A, 1024 in B and 1 in C"""
        (a, na), (b, nb), (c, nc) = self.enc(a), self.enc(b), self.enc(c)
        if off is not None: w1, nw = self.enc(off); w1 -= 256
        else: nw = 1024 * nb + nc
        if w1 is None: w1 = (b - 512) * 1024 + c
        self.code[self.cp] = (op, a, w1, label, na, nw, self.cs[self.fcs][2] if self.curf else None); self.cp += 1
    def here(self): return self.cb + 2 * self.cp
    def char(self, c, cn):
        cp0 = self.cp; super().char(c, cn); self.maxstep = max(self.maxstep, self.cp - cp0)
    def link(self):
        if 2 * self.cp > CODESZ: self.fail(62)
        words = {}
        for i, (op, a, w1, lab, na, nw, nlab) in self.code.items():
            if lab is not None:
                if lab >= NL or self.lab[lab] < 0: self.fail(60); a = 0
                else: a = self.lab[lab] % 8192
            n = self.lab[nlab] if nlab is not None else 0
            words[self.cb + 2 * i] = OP[op] * 8192 + a + na * n; words[self.cb + 2 * i + 1] = w1 + nw * n
        return words, dict(self.data)

    # ---------------- operands
    def var(self, j):
        k, a = self.sym[j][2], self.sym[j][3]
        return L(a) if k == 2 else G(a, self.db)
    def push_od(self, o, t, k=0):
        if self.nd >= ODN: return self.fail(22)
        self.od[self.nd] = o; self.odt[self.nd] = t; self.odk[self.nd] = k; self.nd += 1
    def push_num(self, v, t=3):
        v = (v + (1 << 19)) % (1 << 20) - (1 << 19)
        if -128 <= v < 128: self.push_od(K(v), t)
        else: self.push_od(KBIG, t, v)
    def put(self, dst, i):
        """the value of descriptor i into operand dst"""
        o = self.od[i]
        if o == dst: return
        if o == KBIG: self.emit('LOADK', dst, w1=self.odk[i])
        elif o == CND: cop, b, c = self.pcnd; self.pcnd = None; self.emit(NAME[cop] if cop != 'NOT' else 'NOT', dst, b, c)
        else: self.emit('MOV', dst, o)
    def src(self, i):
        """descriptor i as a source operand (a big constant or a pending comparison goes to its temp first)"""
        if self.od[i] in (KBIG, CND): self.put(T(i), i); self.od[i] = T(i)
        return self.od[i]
    def to_temp(self, i):
        self.put(T(i), i); self.od[i] = T(i)
    def snapshot(self, hit, n=None):
        """operands still on the stack (below n) that a call or ++ / -- is about to change: copied to their temps first. At the
        start of a conditional region (&&, ||, ?:) every variable below is copied: a copy made inside it would be made on one
        path only"""
        for i in range(self.nd if n is None else n):
            if self.od[i] < 768 and hit(self.od[i]): self.emit('MOV', T(i), self.od[i]); self.od[i] = T(i)
    def branch(self, lab, sense):
        """pop the top value and jump to lab if its truth is sense (a pending comparison fuses into the jump)"""
        cp0 = self.cp; self.branch1(lab, sense)
        e = self.code.get(self.cp - 1) if self.cp == cp0 + 1 else None      # the test as one instruction on variables (copyable)
        self.lastbr = e if e and e[0][0] == 'J' and e[0] != 'JMP' and e[4] == 0 and e[5] == 0 else None
    def branch1(self, lab, sense):
        i = self.nd - 1; self.nd -= 1
        if self.od[i] == CND:
            cop, b, c = self.pcnd; self.pcnd = None
            if cop == 'NOT': return self.emit('JZ' if sense else 'JNZ', b=b, label=lab)
            return self.emit('J' + NAME[cop if sense else INV[cop]], b=b, c=c, label=lab)
        if isK(self.od[i]):                             # a constant condition: jump or not, known now
            if (self.od[i] != K(0)) == sense: self.emit('JMP', label=lab)
            return
        if self.od[i] == KBIG and self.odt[i] != 2:
            if (self.odk[i] != 0) == sense: self.emit('JMP', label=lab)
            return
        b = self.src(i); self.emit('JNZ' if sense else 'JZ', b=b, label=lab)

    def popops(self, minprec, mode=None):
        """pop and emit operators with precedence >= minprec. mode 'br': a comparison popped last stays pending (pcnd) for the
        branch that takes the value; ('dest', o): an operator popped last writes operand o directly (an assignment's target)"""
        while self.osp and 0 < prec(self.ops[self.osp - 1]) and prec(self.ops[self.osp - 1]) >= minprec:
            self.osp -= 1; code, val = self.ops[self.osp], self.opv[self.osp]
            last = not (self.osp and 0 < prec(self.ops[self.osp - 1]) >= minprec)
            dest = mode[1] if last and isinstance(mode, tuple) else None
            if code in (AND, OR):                       # the left operand is in T(i), tested; the right one joins it there
                i = self.nd - 2; self.put(T(i), i + 1); self.nd -= 1; self.od[i] = T(i)
                self.odt[i] = tmerge(val // 64, self.odt[i + 1]); self.deflab(val % 64, self.here())
            elif code == M_TELSE:                       # c ? a : b: a went to T(i); b joins it
                i = self.nd - 1; self.to_temp(i); self.odt[i] = tmerge(val // 64, self.odt[i]); self.deflab(val % 64, self.here())
            elif code == NOT and last and mode == 'br' and self.od[self.nd - 1] != CND:
                i = self.nd - 1; self.pcnd = ('NOT', self.src(i), 0); self.od[i] = CND; self.odt[i] = 1
            elif code in (NOT, NEG):
                i = self.nd - 1; b = self.src(i); d = T(i) if dest is None else dest
                self.emit(NAME[code], d, b); self.od[i] = d; self.odt[i] = 1 if code == NOT else 3
            elif code == M_CADD:                        # + at a console.log argument's top level: a string on either side splits it
                i = self.nd - 2
                if 2 in (val, self.odt[i + 1]): self.opv[self.osp - 1] += 4      # two pieces (M_PRINT is right below)
                else: self.binop(ADD, i, dest)
            else:
                if code == ADD and 2 in (val, self.odt[self.nd - 1]): return self.fail(NOTSUB)     # building a string
                self.binop(code, self.nd - 2, dest, mode == 'br' and last)

    def binop(self, code, i, dest, pend=False):
        if code in (LT, GT, LE, GE) and 2 in (self.odt[i], self.odt[i + 1]): return self.fail(NOTSUB)     # strings by their characters
        b, c = self.src(i), self.src(i + 1); self.nd -= 1
        if pend and code in CMPS: self.pcnd = (code, b, c); self.od[i] = CND
        else:
            d = T(i) if dest is None else dest; self.emit(NAME[code], d, b, c); self.od[i] = d
        self.odt[i] = 1 if code in CMPS else 3

    def cond_ctx(self, closer):
        """this token ends a statement-level expression that a branch takes (an if / while / do-while condition, a for test)"""
        if any(self.ops[k] >= 100 for k in range(self.osp)): return False
        t = self.top_cs()[0]
        return (closer == 41 and t in (C_IFC, C_WHILEC, C_DOB, C_DOB1)) or (closer == 59 and t == C_FORCOND)
    def dest_ctx(self):
        """an assignment's value ends here: its last operator may write the target"""
        t = self.top_cs()
        if any(self.ops[k] >= 100 for k in range(self.osp)) or t[0] != C_ASSIGN or t[2]: return None
        return ('dest', self.var(t[1]))
    def end_mode(self, closer):
        return 'br' if self.cond_ctx(closer) else self.dest_ctx()

    def print_call(self, sep):
        """a console.log argument ended: its pieces (a + chain with a string) are on the operand stack from d0; print each"""
        c = self.opv[self.osp - 1] // 4; d0 = self.nd - 1 - c
        for i in range(d0, self.nd):
            flags = 2 * (SEP[sep] if i == self.nd - 1 else 0) + int(self.odt[i] == 1)
            if self.od[i] == KBIG: self.emit('PRINTK', flags, w1=self.odk[i])
            else: self.emit('PRINT', flags, self.src(i))
        self.nd = d0

    def call_end(self, tv, last):
        """a call's ')': its slot T(d0) (pushed at '(') takes the return word, the arguments are in T(d0 + 1) ..."""
        k, argc = tv % 16, tv // 64 + last
        if last: self.to_temp(self.nd - 1)
        if self.fn[k][4] and self.fn[k][4] != argc + 1: return self.fail(76)
        self.fn[k][4] = argc + 1
        d0 = self.nd - argc - 1
        self.emit('CALL', label=self.fn[k][2], off=T(d0))
        self.nd = d0; self.push_od(T(d0), (tv // 16) % 4)

    def incdec(self, h, v, x=0):
        """++ (v 7) / -- (8) of a variable. x: 0 a statement, 1 ++x in an expression (its new value), 2 x++ (the old)"""
        j = self.lookup(h)
        if j < 0: return self.fail(6)
        if self.sym[j][5]: return self.fail(64)
        o = self.var(j)
        if x: self.snapshot(lambda q: q == o)
        if x == 2: self.push_od(o, 3); self.to_temp(self.nd - 1)
        self.emit('ADD' if v == 7 else 'SUB', o, o, K(1))
        if x == 1: self.push_od(o, 3)
        if x: self.pm = 3; self.mode = S_OPER
        else: self.mode = S_INC

    # ---------------- parser: one token (cc_ref.token's structure; the objects, arrays, methods and switch are outside)
    def token(self, kind, v):
        if self.err: return
        isP = lambda c: kind == 'P' and v == c
        isK_ = lambda k: kind == 'ID' and v == KW[k]
        m = self.mode
        if isP(T_NL) and m not in (S_NAMES, S_NAMEE, R.S_OPER, S_VARAFTER, S_INC, S_OPND): return
        if m == S_NAMES:
            h = self.pn
            if isP(61) or (kind == 'P' and v in COMPOUND):
                j = self.lookup(h)
                if j < 0: return self.fail(5)
                if self.sym[j][5]: return self.fail(64)
                if not isP(61): self.push_od(self.var(j), self.sym[j][4])     # x op= e: x is the left operand, read first
                self.push_cs(C_ASSIGN, j, COMPOUND.get(v, 0) if kind == 'P' else 0); self.mode = S_OPND; return
            if isP(7) or isP(8): return self.incdec(h, v)
            if isP(91): return self.fail(NOTSUB)
            self.push_cs(C_EXPR); m = self.mode = S_NAMEE
            if self.err: return
        if m == S_NAMEE:
            h = self.pn
            if h == KW['console']:
                if not isP(46): return self.fail(30)
                self.mode = S_CONLOG; return
            if isP(40):
                if h == KW['putc']: self.push_op(M_PUTC)
                elif h in R.GLOBAL_INDEX: return self.fail(NOTSUB)
                else:
                    self.snapshot(lambda q: q < 256)          # the callee may change a global still waiting on the stack
                    k = self.fnfind(h); self.push_op(M_CALL, k + 16 * self.fn[k][3]); self.push_od(T(self.nd), 0)   # its slot
                self.mode = S_OPND; return
            if isP(7) or isP(8): return self.incdec(h, v, 2)
            j = self.lookup(h)
            if j < 0: return self.fail(NOTSUB if h == KW['String'] else 4)
            self.push_od(self.var(j), self.sym[j][4]); m = self.mode = S_OPER
        if m == S_ELSE:
            if isK_('else'):
                t = self.top_cs(); reuse = t[0] == C_ELSEB1
                lb = t[1] if reuse else self.newlab()
                self.emit('JMP', label=lb); self.deflab(self.pendLa, self.here())
                self.pendLa = lb + 64 * reuse; self.mode = S_AFTERELSE; return
            dook = kind in ('ID', 'EOF') or (kind == 'P' and v in (59, 123, 125, 7, 8, 41))
            self.deflab(self.pendLa, self.here()); self.complete_stmt(1, dook); m = self.mode
        if m == S_DOWHILE:
            if isP(59): return
            if not isK_('while'): return self.fail(66)
            self.mode = S_LPAREN; return
        if m == S_AFTERELSE:
            reuse = self.pendLa >= 64
            if isP(123):
                if reuse: self.push_cs(C_BLOCK)
                else: self.push_cs(C_ELSEB, self.pendLa)
                self.mode = S_STMT; return
            if not reuse: self.push_cs(C_ELSEB1, self.pendLa)
            m = self.mode = S_STMT
        if m == S_LBRACE:
            if isP(123): self.mode = S_STMT; return
            if self.top_cs()[0] not in (C_IFB, C_LOOPB, C_DOB): return self.fail(33)
            self.cs[self.csp - 1][0] += BRACELESS; m = self.mode = S_STMT
        if m == S_STMT:
            if kind == 'EOF':
                if self.csp: return self.fail(40)
                if self.nfdef < self.nfn: return self.fail(60)
                self.emit('HALT'); return
            if isP(123): self.push_cs(C_BLOCK); return
            if isP(125): return self.close_block()
            if isP(59): return self.end_simple_stmt(kind, v)
            if isP(41) and self.top_cs()[0] == C_FORSTEP: return self.end_simple_stmt(kind, v)
            if isP(7) or isP(8): self.pn = (v, 0); self.mode = S_PREINC; return
            if kind != 'ID': return self.fail(8)
            if isK_('var') or isK_('let') or isK_('const'):
                self.pn = (int(isK_('let')) + 2 * int(isK_('const')), 0); self.mode = S_VAR; return
            if isK_('if'): self.push_cs(C_IFC); self.mode = S_LPAREN; return
            if isK_('switch') or isK_('case') or isK_('default'): return self.fail(NOTSUB)
            if isK_('while'):
                lh = self.newlab(); self.deflab(lh, self.here()); self.push_cs(C_WHILEC, lh); self.mode = S_LPAREN; return
            if isK_('do'):
                lt, lc, lb = self.newlab(), self.newlab(), self.newlab(); self.deflab(lt, self.here())
                self.push_cs(C_DOB, lc, lb, lt); self.mode = S_LBRACE; return
            if isK_('for'):
                l1, le, lb, l2 = self.newlab(), self.newlab(), self.newlab(), self.newlab()
                self.push_cs(C_FORINIT, l1, le, lb, l2); self.mode = S_LPAREN; return
            if isK_('return'):
                if not self.curf: return self.fail(57)
                self.push_cs(C_RETURN); self.mode = S_OPND; return
            if isK_('break') or isK_('continue'):
                e = self.loop_entry(isK_('break'))
                if e is None: return self.fail(56)
                self.emit('JMP', label=e[2] if isK_('break') else e[1]); self.mode = S_INC; return
            if isK_('function'):
                if self.curf or self.csp: return self.fail(41)
                lo = self.newlab(); self.emit('JMP', label=lo); self.mode = S_FNAME
                self.push_cs(C_FUNCB, lo); return
            self.pn = v; self.mode = S_NAMES; return
        if m == S_PREINC:
            if kind != 'ID': return self.fail(10)
            return self.incdec(v, self.pn[0], self.pn[1])
        if m == S_VAR:
            if kind != 'ID': return self.fail(9)
            cst, blk = int(self.pn[0] == 2), self.decl_blk()
            if self.pn[0] and self.redecl(v): return self.fail(78)
            if self.curf: self.nloc += 1; self.declare(v, 2, self.npar + self.nloc, cst, blk)
            else:
                if self.dp >= self.db + SDATA: return self.fail(25)
                self.declare(v, 1, self.dp, cst, blk); self.dp += 1
            self.mode = S_VARAFTER; return
        if m == S_VARAFTER:
            j = NS - self.nlet if self.decl_blk() else self.nsym - 1
            if isP(61):
                self.push_cs(C_ASSIGN, j, 0, 1 + self.pn[0]); self.mode = S_OPND; return
            if self.pn[0] == 2: return self.fail(65)
            if self.curf: self.emit('MOV', self.var(j), K(0))      # a local without a value: 0 (no ENTER zeroing here)
            if isP(44): self.mode = S_VAR; return
            if (isP(T_NL) or isP(125)) and self.top_cs()[0] in (C_FORINIT, C_FORSTEP): return None if isP(T_NL) else self.fail(53)
            if isP(125): return self.asi_close(lambda: self.end_simple_stmt('P', T_NL))
            return self.end_simple_stmt(kind, v)
        if m == S_INC:
            if (isP(T_NL) or isP(125)) and self.top_cs()[0] in (C_FORINIT, C_FORSTEP): return None if isP(T_NL) else self.fail(53)
            if isP(125): return self.asi_close(lambda: self.end_simple_stmt('P', T_NL))
            return self.end_simple_stmt(kind, v)
        if m == S_LPAREN:
            if not isP(40): return self.fail(32)
            self.mode = S_STMT if self.top_cs()[0] == C_FORINIT else S_OPND; return
        if m == S_FNAME:
            if kind != 'ID': return self.fail(34)
            k = self.fnfind(v); self.cfn = k; self.deflab(self.fn[k][2], self.here()); self.nfdef += 1
            self.curf = 1; self.nloc = 0; self.npar = 0; self.fsym = self.nsym; self.fcs = self.csp - 1
            le = self.newlab(); self.cs[self.csp - 1][2] = le
            self.mode = S_FPAREN; return
        if m == S_FPAREN:
            if not isP(40): return self.fail(35)
            self.mode = S_FPARAM; return
        if m == S_FPARAM:
            if isP(41): return self.end_params()
            if kind != 'ID': return self.fail(36)
            self.declare(v, 2, PARAM0 + self.npar); self.npar += 1; self.mode = S_FPSEP; return
        if m == S_FPSEP:
            if isP(44): self.mode = S_FPARAM; return
            if isP(41): return self.end_params()
            return self.fail(37)
        if m == S_CONLOG:
            if not isK_('log'): return self.fail(38)
            self.mode = S_CONLP; return
        if m == S_CONLP:
            if not isP(40): return self.fail(39)
            self.push_op(M_PRINT); self.mode = S_CONFIRST; return
        if m == S_CONFIRST:
            if isP(41):
                if self.opv[self.osp - 1] == 2: return self.fail(30)
                self.osp -= 1; self.emit('PUTC', b=K(10)); return self.print_end()
            self.opv[self.osp - 1] = 0
            m = self.mode = S_OPND
        if m in (R.S_DOT, R.S_OKEY, R.S_OCOLON, R.S_SWCASE): return self.fail(NOTSUB)
        if m == S_OPND:
            if kind == 'NUM': self.push_num(v); self.mode = S_OPER; return
            if kind == 'STR':
                if v[0] >= NOROOM: return self.fail(26)
                e = self.intern((v[1], v[2]), v[0], v[3])
                if e < 0: return
                self.push_od(KBIG, 2, e - STRTAG); self.mode = S_OPER; return
            if isK_('true') or isK_('false'): self.push_od(K(int(isK_('true'))), 1); self.mode = S_OPER; return
            if isK_('null'): self.push_od(K(0), 0); self.mode = S_OPER; return
            if isP(123) or isP(91): return self.fail(NOTSUB)
            if isP(40): self.push_op(M_PAREN); return
            if isP(33): self.push_op(NOT); return
            if isP(45): self.push_op(NEG); return
            if isP(7) or isP(8): self.pn = (v, 1); self.mode = S_PREINC; return
            if kind == 'ID': self.pn = v; self.mode = S_NAMEE; return
            if isP(41) and self.top_op()[0] == M_CALL:
                self.osp -= 1; self.call_end(self.opv[self.osp], 0); self.mode = S_OPER; return
            if (isP(59) or isP(T_NL) or isP(125)) and self.top_cs()[0] == C_RETURN and self.osp == 0:
                self.push_od(K(0), 0)
                if isP(125): return self.asi_close(lambda: self.end_expr_stmt('P', T_NL))
                return self.end_expr_stmt(kind, v)
            if isP(T_NL): return
            if isP(59) and self.top_cs()[0] == C_FORCOND and self.osp == 0:
                self.push_od(K(1), 1); return self.end_expr_stmt(kind, v)
            return self.fail(3)
        if m == S_OPER:
            if self.pm == 3:
                self.pm = 0
                if isP(46) or isP(91): return self.fail(48)
            if kind == 'P' and v in BIN:
                op = BIN[v]; self.popops(prec(op))
                t, tv = self.top_op()
                if op == ADD and t == M_PRINT and (tv >= 4 or self.odt[self.nd - 1] == 2):   # "..." + x in console.log: a piece
                    self.opv[self.osp - 1] = tv + 4; self.mode = S_OPND; return
                if op == ADD: self.push_op(M_CADD if t == M_PRINT else ADD, self.odt[self.nd - 1]); self.mode = S_OPND; return
                if prec(op) <= prec(ADD) and t == M_PRINT and tv >= 4: return self.fail(NOTSUB)     # pieces joined: a built string
                if op in (AND, OR):                           # a: tested in its temp; b joins it there (popops)
                    i = self.nd - 1; lt = self.odt[i]; l = self.newlab(); self.to_temp(i); self.snapshot(lambda q: True, i)
                    self.emit('JZ' if op == AND else 'JNZ', b=T(i), label=l)
                    self.push_op(op, l + 64 * lt); self.mode = S_OPND; return
                self.push_op(op, self.odt[self.nd - 1]); self.mode = S_OPND; return
            if isP(63):                                        # c ? a : b
                self.popops(2, 'br'); t, tv = self.top_op()
                if t == M_PRINT and tv >= 4: return self.fail(NOTSUB)
                self.snapshot(lambda q: True, self.nd - 1)
                l = self.newlab(); self.branch(l, False); self.push_op(M_TERN, l + 64 * int(t == M_TELSE)); self.mode = S_OPND; return
            if isP(58):
                self.popops(1); t, tv = self.top_op()
                if t != M_TERN: return self.fail(67)
                self.osp -= 1; i = self.nd - 1; lbt = self.odt[i]; self.to_temp(i); self.nd -= 1
                if tv >= 64:
                    ev = self.opv[self.osp - 1]; self.emit('JMP', label=ev % 64)
                    self.opv[self.osp - 1] = ev % 64 + 64 * tmerge(ev // 64, lbt)
                else:
                    l2 = self.newlab(); self.emit('JMP', label=l2); self.push_op(M_TELSE, l2 + 64 * lbt)
                self.deflab(tv % 64, self.here()); self.mode = S_OPND; return
            if isP(46) or isP(91): return self.fail(NOTSUB)
            if isP(41) or isP(44) or isP(93):
                self.popops(1, self.end_mode(v) if kind == 'P' else None)
                t, tv = self.top_op()
                if isP(93): return self.fail(45)
                if isP(44):
                    if t == M_PRINT: self.print_call(32); self.opv[self.osp - 1] = 2; self.mode = S_CONFIRST; return
                    if t == M_CALL: self.to_temp(self.nd - 1); self.opv[self.osp - 1] += 64
                    if t in (M_CALL, M_PUTC): self.mode = S_OPND; return
                    if self.osp == 0 and self.top_cs()[0] == C_ASSIGN and self.top_cs()[3]: return self.end_expr_stmt(kind, v)
                    return self.fail(44)
                if t == M_PAREN: self.osp -= 1; return
                if t == M_CALL: self.osp -= 1; return self.call_end(tv, 1)
                if t == M_PUTC:
                    self.osp -= 1; self.emit('PUTC', b=self.src(self.nd - 1)); self.nd -= 1; self.push_od(K(0), 0); return
                if t == M_PRINT: self.print_call(10); self.osp -= 1; return self.print_end()
                if self.osp: return self.fail(46)
                return self.end_expr_stmt(kind, v)
            asiok = (not any(self.ops[k] >= 100 for k in range(self.osp)) and self.top_cs()[0] in (C_ASSIGN, C_EXPR, C_RETURN)
                     and not (self.csp >= 2 and self.cs[self.csp - 2][0] in (C_FORINIT, C_FORSTEP)))
            if isP(T_NL) and not asiok: return
            if isP(125) and asiok:
                return self.asi_close(lambda: (self.popops(1, self.dest_ctx()), self.end_expr_stmt('P', T_NL)))
            if isP(59) or isP(T_NL):
                self.popops(1, self.end_mode(59))
                if self.osp: return self.fail(47)
                return self.end_expr_stmt(kind, v)
            return self.fail(48)
        return self.fail(99)

    def end_expr_stmt(self, kind, v):
        isP = lambda c: kind == 'P' and v == c
        t = self.top_cs(); k = t[0]
        if k == C_IFC and isP(41):
            self.pop_cs(); la = self.newlab(); self.branch(la, False); self.push_cs(C_IFB, la); self.mode = S_LBRACE; return
        if k in (C_DOB, C_DOB1) and isP(41):
            self.pop_cs(); self.branch(t[3], True); self.deflab(t[2], self.here()); return self.complete_stmt(0)
        if k == C_WHILEC and isP(41):
            self.pop_cs(); le = self.newlab(); c0 = self.cp; self.branch(le, False); self.push_cs(C_LOOPB, t[1], le); self.mode = S_LBRACE
            if LOOPCOPY and self.lastbr and self.lab[t[1]] == self.cb + 2 * c0:       # the test alone: inverted, back to the body
                lb = self.newlab(); self.deflab(lb, self.here()); op, a, w1, _, na, nw, nl = self.lastbr
                inv = {'JZ': 'JNZ', 'JNZ': 'JZ', **{'J' + NAME[x]: 'J' + NAME[INV[x]] for x in CMPS}}[op]
                self.cs[self.csp - 1].append([(inv, a, w1, lb, na, nw, nl)])
            return
        if k == C_FORCOND and isP(59):                         # t: l1 le lb l2. The test jumps into the body; else out
            self.pop_cs(); c0 = self.cp; self.branch(t[3], True); br = self.lastbr; self.emit('JMP', label=t[2]); self.deflab(t[4], self.here())
            self.push_cs(C_FORSTEP, t[1], t[2], t[3], t[4], e=t[5]); self.mode = S_STMT
            if LOOPCOPY and br and self.lab[t[1]] == self.cb + 2 * c0: self.cs[self.csp - 1].append([br, self.cp])
            return
        if k == C_ASSIGN:
            self.pop_cs(); o = self.var(t[1]); i = self.nd - 1
            if t[2]:                                           # (a snapshot replaced x below e if e changed it)
                if self.odt[i] == 2 or self.odt[i - 1] == 2: return self.fail(NOTSUB)
                self.emit(NAME[t[2]], o, self.src(i - 1), self.src(i)); self.sym[t[1]][4] = 3; self.nd -= 1
            else: self.put(o, i); self.sym[t[1]][4] = self.odt[i]
            self.nd -= 1
            if isP(44) and t[3]: self.pn = (t[3] - 1, 0); self.mode = S_VAR; return
            return self.end_simple_stmt(kind, v)
        if k == C_EXPR:
            self.pop_cs(); self.nd -= 1; self.pcnd = None; return self.end_simple_stmt(kind, v)
        if k == C_RETURN and (isP(59) or isP(T_NL)):
            self.pop_cs(); i = self.nd - 1
            if self.odt[i]: self.fn[self.cfn][3] = self.odt[i]
            self.emit('RET', b=self.src(i)); self.nd -= 1; return self.complete_stmt(0)
        return self.fail(50)

    def end_simple_stmt(self, kind, v):
        isP = lambda c: kind == 'P' and v == c
        t = self.top_cs()
        if t[0] == C_FORINIT:
            if not isP(59): return self.fail(51)
            self.pop_cs(); self.deflab(t[1], self.here()); self.push_cs(C_FORCOND, t[1], t[2], t[3], t[4], e=t[5]); self.mode = S_OPND; return
        if t[0] == C_FORSTEP:
            if not isP(41): return self.fail(52)
            self.pop_cs()
            if len(t) > 6:                                     # the test again, then out; with a one-instruction step, the body
                br, c1 = t[6]; self.emit(*br[:2], w1=br[2], label=br[3]); self.code[self.cp - 1] = br; self.emit('JMP', label=t[2])
                step = [self.code[c1]] if LOOPCOPY > 1 and self.cp - 2 - c1 == 1 else []    # ends with step + test
            else: self.emit('JMP', label=t[1])
            self.deflab(t[3], self.here())
            self.push_cs(C_LOOPB, t[4], t[2], e=t[5]); self.mode = S_LBRACE
            if len(t) > 6 and step: self.cs[self.csp - 1].append(step + [br])
            return
        if not (isP(59) or isP(T_NL)): return self.fail(53)
        self.complete_stmt(0)

    def complete_stmt(self, nonelse, dook=True):
        self.mode = S_STMT
        while self.csp:
            k = self.top_cs()[0]
            if k not in (C_ELSEB1, C_LOOPB1, C_IFB1, C_DOB1) or (k == C_DOB1 and not dook): return
            t = self.pop_cs(); self.nlet = t[5]
            if k == C_DOB1: return self.do_cond(t)
            if k == C_ELSEB1: self.deflab(t[1], self.here())
            elif k == C_LOOPB1: self.loop_end(t); self.deflab(t[2], self.here())
            elif nonelse or self.asic: self.deflab(t[1], self.here())
            else: self.pendLa = t[1]; self.mode = S_ELSE; return

    def loop_end(self, t):
        """a loop body's end: back to the test (t[1]), or (LOOPCOPY) the copied instructions"""
        if len(t) > 6:
            for e in t[6]: self.emit(e[0]); self.code[self.cp - 1] = e
        else: self.emit('JMP', label=t[1])

    def close_block(self):
        if not self.csp: return self.fail(54)
        t = self.pop_cs(); k = t[0]; self.nlet = t[5]
        if k == C_BLOCK: return self.complete_stmt(0)
        if k == C_IFB: self.pendLa = t[1]; self.mode = S_ELSE; return
        if k == C_ELSEB: self.deflab(t[1], self.here()); return self.complete_stmt(0)
        if k == C_DOB: return self.do_cond(t)
        if k == C_LOOPB: self.loop_end(t); self.deflab(t[2], self.here()); return self.complete_stmt(0)
        if k == C_FUNCB:
            self.emit('RET', b=K(0)); self.deflab(t[2], self.nloc); self.deflab(t[1], self.here())
            self.curf = 0; self.nsym = self.fsym; self.mode = S_STMT; return
        return self.fail(55)

    def end_params(self):
        for i in range(self.npar):                           # parameter k sits at fp + 1 + k
            self.sym[self.fsym + i][3] = 1 + i
        f = self.fn[self.cfn]
        if f[4] and f[4] != self.npar + 1: return self.fail(76)
        f[4] = self.npar + 1; self.mode = S_LBRACE

# ---------------- simulator
def run(mem_init, max_steps=10 ** 6, trace=None):
    """the register machine on a RAM image; returns (steps, output). pc starts at code_base, sp = fp = sp0"""
    out_base, cols, rows = LAYOUT['out_base'], LAYOUT['cols'], LAYOUT['rows']
    mem = [0] * 32768
    for a, v in mem_init.items(): mem[a] = v
    s20 = lambda x: (x + (1 << 19)) % (1 << 20) - (1 << 19)
    tdiv = lambda a, b: 0 if b == 0 else int(a / b)
    tmod = lambda a, b: 0 if b == 0 else a - b * int(a / b)
    db, ROMN = LAYOUT['data_base'], LAYOUT['rom_size']
    pc, fp, optr, steps, out = CODE0, LAYOUT['sp0'], 0, 0, []
    def addr(o): return (db + o if o < 256 else fp + o - 256) & 32767
    def val(o): return o - 896 if o >= 768 else mem[addr(o)]
    def wr(a, v):
        if a >= ROMN: mem[a] = s20(v)
    def emit(c):
        nonlocal optr
        if c == 10: optr = (optr // cols + 1) * cols % (cols * rows)
        else: mem[out_base + optr] = c; optr = (optr + 1) % (cols * rows)
        out.append(c)
    ALU = {'ADD': lambda a, b: a + b, 'SUB': lambda a, b: a - b, 'MUL': lambda a, b: a * b, 'DIV': tdiv, 'MOD': tmod,
           'LT': lambda a, b: int(a < b), 'GT': lambda a, b: int(a > b), 'LE': lambda a, b: int(a <= b), 'GE': lambda a, b: int(a >= b),
           'EQ': lambda a, b: int(a == b), 'NE': lambda a, b: int(a != b)}
    while True:
        steps += 1
        if steps > max_steps: raise RuntimeError('step limit')
        w0, w1 = mem[pc], mem[pc + 1]; op = OPN[w0 // 8192]; a = w0 % 8192; b = w1 // 1024 + 512; c = w1 % 1024
        if trace: trace(pc, op, a, b, c, w1)
        pc += 2
        if op in ALU: wr(addr(a), ALU[op](val(b), val(c)))
        elif op == 'MOV': wr(addr(a), val(b))
        elif op == 'NEG': wr(addr(a), -val(b))
        elif op == 'NOT': wr(addr(a), int(not truthy(mem, val(b))))
        elif op == 'LOADK': wr(addr(a), w1)
        elif op == 'JMP': pc = a
        elif op == 'JZ': pc = a if not truthy(mem, val(b)) else pc
        elif op == 'JNZ': pc = a if truthy(mem, val(b)) else pc
        elif op[0] == 'J': pc = a if ALU[op[1:]](val(b), val(c)) else pc
        elif op == 'CALL': wr(fp + w1, w1 * 8192 + pc); fp += w1; pc = a
        elif op == 'RET': r = mem[fp]; wr(fp, val(b)); fp -= r // 8192; pc = r % 8192
        elif op in ('PRINT', 'PRINTK'):
            v = val(b) if op == 'PRINT' else w1; sep = (0, 32, 10)[a // 2]
            if R.isstr(v):
                p = v + STRTAG; text = []
                while p != db + SDATA and mem[p] != 0: text.append(mem[p]); p += 1
            elif a % 2 and v in (0, 1): text = [ord(ch) for ch in ('true' if v else 'false')]
            else: text = [ord(ch) for ch in str(v)]
            for ch in text + ([sep] if sep else []): emit(ch)
        elif op == 'PUTC': emit(val(b))
        elif op == 'HALT': return steps, ''.join(map(chr, out))
        else: raise RuntimeError(f'bad op {op} at {pc - 2}')

def compile_src(src):
    c = Compiler(LAYOUT['data_base'], CODE0)
    words, data = c.compile(src)
    return c, words, data
def image_mem(c, words, data):
    mem = R.image_mem(c, words, data, LAYOUT['init'])
    return mem
def compile_and_run(src, max_steps=10 ** 6):
    c, words, data = compile_src(src)
    if c.err: return c, None
    return c, run(image_mem(c, words, data), max_steps)

def image(src, ram=True):
    """a machine image for the page generator and the pass model (as cc_ref.image with ram=True; no ROM)"""
    La = LAYOUT
    c, words, data = compile_src(src)
    if c.err: raise ValueError(f'compile error {c.err}')
    mem = image_mem(c, words, data); r = run(dict(mem))
    if not ram: mem = {}
    return dict(rom=[], romSize=La['rom_size'], ram=[mem.get(La['rom_size'] + i, 0) for i in range(La['ram_size'])],
                ramSize=La['ram_size'], sp0=La['sp0'], outBase=La['out_base'], rows=La['rows'], cols=La['cols'], source=src,
                codeBase=La['code_base'], init=La['init'], steps=r[0], expected=r[1], isa='reg')

def disasm(words):
    for a in sorted(words)[::2]:
        w0, w1 = words[a], words[a + 1]; op = OPN[w0 // 8192]; A = w0 % 8192; b = w1 // 1024 + 512; c = w1 % 1024
        def o(x): return f'#{x - 896}' if x >= 768 else f'F{x - 256}' if x >= 256 else f'G{x}'
        if op in ('LOADK', 'PRINTK', 'CALL'): args = f'{o(A) if op == "LOADK" else A}, {w1}'
        elif op in ('JMP', 'HALT'): args = f'{A}'
        elif op[0] == 'J': args = f'{A}, {o(b)}' + ('' if op in ('JZ', 'JNZ') else f', {o(c)}')
        elif op in ('MOV', 'NEG', 'NOT'): args = f'{o(A)}, {o(b)}'
        elif op == 'PRINT': args = f'{A}, {o(b)}'
        elif op in ('PUTC', 'RET'): args = o(b)
        else: args = f'{o(A)}, {o(b)}, {o(c)}'
        print(f'{a:5} {op:6} {args}')

if __name__ == '__main__':
    src = open(sys.argv[1]).read()
    c, words, data = compile_src(src)
    print('err', c.err, 'instructions', c.cp, 'max per token', c.maxstep)
    if '-d' in sys.argv: disasm(words)
    if not c.err:
        r = run(image_mem(c, words, data)); print('steps', r[0], 'output:'); print(r[1])
