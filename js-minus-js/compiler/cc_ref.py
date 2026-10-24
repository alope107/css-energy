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
  word0 = op * 8192 + A        A: a destination operand, a jump target (an instruction pair's index: its address / 2), flags
                               or a count
  word1 = (B - 512) * 1024 + C B, C: source operands (10 bits each); LOADK, PRINTK and CALL use word1 whole
An operand o (10 bits) is a cell or a constant: 0 ... 255 a global (data_base + o); 256 ... 767 a frame slot (fp + o - 256);
768 ... 1023 the constant o - 896. A frame is [return word] fp, the parameters fp + 1 ..., the locals, then the temps: the
operand stack's slot d is T(d) = fp + 1 + npar + nloc + d, nloc the function's final count of locals (its frame label,
which the linker adds: times 1 in A, 1024 in B, 1 in C or CALL's word1). A call's slot T(d0) takes the return word and its
arguments go to T(d0 + 1) ...: CALL target, off (fp + off = T(d0)) writes off * 8192 + the return address / 2 there and adds off
to fp; RET v writes v over the return word, the caller's T(d0), and subtracts off again. Top-level code runs with fp = sp0.

Values: integers; a string is a tagged pointer (address - STRTAG), so console.log can tell it from a number at run time;
booleans are 0/1. Values are also typed statically (0 unknown, 1 boolean, 2 string, 3 number), each operand descriptor
with its type: comparisons, !, true/false, string literals, number literals and arithmetic, variables by their last
assignment, functions by their returns. Only booleans need it, to print as true / false (PRINT's boolean flag)."""
import sys, json, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'net'))
from device import Device

# the memory map (compiler/layout.json): ROM 0..rom_size-1 (the lib); RAM from rom_size = data_base; see layout.json's _doc
LAYOUT = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'layout.json')))
OUTMAX = LAYOUT['repl_cols'] * LAYOUT['repl_rows']    # the console's grid: cols x rows, on the REPL repl_cols x repl_rows
LAYOUT['out_base'] = LAYOUT['rom_size'] + LAYOUT['ram_size'] - LAYOUT['console_words']
assert OUTMAX + LAYOUT['marks'] <= LAYOUT['console_words']
# the REPL's output marks follow the console's largest grid (PUTC with A = 1 + k: mark k := the output position + 1): mark L for the
# entry that starts on line L, MARKEND for the program's end
NMARK = LAYOUT['marks']; MARKEND = NMARK - 1
assert LAYOUT['data_base'] == LAYOUT['rom_size'], 'RAM index = address - rom_size = address - data_base (the compile chain relies on it)'
AMASK = 32767                           # addresses are 15-bit

# the register machine's instructions, in class order (machine/gen_css.py dispatches on the opcode's range)
OPN = ('MOV NEG LOADK GETFP KIND  JMP JLT JGT JLE JGE JEQ JNE JLEQ JLNE JNLT JNGT JNLE JNGE HALT  JZ JNZ  CALL RET NOT TENTER '
       ' LDI STI  DADD DSUB DMUL DDIV DMOD DLT DGT DLE DGE DEQ DNE DLEQ DLNE DBIT DNEG NUMLIT  GETX SETX  GETP SETP NEW  PRINT PRINTK PUTC  CALLV  ALLOC'
       '  APUSH  MCPY MUPPER MLOWER MFILL NPUT  MCMP MFEQ MFREF MWALK  NET'
       '  FLD FADD FSUB FMUL FDIV FMOD FPOW FSQRT FFLOOR FCEIL FROUND FTRUNC FABS FTPLO FSCALE FP10 FCONST FEXP FLOG FSIN FCOS FTAN'
       '  FNORM FINT FCMP FEXPO FLOG10 FDIGIT  FCOK FCDIG  FAND FOR FXOR FSHL FSHR FUSHR  ADD SUB MUL DIV MOD LT GT LE GE EQ NE').split()
# The FPU (the runtime library's): a number line is 4 words at an aligned address (fline): w0 = s * (E + 1100) for a finite
# nonzero s * M * 2^(E - 52) (E in -1022 ... 1023; M = w1 * 2^36 + w2 * 2^18 + w3 < 2^53, >= 2^52 unless subnormal), s for +-0,
# s * 3000 for +-Infinity, 4000 for NaN. A boxed double is an 8-word heap block [header 0 0 0 | its number line], its value the
# line's address - DBLTAG. FLOPS A, B, C: the line at A's value := op of the numbers B and C (an integer, NaN, +-Infinity, -0, or
# a double: its line); FVOPS A, B, C: A := a value (FNORM: B as the machine's value: an integer, a special, or B itself, a double; FINT:
# B truncated, a plain integer of the machine's range (-0 is 0);
# FCMP: -1 / 0 / 1, 2 unordered; FEXPO: B's binary exponent E; FLOG10: floor(log10 |B|); FDIGIT: B's decimal digit C, 0 the ones).
# NUMLIT A, word1 (user code): A is a number literal's cache (a global); undefined: the library's numlit parses the string word1 into it
# (word1 >= 16: a function's value, made every time: numlit ignores the cache)
FLOPS = OPN[OPN.index('FLD'):OPN.index('FNORM')]
FVOPS = OPN[OPN.index('FNORM'):OPN.index('FDIGIT') + 1]
# the shortest-digits search's (numstr) instructions, a class of their own: FCOK A, B, C: A = 1 if the candidate at decimal scale C
# (0 ... 22: the integer c nearest B * 10^C, B > 0 a double below 2^53) reads back as B; FCDIG A, B, C: the line at A := c's
# 5-digit limbs [c mod 1e5, ..., c / 1e15] (fcand: exact, with the two-product's low part)
FDOPS = ('FCOK', 'FCDIG')
# the bitwise operators' (a class of their own): FAND ... FUSHR A, B, C: the line at A := B op C, B and C as 32-bit integers
# (JavaScript's ToInt32; >>> ToUint32), the result an integer (a double for the machine when out of its range)
FBOPS = ('FAND', 'FOR', 'FXOR', 'FSHL', 'FSHR', 'FUSHR')
FLINE_I, FVAL_I = FLOPS + ['FCDIG'] + list(FBOPS), FVOPS + ['FCOK']      # __fl's and __fv's ops by index
FCONSTS = ('pi', 'e', 'ln2', 'ln10', 'log2e', 'log10e', 'sqrt2', 'sqrt1_2')
NFLINES = 14                            # the runtime's scratch number lines at fpu_base; then its digit buffer (20 words) and two cells
FSCR = 100                              # in an FPU instruction the constant operands 100 ... 113 are the scratch lines (no LOADK)
DIGS = LAYOUT['fpu_base'] + 4 * NFLINES
def fscr(o):
    """an FPU operand field's scratch line address, or None"""
    return LAYOUT['fpu_base'] + 4 * (kval(o) - FSCR) if isK(o) and FSCR <= kval(o) < FSCR + NFLINES else None
assert DIGS + 22 <= LAYOUT['sp0']
# (user code's instructions come first: word0 = op * 8192 + A must stay below 2^19, the CSS CPU's registers' range; the ones only
# the runtime library uses (the raw arithmetic, the primitives) may lie above)
USEROPS = OPN.index('ALLOC')            # the first that only the runtime library uses
assert USEROPS <= 64
# CALLV A, off (word1): a call of the value in the frame's slot fp + off (the return word's), A arguments above it: a function
# whose meta (its parameters) is A is entered here as CALL enters; anything else traps to the library's callv (frame at
# TRAPOFF), which pads missing parameters with undefined (or reports a TypeError) and enters the function itself
# NET A, B: A = the network gateway's answer to the word B (net/device.py), every part's bytes left in RBUF0 … (netw); the
# lib's fetch(url) / read() are made of it (the ROM reaches it as __net)
# The runtime's primitives (the ROM reaches them through intrinsics; the CSS CPU runs them a cache line per execution):
# KIND A, B, k: A = kind test k of B (KINDS). ALLOC A, n, k: a new block (ALLOCK: a string of n bytes, its header, length and
# NUL written, A its value; an array of capacity n, its first line written, A its value; n raw words or an object chunk's, A
# their address), marked in the collector's map (but raw ones); the heap full: the ROM's galloc collects and the ALLOC executes again. MCPY A, B, C:
# C words from B to A (A <= B if they overlap; MUPPER / MLOWER mapping letters' case; MFILL: the value B); NPUT A, B: B's
# decimal digits at A. MCMP A, B, C: A = the first i < A where B[i] != C[i], else A (MFEQ: B[i] == C; MFREF: B[i] refers into
# the from-space at C; MWALK: through [len][bytes][0] strings from B, the offset of the first of length A, or of the first at
# or past C). APUSH 0, B, C: B.push(C) and return, as the ROM's push routine's first instruction (no array, or a full one:
# on to the next instruction)
KINDS = ['code', 'str', 'arr', 'obj', 'ao', 'notown', 'nlen', 'ref', 'heap', 'typeof', 'special', 'smi', 'dbl', 'fun', 'num']
ALLOCK = ['str', 'arr', 'raw', 'chunk', 'dbl']
# LDI A, B, C: A = mem[B + C]; STI A, B, C: mem[A + B] = C (raw memory: the runtime library's peek, poke and p[i]); GETFP A: A = fp.
# The dynamic operators (user code's arithmetic and comparisons): DADD ... DMOD A, B, C, DNEG A, B and DLT ... DNE compute two
# integers here (a result in range, not -0), DEQ / DNE also compare by identity anything but two strings or NaN, and DADD
# joins a string with a string, an integer or a special (the cat class); anything else traps into the runtime library. The
# jumps JLT ... JNE in user code likewise: two integers here (JEQ / JNE: as DEQ / DNE), else the library's jcmp, which
# decides the jump. GETX A, B, C: A = B[C] (an array inside its length here, else the library);
# GETP A, B, C: A = B.key (C: the key's string-area offset; one execution per pair it probes); NEW A: a new object. SETX A, B, C:
# A[B] = C (an array inside its length here); SETP A, B, C: A.key = B (C the key; a new key in the chunk here, a full chunk in the
# library). A trap is a call into the library: a dest trap's frame is its destination, a temp, so the routine's value lands there;
# SETX / SETP's frame is at TRAPOFF (the CSS CPU writes a trap's frame one word per execution, its arguments then the return word).
# PRINT of an array or an object jumps to pstub with its own address (the CSS CPU keeps it in pst), whose TENTER A writes the
# return word at fp + TRAPOFF (pst + 2) and calls A, ptrap, which decodes the PRINT's operand itself (the out class writes no
# memory). TRAPS names each trapping instruction's routine (lib.json entries)
TRAPOFF = 60
# a dynamic operator's trap (its destination may be any variable): the frame at fp + TRAPDEF, the return to the instruction
# itself, and RET from a frame at that offset leaves pst = 1, which makes the instruction move the routine's value (the
# frame's return word) into A
TRAPDEF = 61
WBACK = 512                             # (the CSS CPU's pst for that move: a trap's own executions count from 1)
TRAPS = {'DADD': 'dadd', 'DSUB': 'dsub', 'DMUL': 'dmul', 'DDIV': 'ddiv', 'DMOD': 'dmod', 'DNEG': 'dneg',
         'DLT': 'dlt', 'DGT': 'dgt', 'DLE': 'dle', 'DGE': 'dge', 'DEQ': 'deq', 'DNE': 'dne', 'DLEQ': 'dleq', 'DLNE': 'dlne',
         'DBIT': 'dbit', 'GETX': 'getx', 'SETX': 'setx', 'SETP': 'setp', 'CALLV': 'callv', 'NEW': 'gcnew', 'PRINT': 'pstub', 'ALLOC': 'galloc', 'JLT': 'jcmp'}
# a string's + that finds the heap full (the cat class's trap): the routine collects, then joins
CATTRAPS = {'DADD': 'gccat'}
OP = {n: i for i, n in enumerate(OPN)}
DYNOPS = ('DADD', 'DSUB', 'DMUL', 'DDIV', 'DMOD', 'DLT', 'DGT', 'DLE', 'DGE', 'DEQ', 'DNE', 'DLEQ', 'DLNE', 'DNEG', 'DBIT')
# DBIT A + 1024 k, B, C: the bitwise operator k (BITOPS: & | ^ << >> >>>) of B and C (~x is x ^ -1); k 7 always traps: RETC B, C,
# the return of a function that makes closures (RET's label turns it into this: the library's retc closes its env cell C)
JCMPS = ('JLT', 'JGT', 'JLE', 'JGE', 'JEQ', 'JNE', 'JLEQ', 'JLNE', 'JNLT', 'JNGT', 'JNLE', 'JNGE')
# JNLT ... JNGE jump when the comparison is false: with NaN a comparison's negation is no comparison (!(x < y) isn't y <= x)
def dyn_fast(op, x, y, k=0):
    """a dynamic operator's (or a jump's: J... as D...) result in user code when the machine computes it, else None (the trap).
    Two integers: a result that is one (and not -0); DEQ / DNE: identity unless both are strings or one is NaN (-0 is 0);
    DLEQ / DLNE (==, !=): that, with null == undefined and a boolean as 1 / 0, unless a string or one object is involved"""
    if isdbl(x) or isdbl(y): return None                 # (a double: the library)
    if op in ('DLEQ', 'DLNE'):
        if isstr(x) or isstr(y) or (isarr(x) or isobj(x)) != (isarr(y) or isobj(y)): return None
        nul = lambda v: v in (NULL, UNDEF)
        norm = lambda v: 1 if v == TRUE else 0 if v in (FALSE, MZERO) else v
        e = (nul(x) and nul(y)) if nul(x) or nul(y) else x != NAN and norm(x) == norm(y)
        return jsb(e == (op == 'DLEQ'))
    if op in ('DEQ', 'DNE'):
        if isstr(x) and isstr(y): return None
        e = x != NAN and (0 if x == MZERO else x) == (0 if y == MZERO else y)
        return jsb(e == (op == 'DEQ'))
    if op == 'DNEG': return -x if issmi(x) and x != 0 and issmi(-x) else None
    if not (issmi(x) and issmi(y)): return None
    if op in ('DLT', 'DGT', 'DLE', 'DGE'): return jsb({'DLT': x < y, 'DGT': x > y, 'DLE': x <= y, 'DGE': x >= y}[op])
    if op == 'DBIT':                                     # (DBIT's operator k; >>> of a negative number: as an unsigned one)
        if k > 5: return None                            # (7: RETC, cc_ref.ret)
        s = y & 31; r = (x & y, x | y, x ^ y, x << s, x >> s, (x + (x < 0) * 2 ** 32) >> s)[k]
    if op == 'DDIV':
        if y == 0 or x % y or (x == 0 and y < 0): return None
        r = x // y
    elif op == 'DMOD':
        if y == 0: return None
        r = x - y * int(x / y)
        if r == 0 and x < 0: return None
    elif op != 'DBIT':
        r = {'DADD': x + y, 'DSUB': x - y, 'DMUL': x * y}[op]
        if op == 'DMUL' and r == 0 and (x < 0 or y < 0): return None
    return r if issmi(r) else None
# operator codes on the parser's operator stack (and their precedences: prec)
(NOP, PUSHI, LOADG, STOREG, LOADL, STOREL, LOADI, STOREI, ADD, SUB, MUL, DIV, MOD, LT, GT, LE, GE, EQ, NE, LEQ, LNE,
 BAND, BOR, BXOR, SHL, SHR, USHR, AND, OR, NOT, NEG, TYPEOF, BNOT) = range(33)
# (ADD ... LNE in the order of their dynamic instructions, DADD ... DLNE: the opcode is the code + a constant; BAND ... USHR right
# after them are DBIT, whose A's 1024s are the code - BAND)
BITOPS = (BAND, BOR, BXOR, SHL, SHR, USHR)
NAME = {ADD: 'ADD', SUB: 'SUB', MUL: 'MUL', DIV: 'DIV', MOD: 'MOD', LT: 'LT', GT: 'GT', LE: 'LE', GE: 'GE', EQ: 'EQ', NE: 'NE',
        NOT: 'NOT', NEG: 'NEG', LEQ: 'EQ', LNE: 'NE'}            # (== and != in the runtime library: raw)
CMPS = (LT, GT, LE, GE, EQ, NE, LEQ, LNE)
INV = {LT: GE, GE: LT, GT: LE, LE: GT, EQ: NE, NE: EQ, LEQ: LNE, LNE: LEQ}
DYN = {ADD: 'DADD', SUB: 'DSUB', MUL: 'DMUL', DIV: 'DDIV', MOD: 'DMOD', LT: 'DLT', GT: 'DGT', LE: 'DLE', GE: 'DGE', EQ: 'DEQ', NE: 'DNE',
       LEQ: 'DLEQ', LNE: 'DLNE'}
SEP = {0: 0, 32: 1, 10: 2}              # PRINT / PRINTK's A: separator * 2

# limits (= the CSS chain's fixed table sizes)
OD, CD, NS, NF, NL, NI = 8, 8, 32, 16, 64, 32  # NI: interned strings and property names
ODN = 10                                # the operand stack (its temps T(0) ... T(9))
TBMAX = 24                              # descriptors + collapsed arguments: a frame's live words stay below TRAPOFF
EMAX = 7                                # instructions per step (14 code words)
SDATA = 256                             # globals: data_base + 1 .. + SDATA - 1 (data_base itself holds STRTAG, for the lib)
STR0 = LAYOUT['data_base'] + SDATA      # the string area: STR0 (the lib's empty DONE marker) .. SEND
SEND = STR0 + LAYOUT['str_size']
# FTAB + k (the NF words after the DONE marker): function k's body (its instruction pair's index) + 8192 * its parameters, for
# its value (the library's mkfn: the pair before the body holds [MOV][word1: its name]); FCACHE + k: the global that caches it
FTAB = STR0 + 1
# The special values: words of slot 15 (no number, string, array or object is one), JavaScript's values that aren't numbers in
# the machine's integer range: the booleans, null, undefined, and the numbers NaN, +-Infinity and -0. Comparisons and ! make
# TRUE / FALSE in user code (the ROM keeps raw 0 / 1). Falsy: 0, FALSE ... MZERO and the empty string
SPECIALS = ('INF', 'NINF', 'TRUE', 'FALSE', 'NULL', 'UNDEF', 'NAN', 'MZERO')
SPV0 = 524280
INF, NINF, TRUE, FALSE, NULL, UNDEF, NAN, MZERO = range(SPV0, SPV0 + 8)
def isspecial(v): return v >= SPV0
def jsb(c): return FALSE - int(bool(c))       # a JavaScript boolean
# The machine's integers (V8's Smis): every number in [SMI_LO, SMI_HI] is one word; slot -8 (strings) is outside it, so a number
# is never a reference. Arithmetic in user code works on these and traps to the ROM for anything else
SMI_LO, SMI_HI = -229376, 262143
def issmi(v): return SMI_LO <= v <= SMI_HI
# The built-in strings (BSTR, the compile chain's .fin overlays): slot k (12 words, [len][bytes][0] at BSTR + 12 k) holds special
# k's name (the console's: -0 prints as -0), then "0" (-0 made a string), typeof's names by type code, "". PRINT and a string's
# + find a special's name by arithmetic. BSTRV(k): slot k's string value
BSTR = LAYOUT['bstr']
BSTRS = ['Infinity', '-Infinity', 'true', 'false', 'null', 'undefined', 'NaN', '-0', '0',
         'undefined', 'object', 'boolean', 'number', 'string', 'function', '']
