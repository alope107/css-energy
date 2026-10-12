#!/usr/bin/env python3
"""cc_ref.py — reference for the CSS compiler: a character-at-a-time pushdown transducer for jsc's JS subset.

Written the way the CSS chain will compute it: one step per source character, fixed-size tables and stacks,
no recursion, no lookahead beyond the next character. Each step may complete one token; the parser handles it
(shunting-yard for expressions, a control stack for statements, symbol/function/label tables) and emits a few
code words. Words that need an address not known yet carry a label id; labels are resolved after the last step.

Subset (= jsc.js minus its internal builtins peek/poke/alloc/exec/halt): var, function (params, locals,
recursion, forward calls), if/else/else if, while, for(;;), return, integers, string literals, static array
literals, a[i] read/write, + - * / % < > <= >= == != && || ! unary -, calls, putc(x), console.log(x).
Code generation mirrors jsc.js, so the same program produces the same instruction sequence.
"""
import sys

# opcodes (jsc.js)
NOP, PUSHI, LOADG, STOREG, LOADL, STOREL, LOADI, STOREI, ADD, SUB, MUL, DIV, MOD, LT, GT, LE, GE, EQ, NE, AND, OR, NOT, NEG, \
    JMP, JZ, JNZ, CALL, ENTER, RET, POP, DUP, PUTC, HALT, JMPI, SHL13, INCG, INCL, IDX, IDXL = range(39)

# limits (= the CSS chain's fixed table sizes)
OD, CD, NS, NF, NL, EMAX = 8, 8, 32, 16, 48, 12
SDATA = 256                             # string literals live at data_base + SDATA
H1M, H2M = 65521, 65519

def h1h2(s):
    a = b = 0
    for ch in s: a = (a * 31 + ord(ch)) % H1M; b = (b * 37 + ord(ch)) % H2M
    return a, b
KW = {k: h1h2(k) for k in ['var', 'if', 'else', 'while', 'for', 'return', 'function', 'putc', 'console', 'log']}

# punctuation codes: single chars by ASCII; two-char ops as jsc: == 1, != 2, <= 3, >= 4, && 5, || 6, ++ 7, -- 8
TWO = {(61, 61): 1, (33, 61): 2, (60, 61): 3, (62, 61): 4, (38, 38): 5, (124, 124): 6, (43, 43): 7, (45, 45): 8}
BIN = {42: MUL, 47: DIV, 37: MOD, 43: ADD, 45: SUB, 60: LT, 62: GT, 3: LE, 4: GE, 1: EQ, 2: NE, 5: AND, 6: OR}
def prec(code):
    return {MUL: 6, DIV: 6, MOD: 6, ADD: 5, SUB: 5, LT: 4, GT: 4, LE: 4, GE: 4, EQ: 3, NE: 3, AND: 2, OR: 1, NOT: 7, NEG: 7}.get(code, 0)

# OPS markers (codes >= 100)
M_PAREN, M_CALL, M_IDXG, M_IDXL, M_PUTC, M_PRINT, M_PUTS, M_IDXA = 100, 101, 102, 103, 104, 105, 106, 107
# control stack kinds
C_BLOCK, C_IFB, C_ELSEB, C_ELSEIF, C_WHILEB, C_FUNCB, C_FORB = 1, 2, 3, 4, 5, 6, 7
C_IFC, C_WHILEC, C_FORINIT, C_FORCOND, C_FORSTEP, C_ASSIGN, C_EXPR, C_RETURN, C_IDXA = 10, 11, 12, 13, 14, 15, 16, 17, 18
# parser modes
(S_STMT, S_OPND, S_OPER, S_NAMES, S_NAMEE, S_VAR, S_VARAFTER, S_LPAREN, S_LBRACE, S_ELSE, S_FNAME, S_FPAREN, S_FPARAM,
 S_FPSEP, S_CONDOT, S_CONLOG, S_CONLP, S_CONFIRST, S_ARR, S_ARRSEP, S_ARRNEG, S_INC, S_IDXEQ, S_AFTERELSE, S_ERR) = range(25)

