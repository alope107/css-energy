"""sim.py — the CSS CPU slice's design, pass by pass (the oracle for gen_css_cpu.py; python3 exp/csscpu/sim.py prog.js [K]).

Memory: ROM + RAM words (ref.load's image). Cache: 16 sets x 2 ways x 4 words, set = (b + b // 16 + b // 256) mod 16
for block b, FIFO replacement (a per-set bit naming the next victim, flipped on each fill), a dirty bit per line,
write-allocate by filling first. A pass: if a miss is pending, fill its block into the set's victim way (a dirty victim
is written back: the pass's one RAM write set), and prefetch the next block into its own set's victim way if that block is
absent and the victim is clean (PREF); then up to K instructions, each executed only if every word it reads
or writes hits and, for a PRINT chunk, the pass's write set is free. The first instruction that can't run ends the
pass (its miss, if any, is pending). Output has its own write set (the console's own cells and channels, so a write-back
doesn't hold it up). PRINT is chunked like uarch.Machine.print_service: up to 4 console cells per
instruction execution, a string chunk ends at its block; the instruction repeats (pst carries the position) until done.
The console is RAM written through the output write set, never cached. Instructions in ROM are fetched from a static table, not
through the cache (ROMF: the font CPU has its ROM in the font too)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref
from ref import OPN, AMASK, s20, BIN, BINF, LA, STRTAG, SDATA, COLS, ROWS, OUT_BASE

NSET, NWAY = 16, 2
ROMF = PREF = True
BLKS = (ref.ROMN + ref.LA['ram_size']) // 4
def setof(b): return (b + b // 16 + b // 256) % NSET
STR_LO, STR_HI = LA['data_base'] + SDATA, LA['data_base'] + 2 * SDATA

class Stall(Exception):
    def __init__(self, miss=None): self.miss = miss

class Sim:
    def __init__(self, st):
        self.st = st                              # pc sp fp optr mem out halt steps (ref.load)
        self.st['pst'] = 0
        self.tag = [[None] * NWAY for _ in range(NSET)]; self.dirty = [[0] * NWAY for _ in range(NSET)]
        self.words = [[[0] * 4 for _ in range(NWAY)] for _ in range(NSET)]; self.fifo = [0] * NSET
        self.pending = None; self.passes = 0; self.wbacks = 0
    def way(self, b):
        s = setof(b)
        for w in range(NWAY):
            if self.tag[s][w] == b: return s, w
        raise Stall(b)
    def rd(self, a):
        a &= AMASK; s, w = self.way(a // 4); return self.words[s][w][a % 4]
    def fill(self, b, cw):
        s = setof(b); w = self.fifo[s]
        if self.dirty[s][w]:
            vt = self.tag[s][w]
            for j in range(4): self.st['mem'][4 * vt + j] = self.words[s][w][j]
            self.wbacks += 1
        self.tag[s][w] = b; self.dirty[s][w] = 0; self.fifo[s] ^= 1
        self.words[s][w] = [self.st['mem'].get(4 * b + j, 0) for j in range(4)]
        nb = b + 1; s = setof(nb); w = self.fifo[s]
        if PREF and nb < BLKS and nb not in self.tag[s] and not self.dirty[s][w]:
            self.tag[s][w] = nb; self.fifo[s] ^= 1
            self.words[s][w] = [self.st['mem'].get(4 * nb + j, 0) for j in range(4)]
        return cw
    def chunk(self, op, v):
        """one PRINT execution: (cells written, newline after, done, next pst); reads may stall"""
        st = self.st; sep = 10 if op.endswith('LN') else 32 if op.endswith('SP') else 0
        isb = op in ('PRINTB', 'PRINTBSP', 'PRINTBLN'); p = v + STRTAG; cells = []
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
        """one instruction, or Stall; returns cw (the write set used)"""
        st = self.st; mem_w = {}
        def wr(a, v):
            a &= AMASK; s, w = self.way(a // 4); mem_w[(s, w, a % 4)] = s20(v)
        rd = self.rd
        pc, sp, fp = st['pc'], st['sp'], st['fp']
        word = st['mem'].get(pc, 0) if ROMF and pc < ref.ROMN else rd(pc); op, imm = OPN[word // 8192], word % 8192; simm = imm - 8192 if imm >= 4096 else imm; pc += 1
        out = None
        if op == 'NOP': pass
        elif op == 'PUSHI': wr(sp, imm); sp += 1
        elif op == 'LOADG': wr(sp, rd(imm)); sp += 1
        elif op == 'STOREG': sp -= 1; wr(imm, rd(sp))
        elif op == 'LOADL': wr(sp, rd(fp + simm)); sp += 1
        elif op == 'STOREL': sp -= 1; wr(fp + simm, rd(sp))
        elif op == 'LOADI': wr(sp - 1, rd(rd(sp - 1)))
        elif op == 'STOREI': b = rd(sp - 1); a = rd(sp - 2); sp -= 2; wr(a, b)
        elif op in BIN: b = rd(sp - 1); a = rd(sp - 2); sp -= 1; wr(sp - 1, BINF[BIN.index(op)](a, b))
        elif op == 'NOT': wr(sp - 1, int(rd(sp - 1) == 0))
        elif op == 'NEG': wr(sp - 1, -rd(sp - 1))
        elif op == 'JMP': pc = imm
        elif op == 'JZ': sp -= 1; pc = imm if rd(sp) == 0 else pc
        elif op == 'JNZ': sp -= 1; pc = imm if rd(sp) != 0 else pc
        elif op == 'CALL': wr(sp, pc); sp += 1; pc = imm
        elif op == 'ENTER': wr(sp, fp); fp = sp; sp = sp + 1 + imm
        elif op == 'RET': v = rd(sp - 1); ofp = rd(fp); ret = rd(fp - 1); nsp = fp - 1 - imm; wr(nsp, v); sp = nsp + 1; fp = ofp; pc = ret
        elif op == 'POP': sp -= 1
        elif op == 'DUP': wr(sp, rd(sp - 1)); sp += 1
        elif op == 'HALT': pc -= 1; st['halt'] = True
        elif op == 'JMPI': sp -= 1; pc = rd(sp)
        elif op == 'SHL13': wr(sp - 1, rd(sp - 1) * 8192)
        elif op == 'INCG': wr(imm, rd(imm) + 1)
        elif op == 'INCL': wr(fp + simm, rd(fp + simm) + 1)
        elif op == 'IDX': wr(sp - 1, rd(rd(imm) + rd(sp - 1)))
        elif op == 'IDXL': wr(sp - 1, rd(rd(fp + simm) + rd(sp - 1)))
        elif op.startswith('PRINT'):
            if cw: raise Stall()
            v = rd(sp - 1)
            cells, nl, done, pst = self.chunk(op, v)
            out = (cells, nl)
            if done: sp -= 1; st['pst'] = 0
            else: pc -= 1; st['pst'] = pst
        elif op == 'PUTC':
            if cw: raise Stall()
            ch = rd(sp - 1); sp -= 1; out = ([], True) if ch == 10 else ([ch], False); done = True
        else: raise SystemExit(f'op {op} not in sim.py')
        # commit
        for (s, w, j), v in mem_w.items(): self.words[s][w][j] = v; self.dirty[s][w] = 1
        if out:
            cells, nl = out
            for ch in cells:
                st['mem'][OUT_BASE + st['optr']] = ch; st['out'].append(ch); st['optr'] = (st['optr'] + 1) % (COLS * ROWS)
            if nl: st['optr'] = (st['optr'] // COLS + 1) * COLS % (COLS * ROWS); st['out'].append(10)
            if cells: cw = 1
        st['pc'], st['sp'], st['fp'] = pc, sp, fp; st['steps'] += 0 if out and not done else 1
        return cw
    def run_pass(self, K):
        """one pass: (instructions executed, why it ended)"""
        self.passes += 1; cw = 0
        if self.pending is not None: cw = self.fill(self.pending, cw); self.pending = None
        n = 0
        while n < K and not self.st['halt']:
            try: cw = self.execute(cw); n += 1
            except Stall as e:
                self.pending = e.miss; return n, 'miss' if e.miss is not None else 'write'
        return n, 'halt' if self.st['halt'] else 'K'

if __name__ == '__main__':
    path = sys.argv[1]; K = int(sys.argv[2]) if len(sys.argv) > 2 else 64
    sim = Sim(ref.load(path)); ends = {}
    while not sim.st['halt'] and sim.passes < 100000:
        n, why = sim.run_pass(K); ends[why] = ends.get(why, 0) + 1
    import json, cc_ref as R
    lib = json.load(open(os.path.join(ref.ROOT, 'compiler', 'lib.json')))
    steps, out = R.compile_and_run(open(path).read(), lib)[1]
    got = ''.join(map(chr, sim.st['out']))
    print(f"{os.path.basename(path)}: passes {sim.passes} {ends}, steps {sim.st['steps']} (cc_ref {steps}), output ok {got == out}")