BS_ZERO, BS_TYPE, BS_EMPTY = 8, 9, 15        # "0", typeof's first ("undefined": type 0), ""
TYPENAMES = ('undefined', 'object', 'boolean', 'number', 'string', 'function')
def BSTRV(k): return BSTR + 12 * k + 1 - 262144                       # (- STRTAG)
BSTRW = {BSTR + 12 * k + i: w for k, t in enumerate(BSTRS) for i, w in enumerate([len(t)] + [ord(ch) for ch in t]) if w}   # (RAM holds the zeros)
assert all(len(t) <= 10 for t in BSTRS) and BSTR + 12 * len(BSTRS) <= LAYOUT['strend']
TRUEV, FALSEV = BSTRV(2), BSTRV(3)
STRP0 = FTAB + NF                       # the program's own strings start here (STR0 is the empty DONE marker, then FTAB)
assert SEND == LAYOUT['code_base']
CODESZ = LAYOUT['init'] - 1 - LAYOUT['code_base']     # code words (init - 1 holds the staged-data count)
STRTAG = 262144                         # a string value is its address - STRTAG (machine words are 20-bit signed)
NOROOM = 32768                          # added to a string token's address when it didn't fit (addresses are 15-bit)
PARAM0 = 6144                           # parameter i's symbol address until its function's ')' (cc_dsl's encoding; above the globals)
OBJTAG = LAYOUT['objtag']
HEAP0 = LAYOUT['heap_lo']
# the global object (this outside a function, or in one called without a receiver): an object made the first time, in global 1
# (NUMLIT G1 with word1 GLOBK: the library's numlit makes it)
GCELL, GLOBK = 1, -1
# Prototypes: an object's own keys end with 0 or with a link to its prototype's first chunk (its address - PROTAG: tag -16), which
# GETP / GETX probes follow as they follow a chunk's link (to read inherited properties) and SETP / SETX treat as the end (a new
# pair carries it on). x.__proto__ / x.prototype are x[PKPROTO] / x[PKPT]: keys no probe takes, so the library's getx / setx
# handle them (an object's link; a function's prototype object, made the first time)
PROTAG = 16 * 32768
def isplink(k): return k < -OBJTAG
PKPROTO, PKPT = SPV0 - 1, SPV0 - 2
# Math.PI ... (MATHK), Math.min / max, Object.create as values (MATHV): x[PKSTAT - i] on the dummy receiver (getx: the constant or
# the native; setx ignores them: Object.create = f is no error)
PKSTAT = SPV0 - 3
HP, GCLIM, GCSP, KEYCELL, RETCELL = range(LAYOUT['rt_base'], LAYOUT['rt_base'] + 5)
RBUF0 = LAYOUT['rt_base'] + LAYOUT['rt_cells'].index('RBUF0')        # NET's answers, unpacked into bytes (net/device.py)
def netw(ans):
    """NET's writes for the parts' answers: [(address, value)], part 0's whole answer last (at A: address None)"""
    out = [(RBUF0 + 2 * j + k, (d >> 8 * k) & 255 if d >> 16 > k else -1) for j, d in enumerate(ans) for k in (0, 1)]
    return out + [(None, ans[0])]
ARRTAG = LAYOUT['arrtag']
HEAP_HI = HEAP0 + 2 * LAYOUT['heap_size']
STRV_LO, STRV_HI = LAYOUT['data_base'] + SDATA - STRTAG, HEAP_HI - STRTAG     # a value in [STRV_LO, STRV_HI) is a string
def isstr(v): return STRV_LO <= v < STRV_HI
def isarr(v): return HEAP0 <= v - ARRTAG < HEAP_HI
def isobj(v): return HEAP0 <= v + OBJTAG < HEAP_HI
DBLTAG = 425984                         # a boxed double is its number line's address - DBLTAG (slot -13)
def isdbl(v): return -DBLTAG <= v < -DBLTAG + 32768
def isnum(v): return issmi(v) or v in (INF, NINF, NAN, MZERO) or isdbl(v)
# A function is an 8-word heap block [hdr | code | meta | env | name | props | . .] (collector kind 3), its value the address of
# its code word - FUNTAG (slot -14): code is its body's instruction pair, meta its parameters' count, name its name (a string
# or 0). (The runtime library makes them: mkfn)
FUNTAG = 458752
def isfun(v): return -FUNTAG <= v < -FUNTAG + 32768
# An env cell (a closure's outer frame, cc_ref.captured) is a heap block (collector kind 4) [hdr | base | size | the frame's
# words when closed], its value the address of its base word - ENVTAG (slot -12). base: the frame's fp while it runs, else
# the cell's own address + 1 (the frame's slot k at base + k)
ENVTAG = 393216
def isenv(v): return -ENVTAG <= v < -ENVTAG + 32768
def isref(v): return isstr(v) or isarr(v) or isobj(v) or isdbl(v) or isfun(v)

# ---- the FPU's numbers (Python floats are the same IEEE doubles as Chrome's calc())
import math, struct
def fenc(x):
    """a double's number line (FLOPS' comment)"""
    if x != x: return [4000, 0, 0, 0]
    sg = -1 if math.copysign(1.0, x) < 0 else 1
    if math.isinf(x): return [sg * 3000, 0, 0, 0]
    if x == 0: return [sg, 0, 0, 0]
    a = abs(x); E = max(math.frexp(a)[1] - 1, -1022); M = int(fscale(a, 52 - E))
    return [sg * (E + 1100), M >> 36, (M >> 18) & 0x3FFFF, M & 0x3FFFF]
def fdec(w):
    w0 = w[0]
    if w0 == 4000: return math.nan
    if abs(w0) == 3000: return math.copysign(math.inf, w0)
    if abs(w0) == 1: return math.copysign(0.0, w0)
    return math.copysign(fscale(float((w[1] << 36) + (w[2] << 18) + w[3]), abs(w0) - 1152), w0)
def fscale(x, n):
    """x * 2^n as the CSS computes it: x * 2^k1 * 2^(n - k1), k1 = floor(n / 2) (each factor finite)"""
    k1 = n // 2; return x * 2.0 ** k1 * 2.0 ** (n - k1)
def fval(v, rd):
    """the double a number is (rd: memory, for a boxed double's line); anything else is NaN"""
    if issmi(v): return float(v)
    if isdbl(v): a = (v + DBLTAG) & AMASK; return fdec([rd(a + j) for j in range(4)])
    return {INF: math.inf, NINF: -math.inf, MZERO: -0.0}.get(v, math.nan)
def fnorm(x, v):
    """FNORM: the machine's value for the double x: an integer in range (not -0), a special, else v (the double itself)"""
    if x != x: return NAN
    if math.isinf(x): return INF if x > 0 else NINF
    if x == 0 and math.copysign(1.0, x) < 0: return MZERO
    if x == math.floor(x) and SMI_LO <= x <= SMI_HI: return int(x)
    return v
def _split(a):
    c = 134217729.0 * a; h = c - (c - a); return h, a - h
def ftplo(a, b):
    """the exact error of a * b (Dekker's two-product, as the CSS computes it)"""
    p = a * b; ah, al = _split(a); bh, bl = _split(b)
    return ((ah * bh - p) + ah * bl + al * bh) + al * bl
def cpow(x, y):
    """C's pow (CSS pow()): pow(x, +-0) = 1, pow(1, y) = 1, overflow +-Infinity, a negative x to a non-integer NaN"""
    try: return math.pow(x, y)
    except OverflowError:
        neg = x < 0 and float(y).is_integer() and int(y) % 2 == 1
        return -math.inf if neg else math.inf
    except ValueError:
        if x == 0 and y < 0:
            neg = math.copysign(1.0, x) < 0 and float(y).is_integer() and int(y) % 2 == 1
            return -math.inf if neg else math.inf
        return math.nan
def _f1(fn, x):
    try: return fn(x)
    except OverflowError: return math.inf
    except ValueError: return math.nan
def flog(x):
    if x != x or x < 0: return math.nan
    if x == 0: return -math.inf
    return math.log(x) if not math.isinf(x) else math.inf
def jround(x):
    """JavaScript's Math.round (CSS round(nearest): ties toward +Infinity; -0 kept)"""
    if not math.isfinite(x) or x == 0: return x
    f = math.floor(x); r = float(f + 1 if x - f >= 0.5 else f)
    return -0.0 if r == 0 and x < 0 else r
def zkeep(fn, x):
    """floor / ceil / trunc with -0 and specials as the CSS's round()"""
    if not math.isfinite(x) or x == 0: return x
    r = float(fn(x)); return -0.0 if r == 0 and x < 0 else r
def fmod(x, y):
    if x != x or y != y or math.isinf(x) or y == 0: return math.nan
    if math.isinf(y): return x
    return math.fmod(x, y)
def fdiv(x, y):
    if y == 0:
        if x == 0 or x != x: return math.nan
        return math.copysign(math.inf, x) * math.copysign(1.0, y)
    return x / y
FCONSTV = {'pi': math.pi, 'e': math.e, 'ln2': math.log(2), 'ln10': math.log(10), 'log2e': math.log(math.e) / math.log(2),
           'log10e': math.log(math.e) / math.log(10), 'sqrt2': math.sqrt(2), 'sqrt1_2': math.sqrt(0.5)}
def fline_op(op, x, y):
    """FLOPS op on the doubles x, y (y: an integer for FSCALE, FP10, FCONST)"""
    if op == 'FLD': return x
    if op == 'FADD': return x + y
    if op == 'FSUB': return x - y
    if op == 'FMUL': return x * y
    if op == 'FDIV': return fdiv(x, y)
    if op == 'FMOD': return fmod(x, y)
    if op == 'FPOW': return cpow(x, y)
    if op == 'FSQRT': return math.nan if x < 0 else math.sqrt(x) if x == x else x
    if op == 'FFLOOR': return zkeep(math.floor, x)
    if op == 'FCEIL': return zkeep(math.ceil, x)
    if op == 'FROUND': return jround(x)
    if op == 'FTRUNC': return zkeep(math.trunc, x)
    if op == 'FABS': return abs(x)
    if op == 'FTPLO': return ftplo(x, y)
    if op == 'FSCALE': return fscale(x, int(y))
    if op == 'FP10': return cpow(10.0, y)
    if op == 'FCONST': return FCONSTV[FCONSTS[int(y)]]
    if op == 'FEXP': return _f1(math.exp, x)
    if op == 'FLOG': return flog(x)
    if op in ('FSIN', 'FCOS', 'FTAN'): return math.nan if math.isinf(x) else getattr(math, op[1:].lower())(x)
    if op in FBOPS:
        a, b = toi32(x), toi32(y); s = b & 31
        return float((a & b, a | b, a ^ b, toi32(a << s), a >> s, (a % 2 ** 32) >> s)[FBOPS.index(op)])
    raise ValueError(op)
def toi32(x):
    """JavaScript's ToInt32 of the double x"""
    u = int(math.trunc(x)) % 2 ** 32 if math.isfinite(x) else 0
    return u - 2 ** 32 * (u >= 2 ** 31)
def fcand(v, n):
    """FCOK / FCDIG: the candidate at scale n for v > 0 (below 2^53): (c, ok), exactly as the CSS computes it (numstr's notes)"""
    E = max(math.frexp(v)[1] - 1, -1022); q = E - 52; M = fscale(v, -q)
    f5 = cpow(5.0, n); Nh = M * f5; Nl = ftplo(M, f5); s = q + n
    xh, xl = Nh * cpow(2.0, s), Nl * cpow(2.0, s)
    if s >= 0: return int(xh) + int(xl), 1
    if xh >= 2.0 ** 52:
        rf = math.floor(xl); d = xl - rf; chi = xh; clo = rf + (d > 0.5 or (d == 0.5 and rf % 2 != 0))
    else:
        f = math.floor(xh); hf = 0.5 - (xh - f); chi = f + (xl > hf or (xl == hf and f % 2 == 1)); clo = 0
    t1 = 1 - s
    D = (chi * cpow(2.0, t1) - 2 * Nh) + clo * cpow(2.0, t1) - 2 * Nl
    lim = f5 / (2 if D < 0 and M == 2.0 ** 52 and E > -1022 else 1)
    return int(chi) + int(clo), int(abs(D) < lim or (abs(D) == lim and M % 2 == 0))
def fval_op(op, x, y, v):
    """FVOPS op on the doubles x, y (v: the value B, for FNORM's double)"""
    if op == 'FNORM': return fnorm(x, v)
    if op == 'FINT': return int(math.trunc(x)) if math.isfinite(x) else 0
    if op == 'FCMP': return 2 if x != x or y != y else (x > y) - (x < y)
    if op == 'FEXPO': return max(math.frexp(abs(x))[1] - 1, -1022) if math.isfinite(x) and x != 0 else 0
    if op == 'FLOG10':
        if not (math.isfinite(x) and x != 0): return 0
        a = abs(x); k = math.floor(math.log(a) / math.log(10))
        return k + (a >= cpow(10.0, k + 1)) - (a < cpow(10.0, k))
    if op == 'FDIGIT': j = int(y); return int((fmod(x, cpow(10.0, j + 1)) - fmod(x, cpow(10.0, j))) / cpow(10.0, j))
    raise ValueError(op)
def truthy(mem, v, user=True):
    """JZ / JNZ / NOT: 0 and the empty string are false (a string's length is the word before its value's address); in user
    code also FALSE, null, undefined, NaN and -0"""
    return v != 0 and not (user and v >= FALSE) and not (isstr(v) and mem[(v - 1) & AMASK] == 0)
def catv(v):
    """an operand of a string's +: a special as its name (-0 as "0"), anything else as it is"""
    return BSTRV(BS_ZERO if v == MZERO else v - SPV0) if isspecial(v) else v
def catok(x, y):
    """a string's + the machine joins (the cat class): a string with a string, an integer or a special"""
    return (isstr(x) or isstr(y)) and not any(isarr(v) or isobj(v) or isdbl(v) or isfun(v) for v in (x, y))
def notown(v):
    """a string that isn't the program's own (a heap string, or a built-in one): run-time keys look these up by their characters"""
    return isstr(v) and not (STRP0 <= v + STRTAG < SEND)
def ownkey(k):
    """a key the machine probes an object for (GETX / SETX): an integer or one of the program's strings"""
    return issmi(k) or (isstr(k) and not notown(k))
def typecode(v):
    """typeof's type code (TYPENAMES)"""
    if isstr(v): return 4
    if isfun(v): return 5
    if isarr(v) or isobj(v) or v == NULL: return 1
    if v == UNDEF: return 0
    if v in (TRUE, FALSE): return 2
    return 3
def kind(k, v):
    """KIND's tests (KINDS[k])"""
    return [isstr(v) + 2 * isarr(v) + 3 * isobj(v), int(isstr(v)), int(isarr(v)), int(isobj(v)), int(isarr(v) or isobj(v)),
            int(notown(v)), len(str(v)), int(isref(v)), int(isstr(v) and v + STRTAG >= HEAP0), BSTRV(BS_TYPE + typecode(v)),
            int(isspecial(v)), int(issmi(v)), int(isdbl(v)), int(isfun(v)), int(isnum(v))][k]
def rnd8(n): return -(-n // 8) * 8
def allocw(k, n):
    """an ALLOC's block, in words: a string of n bytes ([hdr][len][bytes][0]), an array of capacity n ([hdr][cap][len][ptr]
    [elements]), n raw words, an object chunk of n words, a boxed double (8)"""
    return rnd8(n + (3, 4, 0, 0, 8)[k])
# ALLOC's executions on the CSS CPU (csssim.py, gen_css.py), --pst the phase: HP (or the trap), the header's line (a string's
# [hdr][len][0][0], an array's [hdr][cap][0][ptr]), a string's NUL past that line, the map's bit, A
AP_HP, AP_HDR, AP_NUL, AP_MAP, AP_RES = range(5)
def allocnext(ph, k, n):
    """the phase after ph for an ALLOC of kind k, n"""
    while True:
        ph += 1
        if ph == AP_HDR and k in (2, 3): continue
        if ph == AP_NUL and (k != 0 or n < 2): continue
        if ph == AP_MAP and k == 2: continue
        return ph
def allochdr(k, n, nw, base):
    """the header line ALLOC writes (kinds 0, 1, 4: the block kinds 0 string, 1 array, 2 double)"""
    return [-2 - nw, n, 0, 0] if k == 0 else [-3 - nw, n, 0, base + 4] if k == 1 else [-4 - nw, 0, 0, 0]
def allocres(k, base):
    """ALLOC's value for the block at base"""
    return (base + 2 - STRTAG, base + 3 + ARRTAG, base, base, base + 4 - DBLTAG)[k]
# The collector's map of block starts (a bit per 8 heap words, 16 to a word, both semi-spaces: MAPN words from MAP), kept as
# blocks are made (ALLOC, NEW, a string's +, the collector's copies): a stack word is a reference only if its block is marked
MAP = LAYOUT['map_base']; MAPN = 2 * LAYOUT['heap_size'] // 128
def mapbit(b):
    """the map's word and bit for the block at b"""
    x = (b - HEAP0) // 8; return MAP + x // 16, x % 16
def isfref(w, flo):
    """MFREF's test: w refers to a block in the from-space at flo (an object, a string, an array)"""
    H = LAYOUT['heap_size']
    return (flo <= w + OBJTAG < flo + H or flo + 2 <= w + STRTAG < flo + H or flo + 3 <= w - ARRTAG < flo + H
            or flo + 4 <= w + DBLTAG < flo + H or flo + 1 <= w + FUNTAG < flo + H or flo + 1 <= w + ENVTAG < flo + H)
def mcase(op, c):
    """MCPY's letters: MUPPER a-z to A-Z, MLOWER A-Z to a-z"""
    lo = 97 if op == 'MUPPER' else 65
    return c + (-32 if op == 'MUPPER' else 32) if op in ('MUPPER', 'MLOWER') and lo <= c < lo + 26 else c
def s20(x): return (x + (1 << 19)) % (1 << 20) - (1 << 19)       # machine words: 20-bit two's complement
H1M, H2M = 65521, 65519

# operand encodings (10-bit fields)
def L(off): return 256 + off            # frame slot fp + off
KLIM = 120                              # constants -128 ... 119 are 768 ... 1015; the specials 1016 ... 1023
def K(v):
    assert -128 <= v < KLIM or isspecial(v), v
    return 896 + v if v < KLIM else 1016 + v - SPV0
def isK(o): return 768 <= o < 1024
def kval(o): return o - 896 if o < 1016 else o - 1016 + SPV0         # a constant operand's value
FALSYK = range(K(FALSE), K(MZERO) + 1)  # the falsy specials' operands (and K(0))
# operand descriptors (od entries: type * 4096 + descriptor): an operand encoding (< 1024), KBIG (the value pk, LOADK must load it:
# only on top), TMP (the value is in this entry's temp), CND + cop * 4 + nloc flags of B and C (a pending comparison; B and C in
# pk as word1 packs them; only on top)
KBIG, TMP, CND = 1024, 1025, 1028
CNDOPS = CMPS + (NOT,)

# (__dadd: the dynamic + instruction, a string built in CSS; the rest: the runtime's primitives, OPN's comment)
INTR = ['peek', 'poke', '__fp', 'prn', 'halt', '__dadd', '__kind', '__alloc', '__mcpy', '__mupper', '__mlower', '__mfill', '__nput',
        '__mcmp', '__mfeq', '__mfref', '__mwalk', '__apush', '__net', '__fl', '__fv']
INTRN = (1, 2, 0, 1, 0, 2, 2, 2, 3, 3, 3, 3, 2, 3, 3, 3, 3, 2, 1, 4, 3)      # their arguments
INTRV = ('peek', '__fp', '__dadd', '__kind', '__alloc', '__mcmp', '__mfeq', '__mfref', '__mwalk', '__net', '__fv')    # those with a value
# __fl(k, d, a, b): FLOPS[k] d, a, b (the line d := op of a and b); __fv(k, a, b): FVOPS[k] T, a, b (k: a constant)
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
           ('toString', {0: 'tostring0'}, 2), ('splice', {k: f'splice{k}' for k in range(9)}, 0), ('bind', {1: 'bind1', 2: 'bind2', 3: 'bind3'}, 0),
           ('hasOwnProperty', {1: 'hasown'}, 1)]
# functions called like methods on a dummy receiver (0): parseInt(s), Number(x), String(x), parseFloat(s); their names are reserved
GLOBALS = [('parseInt', {1: 'parseint'}, 3), ('Number', {1: 'number'}, 3), ('String', {1: 'tostring'}, 2), ('parseFloat', {1: 'parsefloat'}, 3),
           ('fetch', {1: 'fetch'}, 3), ('read', {0: 'read'}, 3),       # the network (net/device.py)
           ('setTimeout', {1: 'settimeout1', 2: 'settimeout'}, 3), ('setInterval', {2: 'setinterval'}, 3),
           ('clearTimeout', {1: 'cleartimer'}, 0), ('clearInterval', {1: 'cleartimer'}, 0), ('alert', {1: 'alert'}, 0)]
