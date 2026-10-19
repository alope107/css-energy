#!/usr/bin/env python3
"""cc_ref.py — reference for the CSS compiler: a character-at-a-time pushdown transducer for a JS subset.

Written the way the CSS chain will compute it: one step per source character, fixed-size tables and stacks,
no recursion, no lookahead beyond the next character. Each step may complete one token; the parser handles it
(shunting-yard for expressions, a control stack for statements, symbol/function/label tables) and emits a few
code words. Words that need an address not known yet carry a label id; labels are resolved after the last step.

Subset: var/let/const (also `var a = 1, b = 2`), function (params, locals, recursion, forward calls),
if/else/else if, while, do-while, for(;;), switch/case/default, break, continue, return; bodies with or without braces;
integers, true/false, string literals ("..." or '...', escapes \\n \\t \\r \\\\ \\" \\'), static array literals (with .length),
a[i] read/write; + - * / % < > <= >= == != === !== && || (short-circuit, JS value semantics) ?: ! unary -; = += -= *= /= %=
++ -- (also on a[i]) as statements; x++ x-- ++x --x also in expressions; calls; putc(x); console.log(a, b, ...), where + at the top
level of an argument concatenates when an operand is a string ("n = " + n, s + "!"); // and /* */ comments;
statements end with ';', or a newline / '}' where JavaScript would insert one. Objects: literals {a: 1, "b": 2, 3: x},
o.x and x[k] reads, o.x / x[k] assignment statements (=, op=, ++, --), null; strings are interned (see OBJTAG below).

Strings cannot be built: + on a string anywhere but the top level of a console.log argument is a compile error
(when the compiler knows the operand is a string). Inside console.log, + whose operands are known strings prints
the pieces in turn; + whose operand types are unknown calls the lib's addc, which adds numbers, or prints both
pieces and returns a marker that print skips.

Values: integers; a string is a tagged pointer (address - STRTAG), so console.log can tell it from a number at
run time; booleans are 0/1. Values are also typed statically: the compiler tracks the type of the last value it
emitted (lb: 0 unknown, 1 boolean, 2 string, 3 number) -- comparisons, !, true/false, string literals, number
literals and arithmetic, variables by their last assignment, functions by their returns -- and calls the lib's
printBool, puts or printNum (also for an unknown type: printNum checks for a string among negative values, so a
wrong guess costs nothing for non-negative numbers and still prints correctly). The last argument calls the ...Ln entry (prints a newline); others
are followed by PUSHI 32 PUTC.
"""
import sys, json, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'net'))
from device import Device

# the memory map (compiler/layout.json): ROM 0..rom_size-1 (the lib); RAM from rom_size = data_base; see layout.json's _doc
LAYOUT = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'layout.json')))
LAYOUT['out_base'] = LAYOUT['rom_size'] + LAYOUT['ram_size'] - LAYOUT['cols'] * LAYOUT['rows']
assert LAYOUT['data_base'] == LAYOUT['rom_size'], 'RAM index = address - rom_size = address - data_base (the compile chain relies on it)'
AMASK = 32767                           # addresses are 15-bit (the font's address registers: 4 hex digits, the top one 3 bits)

# opcodes (jsc.js)
NOP, PUSHI, LOADG, STOREG, LOADL, STOREL, LOADI, STOREI, ADD, SUB, MUL, DIV, MOD, LT, GT, LE, GE, EQ, NE, AND, OR, NOT, NEG, \
    JMP, JZ, JNZ, CALL, ENTER, RET, POP, DUP, PUTC, HALT, JMPI, SHL13, INCG, INCL, IDX, IDXL, \
    PRINT, PRINTB, PRINTSP, PRINTBSP, PRINTLN, PRINTBLN, SCANI, SCAN, LDF, PUTV, NEW, SETF, ENDK, OVER, JNEG, NET = range(55)
# NET (machine/uarch.py): pop a word, push the network gateway's answer (net/device.py); the lib's fetch / read are made of it
# PRINT family (serviced by CSS on the page, machine/uarch.py in the model): pop a value and print it. A tagged string pointer
# prints its bytes, anything else prints in decimal; the B forms print 0 / 1 as false / true (the static type says
# boolean). SP / LN add a space / newline. PRINT_OP[sep] + (type == boolean) is the opcode.
PRINT_OP = {0: PRINT, 32: PRINTSP, 10: PRINTLN}
PRINT_SEP = {PRINT: 0, PRINTB: 0, PRINTSP: 32, PRINTBSP: 32, PRINTLN: 10, PRINTBLN: 10}

# limits (= the CSS chain's fixed table sizes)
OD, CD, NS, NF, NL, EMAX, NI = 8, 8, 32, 16, 64, 12, 16      # NI: interned strings and property names
SDATA = 256                             # string literals live at data_base + SDATA; data_base itself holds STRTAG (for the lib)
STRTAG = 262144                         # a string value is its address - STRTAG (machine words are 20-bit signed)
# objects (machine/uarch.py has the instructions, compiler/rtlib.py the ROM routines): an object is an 8-word chunk of pairs in the
# heap, its value the chunk's address - OBJTAG. A property key is stored as its value + STRTAG: a string key becomes its address.
# String literals and property names are interned (a table of NI by content hash), so equal strings are one value and o.x,
# o["x"] and o[s] with s = "x" find the same key. o.x is SCANI x then LDF 1 (or PUTV x to store); x[k] calls the ROM's GETX /
# SETX, which also index arrays (an array is an address, an object negative), except for a name whose static type is number
# (an array literal), indexed as before.
OBJTAG = LAYOUT['objtag']
HEAP0 = LAYOUT['heap_lo']
HP, GCLIM, GCSP, KEYCELL, RETCELL = range(LAYOUT['rt_base'], LAYOUT['rt_base'] + 5)       # = machine/uarch.py
GCVEC, PUTVEC = LAYOUT['vec_base'], LAYOUT['vec_base'] + 1
H1M, H2M = 65521, 65519

def h1h2(s):
    a = b = 0
    for ch in s: a = (a * 31 + ord(ch)) % H1M; b = (b * 37 + ord(ch)) % H2M
    return a, b
KW = {k: h1h2(k) for k in ['var', 'let', 'const', 'if', 'else', 'while', 'for', 'return', 'function', 'putc', 'fetch', 'read', 'console', 'log',
                           'true', 'false', 'break', 'continue', 'do', 'null', 'switch', 'case', 'default', 'length']}

# punctuation codes: single chars by ASCII; two-char ops: == 1, != 2, <= 3, >= 4, && 5, || 6, ++ 7, -- 8,
# += 9, -= 10, *= 11, /= 12, %= 13 (=== and !== lex as == and !=); NL 14: a newline after a token that can end a
# statement (identifier, number, string, ) ] } ++ --), for automatic semicolon insertion. (After a block's '}' the parser
# is in a mode that ignores it; after an object literal's it ends the statement.)
TWO = {(61, 61): 1, (33, 61): 2, (60, 61): 3, (62, 61): 4, (38, 38): 5, (124, 124): 6, (43, 43): 7, (45, 45): 8,
       (43, 61): 9, (45, 61): 10, (42, 61): 11, (47, 61): 12, (37, 61): 13}
BIN = {42: MUL, 47: DIV, 37: MOD, 43: ADD, 45: SUB, 60: LT, 62: GT, 3: LE, 4: GE, 1: EQ, 2: NE, 5: AND, 6: OR}
T_NL = 14
# Semicolon insertion. A newline after a token that can end a statement (lt) is pending (pnl) until the next significant
# character, which the lexer sees as the lookahead cn of the blank or comment end before it: a line starting with one of
# CONT continues the statement or ends it by itself (no T_NL: ';' and '}' end it without one), any other starts a new one (T_NL). '+' '-' (++x / --x start a statement, x + y
# continues) and '/' (a comment or a division) are decided on the character itself. After return (lt 2, JavaScript's
# restricted production) the newline always ends the statement. A newline inside a /* */ comment counts.
CONT = (46, 91, 40, 63, 58, 44, 41, 93, 42, 37, 60, 62, 38, 124, 61, 59, 125)    # . [ ( ? : , ) ] * % < > & | = ; }
BLANK = (9, 10, 13, 32)
COMPOUND = {9: ADD, 10: SUB, 11: MUL, 12: DIV, 13: MOD}
ESC = {110: 10, 116: 9, 114: 13}
BOOLOPS = (LT, GT, LE, GE, EQ, NE, NOT)
NUMOPS = (PUSHI, ADD, SUB, MUL, DIV, MOD, NEG, SHL13)
def prec(code):
    return {MUL: 7, DIV: 7, MOD: 7, ADD: 6, M_CADD: 6, SUB: 6, LT: 5, GT: 5, LE: 5, GE: 5, EQ: 4, NE: 4, AND: 3, OR: 2, M_TELSE: 1,
            NOT: 8, NEG: 8}.get(code, 0)

