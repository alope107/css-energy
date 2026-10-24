"""uarch.py — the register machine's constants for the machine's files: the instructions (compiler/cc_ref.py's OPN, in class
order), the memory map's named cells, the value representation. The instructions' semantics are cc_ref.run() (the reference)
and machine/csssim.py (the CSS CPU pass by pass); machine/gen_css.py implements them in CSS."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'compiler'))
import cc_ref as R

LAYOUT = R.LAYOUT
ROM = LAYOUT['rom_size']                    # RAM starts here
AMASK = 32767                               # 15-bit addresses
MASK = (1 << 20) - 1
s20 = R.s20
OPN, OP = R.OPN, R.OP
STRTAG = R.STRTAG                           # a string value is its address - STRTAG
STR_LO = LAYOUT['data_base'] + 256; STR_HI = STR_LO + LAYOUT['str_size']   # the string area (cc_ref STR0 .. SEND); STR_LO itself is the DONE marker
OUT_COLS, OUT_ROWS = LAYOUT['cols'], LAYOUT['rows']
OUT_BASE = LAYOUT['rom_size'] + LAYOUT['ram_size'] - LAYOUT['console_words']   # console: the last words of RAM (the grid, the REPL's marks)
OBJTAG = LAYOUT['objtag']
RT = LAYOUT['rt_base']; CELL = {n: RT + i for i, n in enumerate(LAYOUT['rt_cells'])}; HP, GCLIM, GCSP, KEYCELL, RETCELL = (CELL[n] for n in ('HP', 'GCLIM', 'GCSP', 'KEYCELL', 'RETCELL'))
HEAP0 = LAYOUT['heap_lo']
ARRTAG = LAYOUT['arrtag']
HEAP_HI = HEAP0 + 2 * LAYOUT['heap_size']
STRP_HI = HEAP_HI                           # a value v is a string iff STR_LO <= v + STRTAG < STRP_HI (a literal or a heap string)
