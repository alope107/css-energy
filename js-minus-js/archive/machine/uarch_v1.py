#!/usr/bin/env python3
"""uarch.py — value-level reference model of the font CPU (what the GSUB will implement).

Core: PC SP FP (persistent), IMM/SIM (from fetch), temps T1 T2 T3, MDR. One memory operation per
micro-cycle. An instruction commits (memory write + SP/FP/PC) only in its last micro-cycle, so any
trap or the end of a shaping simply restarts it.

Memory: N-line FIFO cache held in the glyph string. Read miss -> trap MISS. Write miss allocates by
shifting the lines left (oldest falls off) unless the oldest is dirty -> trap WFAIL.
Traps: MISS(addr) WFAIL EXT(op,a,b) for MUL DIV MOD SHL13, PUTC(c), HALT. Values are 20-bit two's
complement (the compiler never needs more; asserted).

CSS-side service (modelled in `service`): write back / read RAM, compute EXT, print.
"""
import json, sys

ROM = 4096
MASK = (1 << 20) - 1
def s20(v): v &= MASK; return v - (1 << 20) if v >> 19 else v

OPN = 'NOP PUSHI LOADG STOREG LOADL STOREL LOADI STOREI ADD SUB MUL DIV MOD LT GT LE GE EQ NE AND OR NOT NEG JMP JZ JNZ CALL ENTER RET POP DUP PUTC HALT JMPI SHL13 INCG INCL IDX IDXL'.split()
OP = {n: i for i, n in enumerate(OPN)}
FETCH = 39                                  # pseudo-op: fetch an instruction word from RAM

def tdiv(a, b): return 0 if b == 0 else int(a / b)
def tmod(a, b): return 0 if b == 0 else a - b * int(a / b)
BINF = {'ADD': lambda a, b: a + b, 'SUB': lambda a, b: a - b, 'LT': lambda a, b: +(a < b), 'GT': lambda a, b: +(a > b),
        'LE': lambda a, b: +(a <= b), 'GE': lambda a, b: +(a >= b), 'EQ': lambda a, b: +(a == b), 'NE': lambda a, b: +(a != b),
        'AND': lambda a, b: +(a != 0 and b != 0), 'OR': lambda a, b: +(a != 0 or b != 0)}
EXTF = {'MUL': lambda a, b: a * b, 'DIV': tdiv, 'MOD': tmod, 'SHL13': lambda a, b: a * 8192}

# ---- microcode: UCODE[op] = list of micro-cycles. Each cycle is a dict:
#   mem: None | ('R', addr) | ('W', addr, data)    (addr/data are expression names, see EXPR)
#   t:   {temp: 'MDR'}  temp loads from the read result
#   commit: {reg: expr}  last cycle only (applied with the write); 'ext'/'putc'/'halt' special
R = lambda a: ('R', a)
W = lambda a, d: ('W', a, d)
def bin_ops():
    u = {}
    for n in BINF:
        u[n] = [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(mem=R('SP-2'), t={'T2': 'MDR'}),
                dict(mem=W('SP-2', n + '(T2,T1)'), commit={'SP': 'SP-1', 'PC': 'PC+1'})]
    for n in ('MUL', 'DIV', 'MOD'):
        u[n] = [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(mem=R('SP-2'), t={'T2': 'MDR'}),
                dict(ext=n, mem=W('SP-2', 'RES'), commit={'SP': 'SP-1', 'PC': 'PC+1'})]
    return u
