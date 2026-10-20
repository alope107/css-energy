"""uarch.py — the bytecode ISA's constants: opcodes, the memory map's named cells, the object representation.
The instructions' semantics are cc_ref.run() (the reference) and machine/csssim.py (the CSS CPU pass by pass);
machine/gen_css.py implements them in CSS. (Until 2026-10-19 this file also held the font CPU's microcode model;
README "History" names the commit.)"""
import json, os

LAYOUT = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'compiler', 'layout.json')))
ROM = LAYOUT['rom_size']                    # RAM starts here
AMASK = 32767                               # 15-bit addresses
MASK = (1 << 20) - 1
def s20(v): v &= MASK; return v - (1 << 20) if v >> 19 else v

# PRINT family: pop a value and print it (a number in decimal, a tagged string pointer's bytes, or with the B flag true/false
# for 0/1); SP = a space after, LN = a newline after. The CSS CPU writes up to 4 console cells per execution (one write
# channel per bank) and repeats the instruction until the value is out.
PRINTOPS = ['PRINT', 'PRINTB', 'PRINTSP', 'PRINTBSP', 'PRINTLN', 'PRINTBLN']
# objects (cc_ref.py): SCANI / SCAN probe an object's keys, LDF loads a field, SETF stores one, PUTV stores a property, NEW
# allocates an 8-word chunk, ENDK ends its keys; OVER copies the word under the top, JNEG branches on the sign of that word
# (array or object)
OBJOPS = 'SCANI SCAN LDF PUTV NEW SETF ENDK OVER JNEG'.split()
OPN = 'NOP PUSHI LOADG STOREG LOADL STOREL LOADI STOREI ADD SUB MUL DIV MOD LT GT LE GE EQ NE AND OR NOT NEG JMP JZ JNZ CALL ENTER RET POP DUP PUTC HALT JMPI SHL13 INCG INCL IDX IDXL'.split() + PRINTOPS + OBJOPS + ['PUSHS', 'IDXA', 'STOREX', 'DYN']
# PUSHS a: push the string value of address a (a - STRTAG): a string literal. IDXA [x, k] -> [x[k]] and STOREX [x, k, v] -> []
# index an array (0 past its length; a store inside it); anything else, or a store outside the length, traps into the ROM's
# GETX / SETX: the return address is pushed (as CALL does) and pc goes to the routine. DYN op [a, b] -> [a op b] (op: the
# binary opcode in the immediate's low 6 bits; ADD, EQ, NE, LT, GT, LE, GE) for numbers; a string operand traps into dyn.
OP = {n: i for i, n in enumerate(OPN)}
STRTAG = 262144                             # a string value is its address - STRTAG (cc_ref.STRTAG)
STR_LO = LAYOUT['data_base'] + 256; STR_HI = STR_LO + LAYOUT['str_size']   # the string area (cc_ref STR0 .. SEND); STR_LO itself is the DONE marker
OUT_COLS, OUT_ROWS = LAYOUT['cols'], LAYOUT['rows']
OUT_BASE = LAYOUT['rom_size'] + LAYOUT['ram_size'] - OUT_COLS * OUT_ROWS   # console: the last words of RAM
# objects: an object is an 8-word chunk [k0 v0 k1 v1 k2 v2 L pad] in the heap, its value the chunk's address - OBJTAG (a multiple of
# 32768, so the 15-bit address registers untag it for free). A key is stored as its value + KBIAS (a string key becomes its
# address, positive and small; a number n becomes n + KBIAS), 0 marks a free pair (it ends the keys), and L links to an overflow
# chunk (a negative object value) or is 0. NEW calls the GC through the jump table when the heap is full; a store that must add
# a key calls the ROM's append routine.
OBJTAG, KBIAS = LAYOUT['objtag'], STRTAG
RT = LAYOUT['rt_base']; CELL = {n: RT + i for i, n in enumerate(LAYOUT['rt_cells'])}; HP, GCLIM, GCSP, KEYCELL, RETCELL = (CELL[n] for n in ('HP', 'GCLIM', 'GCSP', 'KEYCELL', 'RETCELL'))
# HP / GCLIM: the next free chunk and the space's end - 7 (offsets from HEAP0); GCSP: SP at a GC call; KEYCELL: the key KEYV made
# for SCAN; RETCELL: the return address of a call into the ROM routines
HEAP0 = LAYOUT['heap_lo']
VEC = LAYOUT['vec_base']; VECS = {n: VEC + i for i, n in enumerate(LAYOUT['vectors'])}   # the ROM's jump table (compiler/rtlib.py)
GCVEC, PUTVEC, SETXVEC, GETXVEC, DYNVEC, PRINTVEC = (VECS[n] for n in ('gc', 'append', 'setx', 'getx', 'dyn', 'print'))
ARRTAG = LAYOUT['arrtag']                   # an array value is its ptr word's address + ARRTAG (a multiple of 32768, like the tags)
HEAP_HI = HEAP0 + 2 * LAYOUT['heap_size']
STRP_HI = HEAP_HI                           # a value v is a string iff STR_LO <= v + STRTAG < STRP_HI (a literal or a heap string)
