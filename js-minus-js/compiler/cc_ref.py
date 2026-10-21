#!/usr/bin/env python3
"""cc_ref.py — reference for the CSS compiler: a character-at-a-time pushdown transducer for a JS subset, generating
code for the register machine.

Written the way the CSS chain will compute it: one step per source character, fixed-size tables and stacks,
no recursion, no lookahead beyond the next character. Each step may complete one token; the parser handles it
(shunting-yard for expressions, a control stack for statements, symbol/function/label tables) and emits a few
instructions. Words that need an address not known yet carry a label id; labels are resolved after the last step.

Code generation. An operand of an expression is a descriptor on an operand stack (od): a variable, a constant, a value in
its temp, a big constant LOADK must load first, or a comparison a branch may take as it is. Code is emitted when an
operator pops (shunting-yard), as one three-address instruction reading the operands where they are:
- the last operator of an assignment's value writes the target directly (n = n + 1 is ADD n, n, #1);
- a comparison (or a !) popped last where a branch takes the value stays pending and fuses into the branch;
- an operand still on the stack is copied to its temp before something changes it: a global before a call, a variable
  before its ++ / --, every variable at the start of a conditional region (&&, ||, ?:), since a copy made inside one
  would be made on one path only; x op= e reads x first (it is the left operand);
- console.log's + chains keep their pieces on the operand stack and print them at the argument's end.

The machine (machine/csssim.py, machine/gen_css.py). An instruction is two words at an even address:
  word0 = op * 8192 + A        A: a destination operand, a jump target, flags or a count
  word1 = (B - 512) * 1024 + C B, C: source operands (10 bits each); LOADK, PRINTK and CALL use word1 whole
An operand o (10 bits) is a cell or a constant: 0 ... 255 a global (data_base + o); 256 ... 767 a frame slot (fp + o - 256);
768 ... 1023 the constant o - 896. A frame is [return word] fp, the parameters fp + 1 ..., the locals, then the temps: the
operand stack's slot d is T(d) = fp + 1 + npar + nloc + d, nloc the function's final count of locals (its frame label,
which the linker adds: times 1 in A, 1024 in B, 1 in C or CALL's word1). A call's slot T(d0) takes the return word and its
arguments go to T(d0 + 1) ...: CALL target, off (fp + off = T(d0)) writes off * 8192 + the return address there and adds off
to fp; RET v writes v over the return word, the caller's T(d0), and subtracts off again. Top-level code runs with fp = sp0.

Values: integers; a string is a tagged pointer (address - STRTAG), so console.log can tell it from a number at run time;
booleans are 0/1. Values are also typed statically (0 unknown, 1 boolean, 2 string, 3 number), each operand descriptor
with its type: comparisons, !, true/false, string literals, number literals and arithmetic, variables by their last
assignment, functions by their returns. Only booleans need it, to print as true / false (PRINT's boolean flag)."""
import sys, json, os

# the memory map (compiler/layout.json): ROM 0..rom_size-1 (the lib); RAM from rom_size = data_base; see layout.json's _doc
LAYOUT = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'layout.json')))
LAYOUT['out_base'] = LAYOUT['rom_size'] + LAYOUT['ram_size'] - LAYOUT['cols'] * LAYOUT['rows']
assert LAYOUT['data_base'] == LAYOUT['rom_size'], 'RAM index = address - rom_size = address - data_base (the compile chain relies on it)'
AMASK = 32767                           # addresses are 15-bit

# the register machine's instructions, in class order (machine/gen_css.py dispatches on the opcode's range)
OPN = ('ADD SUB MUL DIV MOD LT GT LE GE EQ NE  MOV NEG LOADK  JMP JLT JGT JLE JGE JEQ JNE HALT  JZ JNZ  CALL RET NOT '
       ' PRINT PRINTK PUTC').split()
OP = {n: i for i, n in enumerate(OPN)}
# operator codes on the parser's operator stack (and their precedences: prec)
NOP, PUSHI, LOADG, STOREG, LOADL, STOREL, LOADI, STOREI, ADD, SUB, MUL, DIV, MOD, LT, GT, LE, GE, EQ, NE, AND, OR, NOT, NEG = range(23)
NAME = {ADD: 'ADD', SUB: 'SUB', MUL: 'MUL', DIV: 'DIV', MOD: 'MOD', LT: 'LT', GT: 'GT', LE: 'LE', GE: 'GE', EQ: 'EQ', NE: 'NE',
        NOT: 'NOT', NEG: 'NEG'}
CMPS = (LT, GT, LE, GE, EQ, NE)
INV = {LT: GE, GE: LT, GT: LE, LE: GT, EQ: NE, NE: EQ}
SEP = {0: 0, 32: 1, 10: 2}              # PRINT / PRINTK's A: separator * 2 + boolean

