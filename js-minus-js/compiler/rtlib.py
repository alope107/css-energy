#!/usr/bin/env python3
"""rtlib.py lib.json — the object runtime in ROM: hand-written routines after the jsc-compiled lib (libbuild.js), and the jump
table at vec_base that the object instructions and the compiler call (machine/uarch.py documents the instructions).

Objects are 8-word chunks [k0 v0 k1 v1 k2 v2 L pad] in a heap of two semi-spaces; a key is stored as its value + KBIAS (a
string key is its address), 0 marks a free pair, L links to an overflow chunk. The routines:

  GC      (vec + 0)  NEW found the heap full. A copying collector (Cheney): the roots are the globals, the routines' scratch
                     cells and the stack up to GCSP; a root may point into a chunk (a SCANI cursor), a heap word only at one.
                     The first call only sets up the heap.
  APPEND  (vec + 1)  PUTV found no key: claim the free pair at the cursor, or (the chunk is full) link a new chunk there.
  SETX    (vec + 2)  CALL from compiled code: x[k] = v for x an array (an address) or an object.
  GETX    (vec + 3)  CALL from compiled code: x[k].

Routines keep their state in fixed cells (rt_base..), not in frames: GC and the append path may run inside one another.
"""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, '..', 'machine')]
import uarch as U
from uarch import OP, HP, GCLIM, GCSP, KEYCELL, RETCELL, HEAP0, OBJTAG, KBIAS, STRTAG

L = U.LAYOUT
H = L['heap_size']; BOFF = H                         # space B starts BOFF words after space A
DB, INIT, SP0, VEC = L['data_base'], L['init'], L['sp0'], L['vec_base']
assert H % 8 == 0 and HEAP0 % 8 == 0 and HEAP0 + 2 * BOFF <= L['rom_size'] + L['ram_size'] - L['cols'] * L['rows']
TAG0 = HEAP0 - OBJTAG                                 # the object value of the heap's first word
assert TAG0 % 8 == 0 and TAG0 < 0
FWD = -1                                              # k0 of a chunk the GC has copied (k1 holds the copy)
# scratch cells after the instructions' own (HP GCLIM GCSP KEYCELL RETCELL)
S_RET, S_V, S_K = RETCELL + 1, RETCELL + 2, RETCELL + 3         # dynamic get / put / append: return, value, key
ROOTS = (S_V, S_V + 1)                                # scratch cells that may hold an object while the GC runs
G_RET, G_FLO, G_FHI, G_FREE, G_TOFF, G_END, F_RET, F_OFF, F_NEW, K_PUTV = range(RETCELL + 4, RETCELL + 14)
assert K_PUTV < L['sp0']

