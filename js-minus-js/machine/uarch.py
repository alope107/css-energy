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
import json, sys, os

LAYOUT = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'compiler', 'layout.json')))
ROM = LAYOUT['rom_size']                    # RAM starts here
AMASK = 32767                               # 15-bit addresses
MASK = (1 << 20) - 1
def s20(v): v &= MASK; return v - (1 << 20) if v >> 19 else v

# PRINT family: pop a value and print it (CSS services the trap: a number in decimal, a tagged string pointer's bytes, or with
# the B flag true/false for 0/1); SP = a space after, LN = a newline after. One trap per chunk of up to 4 console cells
# (one write channel per bank), so a short number or string costs one shaping, "false" or a 5-digit number two.
PRINTOPS = ['PRINT', 'PRINTB', 'PRINTSP', 'PRINTBSP', 'PRINTLN', 'PRINTBLN']
# objects (cc_ref.py): SCANI / SCAN probe an object's keys, LDF loads a field, SETF stores one, PUTV stores a property, NEW
# allocates an 8-word chunk, ENDK ends its keys; OVER copies the word under the top, JNEG branches on the sign of that word
# (array or object)
OBJOPS = 'SCANI SCAN LDF PUTV NEW SETF ENDK OVER JNEG'.split()
OPN = 'NOP PUSHI LOADG STOREG LOADL STOREL LOADI STOREI ADD SUB MUL DIV MOD LT GT LE GE EQ NE AND OR NOT NEG JMP JZ JNZ CALL ENTER RET POP DUP PUTC HALT JMPI SHL13 INCG INCL IDX IDXL'.split() + PRINTOPS + OBJOPS
OP = {n: i for i, n in enumerate(OPN)}
STRTAG = 262144                             # a string value is its address - STRTAG (cc_ref.STRTAG)
STR_LO, STR_HI = LAYOUT['data_base'] + 256, LAYOUT['data_base'] + 512   # string area (cc_ref: data_base + SDATA .. + 2 * SDATA); STR_LO itself is the DONE marker
OUT_COLS, OUT_ROWS = LAYOUT['cols'], LAYOUT['rows']
OUT_BASE = LAYOUT['rom_size'] + LAYOUT['ram_size'] - OUT_COLS * OUT_ROWS   # console: the last words of RAM
PRINT_CHUNK = 4                             # console cells one service can write (one per bank)
# objects: an object is an 8-word chunk [k0 v0 k1 v1 k2 v2 L pad] in the heap, its value the chunk's address - OBJTAG (a multiple of
# 32768, so the 15-bit address registers untag it for free). A key is stored as its value + KBIAS (a string key becomes its
# address, positive and small; a number n becomes n + KBIAS), 0 marks a free pair (it ends the keys), and L links to an overflow
# chunk (a negative object value) or is 0. NEW calls the GC through the jump table when the heap is full; a store that must add
# a key calls the ROM's append routine.
OBJTAG, KBIAS = LAYOUT['objtag'], STRTAG
RT = LAYOUT['rt_base']; HP, GCLIM, GCSP, KEYCELL, RETCELL = range(RT, RT + 5)
# HP / GCLIM: the next free chunk and the space's end - 7 (offsets from HEAP0); GCSP: SP at a GC call; KEYCELL: the key KEYV made
# for SCAN; RETCELL: the return address of a call into the ROM routines
HEAP0 = LAYOUT['heap_lo']
VEC = LAYOUT['vec_base']; GCVEC, PUTVEC, SETXVEC, GETXVEC = range(VEC, VEC + 4)   # ROM jump table: GC, append, dynamic put, dynamic get
# selectors: a micro-cycle with 'sel' picks its address, data and commit expressions ({value: expr}) by a flag of T1 / T2
SEL = {'scan': lambda r: 1 if r['T2'] in (r['T1'], 0) else 2 if r['T2'] < 0 else 0,   # found / free or end: stop; a link: follow
       'nst2': lambda r: int(r['T2'] >= 0), 'nzt2': lambda r: int(r['T2'] != 0),
       'sd': lambda r: int(s20(r['T2'] - r['T1']) < 0)}
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
    # objects. SCANI / SCAN probe one key per execution and execute again until the key is found, a free pair ends the keys or
    # L is 0 (the cursor is left on that key word); a negative word is a link, followed. SCANI's key is its immediate, SCAN's
    # the word in KEYCELL (the ROM's dynamic get / put store it there).
    'SCANI':  [dict(mem=R('SP-1'), t={'T3': 'MDR', 'T1': 'IMM'}), dict(mem=R('T3'), t={'T2': 'MDR'}),             # [o] -> [cursor]
               dict(sel='scan', mem=W('SP-1', {0: 'T3+2', 1: 'T3', 2: 'T2'}), commit={'PC': {1: 'PC+1'}})],
    'SCAN':   [dict(mem=R(str(KEYCELL)), t={'T1': 'MDR'}), dict(mem=R('SP-1'), t={'T3': 'MDR'}), dict(mem=R('T3'), t={'T2': 'MDR'}),
               dict(sel='scan', mem=W('SP-1', {0: 'T3+2', 1: 'T3', 2: 'T2'}), commit={'PC': {1: 'PC+1'}})],
    'LDF':    [dict(mem=R('SP-1'), t={'T2': 'MDR'}), dict(mem=R('T2+IMM'), t={'T1': 'MDR'}), dict(mem=W('SP-1', 'T1'), commit={'PC': 'PC+1'})],
    # [cursor, v] (cursor from SCANI imm): the key is there -> store v; else call the append routine with [cursor, v], its return
    # address (this PUTV) in the value word after the cursor
    'PUTV':   [dict(mem=R('SP-2'), t={'T3': 'MDR'}), dict(mem=R('T3'), t={'T2': 'MDR'}), dict(mem=R('SP-1'), t={'T1': 'MDR'}),
               dict(sel='nzt2', mem=W('T3+1', {1: 'T1', 0: 'PC'}), commit={'SP': {1: 'SP-2'}, 'PC': {1: 'PC+1', 0: str(PUTVEC)}})],
    # [] -> [o]: the chunk at HP (an offset from HEAP0; its write is last, since an instruction restarts after a trap). Nothing
    # is zeroed: whoever fills the chunk ends its keys (ENDK, the append routine). Heap full (HP >= GCLIM; both 0 at first):
    # GCSP = SP, RETCELL = PC (this NEW), and call the GC (it pops the extra word and returns here).
    'NEW':    [dict(mem=R(str(HP)), t={'T2': 'MDR'}), dict(mem=R(str(GCLIM)), t={'T1': 'MDR'}),
               dict(sel='sd', mem=W({1: 'SP', 0: str(GCSP)}, {1: f'T2+{HEAP0 - OBJTAG}', 0: 'SP'})),
               dict(sel='sd', mem=W({1: str(HP), 0: str(RETCELL)}, {1: 'T2+8', 0: 'PC'}), commit={'SP': 'SP+1', 'PC': {1: 'PC+1', 0: str(GCVEC)}})],
    # [o] -> [o]: a free pair at o + imm (the word a SCAN stops at, and the 0 read after it for a missing key)
    'ENDK':   [dict(mem=R('SP-1'), t={'T2': 'MDR'}), dict(mem=W('T2+IMM', '0')), dict(mem=W('T2+IMM+1', '0'), commit={'PC': 'PC+1'})],
    'SETF':   [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(mem=R('SP-2'), t={'T2': 'MDR'}), dict(mem=W('T2+IMM', 'T1'), commit={'SP': 'SP-1', 'PC': 'PC+1'})],
    'OVER':   [dict(mem=R('SP-2'), t={'T1': 'MDR'}), dict(mem=W('SP', 'T1'), commit={'SP': 'SP+1', 'PC': 'PC+1'})],    # [a, b] -> [a, b, a]
    # jump to imm if the word under the top is negative (an object, where an array is an address); the commit is JNZ's
    'JNEG':   [dict(mem=R('SP-2'), t={'T2': 'MDR'}), dict(sel='nst2', commit={'PC': {0: 'IMM', 1: 'PC+1'}})],
    # like PUTC, but the service may take several shapings: RESV is raised only when the whole value has been printed
    **{n: [dict(mem=R('SP-1'), t={'T1': 'MDR'}), dict(ext=n, commit={'SP': 'SP-1', 'PC': 'PC+1'})] for n in PRINTOPS},
}
def ext_a(name): return name == 'SHL13' or name in PRINTOPS      # unary EXT ops: the operand is T1 (binary ones: a = T2, b = T1)
assert set(UCODE) == set(OPN), set(OPN) - set(UCODE)