# Math.f(...) (after 'Math.': S_MATHDOT; not methods of anything else); its constants (FCONST's); min / max as values: natives
MATHM = [('abs', {1: 'mabs'}, 3), ('floor', {1: 'mfloor'}, 3), ('ceil', {1: 'mceil'}, 3), ('round', {1: 'mround'}, 3),
         ('trunc', {1: 'mtrunc'}, 3), ('sign', {1: 'msign'}, 3), ('sqrt', {1: 'msqrt'}, 3), ('exp', {1: 'mexp'}, 3), ('log', {1: 'mlog'}, 3),
         ('sin', {1: 'msin'}, 3), ('cos', {1: 'mcos'}, 3), ('tan', {1: 'mtan'}, 3), ('pow', {2: 'mpow'}, 3),
         ('min', {k: f'min{k}' for k in range(5)}, 3), ('max', {k: f'max{k}' for k in range(5)}, 3), ('random', {0: 'mrandom'}, 3),
         ('create', {1: 'ocreate'}, 0)]                  # (Object.create: Object. is a dummy receiver as Math. is)
MATHK = {'PI': 0, 'E': 1, 'LN2': 2, 'LN10': 3, 'LOG2E': 4, 'LOG10E': 5, 'SQRT2': 6, 'SQRT1_2': 7}      # (cc_ref.FCONSTS)
MATHV = ('min', 'max', 'create')                        # as values: the library's natives (mathfn)
# new Number(x) / new String(x) / new Object(): wrapper objects (the library's wrapnum ...: an object whose first key, PKVAL, holds
# the primitive, which ToPrimitive (prim) takes)
NEWM = [('Number', {0: 'wrapnum0', 1: 'wrapnum'}, 0), ('String', {0: 'wrapstr0', 1: 'wrapstr'}, 0), ('Object', {0: 'wrapobj0', 1: 'wrapobj'}, 0)]
ALLM = METHODS + GLOBALS + MATHM + NEWM
assert len(ALLM) < 64
KW = {k: h1h2(k) for k in ['var', 'let', 'const', 'if', 'else', 'while', 'for', 'return', 'function', 'putc', 'console', 'log',
                           'true', 'false', 'break', 'continue', 'do', 'null', 'switch', 'case', 'default', 'length', 'String',
                           'undefined', 'NaN', 'Infinity', 'typeof', 'window', 'globalThis', 'of', 'in', 'this', 'new', 'call', 'apply', '__proto__', 'prototype', 'Object', 'Math'] + list(MATHK)
                          + [m[0] for m in ALLM] + INTR}
METHOD_INDEX = {KW[m[0]]: i for i, m in enumerate(METHODS)}
# f.call( / f.apply( (pm PMFN + 0 / 1): f is called with this = the first argument (apply: the second's elements as arguments)
FMETH = {KW['call']: 0, KW['apply']: 1}
PMFN = 68
GLOBAL_INDEX = {KW[m[0]]: len(METHODS) + i for i, m in enumerate(GLOBALS)}
MATH_INDEX = {KW[m[0]]: len(METHODS) + len(GLOBALS) + i for i, m in enumerate(MATHM)}
NEW_INDEX = {KW[m[0]]: len(METHODS) + len(GLOBALS) + len(MATHM) + i for i, m in enumerate(NEWM)}
assert len(set(KW.values())) == len(KW), 'keyword hashes collide'
# the literals that are words: their constant operands and static types
LITERALS = {'true': (K(TRUE), 1), 'false': (K(FALSE), 1), 'null': (K(NULL), 0), 'undefined': (K(UNDEF), 0), 'NaN': (K(NAN), 3),
            'Infinity': (K(INF), 3)}
LITK = {KW[w]: v for w, v in LITERALS.items()}
# Implicit globals (an assignment to an undeclared name, window.x, or a name read before it is declared): symbol entries 0 ...
# NIMP - 1 are kept for those that appear inside a function or are read first (one assigned at the top level first is an
# ordinary global); entry k is global IMPC + k. One read first is kind 3 until it is assigned or declared; a name that never
# is is an undefined variable (error 4, at the end). A call of a function that is never declared is JavaScript's
# ReferenceError at run time: its label stays undefined, and the page's undefined labels are 0, the library's refstub
NIMP, IMPC = 4, 2
FCACHE = IMPC + NIMP
# the timers' queue (setTimeout / setInterval): global TCELL, past the functions' caches; nfdef + TIMERS once the program sets one,
# so that its end runs them (cc_ref timer_loop)
TCELL, TIMERS = FCACHE + 16, 64
RCELL = TCELL + 1                       # Math.random's state
SPCELL = RCELL + 1                      # String.prototype (an object made the first time)
ECELL = SPCELL + 1                      # the REPL's entry value (Compiler repl): what the entry's last expression statement left
PKVAL = 1                               # a wrapper object's key for its primitive (no string's address, no number's key)
# every global starts undefined (a read before its var runs: hoisting; so var x without a value is no code at the top level),
# the caches too (FCACHE's, a double literal's: NUMLIT's 'not made yet'). The images hold it (the page's RAM groups with these
# cells are live from the start, gen_css.py); a cell the program writes can't be an overlay
GINIT = {LAYOUT['data_base'] + a: UNDEF for a in range(GCELL, SDATA)}
WGLOB = (KW['window'], KW['globalThis'])
RETC = (OP['DBIT'] - OP['RET']) * 8192 + 7 * 1024     # RET + it: DBIT k 7 (cc_ref.ret)
# JavaScript's reserved words among the keywords: no variable, parameter or function may be named so. A declaration checks at
# once; a name read or called (an implicit global, a function never declared) is checked at the end, in the tables
RESERVED = tuple(KW[w] for w in ('var', 'let', 'const', 'if', 'else', 'while', 'for', 'return', 'function', 'break', 'continue',
                                 'do', 'switch', 'case', 'default', 'typeof', 'true', 'false', 'null'))
# punctuation that can start an expression statement (not a statement): ( [ ! - ~; at a statement's start the CSS compiler's
T_THIS, T_NEW = 25, 26                  # this, new: the lexer makes them punctuation (variants of their own: no cost to other names)
T_PROTO, T_PTYPE = 27, 28               # __proto__, prototype (after '.': x[a hidden key], so GETX / SETX trap to the library)
PKW = {KW['this']: T_THIS, KW['new']: T_NEW, KW['__proto__']: T_PROTO, KW['prototype']: T_PTYPE}
# variants don't tell them apart (cc_dsl.variant_key: STMTM)
XSTART = (40, 91, 33, 45, 126, T_THIS, T_NEW)

# punctuation codes: single chars by ASCII; two-char ops: === 1, !== 2, <= 3, >= 4, && 5, || 6, ++ 7, -- 8,
# += 9, -= 10, *= 11, /= 12, %= 13 (== and != as === and !== with tflag); NL 14: a newline after a token that can end a
# statement (identifier, number, string, ) ] } ++ --), for automatic semicolon insertion. (After a block's '}' the parser
# is in a mode that ignores it; after an object literal's it ends the statement.)
TWO = {(61, 61): 1, (33, 61): 2, (60, 61): 3, (62, 61): 4, (38, 38): 5, (124, 124): 6, (43, 43): 7, (45, 45): 8,
       (43, 61): 9, (45, 61): 10, (42, 61): 11, (47, 61): 12, (37, 61): 13, (60, 60): 15, (62, 62): 16, (38, 61): 18, (124, 61): 19, (94, 61): 20,
       (61, 62): 24}
# (the lexer makes three- and four-character ones of them: >>> 17 (>> and >); <<= 21, >>= 22, >>>= 23 (<< >> >>> and =: + 6))
T_NL = 14
T_ARROW = 24                            # =>
# == and != are === and !== (1, 2) with the token's flag set (cc_ref: tflag; the page: its hash1 word), which the lexer knows from the
# character after them: so they share the parser's variants
BIN = {42: MUL, 47: DIV, 37: MOD, 43: ADD, 45: SUB, 60: LT, 62: GT, 3: LE, 4: GE, 1: EQ, 2: NE, 5: AND, 6: OR,
       38: BAND, 124: BOR, 94: BXOR, 15: SHL, 16: SHR, 17: USHR}
# Semicolon insertion. A newline after a token that can end a statement (lt) is pending (pnl) until the next significant
# character, which the lexer sees as the lookahead cn of the blank or comment end before it: a line starting with one of
# CONT continues the statement or ends it by itself (no T_NL: ';' and '}' end it without one), any other starts a new one (T_NL). '+' '-' (++x / --x start a statement, x + y
# continues) and '/' (a comment or a division) are decided on the character itself. After return (lt 2, JavaScript's
# restricted production) the newline always ends the statement. A newline inside a /* */ comment counts.
CONT = (46, 91, 40, 63, 58, 44, 41, 93, 42, 37, 60, 62, 38, 124, 94, 61, 59, 125)    # . [ ( ? : , ) ] * % < > & | ^ = ; }
# The REPL (Compiler repl) leaves a newline pending after any token, and a line that starts with ( [ + or - starts a statement, as in
# Node's REPL: so the next line's first token comes after a T_NL wherever a statement could start there
CONTR = tuple(x for x in CONT if x not in (40, 91))
BLANK = (9, 10, 13, 32)
COMPOUND = {9: ADD, 10: SUB, 11: MUL, 12: DIV, 13: MOD, 18: BAND, 19: BOR, 20: BXOR, 21: SHL, 22: SHR, 23: USHR}
# the bitwise operators' tokens: rare, so the CSS compiler's variants don't tell them apart (cc_dsl.PUNCT)
BITTOK = (38, 124, 94, 126, 15, 16, 17, 18, 19, 20, 21, 22, 23)
ESC = {110: 10, 116: 9, 114: 13}
def prec(code):
    return {MUL: 11, DIV: 11, MOD: 11, ADD: 10, M_CADD: 10, SUB: 10, SHL: 9, SHR: 9, USHR: 9, LT: 8, GT: 8, LE: 8, GE: 8,
            EQ: 7, NE: 7, LEQ: 7, LNE: 7, BAND: 6, BXOR: 5, BOR: 4, AND: 3, OR: 2, M_TELSE: 1, NOT: 12, NEG: 12, TYPEOF: 12, BNOT: 12}.get(code, 0)

# popops pops at most popcap(minprec) operators: between markers the binary operators' precedences increase upwards (one per
# class from minprec to 11, M_TELSE at 1), and unary ones (12) stack only on top: UNARYRUN of them at most (more: error 22). The CSS
# compiler's popops loops that many times
UNARYRUN = 4
def popcap(minprec): return min(OD, 12 - minprec + UNARYRUN)
# + at the top level of a console.log argument (value: the left operand's static type); precedence of +. M_PRINT's value: 2 after a
# ',' (until the next argument starts) + 4 * the pieces of a + chain already on the operand stack (PIECES at most)
M_CADD = 50
PIECES = 4                              # (each a PRINT at the argument's end: EMAX bounds them)
# c ? a : b is  c Jfalse L1  a -> T(i) JMP L2  L1: b -> T(i)  L2:. '?' pushes the marker M_TERN (value L1 + 64 * reuse); ':'
# replaces it with the operator M_TELSE (value L2 + 64 * the then-branch's static type), lowest precedence, whose pop moves the
# else value to T(i) and defines L2. In a chain a ? x : b ? y : z the inner ternary reuses the outer L2 (reuse: M_TELSE was on
# top at '?'), so at most one M_TELSE sits between markers.
M_TELSE = 51
# OPS markers (codes >= 100)
# M_ARR: an array literal (value: its elements so far); M_METH: a method call's arguments (value: method + 64 * commas)
M_PAREN, M_CALL, M_ARR, M_METH, M_PUTC, M_PRINT, M_TERN = 100, 101, 102, 103, 104, 105, 108
M_OBJ, M_OKEY, M_INDEX = 109, 110, 111
# M_CALLV: a call of a value (the callee in its slot, below the arguments; value: 64 * commas) -> CALLV
M_CALLV = 113
# M_FN: a function expression's barrier (its value: the name it takes from an object literal's key, or 0); a function body's
# expressions use the operator and operand stacks above obase / dbase
M_FN = 114
# the runtime library's intrinsics (rom mode): M_INTR's value = the intrinsic (INTR) + 32 * its slot on the operand stack (d0)
M_INTR = 112
# control stack kinds. Bodies: IFB / ELSEB / LOOPB and DOB (a = continue target, b = break target; DOB c = the loop
# top) / FUNCB (a = the label past the function, b = its frame label: its count of locals); + BRACELESS: the body is a single
# statement, closed when that statement completes. A DOB stays on the stack through its while (cond): a ')' with a DOB on top
# can only end that condition. A function is declared at the program's top level, so its FUNCB is entry 0.
C_BLOCK, C_IFB, C_ELSEB, C_DOB, C_LOOPB, C_FUNCB = 1, 2, 3, 4, 5, 6
# a function's body: C_FUNCB a top-level declaration (static calls), C_FUNCN one inside a function (a local variable of that
# name gets its value where it stands), C_FUNCE an expression (its value is the operand). a: the label past it, b: its frame
# label, c: C_FUNCN's local. Functions nest two deep (curf: 0 the top level, 1, 2); fn_enter saves the outer context (sv0 ... sv3)
C_FUNCN, C_FUNCE = 7, 8
FUNCS = (C_FUNCB, C_FUNCN, C_FUNCE)
C_IFC, C_WHILEC, C_FORINIT, C_FORCOND, C_FORSTEP, C_ASSIGN, C_EXPR, C_RETURN = 10, 11, 12, 13, 14, 15, 16, 17
C_PSET = 19
# for (x of e) / for (x in e): C_FOROF (a l1, b lb, c x's symbol, d 1 for in) while e is parsed. Two temps below the operand stack
# (tb moves past them, back at the loop's end: C_LOOPB's d) hold the array and the index; e's ')' emits
#   for of ('of': MOV i, #0)  MOV a, e  l1: LDI n, a, #-1  JGE i, n -> lb  GETX n, a, i  MOV x, n  i++
#   for in  MOV i, e  CALL keys at a (a := keys(e), i := 0)  l1: GETX n, a, i  JEQ n, #undefined -> lb  MOV x, n  i++
# (a key is never undefined); 6 instructions, so that e's last one (a property's read) fits beside them (EMAX)
C_FOROF = 18
C_SWITCHC, C_SWITCH, C_CASE = 30, 31, 32
BRACELESS = 20
C_IFB1, C_ELSEB1, C_DOB1, C_LOOPB1 = C_IFB + BRACELESS, C_ELSEB + BRACELESS, C_DOB + BRACELESS, C_LOOPB + BRACELESS
# parser modes
(S_STMT, S_OPND, S_OPER, S_NAMES, S_NAMEE, S_VAR, S_VARAFTER, S_LPAREN, S_LBRACE, S_ELSE, S_FNAME, S_FPAREN, S_FPARAM,
 S_FPSEP, S_CONDOT, S_CONLOG, S_CONLP, S_CONFIRST, S_INC, S_AFTERELSE, S_PREINC,
 S_DOWHILE, S_DOT, S_OKEY, S_OCOLON, S_SWCASE, S_WDOT, S_BRK, S_ERR) = range(29)
# arrow functions: S_APAR1 after '(a,' (a in pn), S_AARROW0 after '()', S_AARROW after an arrow's parameters, S_ABODY after
# '=>' (a block, or else S_OPND: an expression body). S_OPERC / S_NAMEEC are S_OPER / S_NAMEE inside an expression body
# (ca: the step ends there), where a token that ends the body ends the function first (arrow_close): separate modes, so
# that only those variants carry that code (the others are S_OPER's / S_NAMEE's: ccpage5 shares their rules)
S_APAR1, S_AARROW0, S_AARROW, S_ABODY, S_OPERC, S_NAMEEC = range(29, 35)
S_NEW, S_NEWN = 35, 36                    # new F( : after new, after its name
S_MATHDOT = 37                            # after Math.
NMODES = 38
CMODES = {S_OPERC: S_OPER, S_NAMEEC: S_NAMEE}
ACLOSE = (41, 44, 59, 125, T_NL)          # the tokens that can end an expression body (not ']' or ':': [x => x] and c ? x => 1 : 2
                                          # need parentheses; four rules fewer, ccpage5)
# pm = 3 after x++ / ++x in an expression, which no '.' or '[' may follow.

def tmerge(a, b):
    """static type of a value that is one of two values of types a, b (?: && ||). A boolean with anything else is boolean: the
    boolean PRINT prints only 0 / 1 as false / true, and other numbers and strings as they are, so only a 0 or 1 from the
    other side misprints (unknown would misprint every boolean)"""
    return 1 if 1 in (a, b) else a if a == b else 0