# limits (= the CSS chain's fixed table sizes)
OD, CD, NS, NF, NL, NI = 8, 8, 32, 16, 64, 32  # NI: interned strings and property names
ODN = 10                                # the operand stack (its temps T(0) ... T(9))
EMAX = 6                                # instructions per step (12 code words)
NOTSUB = 90                             # a construct the register machine doesn't have yet
SDATA = 256                             # globals: data_base + 1 .. + SDATA - 1 (data_base itself holds STRTAG, for the lib)
STR0 = LAYOUT['data_base'] + SDATA      # the string area: STR0 (the lib's empty DONE marker) .. SEND
SEND = STR0 + LAYOUT['str_size']
# the string area's first strings, there before any program's: "true" and "false" ([len][bytes][0] each), for a boolean made a
# string (the ROM's b2s, tostr) without allocating. TRUEV / FALSEV: their values
SEED = [w for t in ('true', 'false') for w in [len(t)] + [ord(ch) for ch in t] + [0]]
SEED += [0] * (-len(SEED) % 4)          # (a multiple of 4: the program's strings keep their alignment to the cache's blocks)
TRUEV, FALSEV = STR0 + 2 - 262144, STR0 + 8 - 262144                 # (- STRTAG)
STRP0 = STR0 + 1 + len(SEED)            # the program's own strings start here
assert SEND == LAYOUT['code_base']
CODESZ = LAYOUT['init'] - 1 - LAYOUT['code_base']     # code words (init - 1 holds the staged-data count)
STRTAG = 262144                         # a string value is its address - STRTAG (machine words are 20-bit signed)
NOROOM = 8192                           # added to a string token's address when it didn't fit (addresses are 13-bit)
PARAM0 = 6144                           # parameter i's symbol address until its function's ')' (cc_dsl's encoding; above the globals)
OBJTAG = LAYOUT['objtag']
HEAP0 = LAYOUT['heap_lo']
HP, GCLIM, GCSP, KEYCELL, RETCELL = range(LAYOUT['rt_base'], LAYOUT['rt_base'] + 5)
ARRTAG = LAYOUT['arrtag']
HEAP_HI = HEAP0 + 2 * LAYOUT['heap_size']
STRV_LO, STRV_HI = LAYOUT['data_base'] + SDATA - STRTAG, HEAP_HI - STRTAG     # a value in [STRV_LO, STRV_HI) is a string
def isstr(v): return STRV_LO <= v < STRV_HI
def isarr(v): return HEAP0 <= v - ARRTAG < HEAP_HI
def isobj(v): return HEAP0 <= v + OBJTAG < HEAP_HI
def isref(v): return isstr(v) or isarr(v) or isobj(v)
def truthy(mem, v):
    """JZ / JNZ / NOT: 0 and the empty string are false (a string's length is the word before its value's address)"""
    return v != 0 and not (isstr(v) and mem[(v - 1) & AMASK] == 0)
def s20(x): return (x + (1 << 19)) % (1 << 20) - (1 << 19)       # machine words: 20-bit two's complement
H1M, H2M = 65521, 65519

# operand encodings (10-bit fields)
def L(off): return 256 + off            # frame slot fp + off
def K(v): return 896 + v                # constant -128 ... 127
def isK(o): return 768 <= o < 1024
# operand descriptors (od entries: type * 4096 + descriptor): an operand encoding (< 1024), KBIG (the value pk, LOADK must load it:
# only on top), TMP (the value is in this entry's temp), CND + cop * 4 + nloc flags of B and C (a pending comparison; B and C in
# pk as word1 packs them; only on top)
KBIG, TMP, CND = 1024, 1025, 1028
CNDOPS = CMPS + (NOT,)

def h1h2(s):
    a = b = 0
    for ch in s: a = (a * 31 + ord(ch)) % H1M; b = (b * 37 + ord(ch)) % H2M
    return a, b
# methods: (name, {argument count: the ROM entry (lib.json entries)}, static type of the result). They are ROM routines called with
# the receiver and the arguments on the stack; a string method and an array method may share a name (the routine looks)
METHODS = [('push', {1: 'push'}, 3), ('pop', {0: 'pop'}, 0), ('shift', {0: 'shift'}, 0), ('unshift', {1: 'unshift'}, 3),
           ('indexOf', {1: 'indexof'}, 3), ('includes', {1: 'includes'}, 1), ('join', {0: 'join0', 1: 'join'}, 2),
           ('slice', {0: 'slice0', 1: 'slice1', 2: 'slice'}, 0), ('concat', {1: 'concat'}, 0), ('reverse', {0: 'reverse'}, 0),
           ('charAt', {1: 'charat1'}, 2), ('charCodeAt', {1: 'charcode'}, 3), ('substring', {1: 'substr1', 2: 'substring'}, 2),
           ('toUpperCase', {0: 'upper'}, 2), ('toLowerCase', {0: 'lower'}, 2), ('split', {1: 'split'}, 0), ('trim', {0: 'trim'}, 2),
           ('startsWith', {1: 'startswith'}, 1), ('endsWith', {1: 'endswith'}, 1), ('repeat', {1: 'repeat'}, 2),
           ('fromCharCode', {1: 'fromcc'}, 2), ('lastIndexOf', {1: 'lastindexof'}, 3), ('fill', {1: 'fill'}, 0),
           ('toString', {0: 'tostring0'}, 2)]
# functions called like methods on a dummy receiver (0): parseInt(s), Number(s), String(x); their names are reserved
GLOBALS = [('parseInt', {1: 'parseint'}, 3), ('Number', {1: 'parseint'}, 3), ('String', {1: 'tostring'}, 2)]
ALLM = METHODS + GLOBALS
assert len(ALLM) < 64
KW = {k: h1h2(k) for k in ['var', 'let', 'const', 'if', 'else', 'while', 'for', 'return', 'function', 'putc', 'console', 'log',
                           'true', 'false', 'break', 'continue', 'do', 'null', 'switch', 'case', 'default', 'length', 'String']
                          + [m[0] for m in ALLM]}
METHOD_INDEX = {KW[m[0]]: i for i, m in enumerate(METHODS)}
GLOBAL_INDEX = {KW[m[0]]: len(METHODS) + i for i, m in enumerate(GLOBALS)}

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
def prec(code):
    return {MUL: 7, DIV: 7, MOD: 7, ADD: 6, M_CADD: 6, SUB: 6, LT: 5, GT: 5, LE: 5, GE: 5, EQ: 4, NE: 4, AND: 3, OR: 2, M_TELSE: 1,
            NOT: 8, NEG: 8}.get(code, 0)