def ev(e, r):
    """Evaluate an expression name over the register dict r (all values signed 20-bit)."""
    if isinstance(e, dict): return ev(e[r['SEL']], r)
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
        self.lines = [None] * N            # [addr, val, dirty] or None
        self.vp = 0                        # victim pointer
        self.res, self.resv, self.ackwb = 0, 0, 0
        self.inline = None                 # incoming line from the last service
        self.out, self.optr = [], 0
        self.pst = 0                       # PRINT service state: 0 fresh; a string's next byte address; or chunks done + 1 for a number
        self.steps = self.cycles = self.shapings = self.traps = 0
        self.trapkinds = {}
        self.halted = False

    # ---- cache, exactly as the glyph string will behave: N lines in a ring, victim pointer `vp`
    # (None once an in-font allocation used the last line; CSS puts it back on line 0).
    def c_read(self, a):
        for ln in self.lines:
            if ln and ln[0] == a: return True, ln[1]
        return False, 0
    def c_write(self, a, v):
        for ln in self.lines:
            if ln and ln[0] == a: ln[1] = v; ln[2] = 1; return True
        if self.vp is None: return False
        vic = self.lines[self.vp]
        if vic and vic[2]: return False
        self.lines[self.vp] = [a, v, 1]
        self.vp = self.vp + 1 if self.vp + 1 < self.N else None
        return True

    def prologue(self):
        pass

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
            if 'sel' in cyc: r['SEL'] = SEL[cyc['sel']](r)
            if cyc.get('halt'): return self.trap(('HALT',))
            if cyc.get('ext') and not self.resv:
                return self.trap(('EXT', cyc['ext'], r['T1'] if ext_a(cyc['ext']) else r.get('T2', 0), r.get('T1', 0)))
            if cyc.get('putc') and not self.resv:
                return self.trap(('PUTC', r['T1']))
            m = cyc.get('mem')
            if m and m[0] == 'R':
                a = ev(m[1], r) & AMASK      # 15-bit address registers (an object value untags itself)
                hit, v = self.c_read(a)
                if not hit: return self.trap(('MISS', a))
                r['MDR'] = v
            elif m and m[0] == 'W':
                a = ev(m[1], r) & AMASK; v = s20(ev(m[2], r))
                assert cyc.get('wrap') or abs(ev(m[2], r)) < (1 << 19), (name, ev(m[2], r))
                if not self.c_write(a, v): return self.trap(('WFAIL',))
            for t, e in cyc.get('t', {}).items(): r[t] = s20(ev(e, r))
            if last:
                new = {k: s20(ev(e, r)) for k, e in cyc.get('commit', {}).items() if not isinstance(e, dict) or r['SEL'] in e}   # absent: unchanged
                self.pc = new.get('PC', self.pc) & AMASK; self.sp = new.get('SP', self.sp) & AMASK; self.fp = new.get('FP', self.fp) & AMASK
                if cyc.get('ext') or cyc.get('putc'): self.resv = 0
                self.steps += 1; ir = None; r = None
            else:
                mu += 1
        return None

    def trap(self, t):
        k = 'PRINT' if t[0] == 'EXT' and t[1] in PRINTOPS else t[0]      # counted apart from the arithmetic EXT ops
        self.traps += 1; self.trapkinds[k] = self.trapkinds.get(k, 0) + 1
        return t

    def service(self, t):
        """What the CSS side does between shapings (at most one RAM write, at most one RAM read)."""
        if self.vp is None: self.vp = 0
        if t is None: return
        k = t[0]
        if k in ('MISS', 'WFAIL'):
            vic = self.lines[self.vp]
            if vic and vic[2]:                       # write the victim back first
                self.ram[vic[0]] = vic[1]; vic[2] = 0
                if k == 'WFAIL': return
            if k == 'MISS':
                self.lines[self.vp] = [t[1], self.ram.get(t[1], 0), 0]      # below RAM (a property of a non-object): reads 0
                self.vp = (self.vp + 1) % self.N
        elif k == 'EXT' and t[1] in PRINTOPS:
            self.print_service(t[1], t[3])
        elif k == 'EXT':
            self.res = s20(EXTF[t[1]](t[2], t[3])); self.resv = 1
            assert abs(EXTF[t[1]](t[2], t[3])) < (1 << 19), t
        elif k == 'PUTC':
            self.out.append(t[1]); self.resv = 1
        elif k == 'HALT':
            self.halted = True

    def putc(self, c):
        if c == 10: self.optr = (self.optr // OUT_COLS + 1) * OUT_COLS % (OUT_COLS * OUT_ROWS)
        else: self.optr = (self.optr + 1) % (OUT_COLS * OUT_ROWS)
        self.out.append(c)

    def print_service(self, op, v):
        """One shaping's worth of a PRINT: up to PRINT_CHUNK console cells (consecutive cells are in distinct banks), exactly
        as the CSS service does it (gen_fvm4.py). A string chunk also ends at its block (one block read per service), at a
        NUL (done) or at a newline (the newline is taken, the chunk ends). RESV is raised when the value and its separator
        are out; until then the CPU re-traps with the same value and self.pst carries the position."""
        sep = 10 if op.endswith('LN') else 32 if op.endswith('SP') else 0
        isb = op in ('PRINTB', 'PRINTBSP', 'PRINTBLN')
        p = v + STRTAG
        if STR_LO <= p < STR_HI:                                 # a string (STR_LO: the lib's DONE marker, prints nothing)
            q = self.pst or p
            e, term = 0, 0
            if q != STR_LO:
                while (q + e) % 4 != 0 or e == 0:
                    b = self.ram.get(q + e, 0) if q + e >= ROM else 0
                    if b == 0 or b == 10: term = b; break
                    e += 1
                else: term = None                                 # block exhausted, no terminator seen
            else: term = 0
            for i in range(e): self.putc(self.ram.get(q + i, 0))
            if term == 10: self.putc(10); self.pst = q + e + 1; return
            if term is None: self.pst = q + e; return
            text = ''                                             # NUL: the value is out; the separator follows
        else:
            text = ('true' if v else 'false') if isb and v in (0, 1) else str(v)
            text = text[PRINT_CHUNK * (self.pst - 1):] if self.pst else text
        chunk = text + (' ' if sep == 32 else '')
        if len(chunk) > PRINT_CHUNK:
            for ch in chunk[:PRINT_CHUNK]: self.putc(ord(ch))
            self.pst = (self.pst or 1) + 1; return
        for ch in chunk: self.putc(ord(ch))
        if sep == 10: self.putc(10)
        self.pst = 0; self.resv = 1

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