UCODE = {
    'NOP':    [dict(commit={'PC': 'PC+1'})],
    'PUSHI':  [dict(mem=W('SP', 'IMM'), commit={'SP': 'SP+1', 'PC': 'PC+1'})],
    'LOADG':  [dict(mem=R('IMM'), t={'T1': 'MDR'}), dict(mem=W('SP', 'T1'), commit={'SP': 'SP+1', 'PC': 'PC+1'})],
    'STOREG': [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(mem=W('IMM', 'T1'), commit={'SP': 'SP-1', 'PC': 'PC+1'})],
    'LOADL':  [dict(mem=R('FP+SIM'), t={'T1': 'MDR'}), dict(mem=W('SP', 'T1'), commit={'SP': 'SP+1', 'PC': 'PC+1'})],
    'STOREL': [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(mem=W('FP+SIM', 'T1'), commit={'SP': 'SP-1', 'PC': 'PC+1'})],
    'LOADI':  [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(mem=R('T1'), t={'T2': 'MDR'}), dict(mem=W('SP-1', 'T2'), commit={'PC': 'PC+1'})],
    'STOREI': [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(mem=R('SP-2'), t={'T2': 'MDR'}), dict(mem=W('T2', 'T1'), commit={'SP': 'SP-2', 'PC': 'PC+1'})],
    **bin_ops(),
    'NOT':    [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(mem=W('SP-1', 'Z(T1)'), commit={'PC': 'PC+1'})],
    'NEG':    [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(mem=W('SP-1', '-T1'), commit={'PC': 'PC+1'})],
    'JMP':    [dict(commit={'PC': 'IMM'})],
    'JZ':     [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(commit={'SP': 'SP-1', 'PC': 'Z(T1)?IMM:PC+1'})],
    'JNZ':    [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(commit={'SP': 'SP-1', 'PC': 'Z(T1)?PC+1:IMM'})],
    'CALL':   [dict(mem=W('SP', 'PC+1'), commit={'SP': 'SP+1', 'PC': 'IMM'})],
    'ENTER':  [dict(mem=W('SP', 'FP'), commit={'FP': 'SP', 'SP': 'SP+1+IMM', 'PC': 'PC+1'})],
    'RET':    [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(mem=R('FP'), t={'T2': 'MDR'}), dict(mem=R('FP-1'), t={'T3': 'MDR'}),
               dict(mem=W('FP-1-IMM', 'T1'), commit={'SP': 'FP-IMM', 'FP': 'T2', 'PC': 'T3'})],
    'POP':    [dict(commit={'SP': 'SP-1', 'PC': 'PC+1'})],
    'DUP':    [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(mem=W('SP', 'T1'), commit={'SP': 'SP+1', 'PC': 'PC+1'})],
    'PUTC':   [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(putc=True, commit={'SP': 'SP-1', 'PC': 'PC+1'})],
    'HALT':   [dict(halt=True)],
    'JMPI':   [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(commit={'SP': 'SP-1', 'PC': 'T1'})],
    'SHL13':  [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(ext='SHL13', mem=W('SP-1', 'RES'), commit={'PC': 'PC+1'})],
    'INCG':   [dict(mem=R('IMM'), t={'T1': 'MDR'}), dict(mem=W('IMM', 'T1+1'), commit={'PC': 'PC+1'})],
    'INCL':   [dict(mem=R('FP+SIM'), t={'T1': 'MDR'}), dict(mem=W('FP+SIM', 'T1+1'), commit={'PC': 'PC+1'})],
    'IDX':    [dict(mem=R('IMM'), t={'T1': 'MDR'}), dict(mem=R('SP-1'), t={'T2': 'MDR'}), dict(mem=R('T1+T2'), t={'T3': 'MDR'}),
               dict(mem=W('SP-1', 'T3'), commit={'PC': 'PC+1'})],
    'IDXL':   [dict(mem=R('FP+SIM'), t={'T1': 'MDR'}), dict(mem=R('SP-1'), t={'T2': 'MDR'}), dict(mem=R('T1+T2'), t={'T3': 'MDR'}),
               dict(mem=W('SP-1', 'T3'), commit={'PC': 'PC+1'})],
}
assert set(UCODE) == set(OPN), set(OPN) - set(UCODE)

def ev(e, r):
    """Evaluate an expression name over the register dict r (all values signed 20-bit)."""
    if e in r: return r[e]
    if e == 'Z(T1)': return +(r['T1'] == 0)
    if e == '-T1': return -r['T1']
    if e == 'Z(T1)?IMM:PC+1': return r['IMM'] if r['T1'] == 0 else r['PC'] + 1
    if e == 'Z(T1)?PC+1:IMM': return r['PC'] + 1 if r['T1'] == 0 else r['IMM']
    if '(' in e:
        f, args = e.split('(', 1); a, b = args[:-1].split(',')
        return BINF[f](r[a], r[b])
    # linear forms: REG(+REG)?(+/-const)*
    import re
    total = 0
    for sign, tok in re.findall(r'([+-]?)([A-Z0-9]+)', e):
        v = r[tok] if tok in r else int(tok)
        total += -v if sign == '-' else v
    return total