class Compiler:
    def __init__(self, data_base, code_base, print_fn, puts_fn):
        self.db, self.cb, self.print_fn, self.puts_fn = data_base, code_base, print_fn, puts_fn
        # lexer
        self.lx = 0; self.tkc = 0; self.acc = 0; self.h1 = 0; self.h2 = 0; self.p2 = 0; self.sstart = 0
        self.dp = data_base                 # globals and array literals (parser)
        self.sdp = data_base + SDATA        # string literals (lexer)
        # parser
        self.mode = S_STMT; self.pn = (0, 0)
        self.ops = [0] * OD; self.opv = [0] * OD; self.osp = 0
        self.cs = [[0] * 5 for _ in range(CD)]; self.csp = 0
        self.sym = [[0, 0, 0, 0] for _ in range(NS)]; self.nsym = 0            # h1 h2 kind(1 g, 2 l) addr
        self.fn = [[0, 0, 0] for _ in range(NF)]; self.nfn = 0                 # h1 h2 label
        self.lab = [-1] * NL; self.nlab = 0
        self.cp = 0; self.curf = 0; self.nloc = 0; self.npar = 0; self.fsym = 0    # fsym: nsym at function start
        self.pendLa = 0; self.err = 0; self.neg = 0; self.arrstart = 0
        self.code = {}; self.data = {}
        self.emitted = []

    # ---------------- helpers
    def emit(self, op, imm=0, label=None):
        self.code[self.cp] = (op, imm, label); self.emitted.append((self.cp, op, imm, label)); self.cp += 1
    def newlab(self):
        if self.nlab >= NL: self.fail(20)
        self.nlab += 1; return self.nlab - 1
    def deflab(self, l, v): self.lab[l] = v
    def here(self): return self.cb + self.cp
    def fail(self, code):
        if not self.err: self.err = code
    def push_cs(self, *f):
        if self.csp >= CD: self.fail(21); return
        e = list(f) + [0] * (5 - len(f)); self.cs[self.csp] = e; self.csp += 1
    def top_cs(self): return self.cs[self.csp - 1] if self.csp else [0] * 5
    def pop_cs(self):
        self.csp -= 1; return self.cs[self.csp]
    def push_op(self, code, val=0):
        if self.osp >= OD: self.fail(22); return
        self.ops[self.osp] = code; self.opv[self.osp] = val; self.osp += 1
    def lookup(self, h):
        for j in range(self.nsym - 1, -1, -1):
            if (self.sym[j][0], self.sym[j][1]) == h: return j
        return -1
    def fnlab(self, h):
        for k in range(self.nfn):
            if (self.fn[k][0], self.fn[k][1]) == h: return self.fn[k][2]
        if self.nfn >= NF: self.fail(23); return 0
        l = self.newlab(); self.fn[self.nfn] = [h[0], h[1], l]; self.nfn += 1
        return l
    def declare(self, h, kind, addr):
        if self.nsym >= NS: self.fail(24); return
        self.sym[self.nsym] = [h[0], h[1], kind, addr]; self.nsym += 1
    def load(self, j):
        k, a = self.sym[j][2], self.sym[j][3]
        self.emit(LOADL if k == 2 else LOADG, a % 8192)
    def store(self, j):
        k, a = self.sym[j][2], self.sym[j][3]
        self.emit(STOREL if k == 2 else STOREG, a % 8192)
    def popops(self, minprec):
        """shunting-yard: pop and emit operators with precedence >= minprec (stops at markers)."""
        while self.osp and 0 < prec(self.ops[self.osp - 1]) and prec(self.ops[self.osp - 1]) >= minprec:
            self.osp -= 1; self.emit(self.ops[self.osp])

    # ---------------- lexer: one character -> at most one token
    def char(self, c, cn):
        tok = None
        isal = lambda x: 65 <= x <= 90 or 97 <= x <= 122 or x in (95, 36)
        isdg = lambda x: 48 <= x <= 57
        if self.lx == 1:                                  # in a string
            if c == 34: self.data[self.sdp] = 0; self.sdp += 1; self.lx = 0; tok = ('STR', self.sstart)
            elif c == 92: self.lx = 3
            else: self.data[self.sdp] = c; self.sdp += 1
        elif self.lx == 3:
            self.data[self.sdp] = 10 if c == 110 else c; self.sdp += 1; self.lx = 1
        elif self.lx == 2:
            if c == 10: self.lx = 0
        elif self.p2:
            tok = ('P', self.p2); self.p2 = 0
        elif c == 0: tok = ('EOF', 0)
        elif c in (9, 10, 13, 32): pass
        elif c == 47 and cn == 47: self.lx = 2
        elif c == 34: self.lx = 1; self.sstart = self.sdp
        elif isal(c) or (isdg(c) and self.tkc == 1):
            if self.tkc != 1: self.h1 = self.h2 = 0
            self.h1 = (self.h1 * 31 + c) % H1M; self.h2 = (self.h2 * 37 + c) % H2M; self.tkc = 1
            if not (isal(cn) or isdg(cn)): tok = ('ID', (self.h1, self.h2)); self.tkc = 0
        elif isdg(c):
            self.acc = (self.acc * 10 if self.tkc == 2 else 0) + c - 48; self.tkc = 2
            if not isdg(cn): tok = ('NUM', self.acc); self.tkc = 0
        elif (c, cn) in TWO: self.p2 = TWO[(c, cn)]
        else: tok = ('P', c)
        if tok:
            cp0 = self.cp; self.token(*tok)
            if self.cp - cp0 > EMAX: self.fail(61)

    # ---------------- parser: one token
    def token(self, kind, v):
        if self.err: return
        isP = lambda c: kind == 'P' and v == c
        isK = lambda k: kind == 'ID' and v == KW[k]
        m = self.mode
        # ---- pending NAME (statement start): decide what it was
        if m == S_NAMES:
            h = self.pn
            if isP(61):                                   # NAME = e
                j = self.lookup(h)
                if j < 0: return self.fail(5)
                self.push_cs(C_ASSIGN, j); self.mode = S_OPND; return
            if isP(7) or isP(8):                          # NAME++ / NAME--
                j = self.lookup(h)
                if j < 0: return self.fail(6)
                k, a = self.sym[j][2], self.sym[j][3]
                if isP(7): self.emit(INCL if k == 2 else INCG, a % 8192)
                else: self.load(j); self.emit(PUSHI, 1); self.emit(SUB); self.store(j)
                self.mode = S_INC; return
            if isP(91):                                   # NAME[e] = e
                j = self.lookup(h)
                if j < 0: return self.fail(7)
                self.load(j); self.push_cs(C_IDXA); self.push_op(M_IDXA); self.mode = S_OPND; return
            # anything else: an expression statement starting with NAME
            self.push_cs(C_EXPR); m = self.mode = S_NAMEE
        if m == S_NAMEE:
            h = self.pn
            if h == KW['console']:
                if not isP(46): return self.fail(30)
                self.mode = S_CONLOG; return
            if isP(40):
                if h == KW['putc']: self.push_op(M_PUTC)
                else: self.push_op(M_CALL, self.fnlab(h))
                self.mode = S_OPND; return
            j = self.lookup(h)
            if j < 0: return self.fail(4)
            if isP(91):
                k, a = self.sym[j][2], self.sym[j][3]
                self.push_op(M_IDXL if k == 2 else M_IDXG, a % 8192); self.mode = S_OPND; return
            self.load(j); m = self.mode = S_OPER                 # fall through: this token follows an operand
        # ---- after an if body: else?
        if m == S_ELSE:
            if isK('else'):
                lb = self.newlab(); self.emit(JMP, 0, lb); self.deflab(self.pendLa, self.here())
                self.push_cs(C_ELSEIF, lb); self.mode = S_AFTERELSE; return
            self.deflab(self.pendLa, self.here()); self.complete_stmt(); m = self.mode = S_STMT
        if m == S_AFTERELSE:
            top = self.pop_cs()                                # the C_ELSEIF just pushed
            if isK('if'):
                self.push_cs(C_ELSEIF, top[1]); self.push_cs(C_IFC); self.mode = S_LPAREN; return
            if isP(123): self.push_cs(C_ELSEB, top[1]); self.mode = S_STMT; return
            return self.fail(31)
        # ---- statements
        if m == S_STMT:
            if kind == 'EOF':
                if self.csp: return self.fail(40)
                self.emit(HALT); return
            if isP(123): self.push_cs(C_BLOCK); return
            if isP(125): return self.close_block()
            if isP(59): return
            if kind != 'ID': return self.fail(8)
            if isK('var'): self.mode = S_VAR; return
            if isK('if'): self.push_cs(C_IFC); self.mode = S_LPAREN; return
            if isK('while'):
                lh = self.newlab(); self.deflab(lh, self.here()); self.push_cs(C_WHILEC, lh); self.mode = S_LPAREN; return
            if isK('for'):
                l1, le, lb, l2 = self.newlab(), self.newlab(), self.newlab(), self.newlab()
                self.push_cs(C_FORINIT, l1, le, lb, l2); self.mode = S_LPAREN; return
            if isK('return'):
                self.push_cs(C_RETURN); self.mode = S_OPND; return
            if isK('function'):
                if self.curf: return self.fail(41)
                lo = self.newlab(); self.emit(JMP, 0, lo); self.mode = S_FNAME
                self.push_cs(C_FUNCB, lo); return
            self.pn = v; self.mode = S_NAMES; return
        if m == S_VAR:
            if kind != 'ID': return self.fail(9)
            if self.curf: self.nloc += 1; self.declare(v, 2, self.nloc)
            else: self.declare(v, 1, self.dp); self.dp += 1
            self.mode = S_VARAFTER; return
        if m == S_VARAFTER:
            if isP(61): self.push_cs(C_ASSIGN, self.nsym - 1); self.mode = S_OPND; return
            return self.end_simple_stmt(kind, v)
        if m == S_INC:
            return self.end_simple_stmt(kind, v)
        if m == S_LPAREN:
            if not isP(40): return self.fail(32)
            t = self.top_cs()[0]
            if t == C_FORINIT:
                self.mode = S_STMT; return                  # the init statement (or ';')
            self.mode = S_OPND; return
        if m == S_LBRACE:
            if not isP(123): return self.fail(33)
            self.mode = S_STMT; return
        if m == S_FNAME:
            if kind != 'ID': return self.fail(34)
            l = self.fnlab(v); self.deflab(l, self.here())
            self.curf = 1; self.nloc = 0; self.npar = 0; self.fsym = self.nsym
            le = self.newlab(); self.cs[self.csp - 1][2] = le
            self.mode = S_FPAREN; return
        if m == S_FPAREN:
            if not isP(40): return self.fail(35)
            self.mode = S_FPARAM; return
        if m == S_FPARAM:
            if isP(41): return self.end_params()
            if kind != 'ID': return self.fail(36)
            self.declare(v, 2, self.npar); self.npar += 1; self.mode = S_FPSEP; return
        if m == S_FPSEP:
            if isP(44): self.mode = S_FPARAM; return
            if isP(41): return self.end_params()
            return self.fail(37)
        if m == S_CONLOG:
            if not isK('log'): return self.fail(38)
            self.mode = S_CONLP; return
        if m == S_CONLP:
            if not isP(40): return self.fail(39)
            self.mode = S_CONFIRST; return
        if m == S_CONFIRST:
            self.push_op(M_PUTS if kind == 'STR' else M_PRINT)
            m = self.mode = S_OPND
        if m == S_ARR:                                       # [n, -n, ...]
            if isP(93): return self.end_array()
            if isP(45): self.neg = 1; self.mode = S_ARRNEG; return
            if kind != 'NUM': return self.fail(42)
            self.data[self.dp] = v; self.dp += 1; self.mode = S_ARRSEP; return
        if m == S_ARRNEG:
            if kind != 'NUM': return self.fail(42)
            self.data[self.dp] = -v; self.dp += 1; self.neg = 0; self.mode = S_ARRSEP; return
        if m == S_ARRSEP:
            if isP(44): self.mode = S_ARR; return
            if isP(93): return self.end_array()
            return self.fail(43)
        # ---- expressions
        if m == S_OPND:
            if kind == 'NUM':
                if v < 8192: self.emit(PUSHI, v)
                else: self.emit(PUSHI, v // 8192); self.emit(SHL13); self.emit(PUSHI, v % 8192); self.emit(ADD)
                self.mode = S_OPER; return
            if kind == 'STR': self.emit(PUSHI, v); self.mode = S_OPER; return
            if isP(40): self.push_op(M_PAREN); return
            if isP(33): self.push_op(NOT); return
            if isP(45): self.push_op(NEG); return
            if isP(91): self.arrstart = self.dp; self.mode = S_ARR; return
            if kind == 'ID': self.pn = v; self.mode = S_NAMEE; return
            if isP(41) and self.osp and self.ops[self.osp - 1] == M_CALL:      # f()
                self.osp -= 1; self.emit(CALL, 0, self.opv[self.osp]); self.mode = S_OPER; return
            if isP(59) and self.top_cs()[0] == C_RETURN and self.osp == 0:     # return;
                self.emit(PUSHI, 0); return self.end_expr_stmt(kind, v)
            if isP(59) and self.top_cs()[0] == C_FORCOND and self.osp == 0:    # for (; ; )
                self.emit(PUSHI, 1); return self.end_expr_stmt(kind, v)
            return self.fail(3)
        if m == S_OPER:
            if kind == 'P' and v in BIN:
                op = BIN[v]; self.popops(prec(op)); self.push_op(op); self.mode = S_OPND; return
            if isP(41) or isP(44) or isP(93):
                self.popops(1)
                t = self.ops[self.osp - 1] if self.osp else 0
                if isP(44):
                    if t not in (M_CALL, M_PUTC, M_PRINT, M_PUTS): return self.fail(44)
                    self.mode = S_OPND; return
                if isP(93):
                    if t in (M_IDXG, M_IDXL): self.osp -= 1; self.emit(IDXL if t == M_IDXL else IDX, self.opv[self.osp]); return
                    if t == M_IDXA: self.osp -= 1; self.emit(ADD); self.mode = S_IDXEQ; return
                    return self.fail(45)
                if t == M_PAREN: self.osp -= 1; return
                if t == M_CALL: self.osp -= 1; self.emit(CALL, 0, self.opv[self.osp]); return
                if t == M_PUTC: self.osp -= 1; self.emit(PUTC); self.emit(PUSHI, 0); return
                if t == M_PRINT: self.osp -= 1; self.emit(CALL, self.print_fn); return
                if t == M_PUTS: self.osp -= 1; self.emit(CALL, self.puts_fn); return
                if self.osp: return self.fail(46)
                return self.end_expr_stmt(kind, v)             # ')' closing a statement-level paren
            if isP(59):
                self.popops(1)
                if self.osp: return self.fail(47)
                return self.end_expr_stmt(kind, v)
            return self.fail(48)
        if m == S_IDXEQ:
            if not isP(61): return self.fail(49)
            self.mode = S_OPND; return
        return self.fail(99)

    # ---- an expression ended at statement level (';' or ')'): what was it for?
    def end_expr_stmt(self, kind, v):
        isP = lambda c: kind == 'P' and v == c
        t = self.top_cs()
        k = t[0]
        if k == C_IFC and isP(41):
            self.pop_cs(); la = self.newlab(); self.emit(JZ, 0, la); self.push_cs(C_IFB, la); self.mode = S_LBRACE; return
        if k == C_WHILEC and isP(41):
            self.pop_cs(); le = self.newlab(); self.emit(JZ, 0, le); self.push_cs(C_WHILEB, t[1], le); self.mode = S_LBRACE; return
        if k == C_FORCOND and isP(59):
            self.pop_cs()                                      # t: l1 le lb l2
            self.emit(JZ, 0, t[2]); self.emit(JMP, 0, t[3]); self.deflab(t[4], self.here())
            self.push_cs(C_FORSTEP, t[1], t[2], t[3], t[4]); self.mode = S_STMT; return
        if k == C_ASSIGN:
            self.pop_cs(); self.store(t[1])
            return self.end_simple_stmt(kind, v)
        if k == C_IDXA:
            self.pop_cs(); self.emit(STOREI); return self.end_simple_stmt(kind, v)
        if k == C_EXPR:
            self.pop_cs(); self.emit(POP); return self.end_simple_stmt(kind, v)
        if k == C_RETURN and isP(59):
            self.pop_cs(); self.emit(RET, self.npar); self.complete_stmt(); self.mode = S_STMT; return
        return self.fail(50)

    # ---- a simple statement's terminator: ';' normally, ';' after a for init, ')' after a for step
    def end_simple_stmt(self, kind, v):
        isP = lambda c: kind == 'P' and v == c
        t = self.top_cs()
        if t[0] == C_FORINIT:
            if not isP(59): return self.fail(51)
            self.pop_cs(); self.deflab(t[1], self.here()); self.push_cs(C_FORCOND, t[1], t[2], t[3], t[4]); self.mode = S_OPND; return
        if t[0] == C_FORSTEP:
            if not isP(41): return self.fail(52)
            self.pop_cs(); self.emit(JMP, 0, t[1]); self.deflab(t[3], self.here())
            self.push_cs(C_FORB, t[2], t[4]); self.mode = S_LBRACE; return
        if not isP(59): return self.fail(53)
        self.complete_stmt(); self.mode = S_STMT

    def complete_stmt(self):
        """a statement finished: close any 'else if' wrappers it was the body of."""
        while self.csp and self.top_cs()[0] == C_ELSEIF:
            t = self.pop_cs(); self.deflab(t[1], self.here())

    def close_block(self):
        if not self.csp: return self.fail(54)
        t = self.pop_cs(); k = t[0]
        if k == C_BLOCK: self.complete_stmt(); self.mode = S_STMT; return
        if k == C_IFB: self.pendLa = t[1]; self.mode = S_ELSE; return
        if k == C_ELSEB: self.deflab(t[1], self.here()); self.complete_stmt(); self.mode = S_STMT; return
        if k == C_WHILEB: self.emit(JMP, 0, t[1]); self.deflab(t[2], self.here()); self.complete_stmt(); self.mode = S_STMT; return
        if k == C_FORB: self.emit(JMP, 0, t[2]); self.deflab(t[1], self.here()); self.complete_stmt(); self.mode = S_STMT; return
        if k == C_FUNCB:
            self.emit(PUSHI, 0); self.emit(RET, self.npar); self.deflab(t[2], self.nloc); self.deflab(t[1], self.here())
            self.curf = 0; self.nsym = self.fsym; self.mode = S_STMT; return
        return self.fail(55)

    def end_params(self):
        for i in range(self.npar):                           # param k of n sits at fp - 1 - n + k
            self.sym[self.fsym + i][3] = -1 - self.npar + i
        self.emit(ENTER, 0, self.cs[self.csp - 1][2]); self.mode = S_LBRACE

    def end_array(self):
        self.emit(PUSHI, self.arrstart); self.mode = S_OPER

    # ---------------- whole program
    def compile(self, src):
        s = [ord(ch) for ch in src] + [0]
        for i in range(len(s)):
            self.char(s[i], s[i + 1] if i + 1 < len(s) else 0)
        if self.mode == S_ELSE: pass
        return self.link()

    def link(self):
        words = {}
        for a, (op, imm, lab) in self.code.items():
            if lab is not None:
                if self.lab[lab] < 0: self.fail(60); imm = 0
                else: imm = self.lab[lab] % 8192
            words[self.cb + a] = op * 8192 + imm
        return words, dict(self.data)

# ---------------- simulator (= build.js run())
def run(rom, mem_init, sp0, out_base=7040, cols=8, rows=16, max_steps=10 ** 6):
    mem = [0] * 8192
    for i, w in enumerate(rom): mem[i] = w
    for a, v in mem_init.items(): mem[a] = v
    pc, sp, fp, optr, steps, out = 0, sp0, sp0, 0, 0, []
    tdiv = lambda a, b: 0 if b == 0 else int(a / b)
    tmod = lambda a, b: 0 if b == 0 else a - b * int(a / b)
    while True:
        steps += 1
        if steps > max_steps: raise RuntimeError('step limit')
        w = mem[pc]; op, imm = w // 8192, w % 8192; simm = imm - 8192 if imm >= 4096 else imm; pc += 1
        if op == 0: pass
        elif op == 1: mem[sp] = imm; sp += 1
        elif op == 2: mem[sp] = mem[imm]; sp += 1
        elif op == 3: sp -= 1; mem[imm] = mem[sp]
        elif op == 4: mem[sp] = mem[fp + simm]; sp += 1
        elif op == 5: sp -= 1; mem[fp + simm] = mem[sp]
        elif op == 6: a = mem[sp - 1]; mem[sp - 1] = mem[a]
        elif op == 7: sp -= 1; b = mem[sp]; sp -= 1; a = mem[sp]; mem[a] = b
        elif 8 <= op <= 20:
            sp -= 1; b = mem[sp]; a = mem[sp - 1]
            mem[sp - 1] = [a + b, a - b, a * b, tdiv(a, b), tmod(a, b), int(a < b), int(a > b), int(a <= b), int(a >= b), int(a == b), int(a != b),
                           int(a != 0 and b != 0), int(a != 0 or b != 0)][op - 8]
        elif op == 21: mem[sp - 1] = int(mem[sp - 1] == 0)
        elif op == 22: mem[sp - 1] = -mem[sp - 1]
        elif op == 23: pc = imm
        elif op == 24:
            sp -= 1
            if mem[sp] == 0: pc = imm
        elif op == 25:
            sp -= 1
            if mem[sp] != 0: pc = imm
        elif op == 26: mem[sp] = pc; sp += 1; pc = imm
        elif op == 27: mem[sp] = fp; fp = sp; sp = sp + 1 + imm
        elif op == 28:
            v = mem[sp - 1]; oldfp = mem[fp]; ret = mem[fp - 1]; nsp = fp - 1 - imm; mem[nsp] = v; sp = nsp + 1; fp = oldfp; pc = ret
        elif op == 29: sp -= 1
        elif op == 30: mem[sp] = mem[sp - 1]; sp += 1
        elif op == 31:
            sp -= 1; c = mem[sp]
            if c == 10: optr = (optr // cols + 1) * cols % (cols * rows)
            else: mem[out_base + optr] = c; optr = (optr + 1) % (cols * rows)
            out.append(c)
        elif op == 32: return steps, ''.join(map(chr, out))
        elif op == 33: sp -= 1; pc = mem[sp]
        elif op == 34: mem[sp - 1] = mem[sp - 1] * 8192
        elif op == 35: mem[imm] += 1
        elif op == 36: mem[fp + simm] += 1
        elif op == 37: mem[sp - 1] = mem[mem[imm] + mem[sp - 1]]
        elif op == 38: mem[sp - 1] = mem[mem[fp + simm] + mem[sp - 1]]
        else: raise RuntimeError(f'bad op {op} at {pc - 1}')

LAYOUT = dict(data_base=4096, code_base=4608, sp0=5632)

def image_mem(c, words, data, init=5120):
    """RAM as the CSS compiler leaves it: code words; strings in place; initialised globals/arrays staged at
    init (the lib's startup copies them into the data area), their count at init - 1"""
    mem = dict(words)
    sbase = c.db + SDATA
    for a, v in data.items():
        if a >= sbase: mem[a] = v
        else: mem[init + a - c.db] = v
    mem[init - 1] = c.dp - c.db
    return mem

def compile_and_run(src, lib):
    c = Compiler(LAYOUT['data_base'], LAYOUT['code_base'], lib['print'], lib['puts'])
    words, data = c.compile(src)
    if c.err: return c, None
    mem = image_mem(c, words, data, lib.get('init', 5120)) if 'init' in lib else dict(data, **{a: w for a, w in words.items()})
    return c, run(lib['rom'], mem, LAYOUT['sp0'])

if __name__ == '__main__':
    import json
    lib = json.load(open('lib.json'))
    src = open(sys.argv[1]).read()
    c, r = compile_and_run(src, lib)
    print('err', c.err, 'code words', c.cp, 'data words', c.dp - LAYOUT['data_base'], 'labels', c.nlab, 'max emit/char', 'n/a')
    if r: print('steps', r[0], 'output:'); print(r[1])
