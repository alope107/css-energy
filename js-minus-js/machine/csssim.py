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
and a string) evicted each other forever. Instructions in ROM are fetched from a static table, not through the cache (ROMF).

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
    def __init__(self, miss=None): self.miss = miss

class Sim:
    def __init__(self, st):
        self.st = st                              # pc fp optr pst mem out halt steps (cssref)
        self.st.setdefault('pst', 0)
        self.tag = [[None] * NWAY for _ in range(NSET)]; self.dirty = [[0] * NWAY for _ in range(NSET)]
        self.words = [[[0] * 4 for _ in range(NWAY)] for _ in range(NSET)]; self.fifo = [0] * NSET
        self.pending = None; self.passes = 0; self.wbacks = 0; self.stale = self.pstale = False; self.wb = None
        self.latch = {}; self.reads = {}; self.first = False
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
    def fill(self, b, cw):
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
    def chunk(self, flags, v):
        """one PRINT execution (flags: separator * 2 + boolean): (cells written, newline after, done, next pst); reads may stall"""
        st = self.st; sep = (0, 32, 10)[flags // 2 % 4]
        isb = flags % 2; p = v + STRTAG
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
            if term == 10: return text, True, False, q + e + 1
            if term is None: return text, False, False, q + e
            return text + ([32] if sep == 32 else []), sep == 10, True, 0
        text = [ord(ch) for ch in (('true' if v else 'false') if isb and v in (0, 1) else str(v))]
        done_chunks = st['pst'] - 1 if st['pst'] else 0
        text = text[4 * done_chunks:] + ([32] if sep == 32 else [])
        if len(text) > 4: return text[:4], False, False, done_chunks + 2
        return text, sep == 10, True, 0
    def execute(self, cw):
        """one instruction, or Stall; returns cw (the console write set used)"""
        st = self.st; mem_w = {}; rd = self.rd
        def wr(a, v):
            a &= AMASK
            if a < ref.ROMN: return
            s, w = self.way(a // 4); mem_w[(s, w, a % 4)] = s20(v)
        pc, fp = st['pc'], st['fp']
        self.reads = {}
        if ROMF and pc < ref.ROMN: w0, w1 = st['mem'].get(pc, 0), st['mem'].get(pc + 1, 0)
        else: w0 = rd(pc); w1 = rd(pc + 1)
        op = OPN[w0 // 8192]; a = w0 % 8192; b = w1 // 1024 + 512; c = w1 % 1024
        def addr(o): return (DB + o if o < 256 else fp + o - 256) & AMASK
        def val(o): return o - 896 if o >= 768 else rd(addr(o))
        def truthy(v): return v != 0 and not (R.isstr(v) and rd((v - 1) & AMASK) == 0)
        ps = st['pst']; npst = 0
        def trap(F, args, retw, name, s):
            """one execution of a trap: argument s from the last, or (s = len(args)) the return word, fp = F, pc = the routine"""
            nonlocal fp, npst, done
            n = len(args)
            if s < n: wr(F + n - s, args[n - 1 - s]); npst = s + 1; done = False; return pc - 2
            wr(F, retw); fp = F; return st['ent'][name]
        pc += 2; out = None; done = True
        if op in ALU: x, y = val(b), val(c); wr(addr(a), ALU[op](x, y))
        elif op == 'MOV': wr(addr(a), val(b))
        elif op == 'NEG': wr(addr(a), -val(b))
        elif op == 'NOT': wr(addr(a), int(not truthy(val(b))))
        elif op == 'LOADK': wr(addr(a), w1)
        elif op == 'GETFP': wr(addr(a), fp)
        elif op == 'LDI': x, y = val(b), val(c); wr(addr(a), rd(x + y))
        elif op == 'STI': x, y = val(b), val(c); z = val(a); wr(z + x, y)
        elif op == 'TENTER': wr(fp + TRAPOFF, TRAPOFF * 8192 + ps + 2); fp += TRAPOFF; pc = a
        elif op in ('DADD', 'DADDL', 'DADDR', 'DLT', 'DGT', 'DLE', 'DGE', 'DEQ', 'DNE'):
            x, y = val(b), val(c)
            slow = R.isstr(x) and R.isstr(y) if op in ('DEQ', 'DNE') else R.isref(x) or R.isref(y)
            if ps or slow: pc = trap(addr(a), [x, y], (a - 256) * 8192 + pc, R.TRAPS[op], ps)
            else: wr(addr(a), ALU['ADD' if op[1] == 'A' else op[1:]](x, y))
        elif op in ('GETX', 'SETX'):                     # x: the array (B / A), y: the index (C / B), z: its len and ptr, e: the
            g = op == 'GETX'                             # element (GETX, inside the length) or C (SETX)
            x = val(b) if g else val(a); y = val(c) if g else val(b)
            arr = not ps and R.isarr(x); q = (x - ARRTAG) & AMASK
            ln, ptr = (rd(q - 1), rd(q)) if arr else (0, 0)
            inb = arr and 0 <= y < ln
            if g:
                e = rd(ptr + y) if inb else 0
                if arr: wr(addr(a), e)
                else: pc = trap(addr(a), [x, y], (a - 256) * 8192 + pc, 'getx', ps)
            else:
                e = val(c)
                if inb: wr(ptr + y, e)
                else: pc = trap(fp + TRAPOFF, [x, y, e], TRAPOFF * 8192 + pc, 'setx', ps)
        elif op == 'GETP':                               # one pair per execution (pst: the pair's address, 0 the first)
            o = val(b); key = DB + c
            if not R.isobj(o): wr(addr(a), 0)
            else:
                q = ps or (o + OBJTAG) & AMASK; k, v = rd(q), rd(q + 1)
                if k == key or k == 0: wr(addr(a), v if k else 0)
                else: npst = (k + OBJTAG) & AMASK if k < 0 else q + 2; done = False; pc -= 2
        elif op == 'SETP':                               # pst: a pair's address (probing), + 1 (its terminator written), < HEAP0 a trap
            o, v = val(a), val(b); key = DB + c
            if 0 < ps < HEAP0: pc = trap(fp + TRAPOFF, [o, key, v], TRAPOFF * 8192 + pc, 'setp', ps)
            elif R.isobj(o):
                q = (ps - ps % 2) or (o + OBJTAG) & AMASK; k = rd(q); rd(q + 1)
                if ps % 2: wr(q, key); wr(q + 1, v)
                elif k == key: wr(q + 1, v)
                elif k == 0 and (q - HEAP0) % 8 < 6: wr(q + 2, 0); npst = q + 1; done = False; pc -= 2
                elif k == 0: pc = trap(fp + TRAPOFF, [o, key, v], TRAPOFF * 8192 + pc, 'setp', 0)
                else: npst = (k + OBJTAG) & AMASK if k < 0 else q + 2; done = False; pc -= 2
        elif op == 'NEW':                                # the chunk's first key, the value, then HP; full: the collector (NEW again)
            hp, gl = rd(HP), rd(GCLIM)
            if not ps and s20(hp - (gl + HS - 7)) >= 0: pc = trap(addr(a), [], (a - 256) * 8192 + pc - 2, 'gcnew', 0)
            else:
                wr((HEAP0 + hp, addr(a), HP)[ps], (0, hp + HEAP0 - OBJTAG, hp + 8)[ps])
                if ps < 2: npst = ps + 1; done = False; pc -= 2
        elif op == 'JMP': pc = a
        elif op in ('JZ', 'JNZ'): pc = a if truthy(val(b)) == (op == 'JNZ') else pc
        elif op == 'HALT': pc -= 2; st['halt'] = True
        elif op[0] == 'J': x, y = val(b), val(c); pc = a if ALU[op[1:]](x, y) else pc
        elif op == 'CALL': wr(fp + w1, w1 * 8192 + pc); fp += w1; pc = a
        elif op == 'RET': r = rd(fp); v = val(b); wr(fp, v); fp -= r // 8192; pc = r % 8192
        elif op == 'PRINT' and (R.isarr(val(b)) or R.isobj(val(b))): npst = pc - 2; pc = st['ent']['pstub']
        elif op in ('PRINT', 'PRINTK'):
            v = val(b) if op == 'PRINT' else w1
            if cw: raise Stall()
            cells, nl, done, npst = self.chunk(a, v)
            out = (cells, nl)
            if not done: pc -= 2
        elif op == 'PUTC':
            if cw: raise Stall()
            ch = val(b); out = ([], True) if ch == 10 else ([ch], False)
        else: raise SystemExit(f'op {op} not in csssim.py')
        # commit
        for (s, w, j), v in mem_w.items(): self.words[s][w][j] = v; self.dirty[s][w] = 1
        if out:
            cells, nl = out
            for ch in cells:
                st['mem'][OUT_BASE + st['optr']] = ch; st['out'].append(ch); st['optr'] = (st['optr'] + 1) % (COLS * ROWS)
            if nl: st['optr'] = (st['optr'] // COLS + 1) * COLS % (COLS * ROWS); st['out'].append(10)
            if cells: cw = 1
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
                self.pending = e.miss; why = 'miss' if e.miss is not None else 'write'; self.latch = dict(self.reads); break
        else: why = 'halt' if self.st['halt'] else 'K'; self.latch = {}
        self.first = False
        self.stale = self.pending is not None and self.pending == self.wb
        self.pstale = self.pending is not None and self.pending + 1 == self.wb
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