# + at the top level of a console.log argument (value: the left operand's static type); precedence of +
M_CADD = 50
# c ? a : b is  c JZ L1  a JMP L2  L1: b  L2:. '?' pushes the marker M_TERN (value L1 + 64 * reuse); ':' replaces it with
# the operator M_TELSE (value L2 + 64 * the then-branch's static type), lowest precedence, whose pop defines L2. In a
# chain a ? x : b ? y : z the inner ternary reuses the outer L2 (reuse: M_TELSE was on top at '?'), so at most one
# M_TELSE sits between markers and popops defines at most one L2.
M_TELSE = 51
# OPS markers (codes >= 100)
M_PAREN, M_CALL, M_IDXG, M_IDXL, M_PUTC, M_PRINT, M_IDXA, M_TERN = 100, 101, 102, 103, 104, 105, 107, 108
# builtins (M_PUTC's value): putc(c) is PUTC, then 0 as its value; fetch(url) and read() call the lib (net/device.py)
B_PUTC, B_FETCH, B_READ = 0, 1, 2
BUILTIN = {KW['putc']: B_PUTC, KW['fetch']: B_FETCH, KW['read']: B_READ}
# object literal: NEW, then its first pairs (string keys) stored in place (SETF) and the keys ended there (ENDK), the rest the
# general way, as o.x = v / o[n] = v. M_OBJ (value: the pairs stored in place + 4 once the keys are ended), and above it while
# a value is parsed M_OKEY (value: 0 a SETF pair, 1 a number key (SETX), else the key for PUTV); x[k] on a value: M_INDEX
M_OBJ, M_OKEY, M_INDEX = 109, 110, 111
# control stack kinds. Bodies: IFB / ELSEB / LOOPB and DOB (a = continue target, b = break target; DOB c = the loop
# top) / FUNCB; + BRACELESS: the body is a single statement, closed when that statement completes. A DOB stays on
# the stack through its while (cond): a ')' with a DOB on top can only end that condition.
C_BLOCK, C_IFB, C_ELSEB, C_DOB, C_LOOPB, C_FUNCB = 1, 2, 3, 4, 5, 6
C_IFC, C_WHILEC, C_FORINIT, C_FORCOND, C_FORSTEP, C_ASSIGN, C_EXPR, C_RETURN, C_IDXA = 10, 11, 12, 13, 14, 15, 16, 17, 18
# a property assignment statement: a = 0 o.x (the key's string-area offset in c * 64 + d) / 1 x[k], b = the compound op
C_PSET = 19
# switch (e) { ... }: the header C_SWITCHC, then the body C_SWITCH (a = the pending test's label, b = the end (break) label,
# c = default's label, d = 1 a clause seen + 2 a default seen). The value stays on the stack only while it is tested: each
# case is  JMP Bk (the previous body falls through)  Tk: DUP <value> EQ JZ Tk+1 POP  Bk:, so the bodies run with the
# stack as it was. C_CASE (a = Bk, b = 1 if there is a previous body) is on top while the case value is parsed.
C_SWITCHC, C_SWITCH, C_CASE = 30, 31, 32
BRACELESS = 20
C_IFB1, C_ELSEB1, C_DOB1, C_LOOPB1 = C_IFB + BRACELESS, C_ELSEB + BRACELESS, C_DOB + BRACELESS, C_LOOPB + BRACELESS
# parser modes
(S_STMT, S_OPND, S_OPER, S_NAMES, S_NAMEE, S_VAR, S_VARAFTER, S_LPAREN, S_LBRACE, S_ELSE, S_FNAME, S_FPAREN, S_FPARAM,
 S_FPSEP, S_CONDOT, S_CONLOG, S_CONLP, S_CONFIRST, S_ARR, S_ARRSEP, S_ARRNEG, S_INC, S_IDXEQ, S_AFTERELSE, S_PREINC,
 S_DOWHILE, S_DOT, S_OKEY, S_OCOLON, S_SWCASE, S_ERR) = range(31)
# S_DOT: a property name after '.'; S_OKEY / S_OCOLON: an object literal's key / its ':'. After o.x (SCANI emitted, the key in pn)
# or x[k] the parser is in S_OPER with pm = 1 / 2: the load is pending until the next token shows it is not assigned to.
# pm = 3 after x++ / ++x in an expression, which no '.' or '[' may follow.
# S_SWCASE: a switch body's first token (case, default or '}'); default's ':' is read in S_OCOLON

def tmerge(a, b):
    """static type of a value that is one of two values of types a, b (?: && ||). A boolean with anything else is boolean: the
    PRINTB forms print only 0 / 1 as false / true, and other numbers and strings as they are, so only a 0 or 1 from the
    other side misprints (unknown would misprint every boolean)"""
    return 1 if 1 in (a, b) else a if a == b else 0

