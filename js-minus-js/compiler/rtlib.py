#!/usr/bin/env python3
"""rtlib.py lib.json — the runtime in ROM: compiles compiler/lib_src.js with jsc (libbuild.js, under Node; this script writes
its constants), then appends hand-written routines and the jump table at vec_base that the new instructions and the
compiler call (machine/uarch.py documents the instructions, layout.json the representations).

lib_src.js holds the collector, allocation, strings, arrays and the dynamic paths' logic. Here, the routines that must
work on the machine directly:

  GC      (vec gc)      NEW found the heap full: call the collector (lib_src.js gc) with the stack up to GCSP as roots, then
                        execute the NEW again.
  APPEND  (vec append)  PUTV found no key: claim the free pair at the cursor, or (the chunk is full) link a new chunk there.
  SETX    (vec setx)    STOREX's slow path: x[k] = v for an object (here), anything else (lib_src.js setx: an array grows).
  GETX    (vec getx)    IDXA's slow path: x[k] of an object (here), anything else (lib_src.js getx: a string's character).
  DYN     (vec dyn)     DYN's slow path (a string operand): lib_src.js dynop with the instruction's immediate.
  PRINT   (vec print)   PRINT of an array or object: lib_src.js pval prints it (Node's one-line form) and the separator.
  mkarr                 called by compiled code: [e1 .. en, n] -> [an array of those n elements]
  pnK                   called by compiled code: [p1 .. pk, sep] -> [0], printing a + chain's pieces and sep (console.log)

Routines keep their state in fixed cells (layout.json rt_cells), not in frames: GC and the append path may run inside one
another. The cells S_V and S_K may hold values while something allocates: they are roots."""
import sys, os, json, subprocess, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, '..', 'machine')]
import uarch as U
sys.path[:0] = [HERE]; import cc_ref as R
from uarch import OP, HP, GCLIM, GCSP, KEYCELL, RETCELL, HEAP0, OBJTAG, KBIAS, STRTAG, CELL

L = U.LAYOUT
H = L['heap_size']
DB, INIT, SP0, VEC = L['data_base'], L['init'], L['sp0'], L['vec_base']
assert H % 8 == 0 and HEAP0 % 8 == 0 and HEAP0 + 2 * H <= L['rom_size'] + L['ram_size'] - L['cols'] * L['rows']
TAG0 = HEAP0 - OBJTAG                                 # the object value of the heap's first word
assert TAG0 % 8 == 0 and TAG0 < 0
S_RET, S_V, S_K, S_DRET, S_XRET, S_A, S_N, S_T = (CELL[n] for n in 'S_RET S_V S_K S_DRET S_XRET S_A S_N S_T'.split())
assert max(CELL.values()) < SP0
OBJMIN = 393216                                       # x < -OBJMIN: an object (objects lie below it, strings above)
assert -OBJMIN > TAG0 + 2 * H and -OBJMIN < U.STR_LO - STRTAG

def consts():
    """lib_src.js's __NAME__ constants"""
    k = dict(DB=DB, SDATA=256, STR_LO=U.STR_LO, HEAP0=HEAP0, H=H, HEAP_HI=U.HEAP_HI, STRTAG=STRTAG, OBJTAG=OBJTAG, ARRTAG=U.ARRTAG,
             INIT=INIT, SP0=SP0, DATA_BASE=DB, CODE_BASE=L['code_base'], STREND=L['strend'], TRUEV=R.TRUEV, FALSEV=R.FALSEV)
    k.update(CELL)
    k.update({f'OP_{n}': i for n, i in OP.items()}); k.update({f'W_{n}': i * 8192 for n, i in OP.items()})
    return k

