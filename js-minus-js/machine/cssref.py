"""cssref.py — cc_ref.run()'s instruction semantics as a stepper on an explicit state, for the CSS CPU experiments: the
generator's expected results, and cache / pass analyses (python3 machine/cssref.py prog.js prints them).
Objects ops are left out (FizzBuzz-class programs); PRINT follows cc_ref.run (the whole value in one instruction)."""
import os, sys, json, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'compiler'), os.path.join(ROOT, 'machine')]
import cc_ref as R
from uarch import OPN
LA = R.LAYOUT; AMASK = 32767; M20 = 1 << 20; ROMN = LA['rom_size']
COLS, ROWS = LA['cols'], LA['rows']; OUT_BASE = ROMN + LA['ram_size'] - COLS * ROWS
STRTAG = R.STRTAG; SDATA = R.SDATA

def s20(x): return (x + (1 << 19)) % M20 - (1 << 19)
def tdiv(a, b): return 0 if b == 0 else int(a / b)
def tmod(a, b): return 0 if b == 0 else a - b * int(a / b)
BIN = ['ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'LT', 'GT', 'LE', 'GE', 'EQ', 'NE', 'AND', 'OR']
BINF = [lambda a, b: s20(a + b), lambda a, b: s20(a - b), lambda a, b: s20(a * b), tdiv, tmod, lambda a, b: int(a < b),
        lambda a, b: int(a > b), lambda a, b: int(a <= b), lambda a, b: int(a >= b), lambda a, b: int(a == b),
        lambda a, b: int(a != b), lambda a, b: int(a != 0 and b != 0), lambda a, b: int(a != 0 or b != 0)]

def load(path, lib=None):
    """the machine at code_base... no: at pc 0 with ROM, RAM as the CSS compiler leaves it (the CPU-only page's image)"""
    lib = lib or json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
    c = R.Compiler(LA['data_base'], LA['code_base'], lib); words, data = c.compile(open(path).read())
    assert not c.err, c.err
    mem = {i: w for i, w in enumerate(lib['rom'])}
    mem.update(R.image_mem(c, words, data, lib['init']))
    return {'pc': 0, 'sp': LA['sp0'], 'fp': LA['sp0'], 'optr': 0, 'mem': mem, 'out': [], 'halt': False, 'steps': 0}

def from_image(im):
    """the same, from a mkimage-style image (rom + ram lists)"""
    mem = {i: w for i, w in enumerate(im['rom']) if w}
    mem.update({im['romSize'] + i: w for i, w in enumerate(im['ram']) if w})
    return {'pc': 0, 'sp': im['sp0'], 'fp': im['sp0'], 'optr': 0, 'mem': mem, 'out': [], 'halt': False, 'steps': 0}

class Machine:
    def __init__(self, st, on_read=None, on_write=None):
        self.st = st; self.on_read = on_read; self.on_write = on_write
    def rd(self, a):
        a &= AMASK
        if self.on_read: self.on_read(a)
        return self.st['mem'].get(a, 0)
    def wr(self, a, v):
        a &= AMASK
        if self.on_write: self.on_write(a)
        self.st['mem'][a] = s20(v)
    def putc(self, c):
        st = self.st
        if c == 10: st['optr'] = (st['optr'] // COLS + 1) * COLS % (COLS * ROWS)
        else: self.wr(OUT_BASE + st['optr'], c); st['optr'] = (st['optr'] + 1) % (COLS * ROWS)
        st['out'].append(c)
    def step(self):
        st = self.st; rd, wr = self.rd, self.wr
        pc, sp, fp = st['pc'], st['sp'], st['fp']
        w = rd(pc); op, imm = OPN[w // 8192], w % 8192; simm = imm - 8192 if imm >= 4096 else imm; pc += 1
        st['steps'] += 1
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
        elif op == 'PUTC': sp -= 1; self.putc(rd(sp))
        elif op == 'HALT': pc -= 1; st['halt'] = True
        elif op == 'JMPI': sp -= 1; pc = rd(sp)
        elif op == 'SHL13': wr(sp - 1, rd(sp - 1) * 8192)
        elif op == 'INCG': wr(imm, rd(imm) + 1)
        elif op == 'INCL': wr(fp + simm, rd(fp + simm) + 1)
        elif op == 'IDX': wr(sp - 1, rd(rd(imm) + rd(sp - 1)))
        elif op == 'IDXL': wr(sp - 1, rd(rd(fp + simm) + rd(sp - 1)))
        elif op.startswith('PRINT'):
            sp -= 1; v = rd(sp); p = v + STRTAG
            sep = 10 if op.endswith('LN') else 32 if op.endswith('SP') else 0
            if LA['data_base'] + SDATA <= p < LA['data_base'] + 2 * SDATA:
                text = []
                while p != LA['data_base'] + SDATA and rd(p) != 0: text.append(rd(p)); p += 1
            elif op in ('PRINTB', 'PRINTBSP', 'PRINTBLN') and v in (0, 1): text = [ord(ch) for ch in ('true' if v else 'false')]
            else: text = [ord(ch) for ch in str(v)]
            for ch in text + ([sep] if sep else []): self.putc(ch)
        else: raise SystemExit(f'op {op} at {pc - 1} not in ref.py')
        st['pc'], st['sp'], st['fp'] = pc, sp, fp
        return op

if __name__ == '__main__':
    path = sys.argv[1]
    st = load(path); blocks = collections.Counter(); ops = collections.Counter(); seq = []
    m = Machine(st, on_read=lambda a: seq.append(a // 4), on_write=lambda a: seq.append(a // 4))
    while not st['halt']: ops[m.step()] += 1
    lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
    steps, out = R.compile_and_run(open(path).read(), lib)[1]
    print('steps', st['steps'], 'cc_ref', steps, 'output ok', ''.join(map(chr, st['out'])) == out)
    print('ops', dict(ops.most_common()))
    ub = sorted(set(seq)); print('distinct blocks', len(ub), [b for b in ub])