class Compiler:
    def __init__(self, data_base, code_base, lib=None, rom=False, repl=False):
        """lib: the runtime library's entry addresses (lib.json). rom: compile the runtime library itself (rtlib.py): raw memory
        (peek, poke, p[i]), the intrinsics (INTR), no globals, and tables large enough for it. repl: the page's REPL (README REPL):
        each line that starts a top-level statement ends the entry before it, which prints its value and marks the output"""
        self.db, self.cb, self.rom, self.repl = data_base, code_base, rom, int(repl)
        self.NF, self.NL = (NF, NL) if not rom else (256, 8192)
        self.LM, self.FM = self.NL, max(16, self.NF)         # a label + LM * a flag or type; a function + FM * its type
        self.CODESZ = CODESZ if not rom else LAYOUT['rom_size']
        self.ent = (lib or {}).get('entries', {})   # the ROM routines compiled code calls
        # lexer. An identifier that may be a property name (after '.', '{' or ','; kpos 2 / 1 / 1) writes its bytes to the
        # string area at sdp, not committed; the level after it writes the NUL at inul. It is committed (sdp moves past it):
        # after '.' at once, after '{' or ',' when a ':' follows (icm: its length)
        self.lx = 0; self.q = 0; self.lt = 0; self.tkc = 0; self.acc = 0; self.h1 = 0; self.h2 = 0; self.p2 = 0; self.sstart = 0
        self.inul = 0; self.icm = 0; self.kpos = 0; self.lcon = 0; self.tid = 0; self.tlen = 0; self.tparen = 0; self.pnl = 0; self.tflag = 0
        self.line = 0; self.tline = 0           # the line being read; a T_NL's: the line its next token is on (the page: each level's)
        self.dp = 1                         # globals (parser): global k is data_base + k (data_base itself holds STRTAG)
        self.sdp = data_base + SDATA + 1 + NF     # string literals and property names (lexer): STRP0; data_base + SDATA itself is the lib's
                                            # empty DONE marker, which PRINT stops at
        # parser
        self.mode = S_STMT; self.pn = (0, 0)
        self.ops = [0] * OD; self.opv = [0] * OD; self.osp = 0
        self.cs = [[0] * 6 for _ in range(CD)]; self.csp = 0                   # kind a b c d, e: nlet when pushed
        self.od = [0] * ODN; self.nd = 0; self.pk = 0; self.tb = 0                          # operand descriptors; pk: the big constant / pending comparison on top
        # symbols: h1 h2 kind(1 g, 2 l) addr type const. Two regions: function- and program-level names grow up from 0
        # (nsym), block-scoped let / const grow down from NS - 1 (nlet); closing a block restores nlet
        self.sym = [[0, 0, 0, 0, 0, 0] for _ in range(NS)]; self.nsym = 0; self.nlet = 0
        self.fn = [[0, 0, 0, 0, 0] for _ in range(self.NF)]; self.nfn = 0      # h1 h2 label type argc (+1; 0: no call or definition yet)
        self.lab = [-1] * self.NL; self.nlab = 0
        self.itab = [[0, 0, 0] for _ in range(NI)]; self.nint = 0             # interned strings and names: h1 h2 address
        self.cp = 0; self.curf = 0; self.cfn = 0; self.nfdef = 0; self.nloc = 0; self.npar = 0; self.fsym = 0    # fsym: nsym at function start
        self.obase = self.dbase = self.fcsp = self.flab = 0; self.sv0 = self.sv1 = self.sv2 = self.sv3 = 0     # (fn_enter)
        self.optlab = set()                 # labels that may stay undefined (0): the close labels
        self.fmark = 0                      # nlet when the current function started (its block-scoped names lie below NS - fmark)
        self.clab = 0                       # the top-level function's close label (cc_ref.closelab)
        self.ca = 0                         # the current function is an arrow's expression body (S_OPERC)
        self.nimp = 0                       # implicit globals in entries 0 ... NIMP - 1 (user code: those and their globals are kept)
        if not rom: self.nsym = NIMP; self.dp = ECELL + 1
        self.pendLa = 0; self.err = 0; self.asic = 0; self.pm = 0
        self.rpend = 0                      # REPL: a token since the last entry's end (its value is printed at the next)
        self.code = {}; self.data = {}

    # ---------------- helpers
    def frame_label(self): return self.flab if self.curf else None
    def th(self):
        """a user function's frame: [return word][this][parameters][env, locals][temps] (the library's: no this; a built-in
        method's receiver is its first parameter, the same slot)"""
        return int(self.curf > 0 and not self.rom)
    def fn_enter(self, k):
        """a function's body starts (k: its table index): the outer context saved (sv0 the top level's expression stacks, sv1 ... sv3
        a function's), a fresh one: no locals, empty stacks above the outer's (obase / dbase), a frame label"""
        if self.curf >= 2: return self.fail(41)
        if self.curf == 0: self.sv0 = self.obase + 8 * self.dbase + 128 * self.tb
        else:
            self.sv1 = self.nloc + 64 * self.npar + 1024 * self.obase + 8192 * self.ca
            self.sv2 = self.dbase + 16 * self.tb + 512 * self.fsym + 16384 * self.fmark
            self.sv3 = self.cfn + 16 * self.flab + 1024 * self.fcsp
        if self.curf == 1 and not self.rom: self.deflab(self.clab, RETC)     # (it makes closures)
        self.curf += 1; self.cfn = k; self.nloc = self.npar = self.tb = self.ca = 0; self.fsym = self.nsym; self.fmark = self.nlet
        self.obase, self.dbase, self.fcsp = self.osp, self.nd, self.csp
        self.flab = self.newlab(); self.cs[self.csp - 1][2] = self.flab
        if self.curf == 1 and not self.rom: self.clab = self.newlab(); self.optlab.add(self.clab)     # (its RETs' label)
    def fn_exit(self):
        """a function's body ended: the outer context back"""
        self.nsym = self.fsym; self.curf -= 1
        if self.curf == 0:
            v = self.sv0; self.obase, self.dbase, self.tb = v % 8, v // 8 % 16, v // 128
            self.nloc = self.npar = self.fsym = self.cfn = self.flab = self.fcsp = self.ca = self.fmark = 0
        else:
            self.nloc, self.npar, self.obase, self.ca = self.sv1 % 64, self.sv1 // 64 % 16, self.sv1 // 1024 % 8, self.sv1 // 8192
            self.dbase, self.tb, self.fsym, self.fmark = self.sv2 % 16, self.sv2 // 16 % 32, self.sv2 // 512 % 32, self.sv2 // 16384
            self.cfn, self.flab, self.fcsp = self.sv3 % 16, self.sv3 // 16 % 64, self.sv3 // 1024
    def closelab(self):
        """a top-level function's RETs carry its close label (RET + it is RETC once the function makes a closure: fn_enter)"""
        return self.clab if self.curf == 1 and not self.rom else None
    def ret(self, b, a=0):
        """RET b; a top-level function's: RET b, local 1 with its close label (cc_ref RETC)"""
        lab = self.closelab()
        self.emit('RET', (a, 0), b=b, c=(L(self.npar + 1 + self.th()), 0) if lab is not None else (0, 0), label=lab)
    # Closures: a function inside a function (curf 2) reads and writes its outer function's variables through that invocation's
    # env cell (the library's: its base word holds the frame's address while it runs, the cell's own copy of the frame after it
    # returned: RETC). Every function's local 1 holds an env cell: a top-level function's own (once it makes a closure), an inner
    # function's outer one (callv writes it: an inner function's meta has 16 added). x at the outer frame's slot s:
    #   read  LDI t, local1, #0   LDI t, t, #s          write  LDI t, local1, #0   STI t, #s, v
    def captured(self, j):
        """symbol j is the outer function's variable (an inner function reads it through its env)"""
        return (self.sym[j][2] == 2 and self.curf == 2 and not self.rom
                and (NIMP <= j < self.fsym or j >= NS - self.fmark))
    def envbase(self, t):
        """t := the outer frame's base (the env cell's base word)"""
        self.emit('LDI', t, (L(self.npar + 1 + self.th()), 0), (K(0), 0))
    def cread(self, j):
        """captured symbol j's value pushed (a temp)"""
        i = self.nd; t = self.tmp(i); self.envbase(t); self.emit('LDI', t, t, (K(self.var(j) - 256), 0)); self.push_od(TMP, self.sym[j][4])
    def cwrite(self, j, v):
        """captured symbol j := operand v (scratch: the temp above the stack's top)"""
        t = self.tmp(self.nd); self.envbase(t); self.emit('STI', t, (K(self.var(j) - 256), 0), v)
    def fnnew(self):
        """a table entry for a function that isn't called by its name (an expression, one inside a function)"""
        if self.nfn >= self.NF: self.fail(23); return 0
        k = self.nfn; self.fn[k] = [0, H2M + k, self.newlab(), 0, 0]; self.nfn += 1; self.nfdef += 1
        return k
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
        if self.nlab >= self.NL: self.fail(20)
        self.nlab += 1; return self.nlab - 1
    def deflab(self, l, v):
        if l < self.NL: self.lab[l] = v               # (a label past NL comes only after error 20)
    def here(self): return self.cb // 2 + self.cp      # (code labels: an instruction pair's index, the address / 2)
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
    def top_op(self): return (self.ops[self.osp - 1], self.opv[self.osp - 1]) if self.osp > self.obase else (0, 0)
    def lookup(self, h):
        """the current function's names first: its latest block-scoped let / const of that name, else its parameter or
        variable; then outside it the latest block-scoped one, else the latest other name (in a valid program a visible
        block-scoped binding is the innermost of its function: a var of the same name in its block would be a redeclaration);
        else -1 (an implicit global)"""
        hit = lambda j: (self.sym[j][0], self.sym[j][1]) == h and (j >= NIMP or j < self.nimp or self.rom)
        for r in (range(NS - self.nlet, NS - self.fmark), range(self.nsym - 1, self.fsym - 1, -1), range(NS - self.fmark, NS),
                  range(self.fsym - 1, -1, -1)):
            for j in r:
                if hit(j): return j
        return -1
    def settype(self, j, t):
        """symbol j's static type := t. (The CSS compiler writes one symbol per token: when this token wrote an implicit global's
        entry the type stays, unless it is a string's, which would make a + chain print in pieces: error 61)"""
        if self.symstep and self.sym[j][4] != t:
            if self.sym[j][4] == 2: self.fail(61)
            return
        self.sym[j][4] = t
    def implicit(self, h, assign):
        """an undeclared name becomes a global: at the top level, assigned, an ordinary one; else implicit entry nimp (kind 3 if read
        first, until it is assigned)"""
        if not self.curf and assign:
            if self.dp >= SDATA: self.fail(25); return 0
            self.declare(h, 1, self.dp); self.dp += 1; return self.nsym - 1
        k = self.nimp
        if k >= NIMP: self.fail(24); return 0
        self.sym[k] = [h[0], h[1], 1 if assign else 3, IMPC + k, 0, 0]; self.nimp += 1; self.symstep = 1; return k
    def fnlook(self, h):
        """function table index for a name, or -1"""
        return next((k for k in range(self.nfn) if (self.fn[k][0], self.fn[k][1]) == h), -1)
    def fnfind(self, h):
        """function table index for a name (adding it, with a new label, if absent)"""
        for k in range(self.nfn):
            if (self.fn[k][0], self.fn[k][1]) == h: return k
        if self.nfn >= self.NF: self.fail(23); return 0
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
        return int(self.pn[0] > 0 and self.csp > self.fcsp)
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
        return (L(a - PARAM0 + 1 + self.th()) if a >= PARAM0 else L(a + self.th())) if k == 2 else a
    def tmp(self, i): return (L(1 + self.th() + self.npar + self.tb + i - self.dbase), int(self.curf > 0))    # T(i): past the locals (+ the frame label)
    def arg_end(self):
        """an argument or an array element ended: into its temp, which leaves the operand stack (the temps' base tb moves past it
        until the call is made)"""
        self.to_temp(self.nd - 1); self.nd -= 1; self.tb += 1
    # an od entry also holds the temps' base tb it was pushed at (* 16384): below a call's collapsed arguments a descriptor's temp
    # is T(its own tb + i), which a snapshot needs (every other change is to descriptors pushed at the current tb)
    def desc(self, i): return self.od[i] % 4096
    def otype(self, i): return self.od[i] // 4096 % 4
    def set_od(self, i, d, t): self.od[i] = self.tb * 16384 + t * 4096 + d
    def push_od(self, d, t, k=0):
        """push a descriptor (k: a big constant's value). A big constant only stays pending on top: one below goes to its temp"""
        if self.nd >= ODN or self.nd + self.tb >= TBMAX: return self.fail(22)
        if self.nd and self.desc(self.nd - 1) == KBIG: self.src(self.nd - 1)
        self.set_od(self.nd, d, t); self.nd += 1
        if d == KBIG: self.pk = k
    def push_num(self, v, t=3):
        v = s20(v)
        if -128 <= v < KLIM: self.push_od(K(v), t)
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
        for i in range(self.dbase, self.nd if n is None else n):
            d = self.desc(i)
            if d < 768 and hit(d):
                tb = self.od[i] // 16384; f = (L(1 + self.th() + self.npar + tb + i - self.dbase), int(self.curf > 0))
                self.emit('MOV', f, (d, 0)); self.od[i] = tb * 16384 + self.otype(i) * 4096 + TMP
    def pend(self, i, cop, b, c):
        """descriptor i := the pending comparison b cop c (or ! b: cop NOT)"""
        self.set_od(i, CND + 4 * CNDOPS.index(cop) + 2 * b[1] + c[1], 1); self.pk = (b[0] - 512) * 1024 + c[0]
    def branch(self, lab, sense):
        """pop the top value and jump to lab if its truth is sense (a pending comparison fuses into the jump)"""
        i = self.nd - 1; d = self.desc(i); self.nd -= 1
        if d >= CND:
            cop = CNDOPS[(d - CND) // 4]; b = (self.pk // 1024 + 512, (d - CND) // 2 % 2); c = (self.pk % 1024, (d - CND) % 2)
            if cop == NOT: return self.emit('JZ' if sense else 'JNZ', b=b, label=lab)
            return self.emit(self.jname(cop, sense), b=b, c=c, label=lab)
        if isK(d):                                       # a constant condition: jump or not, known now
            if (d != K(0) and d not in FALSYK) == sense: self.emit('JMP', label=lab)
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
                and not (self.ops[self.osp - 1] == M_CADD and 2 in (self.opv[self.osp - 1], self.otype(self.nd - 1))
                         and self.opv[self.osp - 2] < 4 * (PIECES - 1))): self.src(self.nd - 1)        # (M_PRINT is below M_CADD)
        npop = 0
        while not self.err and self.osp and 0 < prec(self.ops[self.osp - 1]) and prec(self.ops[self.osp - 1]) >= minprec:
            if npop == popcap(minprec): return self.fail(22)
            npop += 1
            self.osp -= 1; code, val = self.ops[self.osp], self.opv[self.osp]
            last = not (self.osp and 0 < prec(self.ops[self.osp - 1]) >= minprec)
            dest = mode[1] if last and isinstance(mode, tuple) else None
            if code in (AND, OR):                       # the left operand is in T(i), tested; the right one joins it there
                i = self.nd - 2; self.put(self.tmp(i), i + 1); self.nd -= 1
                self.set_od(i, TMP, tmerge(val // self.LM, self.otype(i + 1))); self.deflab(val % self.LM, self.here())
            elif code == M_TELSE:                       # c ? a : b: a went to T(i); b joins it
                i = self.nd - 1; t = tmerge(val // self.LM, self.otype(i)); self.to_temp(i); self.set_od(i, TMP, t); self.deflab(val % self.LM, self.here())
            elif code == NOT and last and mode == 'br':
                i = self.nd - 1; self.pend(i, NOT, self.src(i), (0, 0))
            elif code in (NOT, NEG, TYPEOF, BNOT):      # (user code's -x: DNEG; typeof x: KIND's test 'typeof'; ~x: x ^ -1)
                i = self.nd - 1; b = self.src(i); t = {NOT: 1, NEG: 3, TYPEOF: 2, BNOT: 3}[code]
                op = 'KIND' if code == TYPEOF else 'DBIT' if code == BNOT else 'DNEG' if code == NEG and not self.rom else NAME[code]
                c = (K(KINDS.index('typeof')) if code == TYPEOF else K(-1) if code == BNOT else K(0) if op == 'DNEG' else 0, 0)
                o = self.tmp(i) if dest is None else (dest, 0)
                if code == BNOT: o = (o[0] + 1024 * (BXOR - BAND), o[1])
                self.emit(op, o, b, c); self.set_od(i, TMP if dest is None else dest, t)
            elif code == M_CADD:                        # + at a console.log argument's top level: a string on either side splits it
                i = self.nd - 2
                if 2 in (val, self.otype(i + 1)) and self.opv[self.osp - 1] < 4 * (PIECES - 1):
                    self.opv[self.osp - 1] += 4                # two pieces (M_PRINT is right below)
                else: self.binop(ADD, i, dest)                 # (past PIECES: the last two joined)
            else: self.binop(code, self.nd - 2, dest, mode == 'br' and last)

    def jname(self, cop, sense=True):
        """the jump on comparison cop, or (sense false) on its negation: user code's == / != are the loose jumps, and a relation's
        negation is JNLT ... JNGE (NaN: false either way)"""
        if not sense and cop in (LT, GT, LE, GE) and not self.rom: return 'JN' + NAME[cop]
        if not sense: cop = INV[cop]
        return 'J' + (DYN[cop][1:] if cop in (LEQ, LNE) and not self.rom else NAME[cop])
    def opname(self, code):
        """user code's arithmetic and comparisons are the dynamic operators (integers in the machine, anything else in the
        library); the runtime library's are raw"""
        return NAME[code] if self.rom else DYN[code]
    def dynop(self, code, o, b, c):
        """o := b code c (a bitwise operator: DBIT, the operator in A's 1024s)"""
        if code in BITOPS: self.emit('DBIT', (o[0] + 1024 * (code - BAND), o[1]), b, c)
        else: self.emit(self.opname(code), o, b, c)
    def btype(self, code, lt, rt):
        """the static type of lt code rt: a comparison is a boolean; + a string if either side is one (else unknown)"""
        if code in CMPS: return 1
        if code == ADD: return 2 if 2 in (lt, rt) else 0
        return 3
    def binop(self, code, i, dest, pend=False):
        lt, rt = self.otype(i), self.otype(i + 1)
        b, c = self.src(i), self.src(i + 1); self.nd -= 1; t = self.btype(code, lt, rt)
        if pend and code in CMPS: self.pend(i, code, b, c)      # (user code: the jump traps for anything but integers)
        elif dest is None: self.dynop(code, self.tmp(i), b, c); self.set_od(i, TMP, t)
        else: self.dynop(code, (dest, 0), b, c); self.set_od(i, dest, t)

    def forof(self, j, isin):
        """for (x of / in: two temps for the loop (the array and the index: tb moves past them), then e (C_FOROF)"""
        if self.tb + 2 > TBMAX: return self.fail(22)
        t = self.pop_cs(); self.tb += 2; self.push_cs(C_FOROF, t[1], t[3], j, int(isin), e=t[5]); self.mode = S_OPND
        if not isin: self.emit('MOV', self.tmp(-1), (K(0), 0))
    def forof_end(self):
        """for (x of / in e)'s ')': the loop's head (C_FOROF's comment), then its body (C_LOOPB, d 2: the temps to free)"""
        t = self.pop_cs(); i = self.nd - 1; a, ix = self.tmp(-2), self.tmp(-1)
        self.put(ix if t[4] else a, i)                         # for in: keys(e) into a: its frame at a, e its argument (ix, which it zeroes)
        if t[4]: self.emit('CALL', (self.ent.get('keys', 0) // 2, 0), w1=(a[0] - 256, a[1]))
        self.nd = i; self.deflab(t[1], self.here())
        n, x = self.tmp(0), (self.var(t[3]), 0)                # (GETX's trap needs a temp: n)
        if self.captured(t[3]): return self.fail(80)          # (an outer function's variable: no for of / in target)
        if t[4]: self.emit('GETX', n, a, ix); self.emit('JEQ', b=n, c=(K(UNDEF), 0), label=t[2]); self.emit('MOV', x, n); self.step1(True)(ix, ix)
        else:
            self.emit('LDI', n, a, (K(-1), 0)); self.emit('JGE', b=ix, c=n, label=t[2]); self.emit('GETX', n, a, ix)
            self.emit('MOV', x, n); self.step1(True)(ix, ix)
        self.push_cs(C_LOOPB, t[1], t[2], 0, 2, e=t[5]); self.mode = S_LBRACE
    def compound(self, code, i, o):
        """x op= e with the old value at i, e above: into o; its static type"""
        self.dynop(code, o, self.src(i), self.src(i + 1)); return self.btype(code, self.otype(i), self.otype(i + 1))

    def cond_ctx(self, closer):
        """this token ends a statement-level expression that a branch takes (an if / while / do-while condition, a for test)"""
        if any(self.ops[k] >= 100 for k in range(self.obase, self.osp)): return False
        t = self.top_cs()[0]
        return (closer == 41 and t in (C_IFC, C_WHILEC, C_DOB, C_DOB1)) or (closer == 59 and t == C_FORCOND)
    def dest_ctx(self):
        """an assignment's value ends here: its last operator may write the target"""
        t = self.top_cs()
        if any(self.ops[k] >= 100 for k in range(self.obase, self.osp)) or t[0] != C_ASSIGN or t[2] or self.captured(t[1]): return None
        return ('dest', self.var(t[1]))
    def end_mode(self, closer):
        return 'br' if self.cond_ctx(closer) else self.dest_ctx()

    def print_call(self, sep):
        """a console.log argument ended: its pieces (a + chain with a string) are on the operand stack from d0; print each"""
        c = self.opv[self.osp - 1] // 4; d0 = self.nd - 1 - c
        for i in range(d0, self.nd):
            flags = 2 * (SEP[sep] if i == self.nd - 1 else 0) + 8 * (c > 0)   # (8: a piece, made a string)
            if self.desc(i) == KBIG: self.emit('PRINTK', (flags, 0), w1=self.pk)
            else: self.emit('PRINT', (flags, 0), self.src(i))
        self.nd = d0

    def numlit(self, v):
        """a double's literal (its string at v[0], v[1] characters): NUMLIT into a global of its own, its cache"""
        a, n = v
        if a >= NOROOM: return self.fail(26)
        self.datum(a - 1, n)
        if self.dp >= SDATA: return self.fail(25)
        g = self.dp; self.dp += 1
        self.emit('NUMLIT', (g, 0), w1=a - STRTAG); self.push_od(g, 3); self.mode = S_OPER

    def key_name(self, h):
        """a property name (identifier token): its key, the interned address (-1: failed)"""
        if self.tid >= NOROOM: self.fail(26); return -1
        return self.intern(h, self.tid, self.tlen)
    def marker(self):
        """the innermost marker on the operator stack (0: none)"""
        return next((self.ops[k] for k in range(self.osp - 1, -1, -1) if self.ops[k] >= 100), 0)

    def join_pieces(self):
        """a + chain's pieces (M_PRINT on top) before an operator that is not +: joined into one string (the left operand)"""
        t, tv = self.top_op()
        if t != M_PRINT or tv < 4: return
        d0 = self.nd - 1 - tv // 4; self.src(self.nd - 1)    # (a big constant on top first: one instruction per join)
        for k in range(d0 + 1, self.nd): self.emit('DADD', self.tmp(d0), self.src(d0), self.src(k)); self.set_od(d0, TMP, 2)
        self.nd = d0 + 1; self.opv[self.osp - 1] = tv % 4

    def prop_read(self, i, key, keep=False):
        """o.key with [o] at i: its value replaces it (keep: pushed above it, for o.key op= e)"""
        o = self.src(i); d = self.nd if keep else i
        if keep and (self.nd >= ODN or self.nd + self.tb >= TBMAX): return self.fail(22)
        self.emit('GETP', self.tmp(d), o, (key - self.db, 0))
        if keep: self.set_od(d, TMP, 0); self.nd += 1
        else: self.set_od(i, TMP, 0); self.nd = i + 1

    def prop_write(self, i, key, val):
        """o.key = val with [o] at i; it is popped"""
        self.emit('SETP', self.src(i), val, (key - self.db, 0)); self.nd = i

    def meth_end(self, tv, last):
        """a method call's ')': M_METH's value tv = the method + 64 * the commas; the receiver and the arguments above its slot"""
        name, ents, ty = ALLM[tv % 64]; argc = tv // 64 + last
        if argc not in ents: return self.fail(77)
        e = ents[argc]
        if last: self.arg_end()
        self.tb -= argc + 1; d0 = self.nd - 1; f = self.tmp(d0)
        self.emit('CALL', (self.ent.get(e, 0) // 2, 0), w1=(f[0] - 256, f[1]))
        self.nd = d0; self.push_od(TMP, ty); self.mode = S_OPER

    def arr_elem(self, tv):
        """an array literal's element ended (','): tv elements before it. The first 8 are collapsed arguments of mkarrN, made at the
        eighth; past it each is stored (SETX of the next index: its trap appends)"""
        if tv >= 8: self.arr_store(tv)
        else:
            self.arg_end()
            if tv == 7: self.arr_make(8)
        self.opv[self.osp - 1] = tv + 1; self.mode = S_OPND

    def arr_store(self, k):
        """element k (past the eighth, on top) into the array below it"""
        if k >= KLIM: return self.fail(22)
        i = self.nd - 1; self.emit('SETX', self.src(i - 1), (K(k), 0), self.src(i)); self.nd = i

    def arr_make(self, n):
        """mkarrN of the n collapsed elements above the slot"""
        self.tb -= n; d0 = self.nd - 1; f = self.tmp(d0)
        self.emit('CALL', (self.ent.get(f'mkarr{n}', 0) // 2, 0), w1=(f[0] - 256, f[1])); self.set_od(d0, TMP, 0)

    def arr_end(self, n, last):
        """an array literal's ']': n elements before (last: and one just ended)"""
        if n >= 8:
            if last: self.arr_store(n)
        else:
            if last: self.arg_end(); n += 1
            self.arr_make(n)
        self.mode = S_OPER

    def okey_end(self, tv, close):
        """an object literal's value ended (',' or, close, '}'): store the pair (tv: the key's string-area offset, 0 a number key below
        the value)"""
        self.osp -= 1; i = self.nd - 1
        if tv: self.emit('SETP', self.src(i - 1), self.src(i), (tv, 0)); self.nd = i
        else: self.emit('SETX', self.src(i - 2), self.src(i - 1), self.src(i)); self.nd = i - 1
        if close: self.osp -= 1; self.mode = S_OPER                 # (M_OBJ)
        else: self.mode = S_OKEY

    def case_end(self):
        """a case value ended (':'): J!= Tnext, T(0), value  Bk:  (the switch's value in T(0), this one above it; strings are
        compared by the library's jcmp)"""
        c = self.pop_cs(); tn = self.newlab()
        self.emit('JNE', b=self.src(self.dbase), c=self.src(self.dbase + 1), label=tn)
        self.nd = self.dbase
        if c[2]: self.deflab(c[1], self.here())
        t = self.top_cs(); t[1] = tn; t[4] |= 1; self.mode = S_STMT

    def stmt_level(self):
        """an assignment to x[k]: only as a statement of its own"""
        return self.osp == self.obase and self.top_cs()[0] == C_EXPR

    def index_read(self, i, keep=False):
        """x[k] with [x, k] at i, i + 1: its value replaces them (keep: pushed above them, for x[k] op= e)"""
        x, k = self.src(i), self.src(i + 1)
        d = self.nd if keep else i
        if keep and (self.nd >= ODN or self.nd + self.tb >= TBMAX): return self.fail(22)
        self.emit('LDI' if self.rom else 'GETX', self.tmp(d), x, k)    # (GETX: an array in bounds inline, else getx)
        if keep: self.set_od(d, TMP, 0); self.nd += 1
        else: self.set_od(i, TMP, 0); self.nd = i + 1

    def index_write(self, i, val):
        """x[k] = val with [x, k] at i, i + 1 (val an operand); they are popped"""
        self.emit('STI' if self.rom else 'SETX', self.src(i), self.src(i + 1), val); self.nd = i

    def intr_end(self, tv):
        """an intrinsic's ')': its operands from d0 + 1 (d0: the slot of its value)"""
        n, d0 = tv % 32, tv // 32; a = [self.src(i) for i in range(d0 + 1, self.nd)]
        if len(a) != INTRN[n]: return self.fail(77)
        name = INTR[n]; t = self.tmp(d0)
        if name in ('__kind', '__alloc') and not isK(a[1][0]): return self.fail(77)       # (the test or kind: a constant)
        if name in ('__fl', '__fv') and not isK(a[0][0]): return self.fail(77)
        if name == 'peek': self.emit('LDI', t, a[0], (K(0), 0))
        elif name == 'poke': self.emit('STI', a[0], (K(0), 0), a[1])
        elif name == '__fp': self.emit('GETFP', t)
        elif name == 'prn': self.emit('PRINT', (0, 0), a[0])
        elif name == '__dadd': self.emit('DADD', t, a[0], a[1])
        elif name == '__kind': self.emit('KIND', t, a[0], a[1])
        elif name == '__alloc': self.emit('ALLOC', t, a[0], a[1])
        elif name == '__nput': self.emit('NPUT', a[0], a[1], (K(0), 0))
        elif name == '__apush': self.emit('APUSH', (K(0), 0), a[0], a[1])
        elif name == '__net': self.emit('NET', t, a[0])
        elif name == '__fl': self.emit(FLINE_I[kval(a[0][0])], a[1], a[2], a[3])
        elif name == '__fv': self.emit(FVAL_I[kval(a[0][0])], t, a[1], a[2])
        elif name in ('__mcmp', '__mfeq', '__mfref', '__mwalk'): self.emit('MOV', t, a[2]); self.emit(name[2:].upper(), t, a[0], a[1])
        elif name != 'halt': self.emit(name[2:].upper(), a[0], a[1], a[2])         # (MCPY, MUPPER, MLOWER, MFILL)
        else: self.emit('PUTC', (1 + MARKEND, 0), (K(0), 0)); self.emit('HALT')     # (the output's end: the REPL shows it, as at a program's end)
        self.nd = d0; self.push_od(TMP if name in INTRV else K(0), 0)

    def print_end(self):
        """console.log(...) ended. Its PRINTs printed every argument, so it leaves no value: it must be a statement of its own
        (C_EXPR, nothing else open), or what a return or an arrow's expression body returns (C_RETURN: undefined)"""
        t = self.top_cs()[0]
        if self.osp > self.obase or t not in (C_EXPR, C_RETURN): return self.fail(30)
        if t == C_RETURN: self.push_od(K(UNDEF), 0); self.mode = S_OPER; return
        self.pop_cs(); self.mode = S_INC

    def call_end(self, tv, last):
        """a call's ')': its slot T(d0) (pushed at '(') takes the return word, the arguments are in T(d0 + 1) .... Our calls pass
        exactly as many words as the function takes, so every call and the definition must agree on the count (the first one
        seen sets it; 76 otherwise)"""
        k, argc = tv % self.FM, tv // (4 * self.FM) + last
        if last: self.arg_end()
        if self.fn[k][4] and self.fn[k][4] != argc + 1: return self.fail(76)
        self.fn[k][4] = argc + 1
        self.tb -= argc + 1 - self.rom; d0 = self.nd - 1; f = self.tmp(d0)     # (a user function's this)
        self.emit('CALL', label=self.fn[k][2], w1=(f[0] - 256, f[1]))
        self.nd = d0; self.push_od(TMP, (tv // self.FM) % 4)

    def callv_end(self, tv, last):
        """a call of a value's ')': CALLV A, its slot (the callee there, its this and arguments above). M_CALLV's value tv: 64 *
        commas + 1 a method call (this: the receiver, A + 32) / 2 f.call (this: the first argument) / 4 f.apply (A 63)"""
        argc, fl = tv // 64 + last, tv % 64
        if last: self.arg_end()
        if fl & 4 and argc != 2: return self.fail(77)
        self.tb -= argc + int(not fl & 6); d0 = self.nd - 1; f = self.tmp(d0)
        a = 63 if fl & 4 else (argc + 31 if argc else 0) if fl & 2 else argc + 32 * int(fl in (1, 8))
        self.emit('CALLV', (a, 0), w1=(f[0] - 256, f[1]))
        if fl & 8: self.emit('MOV', f, self.tmp(d0 + 1))       # (new: the object)
        self.set_od(d0, TMP, 0); self.mode = S_OPER

    def meth_call(self, dyn, key):
        """o.f( / o[k]( : the callee into o's slot, o above it as its this (CALLV's method flag)"""
        i = self.nd - 2 if dyn else self.nd - 1
        if dyn:
            if self.nd + self.tb >= TBMAX: return self.fail(22)
            self.emit('GETX', self.tmp(i + 2), self.src(i), self.src(i + 1)); self.put(self.tmp(i + 1), i); self.emit('MOV', self.tmp(i), self.tmp(i + 2))
        else: self.put(self.tmp(i + 1), i); self.emit('GETP', self.tmp(i), self.tmp(i + 1), (key - self.db, 0))
        self.nd = i + 1; self.set_od(i, TMP, 0); self.snapshot(lambda q: q < 256); self.tb += 1
        self.push_op(M_CALLV, 1); self.mode = S_OPND

    def new_call(self, h):
        """new F(: F's value in T(d0) (a variable's, or a declared function's), mknew(F) into its this T(d0 + 1) (a call of the
        library's: its frame there, F copied above it), then the arguments; callv_end makes the object the value (M_CALLV's 8)"""
        j = self.lookup(h); k = self.fnlook(h) if j < 0 else -1
        if j < 0 and k < 0: return self.fail(4)
        if j >= 0 and self.captured(j): self.cread(j)
        elif j >= 0: self.push_od(self.var(j), 0)
        else: self.emit('NUMLIT', (FCACHE + k, 0), w1=k); self.push_od(FCACHE + k, 0)
        if self.err: return
        d0 = self.nd - 1; self.to_temp(d0); self.snapshot(lambda q: q < 256)
        if self.nd + self.tb + 2 > TBMAX: return self.fail(22)
        self.emit('MOV', self.tmp(d0 + 2), self.tmp(d0)); f = self.tmp(d0 + 1)
        self.emit('CALL', (self.ent.get('mknew', 0) // 2, 0), w1=(f[0] - 256, f[1]))
        self.tb += 1; self.push_op(M_CALLV, 8); self.mode = S_OPND

    def timer_loop(self):
        """the program's end when it set a timer: L: CALL nexttimer -> T(0) (a callback, or 0: none left); JZ T(0) -> end;
        CALLV 0 T(0); JMP L"""
        t = self.tmp(0); l = self.here()
        self.emit('CALL', (self.ent.get('nexttimer', 0) // 2, 0), w1=(t[0] - 256, t[1])); self.emit('JZ', (l + 4, 0), b=t)
        self.emit('CALLV', (0, 0), w1=(t[0] - 256, t[1])); self.emit('JMP', (l, 0))

    def this_val(self):
        """this: a function's own (frame slot 1; its entry's d |= 2: uthis); an arrow's is its outer function's (through the env,
        that function's entry d |= 2); at the top level, and in an arrow there, the global object"""
        f = self.cs[self.fcsp - 1] if self.curf else None
        o = self.cs[self.sv3 // 1024 - 1] if self.curf == 2 else None
        if f is not None and not f[4] & 1: f[4] |= 2; self.push_od(L(1), 0)
        elif o is not None and not o[4] & 1:
            o[4] |= 2; t = self.tmp(self.nd); self.envbase(t); self.emit('LDI', t, t, (K(1), 0)); self.push_od(TMP, 0)
        else: self.emit('NUMLIT', (GCELL, 0), w1=GLOBK); self.push_od(GCELL, 0)
        self.mode = S_OPER
    def mode_stmt(self): self.mode = S_STMT
    def asi_close(self, f):
        """'}' right after a statement without ';': end the statement (knowing the next token is not 'else'),
        then close the block"""
        self.asic = 1; f(); self.asic = 0
        if not self.err: self.close_block()

    def incdec(self, h, v, x=0, pre=0):
        """++ (v 7) / -- (8) of a variable. x: 0 a statement (pre: ++x), 1 ++x in an expression (its new value), 2 x++ (the old)"""
        j = self.lookup(h)
        if j < 0: return self.fail(6)
        if self.sym[j][5]: return self.fail(64)
        if self.captured(j):                                 # through the env: base at T(nd + 1), the value at T(nd) (cc_ref.captured)
            u, t, w = self.tmp(self.nd), self.tmp(self.nd + 1), self.tmp(self.nd + 2); s = (K(self.var(j) - 256), 0)
            self.envbase(t); self.emit('LDI', u, t, s); self.step1(v == 7)(w if x == 2 else u, u); self.emit('STI', t, s, w if x == 2 else u)
            if x: self.push_od(TMP, 3); self.pm = 3; self.mode = S_OPER
            else: self.mode = S_INC
            return
        o = self.var(j)
        if x: self.snapshot(lambda q: q == o)
        if x == 2: self.push_od(o, 3); self.to_temp(self.nd - 1)
        if not x and not pre: self.echo_val((o, 0))           # (REPL: x++'s value is the old one, ++x's the new)
        self.step1(v == 7)((o, 0), (o, 0))
        if not x and pre: self.echo_val((o, 0))
        if x == 1: self.push_od(o, 3)
        if x: self.pm = 3; self.mode = S_OPER
        else: self.mode = S_INC

    def step1(self, up):
        """++ / -- of an operand: the instruction and its constant operand C (user code: x - -1, which never joins strings)"""
        if self.rom: return lambda a, b: self.emit('ADD' if up else 'SUB', a, b, (K(1), 0))
        return lambda a, b: self.emit('DSUB', a, b, (K(-1 if up else 1), 0))

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
        elif self.p2 == 16 and cn == 62: self.p2 = 17       # >> then >: >>> (or >>>=)
        elif self.p2:
            asg = int(self.p2 in (15, 16, 17) and cn == 61)                              # <<= >>= >>>=
            tok = ('P', self.p2 + 6 * asg); self.tflag = int(self.p2 in (1, 2) and cn != 61)      # (== / !=: the flag)
            if (self.p2 in (1, 2) and cn == 61) or asg: self.lx = 5
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
        elif self.tkc >= 2 or (isdg(c) and self.tkc != 1):  # a number: digits [. digits] [e [+-] digits] (tkc 2 3 4 5: the part)
            if self.tkc < 2: self.tkc = 2; self.acc = 0; self.h1 = self.h2 = 0     # acc: its integer value; h1: its characters; h2: a double
            if isdg(c) and self.tkc == 2: self.acc = self.acc * 10 + c - 48
            elif c == 46: self.tkc = 3; self.h2 = 1
            elif c in (69, 101): self.tkc = 4; self.h2 = 1
            elif self.tkc == 4: self.tkc = 5
            self.sbyte(self.sdp + 1 + self.h1, c); self.h1 += 1                     # (a double's characters: a string the parser commits)
            st = self.tkc
            if not (isdg(cn) or (st == 2 and cn in (46, 69, 101)) or (st == 3 and cn in (69, 101)) or (st == 4 and cn in (43, 45))):
                if st == 4 or (st == 5 and not isdg(c)): tok = ('P', 31)        # an exponent without digits ("2e", "1e+"): no number
                elif (self.h2 or self.acc > SMI_HI) and not self.rom:     # a double: its string [len][characters][0] at sdp (the ROM's are raw words)
                    tok = ('NUM', (self.sdp + 1 + NOROOM * int(self.sdp + 2 + self.h1 > SEND), self.h1))
                    self.inul = self.sdp + 1 + self.h1; self.sdp += self.h1 + 2
                else: tok = ('NUM', self.acc)
                self.tkc = 0
        elif isal(c) or (isdg(c) and self.tkc == 1):      # an identifier: hashed; its bytes at sdp (acc: its length so far)
            if self.tkc != 1: self.h1 = self.h2 = 0; self.acc = 0
            self.shash(c); self.tkc = 1
            if self.kpos: self.sbyte(self.sdp + 1 + self.acc, c)      # (sdp itself: the length word)
            self.acc += 1
            if not (isal(cn) or isdg(cn)):
                h = (self.h1, self.h2); tok = ('P', PKW[h]) if h in PKW else ('ID', h)     # (this / new: punctuation)
                self.tkc = 0; self.tlen = self.acc; self.tparen = int(cn == 40)   # (a call follows)
                self.tid = self.sdp + 1 + NOROOM * int(self.sdp + 1 + self.acc >= SEND)    # its address (+ NOROOM: no room)
                if self.kpos: self.inul = self.sdp + 1 + self.acc
                if self.kpos == 2: self.sdp += self.acc + 2
                self.icm = self.acc + 2 if self.kpos == 1 else 0
        elif (c, cn) in TWO: self.p2 = TWO[(c, cn)]
        else: tok = ('P', c)
        if self.pnl:                                      # the pending newline: decide on the next significant character
            if gap:
                if cn in (CONTR if self.repl else CONT): self.pnl = 0
                elif cn not in BLANK + ((47,) if self.repl else (47, 43, 45)): tok = ('P', T_NL); self.pnl = 0
            elif c in (43, 45):                           # ++x / --x: a new statement; x + y / x - y: continues
                if cn == c: tok = ('P', T_NL)
                self.pnl = 0
            elif c == 47 and self.lx == 0: self.pnl = 0   # a division (a comment keeps it pending)
        if tok:
            if tok == ('P', 58) and self.icm: self.sdp += self.icm            # an object literal's key: commit its string
            if tok[0] != 'ID' and tok != ('P', T_NL): self.icm = 0
            if tok != ('P', T_NL):                             # (console.log's log is not a property name)
                self.kpos = 2 if (tok == ('P', 46) and not self.lcon) or (tok == ('ID', KW['function']) and not self.rom) else int(tok in (('P', 123), ('P', 44)))
                self.lcon = int(tok == ('ID', KW['console']))
            self.lt = int(tok[0] in ('ID', 'NUM', 'STR') or (tok[0] == 'P' and tok[1] in (41, 93, 125, 7, 8))) + int(tok == ('ID', KW['return']))
            if tok == ('P', T_NL): self.tline = self.line + (c == 10)
            cp0 = self.cp; self.token(*tok)
            if self.cp - cp0 > EMAX:                     # (instructions; the page's EMAX slots don't hold the rest)
                self.fail(61)
                for k in range(cp0 + EMAX, self.cp): self.code.pop(k, None)
        if c == 10: self.line += 1

    def newline(self):
        """a newline (also in a comment): after return a T_NL at once; after another token that can end a statement, pending"""
        if self.lt == 2: return ('P', T_NL)
        if self.lt or self.repl: self.pnl = 1
        return None

    # ---------------- parser: one token
    def token(self, kind, v):
        nl = kind == 'P' and v == T_NL
        if self.repl and not nl and kind != 'EOF': self.rpend = 1
        self.token_(kind, v)
        if self.repl and nl and not self.err and not self.curf and not self.csp:     # a top-level statement starts on this line:
            if self.mode == S_ELSE: self.deflab(self.pendLa, self.here()); self.mode = S_STMT     # (an if ends at its line, as in Node's REPL)
            if self.mode == S_STMT: self.entry_end(self.tline)
        if self.ca and not self.err: self.mode = {S_OPER: S_OPERC, S_NAMEE: S_NAMEEC}.get(self.mode, self.mode)     # (CMODES)
    def entry_end(self, line):
        """REPL: the entry before line `line` ended: its value printed (echo; only if a token came since the last end), then the
        output's position marked for that line (PUTC with A = 1 + the mark: the page lays the output out under each entry)"""
        if self.rpend:
            t = self.tmp(0); self.emit('CALL', (self.ent.get('echo', 0) // 2, 0), w1=(t[0] - 256, t[1]))
        self.emit('PUTC', (1 + min(line, MARKEND - 1), 0), (K(0), 0)); self.rpend = 0
    def echo_val(self, o):
        """REPL: a top-level expression statement's value (operand o) is the entry's"""
        if self.repl and not self.csp and not self.curf: self.emit('MOV', (ECELL, 0), o)
    def token_(self, kind, v):
        if self.err: return
        isP = lambda c: kind == 'P' and v == c
        isK_ = lambda k: kind == 'ID' and v == KW[k]
        self.symstep = 0                                   # (this token wrote an implicit global's entry: settype)
        m = self.mode
        cc = m in CMODES                                   # (an arrow's expression body: arrow_close)
        if cc: m = self.mode = CMODES[m]
        fallin = m in (S_AFTERELSE, S_LBRACE)              # (a braceless body's statement: no expression statement there)
        if isP(T_NL) and m not in (S_NAMES, S_NAMEE, S_OPER, S_VARAFTER, S_INC, S_OPND, S_BRK): return
        if m == S_NAMES:
            h = self.pn
            if h in WGLOB and isP(46): self.pn = (1, 0); self.mode = S_WDOT; return      # window.x: x
            if (isK_('of') or isK_('in')) and self.top_cs()[0] == C_FORINIT:       # for (x of e) / for (x in e)
                j = self.lookup(h)
                if j < 0: j = self.implicit(h, True)
                if self.err: return
                if self.sym[j][2] == 3: self.sym[j][2] = 1
                return self.forof(j, isK_('in'))
            if isP(58):                                        # a label (outer:): a name of its own (h2 + H2M: no variable's) in the
                if self.top_cs()[0] in (C_FORINIT, C_FORSTEP): return self.fail(67)     # (not in a for header)
                if self.nsym + self.nlet >= NS: return self.fail(24)    # block-scoped region, the next statement's control entry
                self.nlet += 1; self.sym[NS - self.nlet] = [h[0], h[1] + H2M, 0, self.csp, 0, 0]; self.mode = S_STMT; return
            if isP(61) or (kind == 'P' and v in COMPOUND):
                j = self.lookup(h)
                if j < 0 and (self.rom or not isP(61)): return self.fail(5)
                if j < 0: j = self.implicit(h, True)
                if self.err: return
                if self.sym[j][2] == 3: self.sym[j][2] = 1       # (assigned)
                if self.sym[j][5]: return self.fail(64)
                if not isP(61):                                # x op= e: x is the left operand, read first
                    if self.captured(j): self.cread(j)
                    else: self.push_od(self.var(j), self.sym[j][4])
                self.push_cs(C_ASSIGN, j, COMPOUND.get(v, 0) if kind == 'P' else 0); self.mode = S_OPND; return
            if isP(7) or isP(8): return self.incdec(h, v)
            if isP(91) and self.lookup(h) < 0: return self.fail(7)        # NAME[e] = e: an expression statement (x[k] below)
            self.push_cs(C_EXPR); m = self.mode = S_NAMEE
            if self.err: return
        if m == S_NAMEE:
            h = self.pn
            if isP(T_ARROW):                                   # x => / (x) =>
                self.arrow_start(h, 2)
                if not self.err: self.end_params()
                return self.err or self.arrow_body()
            if (isP(41) or isP(44)) and self.top_op()[0] == M_PAREN:     # (x): x, still pending (x => ?); (x, : an arrow's parameters
                self.osp -= 1
                if isP(44): self.mode = S_APAR1
                return
            if h == KW['console']:
                if not isP(46): return self.fail(30)
                self.mode = S_CONLOG; return
            if isP(40):
                if h == KW['putc']: self.push_op(M_PUTC)
                elif self.rom and h in [KW[n] for n in INTR]:          # an intrinsic: its operands stay where they are
                    self.push_op(M_INTR, [KW[n] for n in INTR].index(h) + 32 * self.nd); self.push_od(TMP, 0)
                elif h in GLOBAL_INDEX:                                  # parseInt(s), ...: a method on a dummy receiver
                    self.push_od(TMP, 0); self.tb += 1; self.push_op(M_METH, GLOBAL_INDEX[h])    # (the receiver: unused)
                    if h in (KW['setTimeout'], KW['setInterval']) and self.nfdef < TIMERS: self.nfdef += TIMERS
                elif not self.rom and self.lookup(h) >= 0:   # a variable's value: CALLV (the callee in its slot)
                    j = self.lookup(h); self.snapshot(lambda q: q < 256)
                    if self.captured(j): self.cread(j)
                    else: self.push_od(self.var(j), 0); self.to_temp(self.nd - 1)
                    self.push_op(M_CALLV); self.tb += 1             # (its this: a temp above its slot)
                else:
                    self.snapshot(lambda q: q < 256)          # the callee may change a global still waiting on the stack
                    k = self.fnfind(h); self.push_op(M_CALL, k + self.FM * self.fn[k][3]); self.push_od(TMP, 0)   # its slot
                    if not self.rom: self.tb += 1                    # (and its this)
                self.mode = S_OPND; return
            if isP(7) or isP(8): return self.incdec(h, v, 2)
            if h in WGLOB and isP(46): self.pn = (0, 0); self.mode = S_WDOT; return     # window.x: x
            j = self.lookup(h)
            if j < 0 and h in (KW['String'], KW['Object'], KW['Math']) and isP(46):     # String.fromCharCode(...), Object.create(p), Math.f(x):
                self.push_od(K(0), 0); self.mode = S_DOT if h == KW['String'] else S_MATHDOT; return     # a method on a dummy receiver
            tyo = self.top_op()[0] == TYPEOF
            k = self.fnlook(h) if j < 0 and not self.rom else -1
            if (h in WGLOB or h == KW['Math']) and j < 0 and not self.rom:     # window / globalThis (Math alone): the global object
                self.emit('NUMLIT', (GCELL, 0), w1=GLOBK); self.push_od(GCELL, 0)
            elif k >= 0:                                       # a function's name as a value: its object (made once, cached)
                self.emit('NUMLIT', (FCACHE + k, 0), w1=k); self.push_od(FCACHE + k, 0)
            elif j < 0 and (tyo or self.rom):
                if not tyo: return self.fail(4)
                self.push_od(K(UNDEF), 0)                        # typeof x, x undeclared: "undefined"
            else:
                if j < 0: j = self.implicit(h, False)
                if self.err: return
                if self.captured(j): self.cread(j)
                else: self.push_od(self.var(j), self.sym[j][4])
            m = self.mode = S_OPER
        if m == S_ELSE:
            if isK_('else'):
                t = self.top_cs(); reuse = t[0] == C_ELSEB1
                lb = t[1] if reuse else self.newlab()
                self.emit('JMP', label=lb); self.deflab(self.pendLa, self.here())
                self.pendLa = lb + self.LM * reuse; self.mode = S_AFTERELSE; return
            dook = kind in ('ID', 'EOF') or (kind == 'P' and v in (59, 123, 125, 7, 8, 41))
            self.deflab(self.pendLa, self.here()); self.complete_stmt(1, dook); m = self.mode
        if m == S_DOWHILE:
            if isP(59): return
            if not isK_('while'): return self.fail(66)
            self.mode = S_LPAREN; return
        if m == S_AFTERELSE:
            reuse = self.pendLa >= self.LM
            if isP(123):
                if reuse: self.push_cs(C_BLOCK)
                else: self.push_cs(C_ELSEB, self.pendLa)
                self.mode = S_STMT; return
            if not reuse: self.push_cs(C_ELSEB1, self.pendLa)
            m = self.mode = S_STMT
        if m == S_LBRACE:
            if isP(123): self.mode = S_SWCASE if self.top_cs()[0] == C_SWITCH else S_STMT; return
            if self.top_cs()[0] not in (C_IFB, C_LOOPB, C_DOB): return self.fail(33)
            self.cs[self.csp - 1][0] += BRACELESS; m = self.mode = S_STMT
        if m == S_SWCASE:
            if not (isK_('case') or isK_('default') or isP(125)): return self.fail(74)
            m = self.mode = S_STMT
        if m == S_STMT:
            if kind == 'EOF':
                if self.csp: return self.fail(40)
                if self.rom and self.nfdef < self.nfn: return self.fail(60)
                if not self.rom and (any((self.sym[j][0], self.sym[j][1]) in RESERVED for j in range(self.nsym) if j >= NIMP or j < self.nimp)
                                     or any(self.sym[k][2] == 3 for k in range(self.nimp))     # read, never assigned or declared
                                     or any((self.fn[k][0], self.fn[k][1]) in RESERVED for k in range(self.nfn))): return self.fail(4)
                if self.nfdef >= TIMERS and not self.rom: self.timer_loop()
                if self.repl: self.emit('PUTC', (1 + MARKEND, 0), (K(0), 0))     # (the output's end)
                self.emit('HALT'); return
            if isP(123): self.push_cs(C_BLOCK); return
            if isP(125): return self.close_block()
            if isP(59): return self.end_simple_stmt(kind, v)
            if isP(41) and self.top_cs()[0] == C_FORSTEP: return self.end_simple_stmt(kind, v)
            if isP(7) or isP(8): self.pn = (v, 0); self.mode = S_PREINC; return
            if kind in ('NUM', 'STR') or (kind == 'P' and v in XSTART) or (kind == 'ID' and (v in LITK or isK_('typeof'))):
                if fallin: return self.fail(8)
                self.push_cs(C_EXPR); self.mode = S_OPND; return self.token(kind, v)     # an expression statement: its value is dropped
            if kind != 'ID': return self.fail(8)
            if isK_('var') or isK_('let') or isK_('const'):
                self.pn = (int(isK_('let')) + 2 * int(isK_('const')), 0); self.mode = S_VAR; return
            if isK_('if'): self.push_cs(C_IFC); self.mode = S_LPAREN; return
            if isK_('switch'): self.push_cs(C_SWITCHC); self.mode = S_LPAREN; return
            if isK_('case') or isK_('default'):
                t = self.top_cs(); seen = t[4] & 1
                if t[0] != C_SWITCH: return self.fail(73)
                if isK_('case'):                               # [JMP Bk]  T: <value> J!= Tnext, T(0), value  Bk:
                    bk = self.newlab() if seen else 0
                    if seen: self.emit('JMP', label=bk)
                    self.deflab(t[1], self.here()); self.push_od(TMP, t[4] // 4)      # the switch's value, in T(0)
                    self.push_cs(C_CASE, bk, seen); self.mode = S_OPND; return
                if t[4] & 2: return self.fail(75)              # a second default
                if not seen: self.emit('JMP', label=t[1])      # the value goes to the tests first
                ld = self.newlab(); self.deflab(ld, self.here())
                t[3] = ld; t[4] |= 3; self.mode = S_OCOLON; return
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
            if isK_('break') or isK_('continue'): self.pn = (int(isK_('break')), 0); self.mode = S_BRK; return
            if isK_('function'):                             # a declaration (inside a function: a local variable's value)
                if self.curf >= 2 or (self.rom and self.csp): return self.fail(41)
                lo = self.newlab(); self.emit('JMP', label=lo); self.mode = S_FNAME
                self.push_cs(C_FUNCN if self.curf else C_FUNCB, lo); return
            self.pn = v; self.mode = S_NAMES; return
        if m == S_PREINC:
            if kind != 'ID': return self.fail(10)
            return self.incdec(v, self.pn[0], self.pn[1], 1)
        if m == S_VAR:
            if kind != 'ID' or v in RESERVED: return self.fail(9)
            cst, blk = int(self.pn[0] == 2), self.decl_blk()
            j = self.lookup(v) if not self.curf and not blk and not self.rom else -1
            if j >= 0 and (j < NIMP or (j < self.nsym and not self.pn[0])):    # the program's global of that name (an implicit one,
                self.sym[j][2] = 1; self.sym[j][5] = cst; self.pn = (self.pn[0], j + 1)     # or a var's): the same variable
                self.mode = S_VARAFTER; return
            if self.pn[0] and self.redecl(v): return self.fail(78)
            if self.curf: self.nloc += 1; self.declare(v, 2, self.npar + self.nloc, cst, blk)
            else:
                if self.dp >= SDATA: return self.fail(25)
                self.declare(v, 1, self.dp, cst, blk); self.dp += 1
            self.pn = (self.pn[0], 0); self.mode = S_VARAFTER; return
        if m == S_VARAFTER:
            j = self.pn[1] - 1 if self.pn[1] else NS - self.nlet if self.decl_blk() else self.nsym - 1     # (pn[1]: a reused global + 1)
            if (isK_('of') or isK_('in')) and self.top_cs()[0] == C_FORINIT: return self.forof(j, isK_('in'))
            if isP(61):
                self.push_cs(C_ASSIGN, j, 0, 1 + self.pn[0]); self.mode = S_OPND; return
            if self.pn[0] == 2: return self.fail(65)
            if (self.curf or (self.pn[0] and not self.rom)) and not self.pn[1]:     # a variable without a value: undefined (a global var
                self.emit('MOV', (self.var(j), 0), (K(0 if self.rom else UNDEF), 0))     # is: GINIT; var x runs as nothing)
            if isP(44): self.mode = S_VAR; return
            if (isP(T_NL) or isP(125)) and self.top_cs()[0] in (C_FORINIT, C_FORSTEP): return None if isP(T_NL) else self.fail(53)
            if isP(125): return self.asi_close(lambda: self.end_simple_stmt('P', T_NL))
            return self.end_simple_stmt(kind, v)
        if m == S_BRK:                                         # break / continue (pn[0]: break): a label on its line, or its end
            brk = self.pn[0]
            if kind != 'ID' and not (isP(59) or isP(T_NL) or isP(125)): return self.fail(53)
            if kind == 'ID':                                   # the labeled loop's entry (a label is a loop's: cc_ref S_NAMES)
                j = self.lookup((v[0], v[1] + H2M)); c = self.sym[j][3] if j >= 0 else CD
                if c >= self.csp or self.cs[c][0] not in (C_LOOPB, C_LOOPB1, C_DOB, C_DOB1): return self.fail(56)
                self.emit('JMP', label=self.cs[c][2] if brk else self.cs[c][1]); self.mode = S_INC; return
            e = self.loop_entry(brk)
            if e is None: return self.fail(56)
            self.emit('JMP', label=e[2] if brk else e[1]); m = self.mode = S_INC        # (this token ends the statement)
        if m == S_INC:
            if (isP(T_NL) or isP(125)) and self.top_cs()[0] in (C_FORINIT, C_FORSTEP): return None if isP(T_NL) else self.fail(53)
            if isP(125): return self.asi_close(lambda: self.end_simple_stmt('P', T_NL))
            return self.end_simple_stmt(kind, v)
        if m == S_LPAREN:
            if not isP(40): return self.fail(32)
            self.mode = S_STMT if self.top_cs()[0] == C_FORINIT else S_OPND; return
        if m == S_WDOT:                                        # window.x / globalThis.x: the global x
            if kind != 'ID': return self.fail(69)
            self.mode = S_NAMES if self.pn[0] else S_NAMEE; self.pn = v; return
        if m == S_FNAME:
            fk = self.top_cs()[0]
            if fk == C_FUNCE and isP(40):                      # an anonymous function expression
                nm = self.ops[self.osp - 1] == M_FN and self.opv[self.osp - 1]
                self.emit('MOV', w1=self.db + nm - STRTAG if nm else 0); self.fn_enter(self.fnnew()); m = self.mode = S_FPAREN
                if self.err: return                            # (a label ran out: as cc_dsl, whose S_FPAREN block doesn't run then)
            else:
                if kind != 'ID' or v in RESERVED: return self.fail(34)
                if not self.rom:                               # its value's descriptor (FTAB): [MOV][its name], the name committed
                    if self.tid >= NOROOM: return self.fail(26)
                    self.datum(self.tid - 1, self.tlen); self.emit('MOV', w1=self.tid - STRTAG)
                if fk == C_FUNCB:                              # its calls: CALL its label
                    k = self.fnfind(v); self.nfdef += 1          # (its label: at its end, close_block; the body here, in c / d)
                else:
                    if fk == C_FUNCN:                          # the local variable that holds it (cc_ref FUNCS)
                        self.nloc += 1; self.declare(v, 2, self.npar + self.nloc); self.cs[self.csp - 1][3] = self.nsym - 1
                    k = self.fnnew()
                if self.err: return
                self.fn_enter(k)
                if fk == C_FUNCB:
                    r = self.here() - self.cb // 2; t = self.cs[self.csp - 1]
                    if self.rom: t[3] = r
                    else: t[3], t[4] = r % 64, 4 * (r // 64)
                self.mode = S_FPAREN; return
        if m == S_FPAREN:
            if not isP(40): return self.fail(35)
            self.mode = S_FPARAM; return
        if m == S_FPARAM:
            if isP(41): return self.end_params()
            if kind != 'ID' or v in RESERVED: return self.fail(36)
            self.pn = v; self.mode = S_FPSEP; return
        if m == S_FPSEP:                                       # (a parameter is declared at its ',' or ')': as an arrow's second)
            if not (isP(44) or isP(41)): return self.fail(37)
            self.declare(self.pn, 2, PARAM0 + self.npar); self.npar += 1
            if self.err: return
            if isP(44): self.mode = S_FPARAM; return
            return self.end_params()
        if m == S_APAR1:                                       # (a, b: an arrow's (a in pn)
            if kind != 'ID' or v in RESERVED: return self.fail(36)
            self.arrow_start(self.pn); self.pn = v; self.mode = S_FPSEP; return
        if m == S_MATHDOT:                                     # Math. name: a method (the call: S_OPER, M_METH), a constant, min / max's value
            if kind != 'ID' or not (v in MATH_INDEX or v in [KW[c] for c in MATHK]): return self.fail(69)
            if v in MATH_INDEX and self.tparen: self.pn = (0, 0); self.pm = 4 + MATH_INDEX[v]; self.mode = S_OPER; return
            if v in MATH_INDEX:                                # (a value: dummy[a hidden key], pending as x[k])
                if ALLM[MATH_INDEX[v]][0] not in MATHV: return self.fail(69)
                k = len(MATHK) + MATHV.index(ALLM[MATH_INDEX[v]][0])
            else: k = MATHK[next(c for c in MATHK if KW[c] == v)]
            self.push_od(KBIG, 0, PKSTAT - k); self.pm = 2; self.mode = S_OPER; return
        if m == S_NEW:                                         # new F(...): F's name
            if kind != 'ID' or v in RESERVED: return self.fail(3)
            self.pn = v; self.mode = S_NEWN; return
        if m == S_NEWN:                                        # new F( : F's value, a new object (its prototype F's) as its this
            if not isP(40): return self.fail(35)
            if self.pn in NEW_INDEX:                           # new Number( ...: a method on a dummy receiver (a wrapper)
                self.push_od(TMP, 0); self.tb += 1; self.push_op(M_METH, NEW_INDEX[self.pn]); self.mode = S_OPND; return
            return self.new_call(self.pn)
        if m in (S_AARROW0, S_AARROW):                         # () => / (a, b) =>
            if not isP(T_ARROW): return self.fail(35)
            if m == S_AARROW0:
                self.arrow_start(None, 1)
                if not self.err: self.end_params()
            return self.err or self.arrow_body()
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
        if m == S_DOT:                                         # o . name
            if isP(T_PROTO) or isP(T_PTYPE):                   # o.__proto__ / f.prototype: x[a hidden key]
                self.push_od(KBIG, 0, PKPROTO if isP(T_PROTO) else PKPT); self.pm = 2; self.mode = S_OPER; return
            if kind != 'ID': return self.fail(69)
            if v == KW['length'] or (v in METHOD_INDEX and self.tparen): self.datum(self.tid - 1, self.tlen)   # (its committed bytes' length word)
            if v == KW['length']:                              # a string's or an array's length: the word before its value's address
                i = self.nd - 1; self.emit('LDI', self.tmp(i), self.src(i), (K(-1), 0)); self.set_od(i, TMP, 3); self.mode = S_OPER; return
            if v in FMETH and self.tparen and not self.rom: self.pn = (0, 0); self.pm = PMFN + FMETH[v]; self.mode = S_OPER; return
            if v in METHOD_INDEX and self.tparen:              # x.name( for a method's name: the call (S_OPER)
                self.pn = (0, 0); self.pm = 4 + METHOD_INDEX[v]; self.mode = S_OPER; return
            ks = self.key_name(v)
            if ks < 0: return
            self.pn = (ks, 0); self.mode = S_OPER                 # (a method's name, call or apply: decided at the next token, '(' or not)
            self.pm = 4 + METHOD_INDEX[v] if v in METHOD_INDEX else PMFN + FMETH[v] if v in FMETH and not self.rom else 1; return
        if m == S_OKEY:                                        # { key : value, ... }
            if isP(125): self.osp -= 1; self.mode = S_OPER; return     # {} or a trailing comma (M_OBJ)
            if kind == 'ID': ks = self.key_name(v)
            elif kind == 'STR':
                if v[0] >= NOROOM: return self.fail(26)
                ks = self.intern((v[1], v[2]), v[0], v[3])
            elif kind == 'NUM' and not isinstance(v, tuple): ks = 0; self.push_num(v)       # a number key: as o[n] = v
            else: return self.fail(71)
            if ks < 0: return
            self.push_op(M_OKEY, ks - self.db if ks else 0); self.mode = S_OCOLON; return
        if m == S_OCOLON:
            if not isP(58): return self.fail(72)
            self.mode = S_STMT if self.top_cs()[0] == C_SWITCH else S_OPND; return      # (default's ':')
        if m == S_ABODY:                                       # => {: a block body (the expression body's return goes)
            if isP(123):                                       # (a frame label of its own, defined at its '}')
                self.pop_cs(); self.ca = 0; self.flab = self.newlab(); self.cs[self.csp - 1][2] = self.flab; self.mode = S_STMT; return
            m = self.mode = S_OPND
        if m == S_OPND:
            if kind == 'NUM' and isinstance(v, tuple): return self.numlit(v)
            if kind == 'NUM': self.push_num(v); self.mode = S_OPER; return
            if kind == 'STR':
                if v[0] >= NOROOM: return self.fail(26)
                e = self.intern((v[1], v[2]), v[0], v[3])
                if e < 0: return
                self.push_od(KBIG, 2, e - STRTAG); self.mode = S_OPER; return
            if kind == 'ID' and v in LITK: self.push_od(*LITK[v]); self.mode = S_OPER; return
            if isK_('typeof'): self.push_op(TYPEOF); return
            if isP(T_THIS) and not self.rom: return self.this_val()
            if isP(T_NEW) and not self.rom: self.mode = S_NEW; return
            if isK_('function') and not self.rom:             # a function expression: its value (its name from a key it is the value of)
                if self.curf >= 2: return self.fail(41)
                t, tv = self.top_op()
                self.push_op(M_FN, tv if t == M_OKEY else 0); lo = self.newlab(); self.emit('JMP', label=lo)
                self.push_cs(C_FUNCE, lo); self.mode = S_FNAME; return
            if isP(123):                                       # an object literal: NEW, then each pair as o.key = v
                i = self.nd; self.push_od(TMP, 0)
                if self.err: return
                self.emit('NEW', self.tmp(i)); self.push_op(M_OBJ); self.mode = S_OKEY; return
            if isP(91): self.push_od(TMP, 0); self.push_op(M_ARR, 0); return      # an array literal: its slot, the elements, mkarrN
            if isP(40): self.push_op(M_PAREN); return
            if isP(33): self.push_op(NOT); return
            if isP(45): self.push_op(NEG); return
            if isP(126): self.push_op(BNOT); return
            if isP(7) or isP(8): self.pn = (v, 1); self.mode = S_PREINC; return
            if kind == 'ID': self.pn = v; self.mode = S_NAMEE; return
            if isP(41) and self.top_op()[0] == M_PAREN: self.osp -= 1; self.mode = S_AARROW0; return     # () =>
            if isP(41) and self.top_op()[0] == M_CALL:
                self.osp -= 1; self.call_end(self.opv[self.osp], 0); self.mode = S_OPER; return
            if isP(41) and self.top_op()[0] == M_CALLV:
                self.osp -= 1; return self.callv_end(self.opv[self.osp], 0)
            if isP(41) and self.top_op()[0] == M_INTR:
                self.osp -= 1; self.intr_end(self.opv[self.osp]); self.mode = S_OPER; return
            if isP(41) and self.top_op()[0] == M_METH:       # x.m() (or x.m(a, ) with a trailing comma)
                self.osp -= 1; self.mode = S_OPER; return self.meth_end(self.opv[self.osp], 0)
            if isP(93) and self.top_op()[0] == M_ARR:         # [] (or [a, ] with a trailing comma)
                self.osp -= 1; return self.arr_end(self.opv[self.osp], 0)
            if (isP(59) or isP(T_NL) or isP(125)) and self.top_cs()[0] == C_RETURN and self.osp == self.obase:
                self.push_od(K(0 if self.rom else UNDEF), 0)
                if isP(125): return self.asi_close(lambda: self.end_expr_stmt('P', T_NL))
                return self.end_expr_stmt(kind, v)
            if isP(T_NL): return
            if isP(59) and self.top_cs()[0] == C_FORCOND and self.osp == self.obase:
                self.push_od(K(1), 1); return self.end_expr_stmt(kind, v)
            return self.fail(3)
        if m == S_OPER:
            if self.pm == 3:
                self.pm = 0
                if isP(46) or isP(91): return self.fail(48)
            if self.pm >= 4:                                   # x.name for a method's name: a call (the receiver above its slot),
                if isP(40) and self.pm >= PMFN:                # f.call( / f.apply(: f is the callee (callv_end)
                    self.to_temp(self.nd - 1); self.snapshot(lambda q: q < 256)
                    self.push_op(M_CALLV, 2 + 2 * (self.pm - PMFN)); self.pm = 0; self.mode = S_OPND; return
                if isP(40):                                    # or else the property
                    i = self.nd - 1                            # (the receiver: an argument)
                    self.put(self.tmp(i + 1), i); self.set_od(i, TMP, 0); self.tb += 1
                    self.push_op(M_METH, self.pm - 4); self.pm = 0; self.mode = S_OPND; return
                self.pm = 1
            if self.pm in (1, 2):                              # after o.x ([o] on the operand stack, the key in pn) or x[k] ([x, k]): read
                dyn, key = self.pm == 2, self.pn[0]            # it unless it is assigned to
                asg = isP(61) or (kind == 'P' and v in COMPOUND) or isP(7) or isP(8)
                self.pm = 0
                if asg:
                    if not self.stmt_level(): return self.fail(70)
                    if not isP(61):                            # the old value, above [o] / [x, k]
                        if dyn: self.index_read(self.nd - 2, keep=True)
                        else: self.prop_read(self.nd - 1, key, keep=True)
                        if self.err: return
                    if isP(7) or isP(8):                       # o.x++ / x[k]--
                        i = self.nd - 1; self.step1(isP(7))(self.tmp(i), self.tmp(i))
                        if dyn: self.index_write(i - 2, self.tmp(i))
                        else: self.prop_write(i - 1, key, self.tmp(i))
                        self.pop_cs(); self.mode = S_INC; return
                    off = 0 if dyn else key - self.db
                    self.cs[self.csp - 1][:5] = [C_PSET, int(dyn), COMPOUND.get(v, 0) if kind == 'P' else 0, off // 64, off % 64]
                    self.mode = S_OPND; return
                if isP(40) and not self.rom: return self.meth_call(dyn, key)     # o.f(
                if dyn: self.index_read(self.nd - 2)
                else: self.prop_read(self.nd - 1, key)
            if cc and kind == 'P' and v in ACLOSE and not any(self.ops[k] >= 100 for k in range(self.obase, self.osp)):
                self.popops(1)                                 # an arrow's expression body ends: the function first, then the
                while not self.err and self.ca and self.osp == self.obase: self.arrow_close()     # token (x => y => x + y: both)
                if self.err: return
            if isP(40) and not self.rom:                      # e(...): a call of e's value (CALLV: in its slot)
                self.to_temp(self.nd - 1); self.snapshot(lambda q: q < 256); self.push_op(M_CALLV); self.tb += 1; self.mode = S_OPND; return
            if kind == 'P' and v in BIN:
                op = BIN[v] + 2 * (v in (1, 2) and self.tflag)            # (== / !=: LEQ / LNE)
                self.popops(prec(op))
                if self.err: return
                t, tv = self.top_op()
                if op == ADD and t == M_PRINT and (tv >= 4 or self.otype(self.nd - 1) == 2) and tv < 4 * (PIECES - 1):   # "..." + x in console.log: a piece
                    self.opv[self.osp - 1] = tv + 4; self.mode = S_OPND; return
                full = op == ADD and t == M_PRINT and tv >= 4 * (PIECES - 1)     # (no piece left: the pieces joined, then +)
                tail = full and self.otype(self.nd - 1) == 2   # (unless the last is a string: the rest of the chain joins it, one piece)
                if tail: full = False
                if op == ADD and not full: self.push_op(M_CADD if t == M_PRINT and not tail else ADD, self.otype(self.nd - 1)); self.mode = S_OPND; return
                if prec(op) <= prec(ADD): self.join_pieces()   # (* / % bind tighter: they end no piece)
                if op in (AND, OR):                           # a: tested in its temp; b joins it there (popops)
                    i = self.nd - 1; lt = self.otype(i); l = self.newlab(); self.to_temp(i); self.snapshot(lambda q: True, i)
                    self.emit('JZ' if op == AND else 'JNZ', b=self.tmp(i), label=l)
                    self.push_op(op, l + self.LM * lt); self.mode = S_OPND; return
                self.push_op(M_CADD if full else op, self.otype(self.nd - 1)); self.mode = S_OPND; return
            if isP(63):                                        # c ? a : b
                self.popops(2, 'br')
                if self.err: return
                self.join_pieces(); t, tv = self.top_op()
                self.snapshot(lambda q: True, self.nd - 1)
                l = self.newlab(); self.branch(l, False); self.push_op(M_TERN, l + self.LM * int(t == M_TELSE)); self.mode = S_OPND; return
            if isP(58):
                self.popops(1)
                if self.err: return
                t, tv = self.top_op()
                if t != M_TERN:
                    if self.osp == self.obase and self.top_cs()[0] == C_CASE: return self.case_end()
                    return self.fail(67)
                self.osp -= 1; i = self.nd - 1; lbt = self.otype(i); self.to_temp(i); self.nd -= 1
                if tv >= self.LM:
                    ev = self.opv[self.osp - 1]; self.emit('JMP', label=ev % self.LM)
                    self.opv[self.osp - 1] = ev % self.LM + self.LM * tmerge(ev // self.LM, lbt)
                else:
                    l2 = self.newlab(); self.emit('JMP', label=l2); self.push_op(M_TELSE, l2 + self.LM * lbt)
                self.deflab(tv % self.LM, self.here()); self.mode = S_OPND; return
            if isP(46): self.mode = S_DOT; return               # o.x
            if isP(91): self.push_op(M_INDEX); self.mode = S_OPND; return     # x[k]
            if isP(93):                                        # x[k]: the read is pending (pm 2); or an array literal's end
                self.popops(1)
                if self.err: return
                t, tv = self.top_op()
                if t == M_INDEX: self.osp -= 1; self.pm = 2; return
                if t == M_ARR: self.osp -= 1; return self.arr_end(tv, 1)
                return self.fail(45)
            if isP(125) and self.marker() == M_OKEY:           # '}' ending an object literal's value
                self.popops(1)
                if self.err: return
                return self.okey_end(self.top_op()[1], 1)
            if isP(41) or isP(44):
                self.popops(1, self.end_mode(v))
                if self.err: return
                t, tv = self.top_op()
                if isP(44):
                    if t == M_PRINT: self.print_call(32); self.opv[self.osp - 1] = 2; self.mode = S_CONFIRST; return
                    if t == M_OKEY: return self.okey_end(tv, 0)
                    if t == M_ARR: return self.arr_elem(tv)
                    if t == M_CALL: self.arg_end(); self.opv[self.osp - 1] += 4 * self.FM
                    if t in (M_METH, M_CALLV): self.arg_end(); self.opv[self.osp - 1] += 64    # count the arguments
                    if t in (M_CALL, M_METH, M_PUTC, M_INTR, M_CALLV): self.mode = S_OPND; return
                    if self.osp == self.obase and self.top_cs()[0] == C_ASSIGN and self.top_cs()[3]: return self.end_expr_stmt(kind, v)
                    return self.fail(44)
                if t == M_PAREN: self.osp -= 1; return
                if t == M_CALL: self.osp -= 1; return self.call_end(tv, 1)
                if t == M_CALLV: self.osp -= 1; return self.callv_end(tv, 1)
                if t == M_INTR: self.osp -= 1; return self.intr_end(tv)
                if t == M_METH: self.osp -= 1; return self.meth_end(tv, 1)
                if t == M_PUTC:
                    self.osp -= 1; self.emit('PUTC', b=self.src(self.nd - 1)); self.nd -= 1; self.push_od(K(0), 0); return
                if t == M_PRINT: self.print_call(10); self.osp -= 1; return self.print_end()
                if self.osp > self.obase: return self.fail(46)
                return self.end_expr_stmt(kind, v)
            asiok = (not any(self.ops[k] >= 100 for k in range(self.obase, self.osp)) and self.top_cs()[0] in (C_ASSIGN, C_EXPR, C_RETURN, C_PSET)
                     and not (self.csp >= 2 and self.cs[self.csp - 2][0] in (C_FORINIT, C_FORSTEP)))
            if isP(T_NL) and not asiok: return
            if isP(125) and asiok:
                return self.asi_close(lambda: (self.popops(1, self.dest_ctx()), self.err or self.end_expr_stmt('P', T_NL)))
            if isP(59) or isP(T_NL):
                self.popops(1, self.end_mode(59))
                if self.err: return
                if self.osp > self.obase: return self.fail(47)
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
        if k == C_FOROF and isP(41): return self.forof_end()
        if k == C_SWITCHC and isP(41):                         # the value into T(0), where the case tests read it. C_SWITCH: the
            self.pop_cs(); d0 = self.dbase; self.to_temp(d0); ty = self.otype(d0); self.nd = d0     # next test's label, the end, default's label,
            self.push_cs(C_SWITCH, self.newlab(), self.newlab(), 0, 4 * ty); self.mode = S_LBRACE; return    # 4 * type + seen + 2 default
        if k == C_WHILEC and isP(41):
            self.pop_cs(); le = self.newlab(); self.branch(le, False); self.push_cs(C_LOOPB, t[1], le); self.mode = S_LBRACE; return
        if k == C_FORCOND and isP(59):                         # t: l1 le lb l2. The test jumps into the body; else out
            self.pop_cs(); self.branch(t[3], True); self.emit('JMP', label=t[2]); self.deflab(t[4], self.here())
            self.push_cs(C_FORSTEP, t[1], t[2], t[3], t[4], e=t[5]); self.mode = S_STMT; return
        if k == C_ASSIGN:                                      # t: symbol, compound op, from a declaration
            self.pop_cs(); o = (self.var(t[1]), 0); i = self.nd - 1
            if self.captured(t[1]):                            # (its value in a temp, then through the env)
                if t[2]: self.settype(t[1], self.compound(t[2], i - 1, self.tmp(i - 1))); self.nd -= 1; i -= 1
                else: self.settype(t[1], self.otype(i))
                self.cwrite(t[1], self.src(i))
            elif t[2]:                                         # (a snapshot replaced x below e if e changed it)
                self.settype(t[1], self.compound(t[2], i - 1, o)); self.nd -= 1
            else: self.put(o, i); self.settype(t[1], self.otype(i))
            self.nd -= 1
            if self.err: return                                # (settype's 61: the statement goes no further, as in cc_dsl)
            if not t[3]: self.echo_val(o)                      # (x = e: its value; a declaration's is undefined)
            if isP(44) and t[3]: self.pn = (t[3] - 1, 0); self.mode = S_VAR; return     # var a = 1, b ...
            return self.end_simple_stmt(kind, v)
        if k == C_PSET:                                        # t: dynamic (x[k]), compound op, the key's offset (o.key: 64 * t[3] + t[4]).
            self.pop_cs(); i = self.nd - 1; dyn = t[1]         # [x, k, (old,) e] or [o, (old,) e] on the operand stack
            if t[2]: self.compound(t[2], i - 1, self.tmp(i - 1)); val = self.tmp(i - 1); i -= 1
            else: val = self.src(i)
            if dyn: self.index_write(i - 2, val)
            else: self.prop_write(i - 1, self.db + 64 * t[3] + t[4], val)
            self.echo_val(val)
            return self.end_simple_stmt(kind, v)
        if k == C_EXPR:
            self.pop_cs()
            if self.repl and not self.csp and not self.curf: self.put((ECELL, 0), self.nd - 1)     # (echo_val)
            self.nd -= 1; return self.end_simple_stmt(kind, v)
        if k == C_RETURN and (isP(59) or isP(T_NL)):
            self.pop_cs(); i = self.nd - 1
            if self.otype(i): self.fn[self.cfn][3] = self.otype(i)
            self.ret(self.src(i)); self.nd -= 1; return self.complete_stmt(0)
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
            elif k == C_LOOPB1: self.emit('JMP', label=t[1]); self.deflab(t[2], self.here()); self.tb -= t[4]     # (d: a for of's temps)
            elif nonelse or self.asic: self.deflab(t[1], self.here())
            else: self.pendLa = t[1]; self.mode = S_ELSE; return

    def close_block(self):
        if not self.csp: return self.fail(54)
        t = self.pop_cs(); k = t[0]; self.nlet = t[5]
        if k == C_BLOCK: return self.complete_stmt(0)
        if k == C_IFB: self.pendLa = t[1]; self.mode = S_ELSE; return
        if k == C_ELSEB: self.deflab(t[1], self.here()); return self.complete_stmt(0)
        if k == C_DOB: return self.do_cond(t)
        if k == C_LOOPB: self.emit('JMP', label=t[1]); self.deflab(t[2], self.here()); self.tb -= t[4]; return self.complete_stmt(0)
        if k == C_SWITCH:                                  # the last test failed: to default if there is one
            if t[4] & 2: self.emit('JMP', label=t[2])
            self.deflab(t[1], self.here())
            if t[4] & 2: self.emit('JMP', label=t[3])
            self.deflab(t[2], self.here()); return self.complete_stmt(0)
        if k in FUNCS:                                     # (still inside: the RET's frame label)
            self.ret((K(0 if self.rom else UNDEF), 0), 32 * (t[4] // 2 % 2))     # (A 32: it uses this; the library's mkfn)
            if k == C_FUNCB:                               # its calls' entry: the body, or (it uses this) this := the global object; JMP body
                body = self.cb // 2 + t[3] + 64 * (t[4] // 4); e = body
                if t[4] & 2:
                    e = self.here(); self.emit('NUMLIT', (GCELL, 0), w1=GLOBK); self.emit('MOV', (L(1), 0), (GCELL, 0)); self.emit('JMP', (body, 0))
                self.deflab(self.fn[self.cfn][2], e)
            return self.fn_close(t)
        return self.fail(55)

    def fn_close(self, t, frame=True):
        """a function's body ended (t: its entry, popped; its RET emitted): its value (frame: its frame label is defined here)"""
        k = t[0]
        if frame: self.deflab(t[2], self.nloc)
        self.deflab(t[1], self.here())
        fk = self.cfn; self.fn_exit()
        # its value: NUMLIT 16 + k (an inner function's: + 64 * (its index + 16 * the env's slot), + the frame's size: npar + the
        # frame label, which the linker adds: the library's mkclo makes the env cell). Word1 >= 16: a new value each time
        w1 = (self.npar + 1 + 64 * fk + 1024 * (self.npar + 2), 1) if self.curf == 1 else 16 + fk     # (+ 1: this)
        if k == C_FUNCN: self.emit('NUMLIT', (self.var(t[3]), 0), w1=w1)     # its local's value
        if k == C_FUNCE:                                   # its value
            self.osp -= 1; i = self.nd; self.push_od(TMP, 0); self.emit('NUMLIT', self.tmp(i), w1=w1); self.mode = S_OPER; return
        return self.mode_stmt()

    def arrow_start(self, h, argc=0):
        """an arrow function's head is known ('(a,' '(a) =>' 'a =>' '() =>'): as 'function (' (S_OPND, S_FNAME; C_FUNCE's d 1),
        h its first parameter (None: none). argc: its call count when the head is complete (end_params' f[4], set here as
        cc_dsl's fnnew does: before fn_enter, which can run out of labels)"""
        if self.curf >= 2: return self.fail(41)
        if h in RESERVED: return self.fail(36)            # ((break, x) =>: the first name came as a pending name)
        t, tv = self.top_op()
        if 0 < t < 100: return self.fail(48)              # (an operator's operand: 1 + x => x)
        nm = tv if t == M_OKEY else 0
        self.push_op(M_FN, nm); lo = self.newlab(); self.emit('JMP', label=lo); self.push_cs(C_FUNCE, lo, 0, 0, 1)
        self.emit('MOV', w1=self.db + nm - STRTAG if nm else 0); k = self.fnnew()
        if argc and not self.err: self.fn[k][4] = argc
        self.fn_enter(k)
        if h is not None and not self.err: self.declare(h, 2, PARAM0 + self.npar); self.npar += 1

    def arrow_body(self):
        """'=>' (its parameters ended): a block or an expression; as the expression's return until '{' says otherwise. An
        expression declares no locals: its frame label is 1 here (no label definition at its end: arrow_close)"""
        self.deflab(self.flab, 1); self.push_cs(C_RETURN); self.ca = 1; self.mode = S_ABODY

    def arrow_close(self):
        """an arrow's expression body is complete: its RET, then the function's end (fn_close)"""
        self.pop_cs(); i = self.nd - 1; self.ret(self.src(i)); self.nd -= 1
        t = self.pop_cs(); self.nlet = t[5]; self.fn_close(t, False)

    def do_cond(self, t):
        """a do body (just popped) ended: the continue label; the entry stays for while (cond)"""
        self.deflab(t[1], self.here()); self.csp += 1; self.mode = S_DOWHILE

    def end_params(self):
        f = self.fn[self.cfn]                                # the calls so far must pass npar arguments (call_end)
        if f[4] and f[4] != self.npar + 1: return self.fail(76)
        f[4] = self.npar + 1; t = self.top_cs(); self.mode = S_AARROW if t[0] == C_FUNCE and t[4] else S_LBRACE
        if not self.rom:                                     # (its value's: FTAB, + 16 parameters: a closure, its env in local 1)
            self.nloc = 1; self.datum(FTAB + self.cfn, self.here() + 8192 * (self.npar + 16 * (self.curf == 2)))

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
        if 2 * self.cp > self.CODESZ: self.fail(62)           # (the page checks this in .fin)
        words = {}
        fnl = {self.fn[k][2] for k in range(self.nfn)} | self.optlab
        for a, (w, lab, m) in self.words_ir().items():
            if lab is not None:
                if lab >= self.NL or (self.lab[lab] < 0 and (self.rom or lab not in fnl)): self.fail(60)
                else: w += m * max(0, self.lab[lab])      # (a function never declared: 0, the library's refstub)
            words[a] = w
        return words, dict(self.data)

# ---------------- simulator
def run(rom, mem_init, sp0, out_base=None, cols=None, rows=None, max_steps=10 ** 6, strict=False, trace=None, ent=None, net=None, marks=None):
    """the register machine from code_base (fp = sp0) on a RAM image; returns (steps, output). ent: the runtime library's entries
    (the traps' routines). strict: fp is back at sp0 at HALT. net: the NET instruction's gateway (default: net/device.py's,
    which serves tests/net/). marks: a list that gets the REPL's marks at HALT"""
    if net is None: net = Device()
    if out_base is None: out_base = LAYOUT['out_base']
    cols, rows = cols or LAYOUT['cols'], rows or LAYOUT['rows']
    mem = [0] * (AMASK + 1)
    romw = [w or 0 for w in rom]       # instructions only: a data read below RAM gives 0 (the page has no ROM leaves)
    for a, v in mem_init.items(): mem[a] = v
    db, ROMN = LAYOUT['data_base'], LAYOUT['rom_size']
    pc, fp, optr, steps, out, pst = LAYOUT['code_base'], sp0, 0, 0, [], 0
    def addr(o): return (db + o if o < 256 else fp + o - 256) & AMASK
    def rd(a): a &= AMASK; return mem[a] if a >= ROMN else 0
    def val(o): return kval(o) if o >= 768 else rd(addr(o))
    def wr(a, v):
        a &= AMASK
        if a >= ROMN: mem[a] = s20(v)
    CB = LAYOUT['code_base']
    def fopnd(o):
        """an FPU operand's double: a scratch line, or the number val(o)"""
        f = fscr(o)
        return fdec([rd(f + j) for j in range(4)]) if f else fval(val(o), rd)
    def trap(name, base, args, ret):
        """a call into the runtime library: the frame at fp + base (the arguments above its return word)"""
        nonlocal fp, pc
        for i, x in enumerate(args): wr(fp + base + 1 + i, x)
        wr(fp + base, base * 8192 + ret // 2); fp += base; pc = ent[name]
    def chars(v):
        """a string, number or special operand of +: its characters (a special's name: catv)"""
        v = catv(v)
        if isstr(v): p = (v + STRTAG) & AMASK; return [rd(p + i) for i in range(rd(p - 1))]
        return [ord(ch) for ch in str(v)]
    def cat(a, x, y):
        """the + of a string with a string, number or special into A, as the ROM's cat lays it out (newstr: [hdr][len][bytes][0]
        from HP); False if the heap is full (the ROM's cat collects)"""
        t = chars(x) + chars(y); n = len(t); nw = (n + 10) // 8 * 8; hp = rd(HP)
        if hp + nw - 8 >= rd(GCLIM) + LAYOUT['heap_size'] - 7: return False
        base = HEAP0 + hp; wr(HP, hp + nw)
        for i, w in enumerate([-2 - nw, n] + t + [0]): wr(base + i, w)
        mark(base); wr(addr(a), base + 2 - STRTAG); return True
    def mark(b):
        """the block at b in the collector's map"""
        w, k = mapbit(b); wr(w, rd(w) | 1 << k)
    def probe(o, key, own=False):
        """GETP / SETP: the address of key's word in object o's chunks (own: not its prototypes'), or of the word that ends them"""
        cur = (o + OBJTAG) & AMASK
        while True:
            k = rd(cur)
            if k == key or k == 0 or (own and isplink(k)): return cur
            cur = (k + OBJTAG) & AMASK if k < 0 else cur + 2
    def setp(o, key, v, full=None):
        """SETP / SETX of an object: the key's pair, else a free pair in place, else the library (a full chunk: setp, or for
        SETX setx with its own operands, as the CSS CPU hands it back)"""
        q = probe(o, key, True); e = rd(q)
        if e == key: wr(q + 1, v)
        elif (q - HEAP0) % 8 < 6: wr(q, key); wr(q + 1, v); wr(q + 2, e)     # (the end carried on: 0 or the prototype's link)
        else: name, args = full or ('setp', [o, key, v]); trap(name, TRAPOFF, args, pc)
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
        user = pc - 2 >= CB
        if op in ALU: wr(addr(a), ALU[op](val(b), val(c)))
        elif op == 'MOV': wr(addr(a), val(b))
        elif op == 'NEG': wr(addr(a), -val(b))
        elif op == 'NOT': f = not truthy(mem, val(b), user); wr(addr(a), jsb(f) if user else int(f))
        elif op == 'LOADK': wr(addr(a), w1)
        elif op == 'GETFP': wr(addr(a), fp)
        elif op == 'LDI': wr(addr(a), rd(val(b) + val(c)))
        elif op == 'STI': wr(val(a) + val(b), val(c))
        elif op == 'JMP': pc = 2 * a
        elif op == 'JZ': pc = 2 * a if not truthy(mem, val(b), user) else pc
        elif op == 'JNZ': pc = 2 * a if truthy(mem, val(b), user) else pc
        elif op == 'HALT':                              # (the ROM's halt is out of memory's, inside its routines' frames)
            if strict and fp != sp0 and pc - 2 >= ROMN: raise RuntimeError(f'frame unbalanced at HALT: fp - sp0 = {fp - sp0}')
            if marks is not None: marks[:] = mem[out_base + OUTMAX:out_base + OUTMAX + NMARK]
            return steps, ''.join(chr(ch % 0x10000) for ch in out)     # (putc's code mod 2^16, as String.fromCharCode)
        elif op[0] == 'J':
            x, y = val(b), val(c); ng = op[1] == 'N' and op != 'JNE'
            if not user: pc = 2 * a if ALU[op[1:]](x, y) else pc
            else:                                       # (anything but integers: the library's jcmp decides, see TRAPS)
                r = dyn_fast('D' + op[1 + ng:], x, y)
                if r is None: trap('jcmp', TRAPOFF, [x, y], pc)
                elif (r == TRUE) != ng: pc = 2 * a
        elif op == 'CALL': wr(fp + w1, w1 * 8192 + pc // 2); fp += w1; pc = 2 * a
        elif op == 'CALLV':                             # the callee in the frame's slot fp + off: a function with A parameters (as many
            f = rd(fp + w1); q = (f + FUNTAG) & AMASK   # as the arguments) is called; anything else goes to the library's callv
            m = rd(q + 1) if isfun(f) else -1; inr = 16 * (0 <= m < 64 and m % 32 >= 16)     # (an inner function: its env into its local 1)
            if isfun(f) and a in (m - inr, m - inr + 32):
                if inr: wr(fp + w1 + 2 + a % 32, rd(q + 2))
                wr(fp + w1, w1 * 8192 + pc // 2); fp += w1; pc = 2 * rd(q)
            else: trap('callv', TRAPOFF, [f], pc)
        elif op == 'RET': r = mem[fp]; wr(fp, val(b)); fp -= r // 8192; pc = 2 * (r % 8192); pst = WBACK * int(r // 8192 == TRAPDEF)
        elif op == 'PRINT' and (isarr(val(b)) or isobj(val(b)) or isdbl(val(b)) or isfun(val(b))): pst = pc - 2; pc = ent['pstub']      # (Node's form)
        elif op == 'TENTER': wr(fp + TRAPOFF, TRAPOFF * 8192 + (pst + 2) // 2); fp += TRAPOFF; pc = 2 * a; pst = 0
        elif op in ('PRINT', 'PRINTK'):
            v = val(b) if op == 'PRINT' else w1; sep = (0, 32, 10)[a // 2 % 4]
            if isspecial(v): v = catv(v) if a & 8 else BSTRV(v - SPV0)     # (its name; a + chain's piece as a string: -0 is 0)
            if isstr(v):                                   # a literal or a heap string (data_base + SDATA: the lib's DONE marker, empty)
                p = v + STRTAG; text = []
                while p != db + SDATA and mem[p] != 0: text.append(mem[p]); p += 1
            else: text = [ord(ch) for ch in str(v)]
            for ch in text + ([sep] if sep else []): emit(ch)
        elif op == 'PUTC' and a: mem[out_base + OUTMAX + a - 1] = optr + 1     # a REPL mark (NMARK): where the output stands
        elif op == 'PUTC': emit(val(b))
        elif op == 'NUMLIT':                            # a number literal: its cache, or the library parses it (once)
            if pst == WBACK: wr(addr(a), rd(fp + TRAPDEF)); pst = 0
            elif rd(addr(a)) == UNDEF or w1 >= 16: trap('numlit', TRAPDEF, [w1, 0], pc - 2)     # (word1 >= 16: a function's value, made each time)
        elif op in FLOPS or op in FBOPS:                # the line at A's value (or scratch line A) := op of B and C
            x, y = fopnd(b), fopnd(c); d = fscr(a) or val(a)
            for j, w in enumerate(fenc(fline_op(op, x, y))): wr(d + j, w)
        elif op in FVOPS: wr(addr(a), fval_op(op, fopnd(b), fopnd(c), val(b)))
        elif op == 'FCOK': wr(addr(a), fcand(fopnd(b), val(c))[1])
        elif op == 'FCDIG':
            cv = fcand(fopnd(b), val(c))[0]; d = fscr(a) or val(a)
            for j in range(4): wr(d + j, cv // 10 ** (5 * j) % 100000 if j < 3 else cv // 10 ** 15)
        elif op in DYNOPS:                              # (pst WBACK: the library's value, after its trap)
            k = a // 1024; a %= 1024                    # (DBIT's operator)
            x, y = val(b), val(c); r = dyn_fast(op, x, y, k) if not pst else None
            if pst == WBACK: wr(addr(a), rd(fp + TRAPDEF)); pst = 0
            elif r is not None: wr(addr(a), r)
            elif op == 'DADD' and catok(x, y):
                if not cat(a, x, y): trap(CATTRAPS[op], TRAPDEF, [x, y], pc - 2)
            else: trap(TRAPS[op], TRAPDEF, [x, y], pc - 2)
        elif op == 'GETX':                              # an array and an integer: its element (undefined past its length); an object and
            x, k = val(b), val(c)                       # an integer or the program's string: probed; anything else: the library
            if isarr(x) and issmi(k):
                q = (x - ARRTAG) & AMASK; wr(addr(a), rd(rd(q) + k) if 0 <= k < rd(q - 1) else UNDEF)
            elif isobj(x) and ownkey(k): q = probe(x, s20(k + STRTAG)); wr(addr(a), rd(q + 1) if rd(q) else UNDEF)
            else: trap('getx', a - 256, [x, k], pc)
        elif op == 'SETX':                              # an array, k inside its length: the store; anything else: the library
            x, k, v = val(a), val(b), val(c); q = (x - ARRTAG) & AMASK
            if isarr(x) and 0 <= k < rd(q - 1): wr(rd(q) + k, v)
            elif isobj(x) and ownkey(k): setp(x, s20(k + STRTAG), v, ('setx', [x, k, v]))
            else: trap('setx', TRAPOFF, [x, k, v], pc)
        elif op == 'NEW':                               # a chunk with no keys (the heap full: the collector, then NEW again)
            hp = rd(HP)
            if s20(hp - (rd(GCLIM) + LAYOUT['heap_size'] - 7)) < 0: wr(HEAP0 + hp, 0); mark(HEAP0 + hp); wr(HP, hp + 8); wr(addr(a), hp + HEAP0 - OBJTAG)
            else: trap('gcnew', a - 256, [], pc - 2)
        elif op == 'GETP':                              # o.key (C: the key's offset from data_base): undefined if missing or not an object
            o = val(b)                                  # (a string: the library's getps, String.prototype's)
            if isstr(o): trap('getps', a - 256, [], pc)     # (no arguments: its frame is at A, below a method's this)
            else: wr(addr(a), rd(probe(o, db + c) + 1) if isobj(o) and rd(probe(o, db + c)) else UNDEF)
        elif op == 'SETP':                              # o.key = v: the key's pair, else a free pair in place, else the library
            o, v = val(a), val(b)
            if isobj(o): setp(o, db + c, v)
        elif op == 'KIND': wr(addr(a), kind(c - 896, val(b)))
        elif op == 'ALLOC':                             # a block at HP (the heap full: the collector, then ALLOC again)
            n, k = val(b), c - 896; nw = allocw(k, n); hp = rd(HP); base = HEAP0 + hp
            if hp + nw > rd(GCLIM) + LAYOUT['heap_size']: trap('galloc', a - 256, [nw], pc - 2)
            else:
                if k in (0, 1, 4):
                    for j, w in enumerate(allochdr(k, n, nw, base)): wr(base + j, w)
                if k == 0: wr(base + 2 + n, 0)
                if k != 2: mark(base)
                wr(HP, hp + nw); wr(addr(a), allocres(k, base))
        elif op in ('MCPY', 'MUPPER', 'MLOWER'):
            d, s_, n = val(a), val(b), val(c)
            for i in range(n): wr(d + i, mcase(op, rd(s_ + i)))
        elif op == 'MFILL':
            d, v, n = val(a), val(b), val(c)
            for i in range(n): wr(d + i, v)
        elif op == 'NPUT':
            p, v = val(a), val(b)
            for i, ch in enumerate(str(v)): wr(p + i, ord(ch))
        elif op in ('MCMP', 'MFEQ', 'MFREF'):
            n, p, q = val(a), val(b), val(c); i = 0
            while i < n and not (rd(p + i) != rd(q + i) if op == 'MCMP' else rd(p + i) == q if op == 'MFEQ' else isfref(rd(p + i), q)): i += 1
            wr(addr(a), i)
        elif op == 'MWALK':
            n, p, e = val(a), val(b), val(c); o = 0
            while p + o < e and rd(p + o) != n: o += rd(p + o) + 2
            wr(addr(a), o)
        elif op == 'APUSH':                             # (no array, or a full one: on to the ROM's push)
            x, v = val(b), val(c); q = (x - ARRTAG) & AMASK
            if isarr(x) and rd(q - 1) < rd(q - 2):
                n = rd(q - 1); wr(rd(q) + n, v); wr(q - 1, n + 1); r = mem[fp]; wr(fp, n + 1); fp -= r // 8192; pc = 2 * (r % 8192)
        elif op == 'NET':                               # the answers' bytes into RBUF0 …, part 0's answer into A
            for ad, v in netw(net(val(b))): wr(addr(a) if ad is None else ad, v)
        else: raise RuntimeError(f'bad op {op} at {pc - 2}')

def image_mem(c, words, data, init=None):
    """RAM as the CSS compiler leaves it: code words; strings in place; the globals' count at init - 1"""
    if init is None: init = LAYOUT['init']
    mem = dict(words)
    sbase = c.db + SDATA
    for a, v in data.items(): mem[a] = v
    mem[init - 1] = c.dp
    assert all(a >= sbase for a in data), 'nothing is staged: globals start at 0'
    mem[c.db] = STRTAG                  # the untag constant at data_base (read only: an overlay on the page)
    mem.update(GINIT)                   # the globals: undefined (in the page's image)
    mem.update(BSTRW)                   # the built-in strings (the page: .fin's overlays)
    mem[LAYOUT['strend']] = c.sdp       # the string area's end (the runtime looks string keys up in it)
    return mem

def compile_and_run(src, lib, max_steps=10 ** 6, strict=False, trace=None, repl=False):
    """repl: as the page's REPL compiles and runs it (its console's grid)"""
    c = Compiler(LAYOUT['data_base'], LAYOUT['code_base'], lib, repl=repl)
    words, data = c.compile(src)
    if c.err: return c, None
    mem = image_mem(c, words, data, lib.get('init', LAYOUT['init']))
    geo = dict(cols=LAYOUT['repl_cols'], rows=LAYOUT['repl_rows']) if repl else {}
    return c, run(lib['rom'], mem, LAYOUT['sp0'], max_steps=max_steps, strict=strict, ent=lib.get('entries'), trace=trace, **geo)

def image(src, lib, ram=False, repl=False):
    """The machine image every harness takes (gen_css.py, csssim.py, the C2 pages): ROM = the lib; RAM all zero but the globals
    (undefined: GINIT; the page's compile chain supplies code and data), or with ram=True the program as the CSS compiler leaves it (CPU-only pages,
    the CSS CPU's model). steps/expected come from cc_ref's simulation. repl: compiled and run as the page's REPL (its console's grid)"""
    La = LAYOUT
    c = Compiler(La['data_base'], La['code_base'], lib, repl=repl)
    words, data = c.compile(src)
    if c.err: raise ValueError(f'compile error {c.err}')
    mem = image_mem(c, words, data, lib.get('init', La['init']))
    cols, rows = (La['repl_cols'], La['repl_rows']) if repl else (La['cols'], La['rows'])
    mk = []; r = run(lib['rom'], dict(mem), La['sp0'], ent=lib.get('entries'), cols=cols, rows=rows, marks=mk)
    if not ram: mem = dict(GINIT)
    return dict(rom=lib['rom'], romSize=La['rom_size'], ram=[mem.get(La['rom_size'] + i, 0) for i in range(La['ram_size'])],
                ramSize=La['ram_size'], sp0=La['sp0'], outBase=La['out_base'], rows=rows, cols=cols, repl=int(repl), source=src,
                codeBase=La['code_base'], init=La.get('init'), steps=r[0], expected=r[1], marks=mk, entries=lib.get('entries', {}))

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
    print('err', c.err, 'instructions', c.cp, 'data words', c.dp, 'labels', c.nlab)
    if '-d' in sys.argv: print('\n'.join(disasm(c.link()[0])))
    if r: print('steps', r[0], 'output:'); print(r[1])