# + at the top level of a console.log argument (value: the left operand's static type); precedence of +. M_PRINT's value: 2 after a
# ',' (until the next argument starts) + 4 * the pieces of a + chain already on the operand stack (PIECES at most)
M_CADD = 50
PIECES = 8
# c ? a : b is  c Jfalse L1  a -> T(i) JMP L2  L1: b -> T(i)  L2:. '?' pushes the marker M_TERN (value L1 + 64 * reuse); ':'
# replaces it with the operator M_TELSE (value L2 + 64 * the then-branch's static type), lowest precedence, whose pop moves the
# else value to T(i) and defines L2. In a chain a ? x : b ? y : z the inner ternary reuses the outer L2 (reuse: M_TELSE was on
# top at '?'), so at most one M_TELSE sits between markers.
M_TELSE = 51
# OPS markers (codes >= 100)
# M_ARR: an array literal (value: its elements so far); M_METH: a method call's arguments (value: method + 64 * commas)
M_PAREN, M_CALL, M_ARR, M_METH, M_PUTC, M_PRINT, M_TERN = 100, 101, 102, 103, 104, 105, 108
M_OBJ, M_OKEY, M_INDEX = 109, 110, 111
# control stack kinds. Bodies: IFB / ELSEB / LOOPB and DOB (a = continue target, b = break target; DOB c = the loop
# top) / FUNCB (a = the label past the function, b = its frame label: its count of locals); + BRACELESS: the body is a single
# statement, closed when that statement completes. A DOB stays on the stack through its while (cond): a ')' with a DOB on top
# can only end that condition. A function is declared at the program's top level, so its FUNCB is entry 0.
C_BLOCK, C_IFB, C_ELSEB, C_DOB, C_LOOPB, C_FUNCB = 1, 2, 3, 4, 5, 6
C_IFC, C_WHILEC, C_FORINIT, C_FORCOND, C_FORSTEP, C_ASSIGN, C_EXPR, C_RETURN = 10, 11, 12, 13, 14, 15, 16, 17
C_PSET = 19
C_SWITCHC, C_SWITCH, C_CASE = 30, 31, 32
BRACELESS = 20
C_IFB1, C_ELSEB1, C_DOB1, C_LOOPB1 = C_IFB + BRACELESS, C_ELSEB + BRACELESS, C_DOB + BRACELESS, C_LOOPB + BRACELESS
# parser modes
(S_STMT, S_OPND, S_OPER, S_NAMES, S_NAMEE, S_VAR, S_VARAFTER, S_LPAREN, S_LBRACE, S_ELSE, S_FNAME, S_FPAREN, S_FPARAM,
 S_FPSEP, S_CONDOT, S_CONLOG, S_CONLP, S_CONFIRST, S_INC, S_AFTERELSE, S_PREINC,
 S_DOWHILE, S_DOT, S_OKEY, S_OCOLON, S_SWCASE, S_ERR) = range(27)
# pm = 3 after x++ / ++x in an expression, which no '.' or '[' may follow.

def tmerge(a, b):
    """static type of a value that is one of two values of types a, b (?: && ||). A boolean with anything else is boolean: the
    boolean PRINT prints only 0 / 1 as false / true, and other numbers and strings as they are, so only a 0 or 1 from the
    other side misprints (unknown would misprint every boolean)"""
    return 1 if 1 in (a, b) else a if a == b else 0