class Machine:
    def __init__(self, image, N):
        self.N = N
        self.rom = image['rom']
        self.ram = {ROM + i: v for i, v in enumerate(image['ram'])}
        self.pc, self.sp, self.fp = 0, image['sp0'], image['sp0']
        self.outbase = image['outBase']
        self.lines = [None] * N            # [addr, val, dirty] or None; index 0 = oldest (victim)
        self.evict = None                  # parked dirty victim, written back by CSS at the next trap
        self.res, self.resv, self.ackwb = 0, 0, 0
        self.inline = None                 # incoming line from the last service
        self.out, self.optr = [], 0
        self.steps = self.cycles = self.shapings = self.traps = 0
        self.trapkinds = {}
        self.halted = False

    # ---- cache, exactly as the glyph string will behave
    def c_read(self, a):
        for ln in [self.evict] + self.lines:
            if ln and ln[0] == a: return True, ln[1]
        return False, 0
    def c_write(self, a, v):
        for ln in [self.evict] + self.lines:
            if ln and ln[0] == a: ln[1] = v; ln[2] = 1; return True
        return self.allocate([a, v, 1])
    def allocate(self, new):
        v = self.lines[0]
        if v and v[2] and not (self.sp <= v[0] < self.outbase):   # dead stack cells above SP are dropped
            if self.evict: return False
            self.evict = v
        self.lines = self.lines[1:] + [new]
        return True

    def prologue(self):
        if self.ackwb: self.evict = None; self.ackwb = 0
        if self.inline: assert self.allocate(self.inline); self.inline = None

    def shaping(self, S):
        """One HarfBuzz call: up to S micro-cycles. Returns trap tuple or None (budget)."""
        self.shapings += 1
        self.prologue()
        mu, ir, r = 0, None, None
        for _ in range(S):
            self.cycles += 1
            if ir is None:                                   # instruction start
                if self.pc < ROM:
                    w = self.rom[self.pc]
                else:                                        # RAM code: this cycle is a fetch read
                    hit, w = self.c_read(self.pc)
                    if not hit: return self.trap(('MISS', self.pc))
                    ir = (w // 8192, w % 8192); mu = 0; continue
                ir = (w // 8192, w % 8192); mu = 0
            op, imm = ir
            name = OPN[op]
            r = r or {}
            r.update(PC=self.pc, SP=self.sp, FP=self.fp, IMM=imm, SIM=imm - 8192 if imm >= 4096 else imm, RES=self.res)
            cyc = UCODE[name][mu]
            last = mu == len(UCODE[name]) - 1
            if cyc.get('halt'): return self.trap(('HALT',))
            if cyc.get('ext') and not self.resv:
                return self.trap(('EXT', cyc['ext'], r.get('T2', 0) if cyc['ext'] != 'SHL13' else r['T1'], r.get('T1', 0)))
            if cyc.get('putc') and not self.resv:
                return self.trap(('PUTC', r['T1']))
            m = cyc.get('mem')
            if m and m[0] == 'R':
                a = ev(m[1], r) & MASK
                hit, v = self.c_read(a)
                if not hit: return self.trap(('MISS', a))
                r['MDR'] = v
            elif m and m[0] == 'W':
                a = ev(m[1], r) & MASK; v = s20(ev(m[2], r))
                assert abs(ev(m[2], r)) < (1 << 19), (name, ev(m[2], r))
                if not self.c_write(a, v): return self.trap(('WFAIL',))
            for t, e in cyc.get('t', {}).items(): r[t] = s20(ev(e, r))
            if last:
                new = {k: s20(ev(e, r)) for k, e in cyc.get('commit', {}).items()}
                self.pc = new.get('PC', self.pc) & 8191; self.sp = new.get('SP', self.sp); self.fp = new.get('FP', self.fp)
                if cyc.get('ext') or cyc.get('putc'): self.resv = 0
                self.steps += 1; ir = None; r = None
            else:
                mu += 1
        return None

    def trap(self, t):
        self.traps += 1; self.trapkinds[t[0]] = self.trapkinds.get(t[0], 0) + 1
        return t

    def service(self, t):
        """What the CSS side does between shapings."""
        if self.evict:                     # one write-back per trap (or budget stop)
            self.ram[self.evict[0]] = self.evict[1]; self.ackwb = 1
        if t is None: return
        k = t[0]
        if k == 'MISS':
            assert t[1] >= ROM, ('read below RAM', t)
            self.inline = [t[1], self.ram.get(t[1], 0), 0]
        elif k == 'WFAIL':
            pass                           # the evict buffer was written back above
        elif k == 'EXT':
            self.res = s20(EXTF[t[1]](t[2], t[3])); self.resv = 1
            assert abs(EXTF[t[1]](t[2], t[3])) < (1 << 19), t
        elif k == 'PUTC':
            self.out.append(t[1]); self.resv = 1
        elif k == 'HALT':
            self.halted = True

    def run(self, S, limit=10 ** 6):
        while not self.halted and self.shapings < limit:
            self.service(self.shaping(S))
        return self

if __name__ == '__main__':
    image = json.load(open(sys.argv[1]))
    for N in [16, 32, 64]:
        for S in [16, 32, 48]:
            m = Machine(image, N).run(S)
            ok = ''.join(map(chr, m.out)) == image['expected']
            print(f'N={N:3} S={S:3}  ok={ok}  steps={m.steps} cycles={m.cycles} shapings={m.shapings} '
                  f'steps/shaping={m.steps / m.shapings:.2f}  cyc/step={m.cycles / m.steps:.2f}  traps={m.trapkinds}')
