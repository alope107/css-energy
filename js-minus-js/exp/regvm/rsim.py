"""rsim.py — the register CSS CPU's design, pass by pass (the oracle for gen_rcss.py; python3 exp/regvm/rsim.py prog.js [K]).

machine/csssim.py's machine (cache, fill, prefetch, stalls, latches, PRINT chunks, the console write set) running rc_ref's
instructions. An instruction's accesses: the fetch (both words in one block), its source operands B and C when they are cells,
the destination A; RET reads the return word at fp and writes the value there; CALL writes the return word at fp + off; JZ /
JNZ / NOT read a string's length word. Prints the passes and how they end, beside main's (csssim on cc_ref's code)."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, os.path.join(ROOT, 'machine'), os.path.join(ROOT, 'compiler')]
import csssim as CS
from csssim import Stall, NSET, NWAY, setof
import rc_ref as RC, cc_ref as R
from cc_ref import LAYOUT, STRTAG, SDATA
AMASK = 32767; DB = LAYOUT['data_base']; ROMN = LAYOUT['rom_size']
OUT_BASE, COLS, ROWS = LAYOUT['out_base'], LAYOUT['cols'], LAYOUT['rows']
def s20(x): return (x + (1 << 19)) % (1 << 20) - (1 << 19)
ALU = {'ADD': lambda a, b: s20(a + b), 'SUB': lambda a, b: s20(a - b), 'MUL': lambda a, b: s20(a * b),
       'DIV': lambda a, b: 0 if b == 0 else int(a / b), 'MOD': lambda a, b: 0 if b == 0 else a - b * int(a / b),
       'LT': lambda a, b: int(a < b), 'GT': lambda a, b: int(a > b), 'LE': lambda a, b: int(a <= b), 'GE': lambda a, b: int(a >= b),
       'EQ': lambda a, b: int(a == b), 'NE': lambda a, b: int(a != b)}

class Sim(CS.Sim):
    """st: pc fp optr mem out halt steps"""
    def chunk(self, op, v):
        flags = self.flags; o = {0: 'PRINT', 1: 'PRINTB', 2: 'PRINTSP', 3: 'PRINTBSP', 4: 'PRINTLN', 5: 'PRINTBLN'}[flags]
        return super().chunk(o, v)
    def execute(self, cw):
        st = self.st; mem_w = {}; rd = self.rd
        def wr(a, v):
            a &= AMASK
            if a < ROMN: return
            s, w = self.way(a // 4); mem_w[(s, w, a % 4)] = s20(v)
        pc, fp = st['pc'], st['fp']
        self.reads = {}
        w0 = rd(pc); w1 = rd(pc + 1); op = RC.OPN[w0 // 8192]; a = w0 % 8192; b = w1 // 1024 + 512; c = w1 % 1024
        def addr(o): return (DB + o if o < 256 else fp + o - 256) & AMASK
        def val(o): return o - 896 if o >= 768 else rd(addr(o))
        def truthy(v): return v != 0 and not (R.isstr(v) and rd((v - 1) & AMASK) == 0)
        pc += 2; out = None; done = True
        if op in ALU: x, y = val(b), val(c); wr(addr(a), ALU[op](x, y))
        elif op == 'MOV': wr(addr(a), val(b))
        elif op == 'NEG': wr(addr(a), -val(b))
        elif op == 'NOT': wr(addr(a), int(not truthy(val(b))))
        elif op == 'LOADK': wr(addr(a), w1)
        elif op == 'JMP': pc = a
        elif op in ('JZ', 'JNZ'): pc = a if truthy(val(b)) == (op == 'JNZ') else pc
        elif op[0] == 'J': x, y = val(b), val(c); pc = a if ALU[op[1:]](x, y) else pc
        elif op == 'CALL': wr(fp + w1, w1 * 8192 + pc); fp += w1; pc = a
        elif op == 'RET': r = rd(fp); v = val(b); wr(fp, v); fp -= r // 8192; pc = r % 8192
        elif op in ('PRINT', 'PRINTK'):
            v = val(b) if op == 'PRINT' else w1
            if cw: raise Stall()
            self.flags = a
            cells, nl, done, pst = self.chunk(op, v)
            out = (cells, nl)
            if done: st['pst'] = 0
            else: pc -= 2; st['pst'] = pst
        elif op == 'PUTC':
            if cw: raise Stall()
            ch = val(b); out = ([], True) if ch == 10 else ([ch], False)
        elif op == 'HALT': pc -= 2; st['halt'] = True
        else: raise SystemExit(f'op {op} not in rsim.py')
        for (s, w, j), v in mem_w.items(): self.words[s][w][j] = v; self.dirty[s][w] = 1
        if out:
            cells, nl = out
            for ch in cells:
                st['mem'][OUT_BASE + st['optr']] = ch; st['out'].append(ch); st['optr'] = (st['optr'] + 1) % (COLS * ROWS)
            if nl: st['optr'] = (st['optr'] // COLS + 1) * COLS % (COLS * ROWS); st['out'].append(10)
            if cells: cw = 1
        st['pc'], st['fp'] = pc, fp; st['steps'] += 1 if done else 0
        return cw

def load(src):
    c, words, data = RC.compile_src(src)
    assert not c.err, c.err
    mem = RC.image_mem(c, words, data)
    return {'pc': RC.CODE0, 'fp': LAYOUT['sp0'], 'sp': LAYOUT['sp0'], 'optr': 0, 'mem': mem, 'out': [], 'halt': False, 'steps': 0}

def passes(sim, K):
    ends = {}
    while not sim.st['halt'] and sim.passes < 200000:
        n, why = sim.run_pass(K); ends[why] = ends.get(why, 0) + 1
    return ends

if __name__ == '__main__':
    import cssref as ref
    path = sys.argv[1]; K = int(sys.argv[2]) if len(sys.argv) > 2 else 32
    src = open(path).read()
    sim = Sim(load(src)); ends = passes(sim, K)
    steps, out = RC.compile_and_run(src)[1]
    got = ''.join(map(chr, sim.st['out']))
    m = CS.Sim(ref.load(path)); mends = passes(m, K)
    print(f"{os.path.basename(path)}: passes {sim.passes} {ends}, steps {sim.st['steps']} (rc_ref {steps}), output ok {got == out}; "
          f"main: passes {m.passes} {mends}, steps {m.st['steps']}")
