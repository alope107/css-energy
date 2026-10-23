"""csssim.py — the CSS CPU's design, pass by pass (the oracle for gen_css.py; python3 machine/csssim.py prog.js [K]).

Memory: ROM + RAM words (cssref's state). Cache: 16 sets x 2 ways x 4 words, set = (b + b // 16 + b // 256) mod 16
for block b, FIFO replacement (a per-set bit naming the next victim, flipped on each fill), a dirty bit per line,
write-allocate by filling first. A pass: if a miss is pending, fill its block into the set's victim way (a dirty victim
is written back: the pass's one RAM write set), and prefetch the next block into its own set's victim way if that block is
absent and the victim is clean (PREF); then up to K instructions, each executed only if every word it reads
or writes hits and, for an output instruction, the pass's write set is free. The first instruction that can't run ends the
pass (its miss, if any, is pending). Output has its own write set (the console's own cells and channels, so a write-back
doesn't hold it up). PRINT is chunked: up to 4 console cells per instruction execution, a string chunk ends at its block;
the instruction repeats (pst carries the position) until done. The console is RAM written through the output write set,
never cached. The read ports read a miss's block (and the next) in the pass that misses, so a miss on the block that pass
writes back would read it stale: then the fill waits a pass (the chain re-misses and the ports read it again); a prefetch of
that block is skipped. A stalled instruction keeps the words it did read (latches) for its re-execution at the start of the
next pass, so it needs only its written line resident at the end: without them three blocks in one set (code, an operand
and a string) evicted each other forever. Instructions in ROM are fetched from a static table, not through the cache (ROMF);
user code through a code cache of its own (ISET direct-mapped lines), which only fetches fill, prefetching the next line.

An instruction (compiler/cc_ref.py) is two words at an even address, both in one block, so one fetch. Its accesses: its
source operands B and C when they are cells, its destination A; RET reads the return word at fp and writes the value there;
CALL writes the return word at fp + off; JZ / JNZ / NOT read a string's length word.

An instruction writes at most one word per execution (two in one block for SETP's new pair), so the multi-word ones repeat
(pc stays, pst counts or carries a position; only the last execution is a step): a trap writes its frame's arguments, last
first (a destination trap's C may be the cell after its frame's), then the return word, and once started (pst > 0) it finishes
whatever its operands then hold; GETP / SETP probe one pair per execution (pst: the pair's address); SETP's new pair writes the
terminator after it (pst: the pair's address + 1), then the pair; NEW writes the chunk's first key, the value, then HP. PRINT of
an array or an object jumps to pstub with its own address in pst (the out class writes no memory); TENTER writes the return
word from pst. The reads, in order (a miss stops at the first): x, y, z (and its pair word), e, then the written word."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cssref as ref
from cssref import AMASK, LA, STRTAG, SDATA, COLS, ROWS, OUT_BASE
import cc_ref as R
from cc_ref import OPN, s20
from uarch import STRP_HI, HEAP0, HP, GCLIM, OBJTAG, ARRTAG
TRAPOFF, HS = R.TRAPOFF, LA['heap_size']
TRAPDEF, WBACK = R.TRAPDEF, R.WBACK      # a dynamic operator's trap: its frame, and the pst RET leaves for the move into A
CATT, CAT0 = 1024, 2048        # a DADD's pst: the cat class's trap (+ its step) and its executions (+ k); ALLOC's trap
XBACK = 512                    # a SETX's pst: its probe found the chunk full, the arr class's trap from its first step

NSET, NWAY = 16, 2
ROMF = PREF = True
BLKS = (ref.ROMN + ref.LA['ram_size']) // 4; RB0 = ref.ROMN // 4
DB = LA['data_base']
def setof(b): return (b + b // 16 + b // 256) % NSET
STR_LO, STR_HI = LA['data_base'] + SDATA, STRP_HI     # literals and heap strings
ALU = {'ADD': lambda a, b: s20(a + b), 'SUB': lambda a, b: s20(a - b), 'MUL': lambda a, b: s20(a * b),
       'DIV': lambda a, b: 0 if b == 0 else int(a / b), 'MOD': lambda a, b: 0 if b == 0 else a - b * int(a / b),
       'LT': lambda a, b: int(a < b), 'GT': lambda a, b: int(a > b), 'LE': lambda a, b: int(a <= b), 'GE': lambda a, b: int(a >= b),
       'EQ': lambda a, b: int(a == b), 'NE': lambda a, b: int(a != b)}

class Stall(Exception):
    def __init__(self, miss=None, ic=False): self.miss = miss; self.ic = ic
# user code (code_base .. init) is fetched through a cache of its own, direct-mapped (ISET lines, line b at b mod ISET), which
# only fetches fill, prefetching the next line: data no longer evicts the program's loops (ICACHE=sets,ways to try others)
_IC = os.environ.get('ICACHE', '16,1'); ISET, IWAY = (int(x) for x in _IC.split(','))
CODE0, CODE1 = ref.LA['code_base'] // 4, ref.LA['init'] // 4


class Sim:
    def __init__(self, st):
        self.st = st                              # pc fp optr pst mem out halt steps (cssref)
        self.st.setdefault('pst', 0)
        self.tag = [[None] * NWAY for _ in range(NSET)]; self.dirty = [[0] * NWAY for _ in range(NSET)]
        self.words = [[[0] * 4 for _ in range(NWAY)] for _ in range(NSET)]; self.fifo = [0] * NSET
        self.pending = None; self.passes = 0; self.wbacks = 0; self.stale = self.pstale = False; self.wb = None
        self.latch = {}; self.reads = {}; self.first = False
        self.itag = [[None] * IWAY for _ in range(ISET)]; self.iwords = [[[0] * 4 for _ in range(IWAY)] for _ in range(ISET)]
        self.ififo = [0] * ISET; self.pic = False
    def way(self, b):
        s = setof(b)
        for w in range(NWAY):
            if self.tag[s][w] == b: return s, w
        raise Stall(b)
    def rd(self, a):
        a &= AMASK
        if self.first and a in self.latch: v = self.latch[a]
        else: s, w = self.way(a // 4); v = self.words[s][w][a % 4]
        self.reads[a] = v; return v
    def rdu(self, a):
        """a read that isn't latched (the map's word, MCMP's second line): it must hit"""
        a &= AMASK; s, w = self.way(a // 4); return self.words[s][w][a % 4]
    def ifetch(self, pc):
        """the instruction's two words through the code cache"""
        b = pc // 4; s = b % ISET
        for w in range(IWAY):
            if self.itag[s][w] == b: v = self.iwords[s][w]; return v[pc % 4], v[pc % 4 + 1]
        raise Stall(b, True)
    def ifill(self, b):
        for nb in (b, b + 1):
            s = nb % ISET
            if nb >= CODE1 or nb in self.itag[s]: continue
            w = self.ififo[s]; self.itag[s][w] = nb; self.ififo[s] = (w + 1) % IWAY
            self.iwords[s][w] = [self.st['mem'].get(4 * nb + j, 0) for j in range(4)]
    def fill(self, b, cw):
        if self.pic: self.ifill(b); return cw
        s = setof(b); w = self.fifo[s]
        if self.dirty[s][w]:
            vt = self.tag[s][w]
            if vt >= RB0:
                for j in range(4): self.st['mem'][4 * vt + j] = self.words[s][w][j]
            self.wbacks += 1; self.wb = vt
        self.tag[s][w] = b; self.dirty[s][w] = 0; self.fifo[s] ^= 1
        self.words[s][w] = [self.st['mem'].get(4 * b + j, 0) if b >= RB0 else 0 for j in range(4)]     # (ROM as data: 0)
        nb = b + 1; s = setof(nb); w = self.fifo[s]
        if PREF and nb < BLKS and nb not in self.tag[s] and not self.dirty[s][w] and not self.pstale:
            self.tag[s][w] = nb; self.fifo[s] ^= 1
            self.words[s][w] = [self.st['mem'].get(4 * nb + j, 0) if nb >= RB0 else 0 for j in range(4)]
        return cw
    def cat(self, op, a, x, y, ps, pc, trap, wr, addr):
        """one execution of a string's + (cc_ref.run's cat), pst CAT0 + k: k 0 HP += the block's words (or, the heap full, the ROM's
        gccat through a trap, pst CATT + its step, its frame at TRAPDEF), 1 the header and length, 2 + i the characters from i (a
        line of them: from X or Y, to the end of their line; a string's from its line; the NUL with the last if it fits), n + 2
        the NUL, n + 3 the map's bit, then A. The reads: X's and Y's lengths (a string's length word), HP and GCLIM, a string's
        line. A special joins as its name (a built-in string: R.catv)"""
        rd = self.rd; st = self.st
        x0, y0 = x, y; x, y = R.catv(x), R.catv(y)
        def ln(v):
            if R.isstr(v): return rd((v + STRTAG - 1) & AMASK)
            return len(str(v))
        def text(v): return [ord(ch) for ch in str(v)]
        la, lb = ln(x), ln(y); n = la + lb; nw = (n + 10) // 8 * 8
        hp, gl = rd(HP), rd(GCLIM)
        self.npst, self.cdone = 0, True
        if ps < CAT0 or (ps == CAT0 and hp + nw - 8 >= gl + HS - 7):
            r = trap((self.st['fp'] + TRAPDEF) & AMASK, [x0, y0], TRAPDEF * 8192 + (pc - 2) // 2, R.CATTRAPS[op], 0 if ps == CAT0 else ps - CATT)
            self.npst = self.npst_t + CATT if self.npst_t else 0; self.cdone = self.done_t; return r
        k = ps - CAT0; base = HEAP0 + hp - nw; i = k - 2; nk = k + 1
        if k == 0: wr(HP, hp + nw)
        elif k == 1: wr(base, -2 - nw); wr(base + 1, n)
        elif i < n:
            v, j, lv = (x, i, la) if i < la else (y, i - la, lb); d_ = base + 2 + i
            if R.isstr(v): sa = (v + STRTAG + j) & AMASK; c_ = min(lv - j, 4 - d_ % 4, 4 - sa % 4); t = [rd(sa + q) for q in range(c_)]
            else: c_ = min(lv - j, 4 - d_ % 4); t = text(v)[j:j + c_]
            if i + c_ == n and (d_ + c_) % 4: t.append(0)                 # the NUL, in the same line
            for q, w in enumerate(t): wr(d_ + q, w)
            nk = k + len(t)
        elif i == n: wr(base + 2 + n, 0)
        elif i == n + 1: mw, bit = R.mapbit(base); wr(mw, self.rdu(mw) | 1 << bit)
        else: wr(addr(a), base + 2 - STRTAG); return pc
        self.npst, self.cdone = CAT0 + nk, False; return pc - 2
    def chunk(self, flags, v, f):
        """one PRINT execution (flags: separator * 2): (cells written, newline after, done, next pst); reads may stall.
        f: the cells this pass can still take (the free run of console banks from optr's): a longer chunk is cut there and
        goes on next execution (a string's pst: the next byte's address; a number's: its characters out so far). A special
        prints its name (a built-in string)"""
        st = self.st; sep = (0, 32, 10)[flags // 2 % 4]
        if R.isspecial(v): v = R.catv(v) if flags & 8 else R.BSTRV(v - R.SPV0)     # (a + chain's piece: as a string, -0 is 0)
        p = v + STRTAG
        if STR_LO <= p < STR_HI:
            q = st['pst'] or p
            if q == STR_LO: return ([32] if sep == 32 else []), sep == 10, True, 0
            e = 0; term = None
            while True:
                byte = self.rd(q + e)
                if byte == 0 or byte == 10: term = byte; break
                e += 1
                if (q + e) % 4 == 0: break
            text = [self.rd(q + i) for i in range(e)]
            if e > f: return text[:f], False, False, q + f
            if term == 10: return text, True, False, q + e + 1
            if term is None: return text, False, False, q + e
            if sep == 32 and e == f: return text, False, False, q + e      # (the separator next time)
            return text + ([32] if sep == 32 else []), sep == 10, True, 0
        text = [ord(ch) for ch in str(v)] + ([32] if sep == 32 else [])
        k = st['pst']; n = min(len(text) - k, 4, f)
        if k + n < len(text): return text[k:k + n], False, False, k + n
        return text[k:], sep == 10, True, 0
    def free(self, cw):
        """the console cells this pass can still write from optr on: the run of banks (optr + j) mod 4 not in cw"""
        f = 0
        while f < 4 and not (cw >> ((self.st['optr'] + f) % 4)) & 1: f += 1
        return f
    def execute(self, cw):
        """one instruction, or Stall; returns cw (the console banks this pass has written, a mask)"""
        st = self.st; mem_w = {}; rd = self.rd
        def wr(a, v):
            a &= AMASK
            if a < ref.ROMN: return
            s, w = self.way(a // 4); mem_w[(s, w, a % 4)] = s20(v)
        pc, fp = st['pc'], st['fp']
        self.reads = {}
        if ROMF and pc < ref.ROMN: w0, w1 = st['mem'].get(pc, 0), st['mem'].get(pc + 1, 0)
        elif ISET and CODE0 <= pc // 4 < CODE1:
            if self.first and pc in self.latch: w0, w1 = self.latch[pc], self.latch[pc + 1]
            else: w0, w1 = self.ifetch(pc)
            self.reads[pc], self.reads[pc + 1] = w0, w1
        else: w0 = rd(pc); w1 = rd(pc + 1)
        op = OPN[w0 // 8192]; a = w0 % 8192; b = w1 // 1024 + 512; c = w1 % 1024
        def addr(o): return (DB + o if o < 256 else fp + o - 256) & AMASK
        def val(o): return R.kval(o) if o >= 768 else rd(addr(o))
        user = pc >= ref.LA['code_base']
        def truthy(v): return v != 0 and not (user and v >= R.FALSE) and not (R.isstr(v) and rd((v - 1) & AMASK) == 0)
        ps = st['pst']; npst = 0
        def trap(F, args, retw, name, s):
            """one execution of a trap: argument s from the last, or (s = len(args)) the return word, fp = F, pc = the routine"""
            nonlocal fp, npst, done
            n = len(args); self.npst_t, self.done_t = 0, True
            if s < n: wr(F + n - s, args[n - 1 - s]); npst = self.npst_t = s + 1; done = self.done_t = False; return pc - 2
            wr(F, retw); fp = F; return st['ent'][name]
        pc += 2; out = None; done = True
        if op in ALU: x, y = val(b), val(c); wr(addr(a), ALU[op](x, y))
        elif op == 'MOV': wr(addr(a), val(b))
        elif op == 'NEG': wr(addr(a), -val(b))
        elif op == 'NOT': f = not truthy(val(b)); wr(addr(a), R.jsb(f) if user else int(f))
        elif op == 'LOADK': wr(addr(a), w1)
        elif op == 'GETFP': wr(addr(a), fp)
        elif op == 'LDI': x, y = val(b), val(c); wr(addr(a), rd(x + y))
        elif op == 'STI': x, y = val(b), val(c); z = val(a); wr(z + x, y)
        elif op == 'TENTER': wr(fp + TRAPOFF, TRAPOFF * 8192 + (ps + 2) // 2); fp += TRAPOFF; pc = 2 * a
        elif op == 'DADD' and ps >= CATT:               # the cat class (a string's +, below)
            x, y = val(b), val(c); pc = self.cat(op, a, x, y, ps, pc, trap, wr, addr); npst, done = self.npst, self.cdone
        elif op in R.DYNOPS and ps == WBACK:            # after the library's trap: its value (the frame's first word) into A
            wr(addr(a), rd(fp + TRAPDEF))
        elif op in R.DYNOPS:                            # two integers (cc_ref.dyn_fast) here; a string's + to the cat class; else
            x, y = val(b), val(c); r = None if ps else R.dyn_fast(op, x, y)     # the library, the frame at TRAPDEF, back here
            if r is not None: wr(addr(a), r)
            elif op == 'DADD' and not ps and R.catok(x, y): npst = CAT0; done = False; pc -= 2
            else: pc = trap((fp + TRAPDEF) & AMASK, [x, y], TRAPDEF * 8192 + (pc - 2) // 2, R.TRAPS[op], ps)
        elif op == 'GETX' and ps >= CATT:                # an object's probe, as GETP's, the key from C (+ KBIAS)
            o = val(b); key = s20(val(c) + STRTAG); q = ps; k, v = rd(q), rd(q + 1)
            if k == key or k == 0: wr(addr(a), v if k else R.UNDEF)
            else: npst = (k + OBJTAG) & AMASK if k < 0 else q + 2; done = False; pc -= 2
        elif op == 'SETX' and ps >= CATT:                # as SETP's, the key from B, the value C; a full chunk: back to the
            o, key, v = val(a), s20(val(b) + STRTAG), val(c)     # arr class, whose trap's setx makes a new chunk (pst XBACK)
            q = ps - ps % 2; k = rd(q); rd(q + 1)
            if ps % 2: wr(q, key); wr(q + 1, v)
            elif k == key: wr(q + 1, v)
            elif k == 0 and (q - HEAP0) % 8 < 6: wr(q + 2, 0); npst = q + 1; done = False; pc -= 2
            elif k == 0: npst = XBACK; done = False; pc -= 2
            else: npst = (k + OBJTAG) & AMASK if k < 0 else q + 2; done = False; pc -= 2
        elif op in ('GETX', 'SETX'):                     # x: the array (B / A), y: the index (C / B), z: its len and ptr, e: the
            g = op == 'GETX'                             # element (GETX, inside the length) or C (SETX)
            x = val(b) if g else val(a); y = val(c) if g else val(b)
            arr = not ps and R.isarr(x); q = (x - ARRTAG) & AMASK
            ln, ptr = (rd(q - 1), rd(q)) if arr else (0, 0)
            inb = arr and 0 <= y < ln
            hand = not ps and R.isobj(x) and not R.notown(y)       # (an object: its probe, from the next execution)
            if g:
                e = rd(ptr + y) if inb else R.UNDEF
                if arr: wr(addr(a), e)
                elif hand: npst = (x + OBJTAG) & AMASK; done = False; pc -= 2
                else: pc = trap(addr(a), [x, y], (a - 256) * 8192 + pc // 2, 'getx', ps)
            else:
                e = val(c)
                if inb: wr(ptr + y, e)
                elif hand: npst = (x + OBJTAG) & AMASK; done = False; pc -= 2
                else: pc = trap(fp + TRAPOFF, [x, y, e], TRAPOFF * 8192 + pc // 2, 'setx', ps % XBACK)
        elif op == 'GETP':                               # one pair per execution (pst: the pair's address, 0 the first)
            o = val(b); key = DB + c
            if not R.isobj(o): wr(addr(a), R.UNDEF)
            else:
                q = ps or (o + OBJTAG) & AMASK; k, v = rd(q), rd(q + 1)
                if k == key or k == 0: wr(addr(a), v if k else R.UNDEF)
                else: npst = (k + OBJTAG) & AMASK if k < 0 else q + 2; done = False; pc -= 2
        elif op == 'SETP':                               # pst: a pair's address (probing), + 1 (its terminator written), < HEAP0 a trap
            o, v = val(a), val(b); key = DB + c
            if 0 < ps < HEAP0: pc = trap(fp + TRAPOFF, [o, key, v], TRAPOFF * 8192 + pc // 2, 'setp', ps)
            elif R.isobj(o):
                q = (ps - ps % 2) or (o + OBJTAG) & AMASK; k = rd(q); rd(q + 1)
                if ps % 2: wr(q, key); wr(q + 1, v)
                elif k == key: wr(q + 1, v)
                elif k == 0 and (q - HEAP0) % 8 < 6: wr(q + 2, 0); npst = q + 1; done = False; pc -= 2
                elif k == 0: pc = trap(fp + TRAPOFF, [o, key, v], TRAPOFF * 8192 + pc // 2, 'setp', 0)
                else: npst = (k + OBJTAG) & AMASK if k < 0 else q + 2; done = False; pc -= 2
        elif op == 'NEW':                                # the chunk's first key, the value, then HP; full: the collector (NEW again)
            hp, gl = rd(HP), rd(GCLIM)
            if not ps and s20(hp - (gl + HS - 7)) >= 0: pc = trap(addr(a), [], (a - 256) * 8192 + (pc - 2) // 2, 'gcnew', 0)
            elif ps == 2: mw, bit = R.mapbit(HEAP0 + hp); wr(mw, self.rdu(mw) | 1 << bit); npst = 3; done = False; pc -= 2
            else:
                wr((HEAP0 + hp, addr(a), None, HP)[ps], (0, hp + HEAP0 - OBJTAG, None, hp + 8)[ps])
                if ps < 3: npst = ps + 1; done = False; pc -= 2
        elif op == 'JMP': pc = 2 * a
        elif op in ('JZ', 'JNZ'): pc = 2 * a if truthy(val(b)) == (op == 'JNZ') else pc
        elif op == 'HALT': pc -= 2; st['halt'] = True
        elif op[0] == 'J':                              # user code: two integers (and JEQ ... JLNE's identities) here, else a hand-off
            x, y = val(b), val(c); ng = op[1] == 'N' and op != 'JNE'       # to the jtrap class (pst CATT), which calls jcmp
            if not user: pc = 2 * a if ALU[op[1:]](x, y) else pc
            elif ps >= CATT:
                pc = trap((fp + TRAPOFF) & AMASK, [x, y], TRAPOFF * 8192 + pc // 2, 'jcmp', ps - CATT); npst = CATT + npst if npst else 0
            else:
                r = R.dyn_fast('D' + op[1 + ng:], x, y)
                if r is None: npst = CATT; done = False; pc -= 2
                elif (r == R.TRUE) != ng: pc = 2 * a
        elif op == 'CALL': wr(fp + w1, w1 * 8192 + pc // 2); fp += w1; pc = 2 * a
        elif op == 'RET': r = rd(fp); v = val(b); wr(fp, v); fp -= r // 8192; pc = 2 * (r % 8192); npst = WBACK * (r // 8192 == TRAPDEF)
        elif op == 'PRINT' and (R.isarr(val(b)) or R.isobj(val(b))): npst = pc - 2; pc = st['ent']['pstub']
        elif op in ('PRINT', 'PRINTK'):
            v = val(b) if op == 'PRINT' else w1
            f = self.free(cw)
            cells, nl, done, npst = self.chunk(a, v, f)
            if not cells and not done and not nl: raise Stall()          # (nothing fits this pass)
            out = (cells, nl)
            if not done: pc -= 2
        elif op == 'PUTC':
            ch = val(b)
            if ch != 10 and not self.free(cw): raise Stall()
            out = ([], True) if ch == 10 else ([ch], False)
        elif op == 'KIND': wr(addr(a), R.kind(c - 896, val(b)))
        elif op == 'ALLOC':                              # pst: the phase (cc_ref.AP_*), CATT + a step: the trap
            n = val(b); k = c - 896; nw = R.allocw(k, n); hp, gl = rd(HP), rd(GCLIM)
            if ps >= CATT or (ps == 0 and hp + nw > gl + HS):
                pc = trap(addr(a), [nw], (a - 256) * 8192 + (pc - 2) // 2, 'galloc', ps - CATT if ps else 0)
                npst = self.npst_t + CATT if self.npst_t else 0
            else:
                base = HEAP0 + hp - (nw if ps else 0)
                if ps == R.AP_HP: wr(HP, hp + nw)
                elif ps == R.AP_HDR:
                    for j, w in enumerate(R.allochdr(k, n, nw, base)): wr(base + j, w)
                elif ps == R.AP_NUL: wr(base + 2 + n, 0)
                elif ps == R.AP_MAP: mw, bit = R.mapbit(base); wr(mw, self.rdu(mw) | 1 << bit)
                else: wr(addr(a), (base + 2 - STRTAG, base + 3 + ARRTAG, base, base)[k])
                if ps != R.AP_RES: npst = R.allocnext(ps, k, n); done = False; pc -= 2
        elif op in ('MCPY', 'MUPPER', 'MLOWER', 'MFILL', 'NPUT'):     # a line per execution (pst: the words done)
            sv = val(b); n = val(c) if op != 'NPUT' else None; d_ = val(a); o = ps
            if op == 'NPUT': dg = [ord(ch) for ch in str(sv)]; n = len(dg)
            ad = (d_ + o) & AMASK; cp = op not in ('MFILL', 'NPUT'); as_ = (sv + o) & AMASK
            k = max(0, min(n - o, 4 - ad % 4, 4 - as_ % 4 if cp else 4))
            t = [R.mcase(op, rd(as_ + j)) for j in range(k)] if cp else [sv] * k if op == 'MFILL' else dg[o:o + k]
            for j, w in enumerate(t): wr(ad + j, w)
            if o + k < n: npst = o + k; done = False; pc -= 2
        elif op in ('MCMP', 'MFEQ', 'MFREF'):            # a line of each per execution (pst: the words done); A at the end
            pv, qv, n = val(b), val(c), val(a); o = ps
            ap = (pv + o) & AMASK; aq = (qv + o) & AMASK
            k = max(0, min(n - o, 4 - ap % 4, 4 - aq % 4 if op == 'MCMP' else 4))
            ws = [rd(ap + j) for j in range(k)]; qs = [self.rdu(aq + j) for j in range(k)] if op == 'MCMP' else None
            hit = next((j for j in range(k) if (ws[j] != qs[j] if op == 'MCMP' else ws[j] == qv if op == 'MFEQ' else R.isfref(ws[j], qv))), None)
            if hit is not None: wr(addr(a), o + hit)
            elif o + k >= n: wr(addr(a), o + k)
            else: npst = o + k; done = False; pc -= 2
        elif op == 'MWALK':                              # a string per execution (pst: the offset)
            pv, e, n = val(b), val(c), val(a); o = ps
            if pv + o >= e: wr(addr(a), o)
            else:
                L_ = rd(pv + o)
                if L_ == n: wr(addr(a), o)
                elif pv + o + L_ + 2 >= e: wr(addr(a), o + L_ + 2)
                else: npst = o + L_ + 2; done = False; pc -= 2
        elif op == 'APUSH':                              # pst 0 the element (no array or a full one: on), 1 the length, 2 the
            x, v = val(b), val(c); q = (x - ARRTAG) & AMASK     # result over the return word, and return (reads: x, v, the
            r = rd(fp) if ps == 2 else None                      # return word, the array's first line)
            hl = [rd(q - 3 + j) for j in range(4)] if R.isarr(x) else [0, 0, 0, 0]; cap, ln, ptr = hl[1:]
            if ps == 0 and not (R.isarr(x) and ln < cap): pass
            elif ps == 0: wr(ptr + ln, v); npst = 1; done = False; pc -= 2
            elif ps == 1: wr(q - 1, ln + 1); npst = 2; done = False; pc -= 2
            else: wr(fp, ln); fp -= r // 8192; pc = 2 * (r % 8192)
        elif op == 'NET':                                # the answers come later on the page: it ends the pass, then runs first,
            x = val(b); P = 2 * R.LAYOUT['net_parts'] + 1           # once per write: the bytes, then part 0's answer into A
            if ps == 0 and not self.first: raise Stall()
            a_ = addr(a) if ps == P - 1 else R.RBUF0 + ps
            self.way((a_ & AMASK) // 4)                  # (its line before the gateway: a stall after it would ask twice)
            if ps == 0: st['netans'] = R.netw(st.setdefault('net', R.Device())(x))
            wr(a_, st['netans'][ps][1])
            if ps < P - 1: npst = ps + 1; done = False; pc -= 2
        else: raise SystemExit(f'op {op} not in csssim.py')
        # commit
        for (s, w, j), v in mem_w.items(): self.words[s][w][j] = v; self.dirty[s][w] = 1
        if out:
            cells, nl = out
            for ch in cells:
                cw |= 1 << (st['optr'] % 4)
                st['mem'][OUT_BASE + st['optr']] = ch; st['out'].append(ch); st['optr'] = (st['optr'] + 1) % (COLS * ROWS)
            if nl: st['optr'] = (st['optr'] // COLS + 1) * COLS % (COLS * ROWS); st['out'].append(10)
        st['pc'], st['fp'], st['pst'] = pc, fp, npst; st['steps'] += 1 if done else 0
        return cw
    def run_pass(self, K):
        """one pass: (instructions executed, why it ended)"""
        self.passes += 1; cw = 0; self.wb = None
        if self.pending is not None and not self.stale: self.fill(self.pending, cw)
        self.pending = None
        n = 0; why = 'halt'
        while n < K and not self.st['halt']:
            self.first = n == 0
            try: cw = self.execute(cw); n += 1
            except Stall as e:
                self.pending = e.miss; self.pic = e.ic; why = 'miss' if e.miss is not None else 'write'; self.latch = dict(self.reads); break
        else: why = 'halt' if self.st['halt'] else 'K'; self.latch = {}
        self.first = False
        self.stale = self.pending is not None and self.pending == self.wb and not self.pic
        self.pstale = self.pending is not None and self.pending + 1 == self.wb and not self.pic
        return n, why

if __name__ == '__main__':
    import json
    path = sys.argv[1]; K = int(sys.argv[2]) if len(sys.argv) > 2 else 32
    sim = Sim(ref.load(path)); ends = {}
    while not sim.st['halt'] and sim.passes < 200000:
        n, why = sim.run_pass(K); ends[why] = ends.get(why, 0) + 1
    lib = json.load(open(os.path.join(ref.ROOT, 'compiler', 'lib.json')))
    steps, out = R.compile_and_run(open(path).read(), lib)[1]
    got = ''.join(map(chr, sim.st['out']))
    print(f"{os.path.basename(path)}: passes {sim.passes} {ends}, steps {sim.st['steps']} (cc_ref {steps}), output ok {got == out}")