class Asm:
    def __init__(self, base): self.base, self.code, self.labels, self.fix = base, [], {}, []
    def here(self): return self.base + len(self.code)
    def lab(self, n): assert n not in self.labels, n; self.labels[n] = self.here()
    def __call__(self, op, imm=0):
        if isinstance(imm, str): self.fix.append((len(self.code), imm)); imm = 0
        assert 0 <= imm < 8192, (op, imm)
        self.code.append(OP[op] * 8192 + imm)
    def k(self, v):
        """push the constant v (13 bits by PUSHI; more needs SHL13, an EXT trap: fine where it runs once)"""
        if 0 <= v < 8192: return self('PUSHI', v)
        if v < 0: self.k(-v); return self('NEG')
        self('PUSHI', v // 8192); self('SHL13')
        if v % 8192: self('PUSHI', v % 8192); self('ADD')
    def words(self):
        for i, n in self.fix: self.code[i] += self.labels[n]
        return self.code

def routines(a):
    # ---------------- GC (vec + 0). Entry: SP = GCSP + 1 (NEW's extra word), RETCELL = the NEW to execute again.
    a.lab('gc'); a('POP')
    a('LOADG', GCLIM); a('JNZ', 'gc_run')
    a('PUSHI', H - 7); a('STOREG', GCLIM)             # first call: space A (HP is 0), and a constant for APPEND
    a.k(OP['PUTV'] * 8192); a('STOREG', K_PUTV)
    a('LOADG', RETCELL); a('JMPI')
    a.lab('gc_run'); a('LOADG', RETCELL); a('STOREG', G_RET)
    a('LOADG', GCLIM); a('PUSHI', H - 7); a('EQ'); a('JZ', 'gc_fromB')
    a('PUSHI', BOFF); a('STOREG', G_TOFF); a.k(TAG0); a('JMP', 'gc_setb')        # from A, to B
    a.lab('gc_fromB'); a('PUSHI', 0); a('STOREG', G_TOFF); a.k(TAG0 + BOFF)     # from B, to A
    a.lab('gc_setb'); a('DUP'); a('STOREG', G_FLO); a('PUSHI', H); a('ADD'); a('STOREG', G_FHI)
    a.k(TAG0); a('LOADG', G_TOFF); a('ADD'); a('STOREG', G_FREE)
    # roots: [p, end) ranges; each word below FHI is a candidate (every object is in from-space), fwdi checks the rest
    def roots(lo_code, end_code, tag):
        end_code(); a('STOREG', G_END); lo_code()
        a.lab(f'rs_{tag}'); a('DUP'); a('LOADG', G_END); a('LT'); a('JZ', f'rs_{tag}_done')
        a('DUP'); a('LDF', 0); a('DUP'); a('LOADG', G_FHI); a('LT'); a('JZ', f'rs_{tag}_skip')
        a('CALL', 'fwdi'); a('SETF', 0); a('JMP', f'rs_{tag}_inc')
        a.lab(f'rs_{tag}_skip'); a('POP')
        a.lab(f'rs_{tag}_inc'); a('PUSHI', 1); a('ADD'); a('JMP', f'rs_{tag}')
        a.lab(f'rs_{tag}_done'); a('POP')
    roots(lambda: a('PUSHI', DB + 1), lambda: (a('LOADG', INIT - 1), a('PUSHI', DB), a('ADD')), 'g')     # globals and arrays
    roots(lambda: a('PUSHI', ROOTS[0]), lambda: a('PUSHI', ROOTS[1] + 1), 'r')                         # the routines' scratch
    roots(lambda: a('PUSHI', SP0), lambda: a('LOADG', GCSP), 's')                                      # the stack
    # Cheney scan: each copy's values up to its first free pair, and its link if all three pairs are used (the words after the
    # free pair were never written); a heap word points only at a chunk's start
    a.k(TAG0); a('LOADG', G_TOFF); a('ADD')
    a.lab('cs'); a('DUP'); a('LOADG', G_FREE); a('LT'); a('JZ', 'cs_done')
    for i in (1, 3, 5, 6):
        if i < 6: a('DUP'); a('LDF', i - 1); a('JZ', 'cs_end')
        a('DUP'); a('LDF', i); a('DUP'); a('LOADG', G_FHI); a('LT'); a('JZ', f'cs_skip{i}')
        a('CALL', 'fwdb'); a('SETF', i); a('JMP', f'cs_next{i}')
        a.lab(f'cs_skip{i}'); a('POP'); a.lab(f'cs_next{i}')
    a.lab('cs_end'); a('PUSHI', 8); a('ADD'); a('JMP', 'cs')
    a.lab('cs_done'); a('POP')
    # the new space: HP after the copies, GCLIM its end - 7; full even now: out of memory
    a('LOADG', G_FREE); a.k(-TAG0); a('ADD'); a('DUP'); a('STOREG', HP)
    a('LOADG', G_TOFF); a('PUSHI', H - 7); a('ADD'); a('DUP'); a('STOREG', GCLIM); a('LT'); a('JZ', 'oom')
    a('LOADG', G_RET); a('JMPI')
    a.lab('oom')
    for ch in '\nout of memory\n': a('PUSHI', ord(ch)); a('PUTC')
    a('HALT')
    # fwdi / fwdb: [w, ret] -> [w'], w a word below FHI: a from-space object (fwdi: maybe a pointer into its chunk) is copied to
    # FREE unless it was already, and w' is its copy; anything else is returned as it is
    a.lab('fwdi'); a('STOREG', F_RET)
    a('DUP'); a('LOADG', G_FLO); a('LT'); a('JNZ', 'f_ret')
    a('DUP'); a('LOADG', G_FLO); a('SUB'); a('PUSHI', 8); a('MOD'); a('STOREG', F_OFF); a('JMP', 'f_go')
    a.lab('fwdb'); a('STOREG', F_RET); a('PUSHI', 0); a('STOREG', F_OFF)
    a('DUP'); a('LOADG', G_FLO); a('LT'); a('JNZ', 'f_ret')
    a.lab('f_go'); a('LOADG', F_OFF); a('SUB')                                     # [base]
    a('DUP'); a('LDF', 0); a('PUSHI', 1); a('ADD'); a('JZ', 'f_moved')              # k0 == FWD
    a('LOADG', G_FREE)                                                              # [base, new]
    for i in range(8): a('OVER'); a('LDF', i); a('SETF', i)
    a('STOREG', F_NEW); a('PUSHI', 1); a('NEG'); a('SETF', 0); a('LOADG', F_NEW); a('SETF', 1); a('POP')
    a('LOADG', G_FREE); a('PUSHI', 8); a('ADD'); a('STOREG', G_FREE)
    a('LOADG', F_NEW); a('LOADG', F_OFF); a('ADD'); a('LOADG', F_RET); a('JMPI')
    a.lab('f_moved'); a('LDF', 1); a('LOADG', F_OFF); a('ADD')
    a.lab('f_ret'); a('LOADG', F_RET); a('JMPI')

    # ---------------- APPEND (vec + 1), from PUTV: [c, v]; the word after c holds the PUTV's address (its immediate is the key)
    a.lab('append'); a('OVER'); a('LDF', 1); a('DUP'); a('PUSHI', 1); a('ADD'); a('STOREG', S_RET)
    a('LOADI'); a('LOADG', K_PUTV); a('SUB'); a('STOREG', S_K)
    # common: [c, v], S_K the key, S_RET where to return. c is a free pair, or the link word of a full chunk (offset 6)
    # (chunks are 8-aligned from TAG0, a multiple of 8, and c is negative: offset 6 has c % 8 == -2 under truncating MOD)
    a.lab('add'); a('OVER'); a('PUSHI', 8); a('MOD'); a('PUSHI', 2); a('ADD'); a('JZ', 'add_link')
    def claim():                                      # [p, v] -> [p]: the pair at p, and the keys end after it
        a('SETF', 1); a('LOADG', S_K); a('SETF', 0); a('PUSHI', 0); a('SETF', 2); a('PUSHI', 0); a('SETF', 3)
    claim(); a('POP'); a('LOADG', S_RET); a('JMPI')
    a.lab('add_link'); a('STOREG', S_V)                                             # [c]; v is a root while NEW may collect
    a('DUP'); a('PUSHI', 0); a('SETF', 1); a('POP')                                 # the pad (APPEND's return address)
    a('NEW'); a('LOADG', S_V); claim()                                              # [c, n]: the new chunk's first pair
    a('STOREI'); a('PUSHI', 0); a('STOREG', S_V); a('LOADG', S_RET); a('JMPI')     # L = n

    # ---------------- SETX (vec + 2): [x, k, v, ret]
    a.lab('setx'); a('STOREG', S_RET); a('STOREG', S_V); a('JNEG', 'sx_obj')
    a('ADD'); a('LOADG', S_V); a('STOREI'); a('PUSHI', 0); a('STOREG', S_V); a('LOADG', S_RET); a('JMPI')     # an array
    a.lab('sx_obj'); a('LOADG', DB); a('ADD'); a('DUP'); a('STOREG', KEYCELL); a('STOREG', S_K)              # key + KBIAS
    a('SCAN'); a('DUP'); a('LDF', 0); a('LOADG', S_K); a('EQ'); a('JZ', 'sx_add')
    a('LOADG', S_V); a('SETF', 1); a('POP'); a('PUSHI', 0); a('STOREG', S_V); a('LOADG', S_RET); a('JMPI')
    a.lab('sx_add'); a('LOADG', S_V); a('PUSHI', 0); a('STOREG', S_V); a('JMP', 'add')

    # ---------------- GETX (vec + 3): [x, k, ret]
    a.lab('getx'); a('STOREG', S_RET); a('JNEG', 'gx_obj')
    a('ADD'); a('LOADI'); a('LOADG', S_RET); a('JMPI')                                                        # an array
    a.lab('gx_obj'); a('LOADG', DB); a('ADD'); a('STOREG', KEYCELL); a('SCAN'); a('LDF', 1); a('LOADG', S_RET); a('JMPI')

def build(lib):
    rom = list(lib['rom'])
    assert STRTAG == KBIAS, 'the data_base cell (STRTAG) doubles as the key bias'
    a = Asm(len(rom)); routines(a)
    code = a.words()
    assert len(rom) + len(code) <= VEC, f'ROM overflow: {len(rom)} + {len(code)} words'
    rom += code + [None] * (VEC - len(rom) - len(code))         # never executed: no rules in the font's ROM lookup
    rom += [OP['JMP'] * 8192 + a.labels[n] for n in ('gc', 'append', 'setx', 'getx')]
    assert len(rom) == VEC + 4 <= L['rom_size']
    lib = dict(lib, rom=rom, rt=dict(words=len(code), at=a.base, labels=a.labels), getx=VEC + 3, setx=VEC + 2)
    return lib

if __name__ == '__main__':
    lib = json.load(open(sys.argv[1]))
    lib = build(lib)
    json.dump(lib, open(sys.argv[2] if len(sys.argv) > 2 else sys.argv[1], 'w'))
    print('object runtime', lib['rt']['words'], 'ROM words at', lib['rt']['at'], '; ROM', len(lib['rom']), 'words with the jump table')