class Compiler:
    def __init__(self, data_base, code_base, lib):
        """lib: the runtime library's entry addresses (lib.json)"""
        self.db, self.cb, self.addc_fn = data_base, code_base, lib['addc']
        self.getx_fn, self.setx_fn = lib['getx'], lib['setx']
        self.fetch_fn, self.read_fn = lib['fetch'], lib['read']
        # lexer. An identifier that may be a property name (after '.', '{' or ','; kpos 2 / 1 / 1) writes its bytes to the
        # string area at sdp, not committed; the level after it writes the NUL at inul. It is committed (sdp moves past it):
        # after '.' at once, after '{' or ',' when a ':' follows (icm: its length)
        self.lx = 0; self.q = 0; self.lt = 0; self.tkc = 0; self.acc = 0; self.h1 = 0; self.h2 = 0; self.p2 = 0; self.sstart = 0
        self.inul = 0; self.icm = 0; self.kpos = 0; self.lcon = 0; self.tid = 0; self.pnl = 0
        self.dp = data_base + 1             # globals and array literals (parser); data_base holds STRTAG
        self.sdp = data_base + SDATA + 1    # string literals and property names (lexer); data_base + SDATA itself is the lib's
                                            # empty DONE marker, which PRINT stops at (a property name there printed as '')
        # parser
        self.mode = S_STMT; self.pn = (0, 0)
        self.ops = [0] * OD; self.opv = [0] * OD; self.osp = 0
        self.cs = [[0] * 6 for _ in range(CD)]; self.csp = 0                   # kind a b c d, e: nlet when pushed
        # symbols: h1 h2 kind(1 g, 2 l) addr type const. Two regions: function- and program-level names grow up from 0
        # (nsym), block-scoped let / const grow down from NS - 1 (nlet); closing a block restores nlet
        self.sym = [[0, 0, 0, 0, 0, 0] for _ in range(NS)]; self.nsym = 0; self.nlet = 0
        self.fn = [[0, 0, 0, 0, 0] for _ in range(NF)]; self.nfn = 0           # h1 h2 label type argc (+1; 0: no call or definition yet)
        self.lab = [-1] * NL; self.nlab = 0
        self.itab = [[0, 0, 0] for _ in range(NI)]; self.nint = 0             # interned strings: h1 h2 address + 4096 if no tag word
        self.cp = 0; self.curf = 0; self.cfn = 0; self.nfdef = 0; self.nloc = 0; self.npar = 0; self.fsym = 0    # fsym: nsym at function start
        self.pendLa = 0; self.err = 0; self.arrstart = 0; self.lb = 0; self.asic = 0; self.pm = 0
        self.code = {}; self.data = {}
        self.emitted = []

    # ---------------- helpers
    def emit(self, op, imm=0, label=None, b=None):
        """b: the static type of the value this leaves on the stack (default: by opcode)"""
        self.code[self.cp] = (op, imm, label); self.emitted.append((self.cp, op, imm, label)); self.cp += 1
        self.lb = (1 if op in BOOLOPS else 3 if op in NUMOPS else 0) if b is None else b
    def newlab(self):
        if self.nlab >= NL: self.fail(20)
        self.nlab += 1; return self.nlab - 1
    def deflab(self, l, v):
        if l < NL: self.lab[l] = v                    # (a label past NL comes only after error 20)
    def here(self): return self.cb + self.cp
    def fail(self, code):
        if not self.err: self.err = code
    def push_cs(self, *f, e=None):
        """e: the block-scope mark (nlet to restore when this entry closes; default: the current nlet)"""
        if self.csp >= CD: self.fail(21); return
        self.cs[self.csp] = list(f) + [0] * (5 - len(f)) + [self.nlet if e is None else e]; self.csp += 1
    def top_cs(self): return self.cs[self.csp - 1] if self.csp else [0] * 6
    def pop_cs(self):
        self.csp -= 1; return self.cs[self.csp]
    def push_op(self, code, val=0):
        if self.osp >= OD: self.fail(22); return
        self.ops[self.osp] = code; self.opv[self.osp] = val; self.osp += 1
    def top_op(self): return (self.ops[self.osp - 1], self.opv[self.osp - 1]) if self.osp else (0, 0)
    def lookup(self, h):
        """the latest block-scoped let / const of that name, else the latest other name (in a valid program a visible
        block-scoped binding is always the innermost: a var of the same name in its block would be a redeclaration)"""
        for j in range(NS - self.nlet, NS):
            if (self.sym[j][0], self.sym[j][1]) == h: return j
        for j in range(self.nsym - 1, -1, -1):
            if (self.sym[j][0], self.sym[j][1]) == h: return j
        return -1
    def fnfind(self, h):
        """function table index for a name (adding it, with a new label, if absent)"""
        for k in range(self.nfn):
            if (self.fn[k][0], self.fn[k][1]) == h: return k
        if self.nfn >= NF: self.fail(23); return 0
        l = self.newlab(); self.fn[self.nfn] = [h[0], h[1], l, 0, 0]; self.nfn += 1
        return self.nfn - 1
    def declare(self, h, kind, addr, cst=0, blk=0):
        """blk: a let / const inside a block (the block-scoped region)"""
        if self.nsym + self.nlet >= NS: self.fail(24); return
        if blk: self.nlet += 1; self.sym[NS - self.nlet] = [h[0], h[1], kind, addr, 0, cst]
        else: self.sym[self.nsym] = [h[0], h[1], kind, addr, 0, cst]; self.nsym += 1
    def decl_blk(self):
        """the declaration in progress is block-scoped: let / const (pn[0] 1 / 2) below the function or program level"""
        return int(self.pn[0] > 0 and self.csp > self.curf)
    def load(self, j):
        k, a = self.sym[j][2], self.sym[j][3]
        self.emit(LOADL if k == 2 else LOADG, a % 8192, b=self.sym[j][4])
    def store(self, j):
        k, a = self.sym[j][2], self.sym[j][3]
        self.emit(STOREL if k == 2 else STOREG, a % 8192)
    def popops(self, minprec):
        """shunting-yard: pop and emit operators with precedence >= minprec (stops at markers).
        && / || were emitted as jumps when pushed; popping one defines its jump's target."""
        while self.osp and 0 < prec(self.ops[self.osp - 1]) and prec(self.ops[self.osp - 1]) >= minprec:
            self.osp -= 1; code, val = self.ops[self.osp], self.opv[self.osp]
            if code in (AND, OR):                              # the value is one of the operands: their merged type
                self.deflab(val % 64, self.here()); self.lb = tmerge(val // 64, self.lb)
            elif code == M_TELSE:                              # the value's type: both branches' if they agree
                self.deflab(val % 64, self.here()); self.lb = tmerge(val // 64, self.lb)
            elif code == ADD:                                  # strings cannot be built
                if val == 2 or self.lb == 2: self.fail(63)
                self.emit(ADD)
            elif code == M_CADD:                               # numbers: add; else the lib's addc
                if val == 3 and self.lb == 3: self.emit(ADD)
                else: self.emit(CALL, self.addc_fn, b=0)
            else: self.emit(code)
    def intern(self, h, addr, tag):
        """the interned string of hash h: its table value (address + 4096 if it has no tag word), entering it (at addr) if new;
        -1 when the table is full"""
        for k in range(self.nint):
            if (self.itab[k][0], self.itab[k][1]) == h: return self.itab[k][2]
        if self.nint >= NI: self.fail(68); return -1
        self.itab[self.nint] = [h[0], h[1], addr + 4096 * (1 - tag)]; self.nint += 1
        return addr + 4096 * (1 - tag)
    def key_name(self, h):
        """a property name (identifier token): its key, the interned address (-1: failed)"""
        if self.tid >= 4096: self.fail(26); return -1
        e = self.intern(h, self.tid, 0)
        return -1 if e < 0 else e % 4096
    def stmt_level(self):
        """an assignment to o.x / x[k]: only as a statement of its own"""
        return self.osp == 0 and self.top_cs()[0] == C_EXPR

    def loop_entry(self, brk):
        """the innermost loop (or, for break, switch) entry: a = its continue label, b = its break label"""
        for k in range(self.csp - 1, -1, -1):
            if self.cs[k][0] in (C_LOOPB, C_LOOPB1, C_DOB, C_DOB1) or (brk and self.cs[k][0] == C_SWITCH): return self.cs[k]
        return None
    def print_call(self, sep):
        """print (and pop) the value on the stack, then the separator sep (0 none, 32 space, 10 newline): one PRINT word.
        The machine tells strings from numbers at run time; only booleans need the static type (the B forms)."""
        self.emit(PRINT_OP[sep] + int(self.lb == 1), b=0)

    # ---------------- lexer: one character -> at most one token
    def sbyte(self, a, v):
        """a string-area word (an identifier's tentative bytes may run past the area: dropped, as on the page)"""
        if a < self.db + 2 * SDATA: self.data[a] = v
    def shash(self, c):
        self.h1 = (self.h1 * 31 + c) % H1M; self.h2 = (self.h2 * 37 + c) % H2M
    def char(self, c, cn):
        tok = None; gap = 0                               # gap: a blank or the end of a comment (no token here)
        isal = lambda x: 65 <= x <= 90 or 97 <= x <= 122 or x in (95, 36)
        isdg = lambda x: 48 <= x <= 57
        if self.inul and not (self.lx == 0 and self.p2 == 0 and c in (34, 39)): self.sbyte(self.inul, 0)   # NUL after an identifier
        self.inul = 0
        if c == 0 and self.lx != 0: self.lx = 0; self.p2 = 0; tok = ('EOF', 0)    # unterminated string / comment
        elif self.lx == 1:                                # in a string
            if c == self.q:
                self.data[self.sdp] = 0; self.sdp += 1; self.lx = 0
                tok = ('STR', (self.sstart + 4096 * int(self.sdp > self.db + 2 * SDATA), self.h1, self.h2))
            elif c == 92: self.lx = 3
            else: self.data[self.sdp] = c; self.sdp += 1; self.shash(c)
        elif self.lx == 3:                                # after a backslash
            self.data[self.sdp] = ESC.get(c, c); self.sdp += 1; self.lx = 1; self.shash(ESC.get(c, c))
        elif self.lx == 2:                                # // comment
            if c == 10: self.lx = 0; gap = 1; tok = self.newline()
        elif self.lx == 4:                                # /* comment
            if c == 42 and cn == 47: self.lx = 5
            elif c == 10: tok = self.newline()
        elif self.lx == 5: self.lx = 0; gap = 1           # the '/' of '*/' (or the third char of === / !==)
        elif self.lx == 6: self.lx = 4                    # the '*' of '/*'
        elif self.p2:
            tok = ('P', self.p2)
            if self.p2 in (1, 2) and cn == 61: self.lx = 5
            self.p2 = 0
        elif c == 0: tok = ('EOF', 0)
        elif c in BLANK:
            gap = 1
            if c == 10: tok = self.newline()
        elif c == 47 and cn == 47: self.lx = 2
        elif c == 47 and cn == 42: self.lx = 6
        elif c in (34, 39):                               # a string: its tag word, then its bytes (hashed for interning)
            self.lx = 1; self.q = c; self.data[self.sdp] = self.sdp + 1 - STRTAG; self.sdp += 1; self.sstart = self.sdp
            self.h1 = self.h2 = 0
        elif isal(c) or (isdg(c) and self.tkc == 1):      # an identifier: hashed; its bytes at sdp (acc: its length so far)
            if self.tkc != 1: self.h1 = self.h2 = 0; self.acc = 0
            self.shash(c); self.tkc = 1
            if self.kpos: self.sbyte(self.sdp + self.acc, c)
            self.acc += 1
            if not (isal(cn) or isdg(cn)):
                tok = ('ID', (self.h1, self.h2)); self.tkc = 0
                self.tid = self.sdp + 4096 * int(self.sdp + self.acc >= self.db + 2 * SDATA)    # its address (+ 4096: no room)
                if self.kpos: self.inul = self.sdp + self.acc
                if self.kpos == 2: self.sdp += self.acc + 1
                self.icm = self.acc + 1 if self.kpos == 1 else 0
        elif isdg(c):
            self.acc = (self.acc * 10 if self.tkc == 2 else 0) + c - 48; self.tkc = 2
            if not isdg(cn): tok = ('NUM', self.acc); self.tkc = 0
        elif (c, cn) in TWO: self.p2 = TWO[(c, cn)]
        else: tok = ('P', c)
        if self.pnl:                                      # the pending newline: decide on the next significant character
            if gap:
                if cn in CONT: self.pnl = 0
                elif cn not in BLANK + (47, 43, 45): tok = ('P', T_NL); self.pnl = 0
            elif c in (43, 45):                           # ++x / --x: a new statement; x + y / x - y: continues
                if cn == c: tok = ('P', T_NL)
                self.pnl = 0
            elif c == 47 and self.lx == 0: self.pnl = 0   # a division (a comment keeps it pending)
        if tok:
            if tok == ('P', 58) and self.icm: self.sdp += self.icm            # an object literal's key: commit its string
            if tok[0] != 'ID' and tok != ('P', T_NL): self.icm = 0
            if tok != ('P', T_NL):                             # (console.log's log is not a property name)
                self.kpos = 2 if tok == ('P', 46) and not self.lcon else int(tok in (('P', 123), ('P', 44)))
                self.lcon = int(tok == ('ID', KW['console']))
            self.lt = int(tok[0] in ('ID', 'NUM', 'STR') or (tok[0] == 'P' and tok[1] in (41, 93, 125, 7, 8))) + int(tok == ('ID', KW['return']))
            cp0 = self.cp; self.token(*tok)
            if self.cp - cp0 > EMAX: self.fail(61)

    def newline(self):
        """a newline (also in a comment): after return a T_NL at once; after another token that can end a statement, pending"""
        if self.lt == 2: return ('P', T_NL)
        if self.lt: self.pnl = 1
        return None

    # ---------------- parser: one token
    def token(self, kind, v):
        if self.err: return
        isP = lambda c: kind == 'P' and v == c
        isK = lambda k: kind == 'ID' and v == KW[k]
        m = self.mode
        if isP(T_NL) and m not in (S_NAMES, S_NAMEE, S_OPER, S_VARAFTER, S_INC, S_OPND): return     # a newline elsewhere: nothing
        # ---- pending NAME (statement start): decide what it was
        if m == S_NAMES:
            h = self.pn
            if isP(61) or (kind == 'P' and v in COMPOUND):       # NAME = e, NAME op= e
                j = self.lookup(h)
                if j < 0: return self.fail(5)
                if self.sym[j][5]: return self.fail(64)            # assignment to a constant
                if not isP(61): self.load(j)
                self.push_cs(C_ASSIGN, j, COMPOUND.get(v, 0) if kind == 'P' else 0); self.mode = S_OPND; return
            if isP(7) or isP(8):                          # NAME++ / NAME--
                return self.incdec(h, v)
            if isP(91):                                   # NAME[e] = e (an array: static type number; else via SETX below)
                j = self.lookup(h)
                if j < 0: return self.fail(7)
                if self.sym[j][4] == 3: self.load(j); self.push_cs(C_IDXA); self.push_op(M_IDXA); self.mode = S_OPND; return
            # anything else: an expression statement starting with NAME
            self.push_cs(C_EXPR); m = self.mode = S_NAMEE
        if m == S_NAMEE:
            h = self.pn
            if h == KW['console']:
                if not isP(46): return self.fail(30)
                self.mode = S_CONLOG; return
            if isP(40):
                if h in (KW['putc'], KW['fetch'], KW['read']): self.push_op(M_PUTC, BUILTIN[h])
                else:
                    k = self.fnfind(h); self.push_op(M_CALL, k + 16 * self.fn[k][3])
                self.mode = S_OPND; return
            if isP(7) or isP(8): return self.incdec(h, v, 2)       # x++ / x-- in an expression: the old value
            j = self.lookup(h)
            if j < 0: return self.fail(4)
            if isP(91) and self.sym[j][4] == 3:              # an array literal's variable: IDX
                k, a = self.sym[j][2], self.sym[j][3]
                self.push_op(M_IDXL if k == 2 else M_IDXG, a % 8192); self.mode = S_OPND; return
            self.load(j); m = self.mode = S_OPER                 # fall through: this token follows an operand
        # ---- after an if body: else?
        if m == S_ELSE:
            if isK('else'):
                # an if that is itself the body of a braceless else ends where that else ends: reuse its label and
                # wrapper (an else-if chain then needs one control-stack entry and one end label, however long)
                t = self.top_cs(); reuse = t[0] == C_ELSEB1
                lb = t[1] if reuse else self.newlab()
                self.emit(JMP, 0, lb); self.deflab(self.pendLa, self.here())
                self.pendLa = lb + 64 * reuse; self.mode = S_AFTERELSE; return
            # a token no statement can start with closes no do body (an error either way: 8 rather than 66), so
            # the CSS variants for such tokens stay pure errors and are dropped
            dook = kind in ('ID', 'EOF') or (kind == 'P' and v in (59, 123, 125, 7, 8, 41))
            self.deflab(self.pendLa, self.here()); self.complete_stmt(1, dook); m = self.mode
        if m == S_DOWHILE:                                     # a do body ended: while (cond)
            if isP(59): return                                 # the ';' of a do-while that was the body
            if not isK('while'): return self.fail(66)
            self.mode = S_LPAREN; return
        if m == S_AFTERELSE:                                   # else { ... } or else <statement> (including if)
            reuse = self.pendLa >= 64                          # (the enclosing else's wrapper closes this else too)
            if isP(123):
                if reuse: self.push_cs(C_BLOCK)
                else: self.push_cs(C_ELSEB, self.pendLa)
                self.mode = S_STMT; return
            if not reuse: self.push_cs(C_ELSEB1, self.pendLa)
            m = self.mode = S_STMT
        if m == S_LBRACE:                                      # a body: { ... } or a single statement
            if isP(123): self.mode = S_SWCASE if self.top_cs()[0] == C_SWITCH else S_STMT; return
            if self.top_cs()[0] not in (C_IFB, C_LOOPB, C_DOB): return self.fail(33)
            self.cs[self.csp - 1][0] += BRACELESS; m = self.mode = S_STMT
        if m == S_SWCASE:
            if not (isK('case') or isK('default') or isP(125)): return self.fail(74)
            m = self.mode = S_STMT
        # ---- statements
        if m == S_STMT:
            t = self.top_cs()[0]
            if kind == 'EOF':
                if self.csp: return self.fail(40)
                if self.nfdef < self.nfn: return self.fail(60)        # a function called but never defined
                self.emit(HALT); return
            if isP(123): self.push_cs(C_BLOCK); return
            if isP(125): return self.close_block()
            if isP(59): return self.end_simple_stmt(kind, v)   # empty statement (or an empty for init)
            if isP(41) and t == C_FORSTEP: return self.end_simple_stmt(kind, v)     # for (...;...;)
            if isP(7) or isP(8): self.pn = (v, 0); self.mode = S_PREINC; return
            if kind != 'ID': return self.fail(8)
            if isK('var') or isK('let') or isK('const'):          # pn[0]: the declaration kind, 0 var 1 let 2 const
                self.pn = (int(isK('let')) + 2 * int(isK('const')), 0); self.mode = S_VAR; return
            if isK('if'): self.push_cs(C_IFC); self.mode = S_LPAREN; return
            if isK('switch'): self.push_cs(C_SWITCHC); self.mode = S_LPAREN; return
            if isK('case') or isK('default'):
                t = self.top_cs(); seen = t[4] & 1
                if t[0] != C_SWITCH: return self.fail(73)
                if isK('case'):                                # [JMP Bk]  T: DUP <value> (then ':')
                    bk = self.newlab() if seen else 0
                    if seen: self.emit(JMP, 0, bk)
                    self.deflab(t[1], self.here()); self.emit(DUP)
                    self.push_cs(C_CASE, bk, seen); self.mode = S_OPND; return
                if t[4] & 2: return self.fail(75)              # a second default
                if not seen: self.emit(JMP, 0, t[1])           # the value goes to the tests first
                ld = self.newlab(); self.deflab(ld, self.here())
                t[3] = ld; t[4] = 3; self.mode = S_OCOLON; return
            if isK('while'):
                lh = self.newlab(); self.deflab(lh, self.here()); self.push_cs(C_WHILEC, lh); self.mode = S_LPAREN; return
            if isK('do'):                                      # top: body; continue: cond JNZ top; break:
                lt, lc, lb = self.newlab(), self.newlab(), self.newlab(); self.deflab(lt, self.here())
                self.push_cs(C_DOB, lc, lb, lt); self.mode = S_LBRACE; return
            if isK('for'):
                l1, le, lb, l2 = self.newlab(), self.newlab(), self.newlab(), self.newlab()
                self.push_cs(C_FORINIT, l1, le, lb, l2); self.mode = S_LPAREN; return
            if isK('return'):
                if not self.curf: return self.fail(57)
                self.push_cs(C_RETURN); self.mode = S_OPND; return
            if isK('break') or isK('continue'):
                e = self.loop_entry(isK('break'))
                if e is None: return self.fail(56)
                self.emit(JMP, 0, e[2] if isK('break') else e[1]); self.mode = S_INC; return
            if isK('function'):
                if self.curf or self.csp: return self.fail(41)
                lo = self.newlab(); self.emit(JMP, 0, lo); self.mode = S_FNAME
                self.push_cs(C_FUNCB, lo); return
            self.pn = v; self.mode = S_NAMES; return
        if m == S_PREINC:                                      # ++x / --x (pn[1]: in an expression)
            if kind != 'ID': return self.fail(10)
            return self.incdec(v, self.pn[0], self.pn[1])
        if m == S_VAR:
            if kind != 'ID': return self.fail(9)
            cst, blk = int(self.pn[0] == 2), self.decl_blk()
            if self.curf: self.nloc += 1; self.declare(v, 2, self.nloc, cst, blk)
            else:
                if self.dp >= self.db + SDATA: return self.fail(25)            # globals would reach the strings
                self.declare(v, 1, self.dp, cst, blk); self.dp += 1
            self.mode = S_VARAFTER; return
        if m == S_VARAFTER:
            if isP(61):
                self.push_cs(C_ASSIGN, NS - self.nlet if self.decl_blk() else self.nsym - 1, 0, 1 + self.pn[0]); self.mode = S_OPND; return
            if self.pn[0] == 2: return self.fail(65)           # const without an initialiser
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
            t = self.top_cs()[0]
            if t == C_FORINIT:
                self.mode = S_STMT; return                  # the init statement (or ';')
            self.mode = S_OPND; return
        if m == S_FNAME:
            if kind != 'ID': return self.fail(34)
            k = self.fnfind(v); self.cfn = k; self.deflab(self.fn[k][2], self.here()); self.nfdef += 1
            self.curf = 1; self.nloc = 0; self.npar = 0; self.fsym = self.nsym
            le = self.newlab(); self.cs[self.csp - 1][2] = le
            self.mode = S_FPAREN; return
        if m == S_FPAREN:
            if not isP(40): return self.fail(35)
            self.mode = S_FPARAM; return
        if m == S_FPARAM:
            if isP(41): return self.end_params()
            if kind != 'ID': return self.fail(36)
            self.declare(v, 2, 4096 + self.npar); self.npar += 1; self.mode = S_FPSEP; return     # (= the DSL's encoding until end_params)
        if m == S_FPSEP:
            if isP(44): self.mode = S_FPARAM; return
            if isP(41): return self.end_params()
            return self.fail(37)
        if m == S_CONLOG:
            if not isK('log'): return self.fail(38)
            self.mode = S_CONLP; return
        if m == S_CONLP:
            if not isP(40): return self.fail(39)
            self.push_op(M_PRINT); self.mode = S_CONFIRST; return
        if m == S_CONFIRST:                                    # an argument's first token (a string: concatenation)
            if isP(41):                                        # console.log()
                if self.opv[self.osp - 1] == 2: return self.fail(30)   # console.log(a, ): a's space is printed already
                self.osp -= 1; self.emit(PUSHI, 10); self.emit(PUTC); return self.print_end()
            self.opv[self.osp - 1] = 0
            m = self.mode = S_OPND
        if m == S_ARR:                                       # [n, -n, ...]
            if isP(93): return self.end_array()
            if isP(45): self.mode = S_ARRNEG; return
            if kind != 'NUM': return self.fail(42)
            if self.dp >= self.db + SDATA: return self.fail(25)
            self.data[self.dp] = v; self.dp += 1; self.mode = S_ARRSEP; return
        if m == S_ARRNEG:
            if kind != 'NUM': return self.fail(42)
            if self.dp >= self.db + SDATA: return self.fail(25)
            self.data[self.dp] = -v; self.dp += 1; self.mode = S_ARRSEP; return
        if m == S_ARRSEP:
            if isP(44): self.mode = S_ARR; return
            if isP(93): return self.end_array()
            return self.fail(43)
        if m == S_IDXEQ:                                       # a[i] = e (an array)
            if isP(61): self.mode = S_OPND; return
            if isP(7) or isP(8):                               # a[i]++: address DUP LOADI 1 ADD STOREI
                self.emit(DUP); self.emit(LOADI); self.emit(PUSHI, 1); self.emit(ADD if isP(7) else SUB); self.emit(STOREI)
                self.pop_cs(); self.mode = S_INC; return
            if kind == 'P' and v in COMPOUND:                  # a[i] op= e: address DUP LOADI e op STOREI
                self.emit(DUP); self.emit(LOADI); self.cs[self.csp - 1][1] = COMPOUND[v]; self.mode = S_OPND; return
            if not (isP(46) or isP(91)): return self.fail(49)
            # a[i].x ... / a[i][j] ...: a[i] is an operand of an expression statement (fall through)
            self.emit(LOADI); self.cs[self.csp - 1][0] = C_EXPR; m = self.mode = S_OPER
        # ---- objects
        if m == S_DOT:                                         # o . name
            if kind != 'ID': return self.fail(69)
            if v == KW['length']:                              # an array's length: the word before its first element
                self.emit(PUSHI, 1); self.emit(SUB); self.emit(LOADI, b=3); self.mode = S_OPER; return
            ks = self.key_name(v)
            if ks < 0: return
            self.emit(SCANI, ks); self.pn = (ks, 0); self.pm = 1; self.mode = S_OPER; return
        if m == S_OKEY:                                        # { key : value, ... }
            t, tv = self.top_op()
            if isP(125):                                       # {} or a trailing comma
                if tv < 4: self.emit(ENDK, 2 * tv)
                self.osp -= 1; self.lb = 0; self.mode = S_OPER; return
            if kind == 'ID': ks = self.key_name(v)
            elif kind == 'STR':
                if v[0] >= 4096: return self.fail(26)
                e = self.intern((v[1], v[2]), v[0], 1); ks = -1 if e < 0 else e % 4096
            elif kind == 'NUM': ks = -2
            else: return self.fail(71)
            if ks == -1: return
            if ks >= 0 and tv < 3:                             # one of the first pairs, all string keys: stored in place
                self.emit(PUSHI, ks); self.emit(SETF, 2 * tv); self.push_op(M_OKEY, 0)
            else:
                if tv < 4: self.emit(ENDK, 2 * tv); self.opv[self.osp - 1] = tv | 4          # end the keys stored in place
                self.emit(DUP)
                if ks >= 0: self.emit(SCANI, ks); self.push_op(M_OKEY, ks)             # as o.x = v (PUTV may add a chunk)
                else:                                          # a number key: as o[n] = v
                    if v < 8192: self.emit(PUSHI, v)
                    else: self.emit(PUSHI, v // 8192); self.emit(SHL13); self.emit(PUSHI, v % 8192); self.emit(ADD)
                    self.push_op(M_OKEY, 1)
            self.mode = S_OCOLON; return
        if m == S_OCOLON:
            if not isP(58): return self.fail(72)
            self.mode = S_STMT if self.top_cs()[0] == C_SWITCH else S_OPND; return      # (default's ':')
        # ---- expressions
        if m == S_OPND:
            if kind == 'NUM':
                if v < 8192: self.emit(PUSHI, v)
                else: self.emit(PUSHI, v // 8192); self.emit(SHL13); self.emit(PUSHI, v % 8192); self.emit(ADD)
                self.mode = S_OPER; return
            if kind == 'STR':
                if v[0] >= 4096: return self.fail(26)                         # string data would reach the code
                e = self.intern((v[1], v[2]), v[0], 1)
                if e < 0: return
                if e >= 4096:                                  # first seen as a property name: no tag word to load
                    self.emit(PUSHI, e % 4096); self.emit(LOADG, self.db % 8192); self.emit(SUB, b=2)
                else: self.emit(LOADG, (e - 1) % 8192, b=2)
                self.mode = S_OPER; return
            if isK('true') or isK('false'): self.emit(PUSHI, int(isK('true')), b=1); self.mode = S_OPER; return
            if isK('null'): self.emit(PUSHI, 0, b=0); self.mode = S_OPER; return
            if isP(123):                                       # an object literal
                self.emit(NEW); self.push_op(M_OBJ, 0); self.mode = S_OKEY; return
            if isP(40): self.push_op(M_PAREN); return
            if isP(33): self.push_op(NOT); return
            if isP(45): self.push_op(NEG); return
            if isP(7) or isP(8): self.pn = (v, 1); self.mode = S_PREINC; return      # ++x / --x in an expression
            if isP(91):                                        # an array literal: its length, then its elements
                if self.dp >= self.db + SDATA: return self.fail(25)
                self.arrstart = self.dp; self.dp += 1; self.mode = S_ARR; return
            if kind == 'ID': self.pn = v; self.mode = S_NAMEE; return
            if isP(41) and self.top_op()[0] == M_CALL:      # f() (or f(a, ) with a trailing comma)
                self.osp -= 1; self.call_end(self.opv[self.osp], 0); self.mode = S_OPER; return
            if isP(41) and self.top_op() == (M_PUTC, B_READ):    # read()
                self.osp -= 1; self.emit(CALL, self.read_fn, b=3); self.mode = S_OPER; return
            if (isP(59) or isP(T_NL) or isP(125)) and self.top_cs()[0] == C_RETURN and self.osp == 0:     # return;
                self.emit(PUSHI, 0)
                if isP(125): return self.asi_close(lambda: self.end_expr_stmt('P', T_NL))
                return self.end_expr_stmt(kind, v)
            if isP(T_NL): return
            if isP(59) and self.top_cs()[0] == C_FORCOND and self.osp == 0:    # for (; ; )
                self.emit(PUSHI, 1); return self.end_expr_stmt(kind, v)
            return self.fail(3)
        if m == S_OPER:
            if self.pm == 3:                                   # after x++ / ++x: not a member expression (x++[1], x++.y)
                self.pm = 0
                if isP(46) or isP(91): return self.fail(48)
            if self.pm:                                        # after o.x (cursor on the stack) or x[k] ([x, k] on the stack)
                ks, dyn = self.pn[0], self.pm == 2
                asg = isP(61) or (kind == 'P' and v in COMPOUND) or isP(7) or isP(8)
                if asg:
                    if not self.stmt_level(): return self.fail(70)
                    op = COMPOUND.get(v, 0) if kind == 'P' else 0
                    if not isP(61):                                # the old value: [c] DUP LDF 1 / [x, k] OVER OVER GETX
                        if dyn: self.emit(OVER); self.emit(OVER); self.emit(CALL, self.getx_fn, b=0)
                        else: self.emit(DUP); self.emit(LDF, 1)
                    if isP(7) or isP(8):                           # o.x++ / x[k]--
                        self.emit(PUSHI, 1); self.emit(ADD if isP(7) else SUB)
                        if dyn: self.emit(CALL, self.setx_fn, b=0)
                        else: self.emit(PUTV, ks)
                        self.pop_cs(); self.pm = 0; self.mode = S_INC; return
                    off = ks - self.db - SDATA
                    self.cs[self.csp - 1][:5] = [C_PSET, dyn, op, off // 64 if not dyn else 0, off % 64 if not dyn else 0]
                    self.pm = 0; self.mode = S_OPND; return
                if dyn: self.emit(CALL, self.getx_fn, b=0)
                else: self.emit(LDF, 1)
                self.pm = 0
            if kind == 'P' and v in BIN:
                op = BIN[v]; self.popops(prec(op))
                t, tv = self.top_op()
                if op == ADD and t == M_PRINT and (tv == 1 or self.lb == 2):    # "..." + x in console.log: print the pieces
                    self.print_call(0); self.opv[self.osp - 1] = 1; self.mode = S_OPND; return
                if op == ADD: self.push_op(M_CADD if t == M_PRINT else ADD, self.lb); self.mode = S_OPND; return
                if op in (AND, OR):                            # short-circuit: a DUP JZ/JNZ L POP b L:
                    lb = self.lb; l = self.newlab(); self.emit(DUP); self.emit(JZ if op == AND else JNZ, 0, l); self.emit(POP)
                    self.push_op(op, l + 64 * lb); self.mode = S_OPND; return
                self.push_op(op); self.mode = S_OPND; return
            if isP(63):                                        # c ? ...
                self.popops(2); t, tv = self.top_op()
                l = self.newlab(); self.emit(JZ, 0, l); self.push_op(M_TERN, l + 64 * int(t == M_TELSE)); self.mode = S_OPND; return
            if isP(58):                                        # c ? a : ...
                self.popops(1); t, tv = self.top_op()
                if t != M_TERN:
                    if self.osp == 0 and self.top_cs()[0] == C_CASE: return self.case_end()
                    return self.fail(67)
                self.osp -= 1; lbt = self.lb
                if tv >= 64:                                   # reuse the enclosing M_TELSE's L2
                    ev = self.opv[self.osp - 1]; self.emit(JMP, 0, ev % 64)
                    self.opv[self.osp - 1] = ev % 64 + 64 * tmerge(ev // 64, lbt)
                else:
                    l2 = self.newlab(); self.emit(JMP, 0, l2); self.push_op(M_TELSE, l2 + 64 * lbt)
                self.deflab(tv % 64, self.here()); self.mode = S_OPND; return
            if isP(46): self.mode = S_DOT; return               # o.x
            if isP(91): self.push_op(M_INDEX); self.mode = S_OPND; return     # x[k]
            if isP(125):                                       # '}' ending an object literal's value?
                self.popops(1); t, tv = self.top_op()
                if t == M_OKEY: return self.okey_end(tv, 1)
            if isP(41) or isP(44) or isP(93):
                self.popops(1)
                t, tv = self.top_op()
                if isP(44) and t == M_OKEY: return self.okey_end(tv, 0)
                if isP(93) and t == M_INDEX: self.osp -= 1; self.pm = 2; return
                if isP(44):
                    if t == M_PRINT: self.print_call(32); self.opv[self.osp - 1] = 2; self.mode = S_CONFIRST; return     # (2: after a ',')
                    if t == M_CALL: self.opv[self.osp - 1] += 64      # count the arguments
                    if t == M_CALL or (t == M_PUTC and tv == B_PUTC): self.mode = S_OPND; return
                    if self.osp == 0 and self.top_cs()[0] == C_ASSIGN and self.top_cs()[3]: return self.end_expr_stmt(kind, v)
                    return self.fail(44)
                if isP(93):
                    if t in (M_IDXG, M_IDXL): self.osp -= 1; self.emit(IDXL if t == M_IDXL else IDX, tv); return
                    if t == M_IDXA: self.osp -= 1; self.emit(ADD); self.mode = S_IDXEQ; return
                    return self.fail(45)
                if t == M_PAREN: self.osp -= 1; return
                if t == M_CALL: self.osp -= 1; return self.call_end(tv, 1)
                if t == M_PUTC:
                    self.osp -= 1
                    if tv == B_PUTC: self.emit(PUTC); self.emit(PUSHI, 0); return
                    if tv == B_FETCH: self.emit(CALL, self.fetch_fn, b=3); return
                    return self.fail(76)                       # read(x)
                if t == M_PRINT: self.osp -= 1; self.print_call(10); return self.print_end()
                if self.osp: return self.fail(46)
                return self.end_expr_stmt(kind, v)             # ')' closing a statement-level paren
            asiok = (not any(self.ops[k] >= 100 for k in range(self.osp)) and self.top_cs()[0] in (C_ASSIGN, C_IDXA, C_EXPR, C_RETURN, C_PSET)
                     and not (self.csp >= 2 and self.cs[self.csp - 2][0] in (C_FORINIT, C_FORSTEP)))      # (none in a for header)
            if isP(T_NL) and not asiok: return                   # a newline ends the statement, unless inside ( [ or a call
            if isP(125) and asiok:
                return self.asi_close(lambda: (self.popops(1), self.end_expr_stmt('P', T_NL)))
            if isP(59) or isP(T_NL):
                self.popops(1)
                if self.osp: return self.fail(47)
                return self.end_expr_stmt(kind, v)
            return self.fail(48)
        return self.fail(99)

    def okey_end(self, tv, close):
        """an object literal's value ended (',' or, close, '}'): store the pair"""
        self.osp -= 1; o = self.opv[self.osp - 1]
        if tv == 0: self.emit(SETF, 2 * o + 1); self.opv[self.osp - 1] = o + 1
        elif tv == 1: self.emit(CALL, self.setx_fn, b=0)
        else: self.emit(PUTV, tv)
        if close:
            if self.opv[self.osp - 1] < 4: self.emit(ENDK, 2 * self.opv[self.osp - 1])
            self.osp -= 1; self.lb = 0; self.mode = S_OPER
        else: self.mode = S_OKEY

    def call_end(self, tv, last):
        """a call's ')': M_CALL's value tv = function index + 16 * its type + 64 * the commas; last: an argument just ended.
        Our calls pass exactly as many words as the function pops, so every call and the definition must agree on the count
        (the first one seen sets it; 76 otherwise)"""
        k, argc = tv % 16, tv // 64 + last
        if self.fn[k][4] and self.fn[k][4] != argc + 1: return self.fail(76)
        self.fn[k][4] = argc + 1
        self.emit(CALL, 0, self.fn[k][2], b=(tv // 16) % 4)

    def print_end(self):
        """console.log(...) ended. Its PRINT words popped every argument, so it leaves no value: it must be a statement of its
        own (C_EXPR, nothing else open), which ends here without the expression statement's POP"""
        if self.osp or self.top_cs()[0] != C_EXPR: return self.fail(30)
        self.pop_cs(); self.mode = S_INC

    def case_end(self):
        """a case value ended (':'): EQ JZ Tnext POP Bk:"""
        c = self.pop_cs(); self.emit(EQ); tn = self.newlab(); self.emit(JZ, 0, tn); self.emit(POP)
        if c[2]: self.deflab(c[1], self.here())
        t = self.top_cs(); t[1] = tn; t[4] |= 1; self.mode = S_STMT

    def asi_close(self, f):
        """'}' right after a statement without ';': end the statement (knowing the next token is not 'else'),
        then close the block"""
        self.asic = 1; f(); self.asic = 0
        if not self.err: self.close_block()

    def incdec(self, h, v, x=0):
        """++ (v 7) / -- (8) of a variable. x: 0 a statement, 1 ++x in an expression (leaves the new value), 2 x++ (the old)"""
        j = self.lookup(h)
        if j < 0: return self.fail(6)
        if self.sym[j][5]: return self.fail(64)
        k, a = self.sym[j][2], self.sym[j][3]
        if x == 2: self.load(j)
        if v == 7: self.emit(INCL if k == 2 else INCG, a % 8192)
        else:
            self.load(j); self.emit(PUSHI, 1); self.emit(SUB)
            if x == 1: self.emit(DUP)
            self.store(j)
        if x == 1 and v == 7: self.load(j)
        if x: self.lb = 3; self.pm = 3; self.mode = S_OPER
        else: self.mode = S_INC

    # ---- an expression ended at statement level (';' or ')' or ','): what was it for?
    def end_expr_stmt(self, kind, v):
        isP = lambda c: kind == 'P' and v == c
        t = self.top_cs()
        k = t[0]
        if k == C_IFC and isP(41):
            self.pop_cs(); la = self.newlab(); self.emit(JZ, 0, la); self.push_cs(C_IFB, la); self.mode = S_LBRACE; return
        if k == C_SWITCHC and isP(41):                         # the value on the stack; the first test's label, the end label
            self.pop_cs(); lt, le = self.newlab(), self.newlab(); self.push_cs(C_SWITCH, lt, le); self.mode = S_LBRACE; return
        if k in (C_DOB, C_DOB1) and isP(41):
            # the statement ends at ')': JavaScript inserts a ';' here even without a newline, and a ';' that follows
            # is an empty statement (so `if (a) do s; while (c); else ...` is rejected)
            self.pop_cs(); self.emit(JNZ, 0, t[3]); self.deflab(t[2], self.here()); return self.complete_stmt(0)
        if k == C_WHILEC and isP(41):
            self.pop_cs(); le = self.newlab(); self.emit(JZ, 0, le); self.push_cs(C_LOOPB, t[1], le); self.mode = S_LBRACE; return
        if k == C_FORCOND and isP(59):
            self.pop_cs()                                      # t: l1 le lb l2
            self.emit(JZ, 0, t[2]); self.emit(JMP, 0, t[3]); self.deflab(t[4], self.here())
            self.push_cs(C_FORSTEP, t[1], t[2], t[3], t[4], e=t[5]); self.mode = S_STMT; return
        if k == C_ASSIGN:                                      # t: symbol, compound op, from a declaration
            self.pop_cs()
            if t[2]: self.emit(t[2])
            self.sym[t[1]][4] = self.lb; self.store(t[1])
            if isP(44) and t[3]: self.pn = (t[3] - 1, 0); self.mode = S_VAR; return     # var a = 1, b ...
            return self.end_simple_stmt(kind, v)
        if k == C_IDXA:
            self.pop_cs()
            if t[1]: self.emit(t[1])
            self.emit(STOREI); return self.end_simple_stmt(kind, v)
        if k == C_PSET:                                        # t: dynamic, compound op, key offset (c * 64 + d)
            self.pop_cs()
            if t[2]: self.emit(t[2])
            if t[1]: self.emit(CALL, self.setx_fn, b=0)
            else: self.emit(PUTV, self.db + SDATA + t[3] * 64 + t[4])
            return self.end_simple_stmt(kind, v)
        if k == C_EXPR:
            self.pop_cs(); self.emit(POP); return self.end_simple_stmt(kind, v)
        if k == C_RETURN and (isP(59) or isP(T_NL)):
            self.pop_cs()
            if self.lb: self.fn[self.cfn][3] = self.lb
            self.emit(RET, self.npar); return self.complete_stmt(0)
        return self.fail(50)

    # ---- a simple statement's terminator: ';' normally, ';' after a for init, ')' after a for step
    def end_simple_stmt(self, kind, v):
        isP = lambda c: kind == 'P' and v == c
        t = self.top_cs()
        if t[0] == C_FORINIT:
            if not isP(59): return self.fail(51)
            self.pop_cs(); self.deflab(t[1], self.here()); self.push_cs(C_FORCOND, t[1], t[2], t[3], t[4], e=t[5]); self.mode = S_OPND; return
        if t[0] == C_FORSTEP:
            if not isP(41): return self.fail(52)
            self.pop_cs(); self.emit(JMP, 0, t[1]); self.deflab(t[3], self.here())
            self.push_cs(C_LOOPB, t[4], t[2], e=t[5]); self.mode = S_LBRACE; return
        if not (isP(59) or isP(T_NL)): return self.fail(53)
        self.complete_stmt(0)

    def complete_stmt(self, nonelse, dook=True):
        """a statement finished: close the braceless bodies it was the body of. A braceless if body waits for the
        next token (else?) unless that token is known not to be 'else' (nonelse)."""
        self.mode = S_STMT
        while self.csp:
            k = self.top_cs()[0]
            if k not in (C_ELSEB1, C_LOOPB1, C_IFB1, C_DOB1) or (k == C_DOB1 and not dook): return
            t = self.pop_cs(); self.nlet = t[5]                # the body's block scope ends
            if k == C_DOB1: return self.do_cond(t)
            if k == C_ELSEB1: self.deflab(t[1], self.here())
            elif k == C_LOOPB1: self.emit(JMP, 0, t[1]); self.deflab(t[2], self.here())
            elif nonelse or self.asic: self.deflab(t[1], self.here())
            else: self.pendLa = t[1]; self.mode = S_ELSE; return

    def close_block(self):
        if not self.csp: return self.fail(54)
        t = self.pop_cs(); k = t[0]; self.nlet = t[5]
        if k == C_BLOCK: return self.complete_stmt(0)
        if k == C_IFB: self.pendLa = t[1]; self.mode = S_ELSE; return
        if k == C_ELSEB: self.deflab(t[1], self.here()); return self.complete_stmt(0)
        if k == C_DOB: return self.do_cond(t)
        if k == C_LOOPB: self.emit(JMP, 0, t[1]); self.deflab(t[2], self.here()); return self.complete_stmt(0)
        if k == C_SWITCH:                                      # [JMP end]  T: POP [JMP default]  end:
            if t[4] & 1: self.emit(JMP, 0, t[2])
            self.deflab(t[1], self.here()); self.emit(POP)
            if t[4] & 2: self.emit(JMP, 0, t[3])
            self.deflab(t[2], self.here()); return self.complete_stmt(0)
        if k == C_FUNCB:
            self.emit(PUSHI, 0); self.emit(RET, self.npar); self.deflab(t[2], self.nloc); self.deflab(t[1], self.here())
            self.curf = 0; self.nsym = self.fsym; self.mode = S_STMT; return
        return self.fail(55)

    def do_cond(self, t):
        """a do body (just popped) ended: the continue label; the entry stays for while (cond)"""
        self.deflab(t[1], self.here()); self.csp += 1; self.mode = S_DOWHILE

    def end_params(self):
        for i in range(self.npar):                           # param k of n sits at fp - 1 - n + k
            self.sym[self.fsym + i][3] = -1 - self.npar + i
        f = self.fn[self.cfn]                                # the calls so far must pass npar arguments (call_end)
        if f[4] and f[4] != self.npar + 1: return self.fail(76)
        f[4] = self.npar + 1
        self.emit(ENTER, 0, self.cs[self.csp - 1][2]); self.mode = S_LBRACE

    def end_array(self):
        self.data[self.arrstart] = self.dp - self.arrstart - 1; self.emit(PUSHI, self.arrstart + 1); self.mode = S_OPER

    # ---------------- whole program
    def compile(self, src):
        s = [ord(ch) for ch in src.rstrip('\n') + '\n'] + [0]
        for i in range(len(s)):
            self.char(s[i], s[i + 1] if i + 1 < len(s) else 0)
        return self.link()

    def link(self):
        if self.cp > 2 * SDATA - 1: self.fail(62)          # code area 4608..5118 (the page checks this in .fin)
        words = {}
        for a, (op, imm, lab) in self.code.items():
            if lab is not None:
                if lab >= NL or self.lab[lab] < 0: self.fail(60); imm = 0
                else: imm = self.lab[lab] % 8192
            words[self.cb + a] = op * 8192 + imm
        return words, dict(self.data)

# ---------------- simulator (= build.js run())
def run(rom, mem_init, sp0, out_base=None, cols=8, rows=16, max_steps=10 ** 6, strict=False, net=None):
    """strict: check the stack discipline the compiler promises: statements leave the stack as they found it, so sp
    never goes below sp0 (RuntimeError 'stack underflow') and is back at sp0 at HALT ('stack unbalanced').
    net: the NET instruction's gateway (default: net/device.py's, which serves tests/net/)"""
    if out_base is None: out_base = LAYOUT['out_base']
    if net is None: net = Device()
    mem = [0] * (AMASK + 1)
    for i, w in enumerate(rom): mem[i] = w
    for a, v in mem_init.items(): mem[a] = v
    pc, sp, fp, optr, steps, out = 0, sp0, sp0, 0, 0, []
    s20 = lambda x: (x + (1 << 19)) % (1 << 20) - (1 << 19)       # machine words: 20-bit two's complement
    ROMN = LAYOUT['rom_size']
    def rd(a): a &= AMASK; return mem[a] if a >= ROMN else 0
    def wr(a, v):
        a &= AMASK
        if a >= ROMN: mem[a] = s20(v)
    tdiv = lambda a, b: 0 if b == 0 else int(a / b)
    tmod = lambda a, b: 0 if b == 0 else a - b * int(a / b)
    while True:
        steps += 1
        if steps > max_steps: raise RuntimeError('step limit')
        if strict and sp < sp0 and pc >= LAYOUT['code_base']: raise RuntimeError(f'stack underflow at code word {pc - LAYOUT["code_base"]}')
        w = mem[pc]; op, imm = w // 8192, w % 8192; simm = imm - 8192 if imm >= 4096 else imm; pc += 1
        if op == 0: pass
        elif op == 1: mem[sp] = imm; sp += 1
        elif op == 2: mem[sp] = mem[imm]; sp += 1
        elif op == 3: sp -= 1; mem[imm] = mem[sp]
        elif op == 4: mem[sp] = mem[fp + simm]; sp += 1
        elif op == 5: sp -= 1; mem[fp + simm] = mem[sp]
        elif op == 6: a = mem[sp - 1]; mem[sp - 1] = mem[a & AMASK]
        elif op == 7: sp -= 1; b = mem[sp]; sp -= 1; a = mem[sp]; mem[a & AMASK] = b
        elif 8 <= op <= 20:
            sp -= 1; b = mem[sp]; a = mem[sp - 1]
            mem[sp - 1] = [s20(a + b), s20(a - b), s20(a * b), tdiv(a, b), tmod(a, b), int(a < b), int(a > b), int(a <= b), int(a >= b), int(a == b), int(a != b),
                           int(a != 0 and b != 0), int(a != 0 or b != 0)][op - 8]
        elif op == 21: mem[sp - 1] = int(mem[sp - 1] == 0)
        elif op == 22: mem[sp - 1] = s20(-mem[sp - 1])
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
        elif op == 32:
            if strict and sp != sp0: raise RuntimeError(f'stack unbalanced at HALT: sp - sp0 = {sp - sp0}')
            return steps, ''.join(map(chr, out))
        elif op == 33: sp -= 1; pc = mem[sp]
        elif op == 34: mem[sp - 1] = s20(mem[sp - 1] * 8192)
        elif op == 35: mem[imm] = s20(mem[imm] + 1)
        elif op == 36: mem[fp + simm] = s20(mem[fp + simm] + 1)
        elif op == 37: mem[sp - 1] = mem[(mem[imm] + mem[sp - 1]) & AMASK]
        elif op == 38: mem[sp - 1] = mem[(mem[fp + simm] + mem[sp - 1]) & AMASK]
        # objects (machine/uarch.py's microcode, instruction by instruction). Data reads below RAM give 0, writes there are lost.
        elif op in (SCANI, SCAN):                          # probe one key; execute again unless it stopped
            key = imm if op == SCANI else mem[KEYCELL]
            t3 = mem[sp - 1]; t2 = rd(t3)
            if t2 == key or t2 == 0: pass                  # found, or the keys end: the cursor stays on that word
            else: mem[sp - 1] = t2 if t2 < 0 else s20(t3 + 2); pc -= 1      # a link / the next pair
        elif op == LDF: mem[sp - 1] = rd(mem[sp - 1] + imm)
        elif op == PUTV:
            c = mem[sp - 2]
            if rd(c) != 0: wr(c + 1, mem[sp - 1]); sp -= 2
            else: wr(c + 1, pc - 1); pc = PUTVEC         # the append routine, [c, v]
        elif op == NEW:
            t2 = mem[HP]; t1 = mem[GCLIM]
            if s20(t2 - t1) < 0: mem[sp] = t2 + HEAP0 - OBJTAG; mem[HP] = t2 + 8
            else: mem[GCSP] = sp; mem[RETCELL] = pc - 1; pc = GCVEC
            sp += 1
        elif op == SETF: wr(mem[sp - 2] + imm, mem[sp - 1]); sp -= 1
        elif op == ENDK: wr(mem[sp - 1] + imm, 0); wr(mem[sp - 1] + imm + 1, 0)
        elif op == OVER: mem[sp] = mem[sp - 2]; sp += 1
        elif op == JNEG:
            if mem[sp - 2] < 0: pc = imm
        elif op == NET: mem[sp - 1] = s20(net(mem[sp - 1]))
        elif PRINT <= op <= PRINTBLN:
            sp -= 1; v = mem[sp]; p = v + STRTAG; sep = PRINT_SEP[op]
            if LAYOUT["data_base"] + SDATA <= p < LAYOUT["data_base"] + 2 * SDATA:   # a tagged string (data_base + SDATA: the lib's DONE marker, empty)
                text = []
                while p != LAYOUT["data_base"] + SDATA and mem[p] != 0: text.append(mem[p]); p += 1
            elif op % 2 == 0 and v in (0, 1): text = [ord(ch) for ch in ('true' if v else 'false')]
            else: text = [ord(ch) for ch in str(v)]
            for c in text + ([sep] if sep else []):
                if c == 10: optr = (optr // cols + 1) * cols % (cols * rows)
                else: mem[out_base + optr] = c; optr = (optr + 1) % (cols * rows)
                out.append(c)
        else: raise RuntimeError(f'bad op {op} at {pc - 1}')

def image_mem(c, words, data, init=None):
    """RAM as the CSS compiler leaves it: code words; strings in place; initialised globals/arrays staged at
    init (the lib's startup copies them into the data area), their count at init - 1"""
    if init is None: init = LAYOUT['init']
    mem = dict(words)
    sbase = c.db + SDATA
    for a, v in data.items():
        if a >= sbase: mem[a] = v
        else: mem[init + a - c.db] = v
    mem[init - 1] = c.dp - c.db
    mem[init] = STRTAG                  # the lib's untag constant, staged for data_base
    return mem

def compile_and_run(src, lib, max_steps=10 ** 6, strict=False):
    c = Compiler(LAYOUT['data_base'], LAYOUT['code_base'], lib)
    words, data = c.compile(src)
    if c.err: return c, None
    mem = image_mem(c, words, data, lib.get('init', 5120))
    return c, run(lib['rom'], mem, LAYOUT['sp0'], max_steps=max_steps, strict=strict)

def image(src, lib, ram=False):
    """The machine image every harness takes (gen_fvm4.py, uarch4, hbtest.py): ROM = the lib; RAM all zero (the page's
    compile chain supplies code and data), or with ram=True the program as the CSS compiler leaves it (CPU-only pages,
    the model, the font in uharfbuzz). steps/expected come from cc_ref's simulation."""
    L = LAYOUT
    c = Compiler(L['data_base'], L['code_base'], lib)
    words, data = c.compile(src)
    if c.err: raise ValueError(f'compile error {c.err}')
    mem = image_mem(c, words, data, lib['init'])
    r = run(lib['rom'], dict(mem), L['sp0'])
    if not ram: mem = {}
    return dict(rom=lib['rom'], romSize=L['rom_size'], ram=[mem.get(L['rom_size'] + i, 0) for i in range(L['ram_size'])],
                ramSize=L['ram_size'], sp0=L['sp0'], outBase=L['out_base'], rows=L['rows'], cols=L['cols'], source=src,
                codeBase=L['code_base'], init=L['init'], steps=r[0], expected=r[1])

if __name__ == '__main__':
    import json
    lib = json.load(open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'lib.json')))
    src = open(sys.argv[1]).read()
    c, r = compile_and_run(src, lib)
    print('err', c.err, 'code words', c.cp, 'data words', c.dp - LAYOUT['data_base'], 'labels', c.nlab)
    if r: print('steps', r[0], 'output:'); print(r[1])