class Asm:
    def __init__(self, base, fns): self.base, self.code, self.labels, self.fix, self.fns = base, [], {}, [], fns
    def here(self): return self.base + len(self.code)
    def lab(self, n): assert n not in self.labels, n; self.labels[n] = self.here()
    def __call__(self, op, imm=0):
        if isinstance(imm, str):
            if imm.startswith('js.'): imm = self.fns[imm[3:]]
            else: self.fix.append((len(self.code), imm)); imm = 0
        assert 0 <= imm < 8192, (op, imm)
        self.code.append(OP[op] * 8192 + imm)
    def k(self, v):
        """push the constant v (13 bits by PUSHI; more needs SHL13)"""
        if 0 <= v < 8192: return self('PUSHI', v)
        if v < 0: self.k(-v); return self('NEG')
        self('PUSHI', v // 8192); self('SHL13')
        if v % 8192: self('PUSHI', v % 8192); self('ADD')
    def words(self):
        for i, n in self.fix: self.code[i] += self.labels[n]
        return self.code

def routines(a):
    # ---------------- GC. Entry: SP = GCSP + 1 (NEW's extra word), RETCELL = the NEW to execute again
    a.lab('gc'); a('POP'); a('LOADG', GCSP); a('PUSHI', 8); a('CALL', 'js.gc'); a('POP'); a('LOADG', RETCELL); a('JMPI')

    # ---------------- APPEND, from PUTV: [c, v]; the word after c holds the PUTV's address (its immediate is the key)
    a.lab('append'); a('OVER'); a('LDF', 1); a('DUP'); a('PUSHI', 1); a('ADD'); a('STOREG', S_RET)
    a('LOADI'); a.k(OP['PUTV'] * 8192); a('SUB'); a('STOREG', S_K)
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

    def isobj():                                      # [x, k] -> [x, k, x < -OBJMIN] (x + OBJMIN would wrap for an array)
        a('OVER'); a.k(-OBJMIN); a('LT')

    # ---------------- SETX: [x, k, v, ret]
    a.lab('setx'); a('STOREG', S_RET); a('STOREG', S_V); isobj(); a('JNZ', 'sx_obj')
    a('LOADG', S_V); a('CALL', 'js.setx'); a('POP'); a('PUSHI', 0); a('STOREG', S_V); a('LOADG', S_RET); a('JMPI')
    def canon():                                      # [x, k] -> [x, k']: a heap string key as the program's or the object's (okey)
        a('OVER'); a('OVER'); a('CALL', 'js.okey'); a('STOREG', S_T); a('POP'); a('LOADG', S_T)
    a.lab('sx_obj'); canon(); a('LOADG', DB); a('ADD'); a('DUP'); a('STOREG', KEYCELL); a('STOREG', S_K)              # key + KBIAS
    a('SCAN'); a('DUP'); a('LDF', 0); a('LOADG', S_K); a('EQ'); a('JZ', 'sx_add')
    a('LOADG', S_V); a('SETF', 1); a('POP'); a('PUSHI', 0); a('STOREG', S_V); a('LOADG', S_RET); a('JMPI')
    a.lab('sx_add'); a('LOADG', S_V); a('PUSHI', 0); a('STOREG', S_V); a('JMP', 'add')

    # ---------------- GETX: [x, k, ret]
    a.lab('getx'); a('STOREG', S_RET); isobj(); a('JNZ', 'gx_obj')
    a('CALL', 'js.getx'); a('LOADG', S_RET); a('JMPI')
    a.lab('gx_obj'); canon(); a('LOADG', DB); a('ADD'); a('STOREG', KEYCELL); a('SCAN'); a('LDF', 1); a('LOADG', S_RET); a('JMPI')

    # ---------------- DYN: [a, b, ret] -> dynop(a, b, the DYN's immediate)
    a.lab('dyn'); a('STOREG', S_DRET); a('LOADG', S_DRET); a('PUSHI', 1); a('SUB'); a('LOADI'); a.k(8192); a('MOD')
    a('CALL', 'js.dynop'); a('LOADG', S_DRET); a('JMPI')

    # ---------------- PRINT of an array or object: [v, ret] -> pval(v, ret, the PRINT's opcode), which prints it and returns ret
    a.lab('print'); a('DUP'); a('PUSHI', 1); a('SUB'); a('LOADI'); a.k(8192); a('DIV'); a('CALL', 'js.pval'); a('JMPI')

    # ---------------- b2s: [b, ret] -> ["true" / "false"] (the string area's first strings: cc_ref SEED)
    a.lab('b2s'); a('STOREG', S_T); a('JZ', 'b2s_f'); a('PUSHS', R.TRUEV + STRTAG); a('LOADG', S_T); a('JMPI')
    a.lab('b2s_f'); a('PUSHS', R.FALSEV + STRTAG); a('LOADG', S_T); a('JMPI')

    # ---------------- pnK: [p1 .. pk, sep, ret] -> [0]: print the pieces of a + chain (PRINT, no separator), then sep
    for k in range(2, 9):
        a.lab(f'pn{k}'); a('ENTER', 0)
        for i in range(k): a('LOADL', (-2 - k + i) % 8192); a('PRINT')
        a('LOADL', (-2) % 8192); a('PUTC'); a('PUSHI', 0); a('RET', k + 1)

    # ---------------- mkarrN (N <= 8): [e1 .. eN, ret] -> [an array of them]. Locals: 1 the array, 2 its elements' address. The
    # block is taken from HP here if it fits (lib_src.js halloc otherwise, through newarr, which may collect: the elements are
    # parameters, so roots)
    for N in range(9):
        cap = max(N, 4); nw = cap + 4 + (8 - (cap + 4) % 8) % 8
        a.lab(f'mkarr{N}'); a('ENTER', 2)
        a('LOADG', HP); a('PUSHI', nw); a('ADD'); a('LOADG', GCLIM); a.k(H + 1); a('ADD'); a('LT'); a('JZ', f'mk{N}_slow')
        a('LOADG', HP); a.k(HEAP0); a('ADD'); a('LOADG', HP); a('PUSHI', nw); a('ADD'); a('STOREG', HP)      # [b]
        a('DUP'); a.k(-3 - nw); a('STOREI'); a('DUP'); a('PUSHI', 1); a('ADD'); a('PUSHI', cap); a('STOREI')
        a('DUP'); a('PUSHI', 2); a('ADD'); a('PUSHI', N); a('STOREI'); a('DUP'); a('PUSHI', 3); a('ADD'); a('OVER'); a('PUSHI', 4); a('ADD'); a('STOREI')
        a('PUSHI', 3); a('ADD'); a.k(U.ARRTAG); a('ADD'); a('JMP', f'mk{N}_fill')
        a.lab(f'mk{N}_slow'); a('PUSHI', cap); a('PUSHI', N); a('CALL', 'js.newarr')
        a.lab(f'mk{N}_fill'); a('DUP'); a('STOREL', 1); a('LOADI'); a('STOREL', 2)
        for i in range(N):
            a('LOADL', 2)
            if i: a('PUSHI', i); a('ADD')
            a('LOADL', (-1 - N + i) % 8192); a('STOREI')
        a('LOADL', 1); a('RET', N)

    # ---------------- mkarr: [e1 .. en, n, ret] -> [array]; the elements stay on the stack (roots) while newarr allocates
    a.lab('mkarr'); a('STOREG', S_XRET); a('DUP'); a('DUP'); a('CALL', 'js.newarr'); a('STOREG', S_A); a('STOREG', S_N)
    a.lab('mk_loop'); a('LOADG', S_N); a('JZ', 'mk_done')
    a('LOADG', S_N); a('PUSHI', 1); a('SUB'); a('STOREG', S_N); a('STOREG', S_T)
    a('LOADG', S_A); a('LOADI'); a('LOADG', S_N); a('ADD'); a('LOADG', S_T); a('STOREI'); a('JMP', 'mk_loop')
    a.lab('mk_done'); a('LOADG', S_A); a('PUSHI', 0); a('STOREG', S_A); a('LOADG', S_XRET); a('JMPI')

def build(out):
    assert STRTAG == KBIAS, 'the data_base cell (STRTAG) doubles as the key bias'
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f: json.dump(consts(), f); cpath = f.name
    try: subprocess.run(['node', os.path.join(HERE, 'libbuild.js'), out, cpath], check=True)
    finally: os.unlink(cpath)
    lib = json.load(open(out))
    rom = list(lib['rom'])
    a = Asm(len(rom), lib['fns']); routines(a)
    code = a.words()
    assert len(rom) + len(code) <= VEC, f'ROM overflow: {len(rom)} + {len(code)} words'
    rom += code + [None] * (VEC - len(rom) - len(code))         # never executed: no rules in the ROM fetch table
    rom += [OP['JMP'] * 8192 + a.labels[n] for n in L['vectors']]
    assert len(rom) <= L['rom_size']
    entries = {n: lib['fns'][n] for n in lib['fns']}
    entries.update({n: a.labels[n] for n in ['mkarr', 'b2s'] + [f'pn{k}' for k in range(2, 9)] + [f'mkarr{k}' for k in range(9)]})
    lib = dict(lib, rom=rom, rt=dict(words=len(code), at=a.base, labels=a.labels), getx=U.GETXVEC, setx=U.SETXVEC, entries=entries)
    json.dump(lib, open(out, 'w'))
    print('runtime: lib', a.base, 'words + ROM routines', len(code), '; ROM', len(rom), 'words with the jump table')

if __name__ == '__main__':
    build(sys.argv[1])
