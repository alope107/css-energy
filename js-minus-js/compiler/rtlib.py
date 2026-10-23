#!/usr/bin/env python3
"""rtlib.py lib.json — the runtime in ROM: compiler/lib_src.js compiled by cc_ref in rom mode (raw memory, the intrinsics,
tables large enough), after its __NAME__ constants are filled in. lib.json: the ROM's words, every function's address
(entries: the compiler calls the methods and mkarrN, the machine's traps call cc_ref.TRAPS' routines), the memory map."""
import sys, os, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, '..', 'machine')]
import cc_ref as R, uarch as U
L = R.LAYOUT
H = L['heap_size']
DB, INIT, SP0 = L['data_base'], L['init'], L['sp0']
CELL = U.CELL
MAP, MAPN = R.MAP, R.MAPN                        # the collector's map of block starts (a bit per 8 heap words, 16 to a word)
POWT = MAP + MAPN                                # its powers of two (the collector fills them in)
assert H % 8 == 0 and U.HEAP0 % 8 == 0 and U.HEAP0 + 2 * H <= L['rom_size'] + L['ram_size'] - L['cols'] * L['rows']
assert MAP >= L['rt_base'] + len(L['rt_cells']) and POWT + 16 <= SP0

def consts():
    """lib_src.js's __NAME__ constants"""
    k = dict(DB=DB, SDATA=R.SDATA, STR_LO=U.STR_LO, HEAP0=U.HEAP0, H=H, HEAP_HI=U.HEAP_HI, STRTAG=R.STRTAG, OBJTAG=U.OBJTAG, ARRTAG=U.ARRTAG,
             INIT=INIT, SP0=SP0, TRAPOFF=R.TRAPOFF, STREND=L['strend'], TRUEV=R.TRUEV, FALSEV=R.FALSEV, STRP0=R.STRP0, MAP=MAP, MAPH=MAPN // 2, POWT=POWT)
    k.update(CELL); k['NETPARTS'] = L['net_parts']; k['NBUF'] = 2 * L['net_parts']
    k.update({f'K_{n.upper()}': i for i, n in enumerate(R.KINDS)}); k.update({f'A_{n.upper()}': i for i, n in enumerate(R.ALLOCK)})
    k.update({n: v for n, v in zip(R.SPECIALS, range(R.SPV0, R.SPV0 + 8))}); k.update(SPV0=R.SPV0, TRAPDEF=R.TRAPDEF)
    k.update({f'S_{n}': R.BSTRV(i) for n, i in (('ZERO', R.BS_ZERO), ('EMPTY', R.BS_EMPTY))}); k['BSTRV0'] = R.BSTRV(0)
    k.update({f'OP_{n}': i for i, n in enumerate(R.OPN)})
    return k

def build(out):
    k = consts()
    src = re.sub(r'__([A-Z0-9_]+)__', lambda m: str(k[m.group(1)]), open(os.path.join(HERE, 'lib_src.js')).read())
    c = R.Compiler(DB, 0, None, rom=True)
    words, data = c.compile(src)
    if c.err: raise SystemExit(f'lib_src.js: compile error {c.err} (instruction {c.cp})')
    names = re.findall(r'^function (\w+)\(', src, re.M)
    entries = {}
    for n in names:
        h = R.h1h2(n); f = next(f for f in c.fn[:c.nfn] if (f[0], f[1]) == h)
        entries[n] = c.lab[f[2]]
    rom = [words.get(a, 0) for a in range(max(words) + 1)]
    assert len(rom) % 2 == 0
    entries['pstub'] = len(rom)                         # PRINT's trap: TENTER ptrap (cc_ref.TRAPS)
    rom += [R.OP['TENTER'] * 8192 + entries['ptrap'], 0]
    missing = [t for t in R.TRAPS.values() if t not in entries]
    assert not missing, f'trap routines missing from lib_src.js: {missing}'
    assert len(rom) <= L['rom_size'], f'the ROM holds {L["rom_size"]} words, the library needs {len(rom)}'
    lib = dict(rom=rom, entries=entries, romSize=L['rom_size'], dataBase=DB, codeBase=L['code_base'], init=INIT)
    json.dump(lib, open(out, 'w'))
    print(f'{out}: {len(rom)} words, {len(entries)} functions')

if __name__ == '__main__':
    build(sys.argv[1])