class Compiler:
    def __init__(self, data_base, code_base, lib=None):
        """lib: the runtime library's entry addresses (lib.json)"""
        self.db, self.cb = data_base, code_base
        self.ent = (lib or {}).get('entries', {})   # the ROM routines compiled code calls
        # lexer. An identifier that may be a property name (after '.', '{' or ','; kpos 2 / 1 / 1) writes its bytes to the
        # string area at sdp, not committed; the level after it writes the NUL at inul. It is committed (sdp moves past it):
        # after '.' at once, after '{' or ',' when a ':' follows (icm: its length)
        self.lx = 0; self.q = 0; self.lt = 0; self.tkc = 0; self.acc = 0; self.h1 = 0; self.h2 = 0; self.p2 = 0; self.sstart = 0
        self.inul = 0; self.icm = 0; self.kpos = 0; self.lcon = 0; self.tid = 0; self.tlen = 0; self.tparen = 0; self.pnl = 0
        self.dp = data_base + 1             # globals (parser); data_base holds STRTAG
        self.sdp = data_base + SDATA + 1 + len(SEED)    # string literals and property names (lexer; after SEED); data_base + SDATA itself is the lib's
                                            # empty DONE marker, which PRINT stops at
        # parser
        self.mode = S_STMT; self.pn = (0, 0)
        self.ops = [0] * OD; self.opv = [0] * OD; self.osp = 0
        self.cs = [[0] * 6 for _ in range(CD)]; self.csp = 0                   # kind a b c d, e: nlet when pushed
        self.od = [0] * ODN; self.nd = 0; self.pk = 0                          # operand descriptors; pk: the big constant / pending comparison on top
        # symbols: h1 h2 kind(1 g, 2 l) addr type const. Two regions: function- and program-level names grow up from 0
        # (nsym), block-scoped let / const grow down from NS - 1 (nlet); closing a block restores nlet
        self.sym = [[0, 0, 0, 0, 0, 0] for _ in range(NS)]; self.nsym = 0; self.nlet = 0
        self.fn = [[0, 0, 0, 0, 0] for _ in range(NF)]; self.nfn = 0           # h1 h2 label type argc (+1; 0: no call or definition yet)
        self.lab = [-1] * NL; self.nlab = 0
        self.itab = [[0, 0, 0] for _ in range(NI)]; self.nint = 0             # interned strings and names: h1 h2 address
        self.cp = 0; self.curf = 0; self.cfn = 0; self.nfdef = 0; self.nloc = 0; self.npar = 0; self.fsym = 0    # fsym: nsym at function start
        self.pendLa = 0; self.err = 0; self.asic = 0; self.pm = 0
        self.code = {}; self.data = {}

    # ---------------- helpers
    def frame_label(self): return self.cs[0][2] if self.curf else None
    def emit(self, op, a=(0, 0), b=(512, 0), c=(0, 0), label=None, w1=None):
        """one instruction: op A, B, C, operands as (field, temp?) (a temp adds the frame label: times 1 in A, 1024 in B, 1 in
        C); or A and word1 whole (w1: a value, or (field, temp?) for CALL's offset). label: A is that label's value at link time"""
        fl = self.frame_label()
        if w1 is None: w, m = (b[0] - 512) * 1024 + c[0], 1024 * b[1] + c[1]
        elif isinstance(w1, tuple): w, m = w1
        else: w, m = w1, 0
        lab0 = label if label is not None else fl if a[1] else None
        self.code[self.cp] = (op, a[0], w, lab0, fl if m else None, m); self.cp += 1
    def newlab(self):
        if self.nlab >= NL: self.fail(20)
        self.nlab += 1; return self.nlab - 1
    def deflab(self, l, v):
        if l < NL: self.lab[l] = v                    # (a label past NL comes only after error 20)
    def here(self): return self.cb + 2 * self.cp
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
    def redecl(self, h):
        """the scope a declaration goes into (decl_blk) holds a name h already: the block's own let / const (from its control
        entry's mark), or the function's or program's names (its parameters included)"""
        if self.decl_blk(): js = range(NS - self.nlet, NS - self.top_cs()[5])
        else: js = range(self.fsym if self.curf else 0, self.nsym)
        return any((self.sym[j][0], self.sym[j][1]) == h for j in js)
    def decl_blk(self):
        """the declaration in progress is block-scoped: let / const (pn[0] 1 / 2) below the function or program level"""
        return int(self.pn[0] > 0 and self.csp > self.curf)
    def intern(self, h, addr, ln):
        """the interned string of hash h: its address, entering it (at addr) if new; -1 when the table is full. Every string
        and name in the string area is [length][bytes][0], its address that of the first byte: this copy's length word is
        written here (the lexer can't: it writes one word per character)"""
        self.datum(addr - 1, ln)
        for k in range(self.nint):
            if (self.itab[k][0], self.itab[k][1]) == h: return self.itab[k][2]
        if self.nint >= NI: self.fail(68); return -1
        self.itab[self.nint] = [h[0], h[1], addr]; self.nint += 1
        return addr
    def datum(self, a, v):
        if a < SEND: self.data[a] = v
    def loop_entry(self, brk):
        """the innermost loop (or, for break, switch) entry: a = its continue label, b = its break label"""
        for k in range(self.csp - 1, -1, -1):
            if self.cs[k][0] in (C_LOOPB, C_LOOPB1, C_DOB, C_DOB1) or (brk and self.cs[k][0] == C_SWITCH): return self.cs[k]
        return None

    # ---------------- operands
    def var(self, j):
        """symbol j's operand: a global, or a frame slot (parameter k at fp + 1 + k, its table address PARAM0 + k; local k after
        the parameters)"""
        k, a = self.sym[j][2], self.sym[j][3]
        return (L(a - PARAM0 + 1) if a >= PARAM0 else L(a)) if k == 2 else a - self.db
    def tmp(self, i): return (L(1 + self.npar * self.curf + i), self.curf)      # T(i): past the locals (+ the frame label)
    def desc(self, i): return self.od[i] % 4096
    def otype(self, i): return self.od[i] // 4096
    def set_od(self, i, d, t): self.od[i] = t * 4096 + d
    def push_od(self, d, t, k=0):
        """push a descriptor (k: a big constant's value). A big constant only stays pending on top: one below goes to its temp"""
        if self.nd >= ODN: return self.fail(22)
        if self.nd and self.desc(self.nd - 1) == KBIG: self.src(self.nd - 1)
        self.set_od(self.nd, d, t); self.nd += 1
        if d == KBIG: self.pk = k
    def push_num(self, v, t=3):
        v = s20(v)
        if -128 <= v < 128: self.push_od(K(v), t)
        else: self.push_od(KBIG, t, v)
    def src(self, i):
        """descriptor i as a source operand (field, temp?): a big constant is loaded into its temp first"""
        d = self.desc(i)
        if d == KBIG: self.emit('LOADK', self.tmp(i), w1=self.pk); self.set_od(i, TMP, self.otype(i)); d = TMP
        return self.tmp(i) if d == TMP else (d, 0)
    def put(self, dst, i):
        """the value of descriptor i into operand dst (field, temp?)"""
        if self.desc(i) == KBIG: self.emit('LOADK', dst, w1=self.pk)
        elif self.src(i) != dst: self.emit('MOV', dst, self.src(i))      # (a pending comparison only ever meets a branch)
    def to_temp(self, i):
        self.put(self.tmp(i), i); self.set_od(i, TMP, self.otype(i))
    def snapshot(self, hit, n=None):
        """operands still on the stack (below n) that a call or ++ / -- is about to change: copied to their temps first. At the
        start of a conditional region (&&, ||, ?:) every variable below is copied: a copy made inside it would be made on one
        path only"""
        for i in range(self.nd if n is None else n):
            d = self.desc(i)
            if d < 768 and hit(d): self.emit('MOV', self.tmp(i), (d, 0)); self.set_od(i, TMP, self.otype(i))
    def pend(self, i, cop, b, c):
        """descriptor i := the pending comparison b cop c (or ! b: cop NOT)"""
        self.set_od(i, CND + 4 * CNDOPS.index(cop) + 2 * b[1] + c[1], 1); self.pk = (b[0] - 512) * 1024 + c[0]
    def branch(self, lab, sense):
        """pop the top value and jump to lab if its truth is sense (a pending comparison fuses into the jump)"""
        i = self.nd - 1; d = self.desc(i); self.nd -= 1
        if d >= CND:
            cop = CNDOPS[(d - CND) // 4]; b = (self.pk // 1024 + 512, (d - CND) // 2 % 2); c = (self.pk % 1024, (d - CND) % 2)
            if cop == NOT: return self.emit('JZ' if sense else 'JNZ', b=b, label=lab)
            return self.emit('J' + NAME[cop if sense else INV[cop]], b=b, c=c, label=lab)
        if isK(d):                                       # a constant condition: jump or not, known now
            if (d != K(0)) == sense: self.emit('JMP', label=lab)
            return
        if d == KBIG and self.otype(i) != 2:
            if (self.pk != 0) == sense: self.emit('JMP', label=lab)
            return
        self.emit('JNZ' if sense else 'JZ', b=self.src(i), label=lab)

    def popops(self, minprec, mode=None):
        """pop and emit operators with precedence >= minprec. mode 'br': a comparison or ! popped last stays pending for the
        branch that takes the value; ('dest', o): an operator popped last writes operand o directly (an assignment's target).
        A big constant on top goes to its temp before the first pop (unless that pop splits a console.log + chain), so each pop
        emits at most one instruction"""
        if (self.osp and 0 < prec(self.ops[self.osp - 1]) >= minprec and self.nd and self.desc(self.nd - 1) == KBIG
                and not (self.ops[self.osp - 1] == M_CADD and 2 in (self.opv[self.osp - 1], self.otype(self.nd - 1)))): self.src(self.nd - 1)
        while not self.err and self.osp and 0 < prec(self.ops[self.osp - 1]) and prec(self.ops[self.osp - 1]) >= minprec:
            self.osp -= 1; code, val = self.ops[self.osp], self.opv[self.osp]
            last = not (self.osp and 0 < prec(self.ops[self.osp - 1]) >= minprec)
            dest = mode[1] if last and isinstance(mode, tuple) else None
            if code in (AND, OR):                       # the left operand is in T(i), tested; the right one joins it there
                i = self.nd - 2; self.put(self.tmp(i), i + 1); self.nd -= 1
                self.set_od(i, TMP, tmerge(val // 64, self.otype(i + 1))); self.deflab(val % 64, self.here())
            elif code == M_TELSE:                       # c ? a : b: a went to T(i); b joins it
                i = self.nd - 1; t = tmerge(val // 64, self.otype(i)); self.to_temp(i); self.set_od(i, TMP, t); self.deflab(val % 64, self.here())
            elif code == NOT and last and mode == 'br':
                i = self.nd - 1; self.pend(i, NOT, self.src(i), (0, 0))
            elif code in (NOT, NEG):
                i = self.nd - 1; b = self.src(i)
                if dest is None: self.emit(NAME[code], self.tmp(i), b); self.set_od(i, TMP, 1 if code == NOT else 3)
                else: self.emit(NAME[code], (dest, 0), b); self.set_od(i, dest, 1 if code == NOT else 3)
            elif code == M_CADD:                        # + at a console.log argument's top level: a string on either side splits it
                i = self.nd - 2
                if 2 in (val, self.otype(i + 1)): self.opv[self.osp - 1] += 4      # two pieces (M_PRINT is right below)
                else: self.binop(ADD, i, dest)
            else:
                if code == ADD and 2 in (val, self.otype(self.nd - 1)): return self.fail(NOTSUB)     # building a string
                self.binop(code, self.nd - 2, dest, mode == 'br' and last)

    def binop(self, code, i, dest, pend=False):
        if code in (LT, GT, LE, GE) and 2 in (self.otype(i), self.otype(i + 1)): return self.fail(NOTSUB)     # strings by their characters
        b, c = self.src(i), self.src(i + 1); self.nd -= 1
        t = 1 if code in CMPS else 3
        if pend and code in CMPS: self.pend(i, code, b, c)
        elif dest is None: self.emit(NAME[code], self.tmp(i), b, c); self.set_od(i, TMP, t)
        else: self.emit(NAME[code], (dest, 0), b, c); self.set_od(i, dest, t)

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
            flags = 2 * (SEP[sep] if i == self.nd - 1 else 0) + int(self.otype(i) == 1)
            if self.desc(i) == KBIG: self.emit('PRINTK', (flags, 0), w1=self.pk)
            else: self.emit('PRINT', (flags, 0), self.src(i))
        self.nd = d0

    def print_end(self):
        """console.log(...) ended. Its PRINTs printed every argument, so it leaves no value: it must be a statement of its own
        (C_EXPR, nothing else open)"""
        if self.osp or self.top_cs()[0] != C_EXPR: return self.fail(30)
        self.pop_cs(); self.mode = S_INC

    def call_end(self, tv, last):
        """a call's ')': its slot T(d0) (pushed at '(') takes the return word, the arguments are in T(d0 + 1) .... Our calls pass
        exactly as many words as the function takes, so every call and the definition must agree on the count (the first one
        seen sets it; 76 otherwise)"""
        k, argc = tv % 16, tv // 64 + last
        if last: self.to_temp(self.nd - 1)
        if self.fn[k][4] and self.fn[k][4] != argc + 1: return self.fail(76)
        self.fn[k][4] = argc + 1
        d0 = self.nd - argc - 1; f = self.tmp(d0)
        self.emit('CALL', label=self.fn[k][2], w1=(f[0] - 256, f[1]))
        self.nd = d0; self.push_od(TMP, (tv // 16) % 4)

    def asi_close(self, f):
        """'}' right after a statement without ';': end the statement (knowing the next token is not 'else'),
        then close the block"""
        self.asic = 1; f(); self.asic = 0
        if not self.err: self.close_block()

    def incdec(self, h, v, x=0):
        """++ (v 7) / -- (8) of a variable. x: 0 a statement, 1 ++x in an expression (its new value), 2 x++ (the old)"""
        j = self.lookup(h)
        if j < 0: return self.fail(6)
        if self.sym[j][5]: return self.fail(64)
        o = self.var(j)
        if x: self.snapshot(lambda q: q == o)
        if x == 2: self.push_od(o, 3); self.to_temp(self.nd - 1)
        self.emit('ADD' if v == 7 else 'SUB', (o, 0), (o, 0), (K(1), 0))
        if x == 1: self.push_od(o, 3)
        if x: self.pm = 3; self.mode = S_OPER
        else: self.mode = S_INC

    # ---------------- lexer: one character -> at most one token
    def sbyte(self, a, v):
        """a string-area word (an identifier's tentative bytes may run past the area: dropped, as on the page)"""
        if a < SEND: self.data[a] = v
    def shash(self, c):
        self.h1 = (self.h1 * 31 + c) % H1M; self.h2 = (self.h2 * 37 + c) % H2M
    def char(self, c, cn):
        tok = None; gap = 0                               # gap: a blank or the end of a comment (no token here)
        isal = lambda x: 65 <= x <= 90 or 97 <= x <= 122 or x in (95, 36)
        isdg = lambda x: 48 <= x <= 57
        if self.inul: self.sbyte(self.inul, 0)            # NUL after an identifier
        self.inul = 0
        if c == 0 and self.lx != 0: self.lx = 0; self.p2 = 0; tok = ('EOF', 0)    # unterminated string / comment
        elif self.lx == 1:                                # in a string
            if c == self.q:
                self.data[self.sdp] = 0; self.sdp += 1; self.lx = 0
                tok = ('STR', (self.sstart + NOROOM * int(self.sdp > SEND), self.h1, self.h2, self.sdp - 1 - self.sstart))
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
        elif c in (34, 39):                               # a string: its length word (the parser writes it), then its bytes (hashed)
            self.lx = 1; self.q = c; self.sdp += 1; self.sstart = self.sdp
            self.h1 = self.h2 = 0
        elif isal(c) or (isdg(c) and self.tkc == 1):      # an identifier: hashed; its bytes at sdp (acc: its length so far)
            if self.tkc != 1: self.h1 = self.h2 = 0; self.acc = 0
            self.shash(c); self.tkc = 1
            if self.kpos: self.sbyte(self.sdp + 1 + self.acc, c)      # (sdp itself: the length word)
            self.acc += 1
            if not (isal(cn) or isdg(cn)):
                tok = ('ID', (self.h1, self.h2)); self.tkc = 0; self.tlen = self.acc; self.tparen = int(cn == 40)   # (a call follows)
                self.tid = self.sdp + 1 + NOROOM * int(self.sdp + 1 + self.acc >= SEND)    # its address (+ NOROOM: no room)
                if self.kpos: self.inul = self.sdp + 1 + self.acc
                if self.kpos == 2: self.sdp += self.acc + 2
                self.icm = self.acc + 2 if self.kpos == 1 else 0
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
            if self.cp - cp0 > EMAX: self.fail(61)       # (instructions)

    def newline(self):
        """a newline (also in a comment): after return a T_NL at once; after another token that can end a statement, pending"""
        if self.lt == 2: return ('P', T_NL)
        if self.lt: self.pnl = 1
        return None

    # ---------------- parser: one token
    def token(self, kind, v):
        if self.err: return
        isP = lambda c: kind == 'P' and v == c
        isK_ = lambda k: kind == 'ID' and v == KW[k]
        m = self.mode
        if isP(T_NL) and m not in (S_NAMES, S_NAMEE, S_OPER, S_VARAFTER, S_INC, S_OPND): return
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
                elif h in GLOBAL_INDEX: return self.fail(NOTSUB)
                else:
                    self.snapshot(lambda q: q < 256)          # the callee may change a global still waiting on the stack
                    k = self.fnfind(h); self.push_op(M_CALL, k + 16 * self.fn[k][3]); self.push_od(TMP, 0)   # its slot
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
            if self.curf: self.emit('MOV', (self.var(j), 0), (K(0), 0))      # a local without a value: 0
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
            self.curf = 1; self.nloc = 0; self.npar = 0; self.fsym = self.nsym
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
                self.osp -= 1; self.emit('PUTC', b=(K(10), 0)); return self.print_end()
            self.opv[self.osp - 1] = 0
            m = self.mode = S_OPND
        if m in (S_DOT, S_OKEY, S_OCOLON, S_SWCASE): return self.fail(NOTSUB)
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
                if self.err: return
                t, tv = self.top_op()
                if op == ADD and t == M_PRINT and (tv >= 4 or self.otype(self.nd - 1) == 2):   # "..." + x in console.log: a piece
                    self.opv[self.osp - 1] = tv + 4; self.mode = S_OPND; return
                if op == ADD: self.push_op(M_CADD if t == M_PRINT else ADD, self.otype(self.nd - 1)); self.mode = S_OPND; return
                if prec(op) <= prec(ADD) and t == M_PRINT and tv >= 4: return self.fail(NOTSUB)     # pieces joined: a built string
                if op in (AND, OR):                           # a: tested in its temp; b joins it there (popops)
                    i = self.nd - 1; lt = self.otype(i); l = self.newlab(); self.to_temp(i); self.snapshot(lambda q: True, i)
                    self.emit('JZ' if op == AND else 'JNZ', b=self.tmp(i), label=l)
                    self.push_op(op, l + 64 * lt); self.mode = S_OPND; return
                self.push_op(op, self.otype(self.nd - 1)); self.mode = S_OPND; return
            if isP(63):                                        # c ? a : b
                self.popops(2, 'br')
                if self.err: return
                t, tv = self.top_op()
                if t == M_PRINT and tv >= 4: return self.fail(NOTSUB)
                self.snapshot(lambda q: True, self.nd - 1)
                l = self.newlab(); self.branch(l, False); self.push_op(M_TERN, l + 64 * int(t == M_TELSE)); self.mode = S_OPND; return
            if isP(58):
                self.popops(1)
                if self.err: return
                t, tv = self.top_op()
                if t != M_TERN: return self.fail(67)
                self.osp -= 1; i = self.nd - 1; lbt = self.otype(i); self.to_temp(i); self.nd -= 1
                if tv >= 64:
                    ev = self.opv[self.osp - 1]; self.emit('JMP', label=ev % 64)
                    self.opv[self.osp - 1] = ev % 64 + 64 * tmerge(ev // 64, lbt)
                else:
                    l2 = self.newlab(); self.emit('JMP', label=l2); self.push_op(M_TELSE, l2 + 64 * lbt)
                self.deflab(tv % 64, self.here()); self.mode = S_OPND; return
            if isP(46) or isP(91): return self.fail(NOTSUB)
            if isP(93): return self.fail(45)
            if isP(41) or isP(44):
                self.popops(1, self.end_mode(v))
                if self.err: return
                t, tv = self.top_op()
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
                return self.asi_close(lambda: (self.popops(1, self.dest_ctx()), self.err or self.end_expr_stmt('P', T_NL)))
            if isP(59) or isP(T_NL):
                self.popops(1, self.end_mode(59))
                if self.err: return
                if self.osp: return self.fail(47)
                return self.end_expr_stmt(kind, v)
            return self.fail(48)
        return self.fail(99)

    # ---- an expression ended at statement level (';' or ')' or ','): what was it for?
    def end_expr_stmt(self, kind, v):
        isP = lambda c: kind == 'P' and v == c
        t = self.top_cs(); k = t[0]
        if k == C_IFC and isP(41):
            self.pop_cs(); la = self.newlab(); self.branch(la, False); self.push_cs(C_IFB, la); self.mode = S_LBRACE; return
        if k in (C_DOB, C_DOB1) and isP(41):
            # the statement ends at ')': JavaScript inserts a ';' here even without a newline, and a ';' that follows
            # is an empty statement (so `if (a) do s; while (c); else ...` is rejected)
            self.pop_cs(); self.branch(t[3], True); self.deflab(t[2], self.here()); return self.complete_stmt(0)
        if k == C_WHILEC and isP(41):
            self.pop_cs(); le = self.newlab(); self.branch(le, False); self.push_cs(C_LOOPB, t[1], le); self.mode = S_LBRACE; return
        if k == C_FORCOND and isP(59):                         # t: l1 le lb l2. The test jumps into the body; else out
            self.pop_cs(); self.branch(t[3], True); self.emit('JMP', label=t[2]); self.deflab(t[4], self.here())
            self.push_cs(C_FORSTEP, t[1], t[2], t[3], t[4], e=t[5]); self.mode = S_STMT; return
        if k == C_ASSIGN:                                      # t: symbol, compound op, from a declaration
            self.pop_cs(); o = (self.var(t[1]), 0); i = self.nd - 1
            if t[2]:                                           # (a snapshot replaced x below e if e changed it)
                if self.otype(i) == 2 or self.otype(i - 1) == 2: return self.fail(NOTSUB)
                self.emit(NAME[t[2]], o, self.src(i - 1), self.src(i)); self.sym[t[1]][4] = 3; self.nd -= 1
            else: self.put(o, i); self.sym[t[1]][4] = self.otype(i)
            self.nd -= 1
            if isP(44) and t[3]: self.pn = (t[3] - 1, 0); self.mode = S_VAR; return     # var a = 1, b ...
            return self.end_simple_stmt(kind, v)
        if k == C_EXPR:
            self.pop_cs(); self.nd -= 1; return self.end_simple_stmt(kind, v)
        if k == C_RETURN and (isP(59) or isP(T_NL)):
            self.pop_cs(); i = self.nd - 1
            if self.otype(i): self.fn[self.cfn][3] = self.otype(i)
            self.emit('RET', b=self.src(i)); self.nd -= 1; return self.complete_stmt(0)
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
            self.pop_cs(); self.emit('JMP', label=t[1]); self.deflab(t[3], self.here())
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
            elif k == C_LOOPB1: self.emit('JMP', label=t[1]); self.deflab(t[2], self.here())
            elif nonelse or self.asic: self.deflab(t[1], self.here())
            else: self.pendLa = t[1]; self.mode = S_ELSE; return

    def close_block(self):
        if not self.csp: return self.fail(54)
        t = self.pop_cs(); k = t[0]; self.nlet = t[5]
        if k == C_BLOCK: return self.complete_stmt(0)
        if k == C_IFB: self.pendLa = t[1]; self.mode = S_ELSE; return
        if k == C_ELSEB: self.deflab(t[1], self.here()); return self.complete_stmt(0)
        if k == C_DOB: return self.do_cond(t)
        if k == C_LOOPB: self.emit('JMP', label=t[1]); self.deflab(t[2], self.here()); return self.complete_stmt(0)
        if k == C_FUNCB:                                   # (still inside: the RET's frame label)
            self.emit('RET', b=(K(0), 0)); self.deflab(t[2], self.nloc); self.deflab(t[1], self.here())
            self.curf = 0; self.nsym = self.fsym; self.mode = S_STMT; return
        return self.fail(55)

    def do_cond(self, t):
        """a do body (just popped) ended: the continue label; the entry stays for while (cond)"""
        self.deflab(t[1], self.here()); self.csp += 1; self.mode = S_DOWHILE

    def end_params(self):
        f = self.fn[self.cfn]                                # the calls so far must pass npar arguments (call_end)
        if f[4] and f[4] != self.npar + 1: return self.fail(76)
        f[4] = self.npar + 1; self.mode = S_LBRACE

    # ---------------- whole program
    def compile(self, src):
        s = [ord(ch) for ch in src.rstrip('\n') + '\n'] + [0]
        for i in range(len(s)):
            self.char(s[i], s[i + 1] if i + 1 < len(s) else 0)
        return self.link()

    def words_ir(self):
        """the code as the CSS compiler emits it: {address: (word without labels, label id or None, its multiplier)}"""
        out = {}
        for i, (op, a, w, lab0, lab1, m) in self.code.items():
            out[self.cb + 2 * i] = (OP[op] * 8192 + a, lab0, 1)
            out[self.cb + 2 * i + 1] = (w, lab1, m)
        return out

    def link(self):
        if 2 * self.cp > CODESZ: self.fail(62)                # (the page checks this in .fin)
        words = {}
        for a, (w, lab, m) in self.words_ir().items():
            if lab is not None:
                if lab >= NL or self.lab[lab] < 0: self.fail(60)
                else: w += m * self.lab[lab]
            words[a] = w
        return words, dict(self.data)

# ---------------- simulator
def run(rom, mem_init, sp0, out_base=None, cols=8, rows=16, max_steps=10 ** 6, strict=False, trace=None):
    """the register machine from code_base (fp = sp0) on a RAM image; returns (steps, output). strict: fp is back at sp0 at HALT"""
    if out_base is None: out_base = LAYOUT['out_base']
    mem = [0] * (AMASK + 1)
    romw = [w or 0 for w in rom]       # instructions only: a data read below RAM gives 0 (the page has no ROM leaves)
    for a, v in mem_init.items(): mem[a] = v
    db, ROMN = LAYOUT['data_base'], LAYOUT['rom_size']
    pc, fp, optr, steps, out = LAYOUT['code_base'], sp0, 0, 0, []
    def addr(o): return (db + o if o < 256 else fp + o - 256) & AMASK
    def rd(a): a &= AMASK; return mem[a] if a >= ROMN else 0
    def val(o): return o - 896 if o >= 768 else rd(addr(o))
    def wr(a, v):
        a &= AMASK
        if a >= ROMN: mem[a] = s20(v)
    def emit(c):
        nonlocal optr
        if c == 10: optr = (optr // cols + 1) * cols % (cols * rows)
        else: mem[out_base + optr] = c; optr = (optr + 1) % (cols * rows)
        out.append(c)
    tdiv = lambda a, b: 0 if b == 0 else int(a / b)
    tmod = lambda a, b: 0 if b == 0 else a - b * int(a / b)
    ALU = {'ADD': lambda a, b: a + b, 'SUB': lambda a, b: a - b, 'MUL': lambda a, b: a * b, 'DIV': tdiv, 'MOD': tmod,
           'LT': lambda a, b: int(a < b), 'GT': lambda a, b: int(a > b), 'LE': lambda a, b: int(a <= b), 'GE': lambda a, b: int(a >= b),
           'EQ': lambda a, b: int(a == b), 'NE': lambda a, b: int(a != b)}
    while True:
        steps += 1
        if steps > max_steps: raise RuntimeError('step limit')
        w0, w1 = (romw[pc], romw[pc + 1]) if pc < len(romw) else (mem[pc], mem[pc + 1])
        op = OPN[w0 // 8192]; a = w0 % 8192; b = w1 // 1024 + 512; c = w1 % 1024
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
        elif op == 'HALT':
            if strict and fp != sp0: raise RuntimeError(f'frame unbalanced at HALT: fp - sp0 = {fp - sp0}')
            return steps, ''.join(map(chr, out))
        elif op[0] == 'J': pc = a if ALU[op[1:]](val(b), val(c)) else pc
        elif op == 'CALL': wr(fp + w1, w1 * 8192 + pc); fp += w1; pc = a
        elif op == 'RET': r = mem[fp]; wr(fp, val(b)); fp -= r // 8192; pc = r % 8192
        elif op in ('PRINT', 'PRINTK'):
            v = val(b) if op == 'PRINT' else w1; sep = (0, 32, 10)[a // 2]
            if isstr(v):                                   # a literal or a heap string (data_base + SDATA: the lib's DONE marker, empty)
                p = v + STRTAG; text = []
                while p != db + SDATA and mem[p] != 0: text.append(mem[p]); p += 1
            elif a % 2 and v in (0, 1): text = [ord(ch) for ch in ('true' if v else 'false')]
            else: text = [ord(ch) for ch in str(v)]
            for ch in text + ([sep] if sep else []): emit(ch)
        elif op == 'PUTC': emit(val(b))
        else: raise RuntimeError(f'bad op {op} at {pc - 2}')

def image_mem(c, words, data, init=None):
    """RAM as the CSS compiler leaves it: code words; strings in place; the globals' count at init - 1"""
    if init is None: init = LAYOUT['init']
    mem = dict(words)
    sbase = c.db + SDATA
    for a, v in data.items(): mem[a] = v
    mem[init - 1] = c.dp - c.db
    assert all(a >= sbase for a in data), 'nothing is staged: globals start at 0'
    mem[c.db] = STRTAG                  # the untag constant at data_base (read only: an overlay on the page)
    for i, w in enumerate(SEED): mem[sbase + 1 + i] = w
    mem[LAYOUT['strend']] = c.sdp       # the string area's end (the runtime looks string keys up in it)
    return mem

def compile_and_run(src, lib, max_steps=10 ** 6, strict=False):
    c = Compiler(LAYOUT['data_base'], LAYOUT['code_base'], lib)
    words, data = c.compile(src)
    if c.err: return c, None
    mem = image_mem(c, words, data, lib.get('init', LAYOUT['init']))
    return c, run(lib['rom'], mem, LAYOUT['sp0'], max_steps=max_steps, strict=strict)

def image(src, lib, ram=False):
    """The machine image every harness takes (gen_css.py, csssim.py, the C2 pages): ROM = the lib; RAM all zero (the page's
    compile chain supplies code and data), or with ram=True the program as the CSS compiler leaves it (CPU-only pages,
    the CSS CPU's model). steps/expected come from cc_ref's simulation."""
    La = LAYOUT
    c = Compiler(La['data_base'], La['code_base'], lib)
    words, data = c.compile(src)
    if c.err: raise ValueError(f'compile error {c.err}')
    mem = image_mem(c, words, data, lib.get('init', La['init']))
    r = run(lib['rom'], dict(mem), La['sp0'])
    if not ram: mem = {}
    return dict(rom=lib['rom'], romSize=La['rom_size'], ram=[mem.get(La['rom_size'] + i, 0) for i in range(La['ram_size'])],
                ramSize=La['ram_size'], sp0=La['sp0'], outBase=La['out_base'], rows=La['rows'], cols=La['cols'], source=src,
                codeBase=La['code_base'], init=La.get('init'), steps=r[0], expected=r[1])

def disasm(words, base=None):
    """the instructions of a {address: word} map, as text lines"""
    out = []
    for a in sorted(words)[::2]:
        w0, w1 = words[a], words.get(a + 1, 0); op = OPN[w0 // 8192]; A = w0 % 8192; b = w1 // 1024 + 512; c = w1 % 1024
        def o(x): return f'#{x - 896}' if x >= 768 else f'F{x - 256}' if x >= 256 else f'G{x}'
        if op in ('LOADK', 'PRINTK', 'CALL'): args = f'{o(A) if op == "LOADK" else A}, {w1}'
        elif op in ('JMP', 'HALT'): args = f'{A}'
        elif op[0] == 'J': args = f'{A}, {o(b)}' + ('' if op in ('JZ', 'JNZ') else f', {o(c)}')
        elif op in ('MOV', 'NEG', 'NOT'): args = f'{o(A)}, {o(b)}'
        elif op == 'PRINT': args = f'{A}, {o(b)}'
        elif op in ('PUTC', 'RET'): args = o(b)
        else: args = f'{o(A)}, {o(b)}, {o(c)}'
        out.append(f'{a:5} {op:6} {args}')
    return out

if __name__ == '__main__':
    lib = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib.json')))
    src = open(sys.argv[1]).read()
    c, r = compile_and_run(src, lib)
    print('err', c.err, 'instructions', c.cp, 'data words', c.dp - LAYOUT['data_base'], 'labels', c.nlab)
    if '-d' in sys.argv: print('\n'.join(disasm(c.link()[0])))
    if r: print('steps', r[0], 'output:'); print(r[1])
