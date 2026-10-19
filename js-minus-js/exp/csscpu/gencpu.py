#!/usr/bin/env python3
"""gencpu.py image.json out.html — the pure-CSS CPU: a CPU-only page (gen_fvm4.py's role) with no font. Style alone runs
the instructions; layout only fills the cache and moves the registers. The design is sim.py's, which is its oracle.

A pass (ISSUE passes per frame, gen_fvm4's frame gate):
  #cpu      the registers (view timelines, as gen_fvm4's), the frame gate, the pending miss's victim lines
  .rp/.vp   eight read ports read the pending block's words and the next block's (one port per bank and block) from the
            ROM and RAM leaves
  .fl       the fill: the victim line takes the block (a dirty victim's words go to the write set first); the next block
            is prefetched if it is absent and its victim is clean
  K levels  .f fetch (ROM from a static table, RAM through the cache) and decode > .x execute > .c commit. An instruction
            runs only if every word it touches is cached (and, for output, the write set is free); the first that can't
            stops the chain, noting its missing block (--pend) for the next pass's fill
  .ex       the registers' view-timeline subjects at the chain's final state; the write set goes to the RAM channels
Cache: 16 sets x 2 ways x 4 words, set (b + b / 16 + b / 256) mod 16 of block b; --T<line> = 2 * (block + 1) + dirty
(0: empty), --F<set> the next victim way, --W<line>_<word> the words, line = 2 * set + way. RAM is memtree.py's, the
console gen_fvm4's.

Cost model (measured, README): a container-query test ~2 us, a declaration ~1.3 us, an if() branch ~0.3 us, per element.
So .x dispatches on 7 instruction classes (one container test each) and selects within a class by if(); .c commits a
whole cache set (16 rules) rather than a word (128).
Env: K (levels, default 32), ISSUE (passes per frame, default 2; ENGINE_NOTES 37: more run on stale state)."""
import sys, os, json, html as _h
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(ROOT, "machine"), os.path.join(ROOT, "compiler"), os.path.join(ROOT, "..", "shared", "py"), HERE]
import memtree, csslabel as lbl, cc_ref as R
from uarch import OPN, PRINTOPS, STRTAG, STR_LO, STR_HI
OP = {n: i for i, n in enumerate(OPN)}

image = json.load(open(sys.argv[1])); outp = sys.argv[2]
K = int(os.environ.get('K', 32)); ISSUE = int(os.environ.get('ISSUE', 2))
ROM, RAMN, WB = image['romSize'], image['ramSize'], 4
BANKN = RAMN // WB; BLKS = (ROM + RAMN) // WB; RB0 = ROM // WB
OUT_BASE, ROWS, COLS = image['outBase'], image['rows'], image['cols']; OUT_SIZE = ROWS * COLS
assert OUT_BASE % 4 == 0 and ROM % 4 == 0
WOFF = M20 = 1 << 20; A15 = 32768
NSET, NWAY = 16, 2; NL = NSET * NWAY
CH = 'ABCD'[:2 * ISSUE]; sp0 = image['sp0']

def eq(x, c): return f"calc(1 - min(1, max(({x}) - ({c}), ({c}) - ({x}))))"     # 1 iff x == c (integers)
def s20(e): return f"calc(mod({e} + {1 << 19}, {M20}) - {1 << 19})"
def v(n): return f"var(--{n})"
def sel(key, n, val, default=None):
    """if() over --key = 0 .. n-1 (val(i) each); the last case is the else branch"""
    return "if(" + " ".join(f"style(--{key}: {i}): {val(i)};" for i in range(n - 1)) + f" else: {val(n - 1) if default is None else default})"
def by_op(cases, default):
    """if() on the instruction: {op name: expression}, default for the class's other ops"""
    return "if(" + " ".join(f"style(--op: {OP[o]}): {e};" for o, e in cases.items()) + f" else: {default})"
def setof(b): return f"mod({b} + round(down, {b} / 16) + round(down, {b} / 256), 16)"

# ---------------- registers: (name, H, OFF), value range [-OFF, H - OFF); the subject's expression at the chain's end
regs = [("pc", A15, 0, "var(--pc)"), ("rsp", A15, 0, "var(--sp)"), ("rfp", A15, 0, "var(--fp)"), ("optr", 256, 0, "var(--optr)"),
        ("pst", A15, 0, "var(--pst)"), ("steps", 1 << 21, 0, "var(--steps)"), ("halt", 2, 0, "var(--halt)"), ("pend", 8192, 0, "var(--pend)"),
        ("init", 2, 0, "1"), ("k", 16, 0, "var(--nk)"), ("par", 2, 0, "var(--npar)"), ("tprev", 65536, 0, "var(--t)")]
regs += [(f"T{k}", 16384, 0, f"var(--T{k})") for k in range(NL)] + [(f"F{s}", 2, 0, f"var(--F{s})") for s in range(NSET)]
regs += [(f"W{k}_{j}", M20, M20 // 2, f"var(--W{k}_{j})") for k in range(NL) for j in range(4)]
WREGS = [(f"wa{w}{c}", BANKN + 1, 0, f"var(--nwa{w}{c})") for w in range(WB) for c in CH] + \
        [(f"wd{w}{c}", 1 << 21, 1 << 20, f"var(--nwd{w}{c})") for w in range(WB) for c in CH]
# the console is its own four trees (prefix k<w>, OUT_SIZE / 4 cells each) with their own channels, so output doesn't
# restyle the RAM trees (a channel change restyles its whole tree: ENGINE_NOTES 41)
KN = OUT_SIZE // WB
WREGS += [(f"wak{w}{c}", KN + 1, 0, f"var(--nwak{w}{c})") for w in range(WB) for c in CH] + \
         [(f"wdk{w}{c}", 256, 0, f"var(--nwdk{w}{c})") for w in range(WB) for c in CH]
if 'noW' in os.environ.get('ABL', ''): regs = [r for r in regs if not r[0].startswith('W')]
regs += WREGS
WNAMES = [r[0] for r in WREGS]

# ---------------- #cpu: effective state, frame gate, the fill's victims (all from the registers)
cpu = ["--first: calc(1 - var(--init));",
       f"--sp: calc(var(--init) * var(--rsp) + var(--first) * {sp0});", f"--fp: calc(var(--init) * var(--rfp) + var(--first) * {sp0});",
       "--fresh: calc(min(1, max(var(--t) - var(--tprev), var(--tprev) - var(--t))));",
       f"--go: calc(min(1, var(--fresh) + min(1, max(0, {ISSUE} - var(--k)))));",
       f"--chan: calc({ISSUE} * var(--par) + (1 - var(--fresh)) * var(--k));",
       f"--nk: calc(var(--fresh) + (1 - var(--fresh)) * min({ISSUE}, var(--k) + 1));",   # saturates, so frames settle (ENGINE_NOTES 16)
       "--npar: calc(var(--fresh) * (1 - var(--par)) + (1 - var(--fresh)) * var(--par));",
       # the fill: block fb into set fs's victim way fv (line fk); a dirty victim (block fvb) is written back
       "--fon: calc(var(--go) * min(1, var(--pend)));", "--fb: max(0, var(--pend) - 1);",
       f"--fs: {setof('var(--fb)')};",
       "--fv: " + sel("fs", NSET, lambda s: f"var(--F{s})") + ";", "--fk: calc(2 * var(--fs) + var(--fv));",
       "--fT: " + sel("fk", NL, lambda k: f"var(--T{k})") + ";",
       "--fd: calc(var(--fon) * mod(var(--fT), 2));", "--fvb: calc(round(down, var(--fT) / 2) - 1);",
       "--fk1: calc(var(--fon) * (var(--fk) + 1));", "--pend0: calc((1 - var(--fon)) * var(--pend));",
       f"--rb: clamp(0, var(--fb), {BLKS - 1});", "--rbh: round(down, var(--rb) / 64);", "--rbl: calc(var(--rb) - 64 * var(--rbh));",
       # the prefetch: block fb + 1 into its set's victim way (line gk), if absent there and the victim is clean
       f"--gs: {setof('(var(--fb) + 1)')};", "--gv: " + sel("gs", NSET, lambda s: f"var(--F{s})") + ";", "--gk: calc(2 * var(--gs) + var(--gv));",
       "--gT: " + sel("gk", NL, lambda k: f"var(--T{k})") + ";",
       "--gabs: " + sel("gs", NSET, lambda s: f"calc(1 - {eq(f'round(down, var(--T{2 * s}) / 2)', 'var(--fb) + 2')} - {eq(f'round(down, var(--T{2 * s + 1}) / 2)', 'var(--fb) + 2')})") + ";",
       f"--gk1: calc(var(--fon) * var(--gabs) * (1 - mod(var(--gT), 2)) * clamp(0, {BLKS - 1} - var(--fb), 1) * (var(--gk) + 1));",
       f"--qb: clamp(0, var(--fb) + 1, {BLKS - 1});", "--qbh: round(down, var(--qb) / 64);", "--qbl: calc(var(--qb) - 64 * var(--qbh));"]
cpu += [f"--fwd{w}: " + sel("fk", NL, lambda k, w=w: f"var(--W{k}_{w})") + ";" for w in range(WB)]
HOT = range(256, 768)     # the blocks runs mostly read: globals, strings, code, the bottom of the stack (read ports, below)
cpu += [f"--rbhot: calc(clamp(0, var(--rb) - {HOT.start - 1}, 1) * clamp(0, {HOT.stop} - var(--rb), 1));",
        f"--qbhot: calc(clamp(0, var(--qb) - {HOT.start - 1}, 1) * clamp(0, {HOT.stop} - var(--qb), 1));"]

# ---------------- reads: a word through the cache. For read n of address A: block b, word u, set z, hits h (way 0) and
# H (way 1), each one if() over the set comparing that way's tag, and the word v (set, then way, then word).
def lookup(n, A):
    b = f"var(--b{n})"
    hit = lambda way: sel(f"z{n}", NSET, lambda s: eq(f"round(down, var(--T{2 * s + way}) / 2)", f"{b} + 1"))
    return [f"--b{n}: round(down, ({A}) / 4);", f"--u{n}: mod({A}, 4);", f"--z{n}: {setof(b)};", f"--h{n}: {hit(0)};", f"--H{n}: {hit(1)};"]
def word(n, k): return sel(f"u{n}", 4, lambda j: f"var(--W{k}_{j})")
def read(n, A):
    return lookup(n, A) + [f"--v{n}: " + sel(f"z{n}", NSET, lambda s: f"if(style(--H{n}: 1): {word(n, 2 * s + 1)}; else: {word(n, 2 * s)})") + ";"]
def miss(n): return f"(1 - var(--h{n}) - var(--H{n}))"
LOOKUP = ("b", "u", "z", "h", "H")
READS = ("f", "s1", "s2", "ra", "rb", "w", "p")

# a write of value V through lookup n (a read of the same address, or the write's own): the set's 8 new words and 2 tags,
# and --wz = set + 1, which picks the commit rule on .c (0: no write, as on a stall)
def write(n, V):
    d = [f"--wval: {V};"]
    for i in range(8):
        way, j = divmod(i, 4)
        old = sel(f"z{n}", NSET, lambda s: f"var(--W{2 * s + way}_{j})")
        d.append(f"--n{i}: if(style(--H{n}: {way}) and style(--u{n}: {j}): var(--wval); else: {old});")
    for way in range(2):
        d.append(f"--nT{way}: if(style(--H{n}: {way}): calc(2 * var(--b{n}) + 3); else: {sel(f'z{n}', NSET, lambda s: f'var(--T{2 * s + way})')});")
    return d + [f"--wz: calc(var(--ok) * (var(--z{n}) + 1));"]

# ---------------- instruction classes: (ops, reads [(name, address, the ops needing it or None for all)], write (address
# or None to reuse read `reuse`, value, reuse) or None, next registers {pc, sp, fp}). A class is one rule on .x.
pc, sp, fp, imm, simm = v("pc"), v("sp"), v("fp"), v("imm"), v("simm")
z1 = eq("var(--vs1)", 0)
BINE = {'ADD': s20("var(--vs2) + var(--vs1)"), 'SUB': s20("var(--vs2) - var(--vs1)"), 'MUL': s20("var(--vs2) * var(--vs1)"),
        'DIV': f"calc((1 - {z1}) * round(to-zero, var(--vs2) / (var(--vs1) + {z1})))",
        'MOD': f"calc((1 - {z1}) * (var(--vs2) - var(--vs1) * round(to-zero, var(--vs2) / (var(--vs1) + {z1}))))",
        'LT': "clamp(0, var(--vs1) - var(--vs2), 1)", 'GT': "clamp(0, var(--vs2) - var(--vs1), 1)",
        'LE': "clamp(0, var(--vs1) - var(--vs2) + 1, 1)", 'GE': "clamp(0, var(--vs2) - var(--vs1) + 1, 1)",
        'EQ': eq("var(--vs1)", "var(--vs2)"), 'NE': f"calc(1 - {eq('var(--vs1)', 'var(--vs2)')})",
        'AND': f"calc((1 - {z1}) * (1 - {eq('var(--vs2)', 0)}))", 'OR': f"min(1, calc((1 - {z1}) + (1 - {eq('var(--vs2)', 0)})))"}
BINOPS = ['MOD', 'EQ', 'ADD', 'LE', 'LT', 'SUB', 'GT', 'GE', 'NE', 'MUL', 'DIV', 'AND', 'OR']    # FizzBuzz's most frequent first
fpo = f"{fp} + {simm}"
CLASSES = {
    'push': (['PUSHI', 'CALL', 'ENTER'], [], (sp, by_op({'CALL': f"calc({pc} + 1)", 'ENTER': fp}, imm), None),
             {'sp': by_op({'ENTER': f"calc({sp} + 1 + {imm})"}, f"calc({sp} + 1)"), 'pc': by_op({'CALL': imm}, f"calc({pc} + 1)"), 'fp': by_op({'ENTER': sp}, fp)}),
    'load': (['LOADG', 'LOADL', 'DUP', 'INCG', 'INCL'], [("ra", by_op({'LOADL': fpo, 'INCL': fpo, 'DUP': f"{sp} - 1"}, imm), None)],
             (by_op({'INCG': imm, 'INCL': fpo}, sp), by_op({'INCG': s20("var(--vra) + 1"), 'INCL': s20("var(--vra) + 1")}, "var(--vra)"), None),
             {'sp': by_op({'INCG': sp, 'INCL': sp}, f"calc({sp} + 1)")}),
    'bin': (BINOPS, [("s1", f"{sp} - 1", None), ("s2", f"{sp} - 2", None)], (None, by_op({o: BINE[o] for o in BINOPS[:-1]}, BINE[BINOPS[-1]]), "s2"),
            {'sp': f"calc({sp} - 1)"}),
    'jump': (['JZ', 'JMP', 'JNZ', 'POP', 'JMPI', 'NOP', 'HALT'], [("s1", f"{sp} - 1", ['JZ', 'JNZ', 'JMPI'])], None,
             {'sp': by_op({'JZ': f"calc({sp} - 1)", 'JNZ': f"calc({sp} - 1)", 'POP': f"calc({sp} - 1)", 'JMPI': f"calc({sp} - 1)"}, sp),
              'pc': by_op({'JZ': f"calc({z1} * {imm} + (1 - {z1}) * ({pc} + 1))", 'JMP': imm, 'JNZ': f"calc((1 - {z1}) * {imm} + {z1} * ({pc} + 1))",
                           'JMPI': "mod(var(--vs1), 32768)", 'HALT': pc}, f"calc({pc} + 1)")}),
    'store': (['STOREG', 'STOREL', 'STOREI'], [("s1", f"{sp} - 1", None), ("s2", f"{sp} - 2", ['STOREI'])],
              (by_op({'STOREL': fpo, 'STOREI': "mod(var(--vs2), 32768)"}, imm), "var(--vs1)", None),
              {'sp': by_op({'STOREI': f"calc({sp} - 2)"}, f"calc({sp} - 1)")}),
    'index': (['LOADI', 'IDX', 'IDXL', 'RET', 'NOT', 'NEG', 'SHL13'],
              [("s1", f"{sp} - 1", None), ("ra", by_op({'LOADI': "mod(var(--vs1), 32768)", 'IDXL': fpo, 'RET': fp}, imm), ['LOADI', 'IDX', 'IDXL', 'RET']),
               ("rb", by_op({'RET': f"{fp} - 1"}, "mod(var(--vra) + var(--vs1), 32768)"), ['IDX', 'IDXL', 'RET'])],
              (by_op({'RET': f"{fp} - 1 - {imm}"}, f"{sp} - 1"),
               by_op({'LOADI': "var(--vra)", 'RET': "var(--vs1)", 'NOT': z1, 'NEG': s20("-1 * var(--vs1)"), 'SHL13': s20("var(--vs1) * 8192")}, "var(--vrb)"), None),
              {'sp': by_op({'RET': f"calc({fp} - {imm})"}, sp), 'fp': by_op({'RET': "var(--vra)"}, fp), 'pc': by_op({'RET': "mod(var(--vrb), 32768)"}, f"calc({pc} + 1)")}),
}
def first_miss(acc):
    """the block of the first missing access (dependency order) among [(name, mask)], -1 for none"""
    e = "-1"
    for n, m in reversed(acc): e = f"calc({m}{miss(n)} * var(--b{n}) + (1 - {m}{miss(n)}) * {e})"
    return e
def need(ops): return "" if ops is None else "(" + " + ".join(eq("var(--op)", OP[o]) for o in ops) + ") * "
def nexts(nx, done="1"):
    return [f"--npc: {nx.get('pc', f'calc({pc} + {done})')};", f"--nsp: {nx.get('sp', sp)};", f"--nfp: {nx.get('fp', fp)};",
            f"--nsteps: calc(var(--steps) + {done});"]
cls_rules = {}
for c, (ops, rds, wr, nx) in CLASSES.items():
    d, acc = [], []
    for n, A, ops_n in rds: d += read(n, A); acc.append((n, need(ops_n)))
    if wr:
        A, V, reuse = wr
        if reuse is None: d += lookup("w", A); acc.append(("w", "")); wn = "w"
        else: wn = reuse
        d += write(wn, V)
    d += [f"--ok: calc(1 - min(1, calc({' + '.join(f'{m}{miss(n)}' for n, m in acc)})));" if acc else "--ok: 1;",
          f"--mb: {first_miss(acc)};" if acc else "--mb: -1;"] + nexts(nx)
    if c == 'jump': d += [f"--nstop: {eq('var(--op)', OP['HALT'])};", f"--nhalt: {eq('var(--op)', OP['HALT'])};"]
    cls_rules[c] = (ops, d)

# 'out': the PRINT family and PUTC (uarch.Machine.print_service, gen_fvm4's service): up to 4 console cells per execution,
# one per bank; a string chunk ends at its block (the block's line must be cached), at a NUL (the value is out) or a
# newline (taken); until the value is out the instruction repeats (npc = pc) and --pst carries the position. Output needs
# the pass's write set free. PUTC writes one cell or a newline.
pv = "var(--vs1)"
isputc = eq("var(--op)", OP['PUTC'])
pr = read("s1", f"{sp} - 1") + [
    "--prLN: " + by_op({o: 1 for o in PRINTOPS if o.endswith('LN')}, 0) + ";", "--prSP: " + by_op({o: 1 for o in PRINTOPS if o.endswith('SP')}, 0) + ";",
    "--prB: " + by_op({o: 1 for o in PRINTOPS if o.startswith('PRINTB')}, 0) + ";",
    f"--pp: calc({pv} + {STRTAG});",
    f"--isStr: calc((1 - {isputc}) * clamp(0, var(--pp) - {STR_LO - 1}, 1) * clamp(0, {STR_HI} - var(--pp), 1));",
    f"--isBool: calc((1 - var(--isStr)) * var(--prB) * ({eq(pv, 0)} + {eq(pv, 1)}));",
    "--isNum: calc((1 - var(--isStr)) * (1 - var(--isBool)));",
    "--pq: calc(min(1, var(--pst)) * var(--pst) + (1 - min(1, var(--pst))) * var(--pp));",
    f"--pdone: calc(var(--isStr) * {eq('var(--pq)', STR_LO)});", "--pj0: mod(var(--pq), 4);"]
pr += lookup("p", "var(--pq)")
pr += [f"--pw{j}: " + sel("zp", NSET, lambda s, j=j: f"if(style(--Hp: 1): var(--W{2 * s + 1}_{j}); else: var(--W{2 * s}_{j}))") + ";" for j in range(4)]
pr += [f"--mpp: calc(var(--isStr) * (1 - var(--pdone)) * {miss('p')});",
       f"--pa: max({pv}, -1 * {pv});", f"--pneg: clamp(0, -1 * {pv}, 1);",
       "--pL: calc(1 + " + " + ".join(f"clamp(0, var(--pa) - {10 ** dd - 1}, 1)" for dd in range(1, 6)) + ");",
       f"--ptot: calc(var(--isNum) * (var(--pneg) + var(--pL)) + var(--isBool) * (5 - {pv}) + var(--prSP));",
       "--pph: calc((1 - var(--isStr)) * var(--pst));", "--pbase: calc(4 * var(--pph));"]
for i in range(4):
    g = f"var(--pg{i})"
    inum = f"clamp(0, var(--pneg) + var(--pL) - {g}, 1)"; ineg = f"clamp(0, var(--pneg) - {g}, 1)"
    digit = f"mod(round(down, var(--pa) / pow(10, var(--pneg) + var(--pL) - 1 - {g})), 10)"
    T_, F_ = [ord(c) for c in 'true'], [ord(c) for c in 'false']
    boolc = " + ".join(f"{eq(g, kk)} * ({pv} * {T_[kk] if kk < 4 else 0} + (1 - {pv}) * {F_[kk]})" for kk in range(5))
    pr += [f"--pg{i}: calc(var(--pbase) + {i});",
           f"--pnb{i}: calc(var(--isNum) * ({ineg} * 45 + ({inum} - {ineg}) * (48 + {digit})) + var(--isBool) * ({boolc}) + (1 - var(--isStr)) * var(--prSP) * {eq(g, 'var(--ptot) - 1')} * 32);"]
for i in range(4):
    inb = f"clamp(0, 4 - var(--pj0) - {i}, 1)"
    pr += [f"--pb{i}: calc({inb} * (" + " + ".join(f"{eq(f'var(--pj0) + {i}', j)} * var(--pw{j})" for j in range(4)) + "));",
           f"--pc{i}: calc({inb} * (1 - {eq(f'var(--pb{i})', 0)}) * (1 - {eq(f'var(--pb{i})', 10)}));",
           f"--pr{i}: " + ("var(--pc0);" if i == 0 else f"calc(var(--pr{i - 1}) * var(--pc{i}));")]
pr += ["--pe: calc((1 - var(--pdone)) * (var(--pr0) + var(--pr1) + var(--pr2) + var(--pr3)));",
       "--pvE: clamp(0, 4 - var(--pj0) - var(--pe), 1);",
       "--pbE: calc(" + " + ".join(f"{eq('var(--pe)', i)} * var(--pb{i})" for i in range(4)) + ");",
       f"--ptNul: calc(var(--pdone) + (1 - var(--pdone)) * var(--pvE) * {eq('var(--pbE)', 0)});",
       f"--ptNL: calc((1 - var(--pdone)) * var(--pvE) * {eq('var(--pbE)', 10)});",
       f"--pn: if(style(--op: {OP['PUTC']}): calc(1 - {eq(pv, 10)}); else: calc(var(--isStr) * (var(--pe) + var(--ptNul) * var(--prSP)) + (1 - var(--isStr)) * clamp(0, var(--ptot) - var(--pbase), 4)));",
       f"--pfin: if(style(--op: {OP['PUTC']}): 1; else: calc(var(--isStr) * var(--ptNul) + (1 - var(--isStr)) * clamp(0, var(--pbase) + 5 - var(--ptot), 1)));",
       f"--pnl: if(style(--op: {OP['PUTC']}): {eq(pv, 10)}; else: calc(var(--isStr) * (var(--ptNL) + var(--ptNul) * var(--prLN)) + (1 - var(--isStr)) * var(--pfin) * var(--prLN)));",
       "--npst: calc(var(--isStr) * (1 - var(--ptNul)) * (var(--pq) + var(--pe) + var(--ptNL)) + (1 - var(--isStr)) * (1 - var(--pfin)) * (var(--pph) + 1));"]
for i in range(4):
    pr.append(f"--pch{i}: " + (f"if(style(--op: {OP['PUTC']}): {pv}; else: " if i == 0 else "") +
              f"calc(var(--isStr) * (var(--pr{i}) * var(--pb{i}) + {eq('var(--pe)', i)} * var(--ptNul) * var(--prSP) * 32)"
              f" + (1 - var(--isStr)) * clamp(0, var(--pn) - {i}, 1) * var(--pnb{i}))" + (")" if i == 0 else "") + ";")
pr += ["--ok: calc((1 - min(1, calc(var(--ms1) + var(--mpp)))) * (1 - var(--cw)));".replace("var(--ms1)", miss("s1")),
       f"--mb: calc({miss('s1')} * var(--bs1) + (1 - {miss('s1')}) * (var(--mpp) * var(--bp) + (1 - var(--mpp)) * -1));"]
pr += nexts({'pc': f"calc({pc} + var(--pfin))", 'sp': f"calc({sp} - var(--pfin))"}, "var(--pfin)")
# cell i of the chunk goes to optr + i, bank (optr + i) mod 4 (OUT_BASE is a multiple of 4)
pr += ["--pout: var(--ok);", "--ncw: min(1, var(--pn));",
       f"--noptr: mod(var(--pnl) * (round(down, (var(--optr) + var(--pn)) / {COLS}) + 1) * {COLS} + (1 - var(--pnl)) * (var(--optr) + var(--pn)), {OUT_SIZE});"]
for w in range(WB):
    pr += [f"--pi{w}: mod({w} - var(--optr), 4);", f"--dp{w}: clamp(0, var(--pn) - var(--pi{w}), 1);",
           f"--nwA{w}: calc(var(--dp{w}) * (round(down, mod(var(--optr) + var(--pi{w}), {OUT_SIZE}) / 4) + 1));",
           f"--nwD{w}: calc(" + " + ".join(f"{eq(f'var(--pi{w})', i)} * var(--pch{i})" for i in range(4)) + ");"]
cls_rules['out'] = (PRINTOPS + ['PUTC'], pr)
CLS = {c: i + 1 for i, c in enumerate(cls_rules)}
assert sorted(o for ops, _ in cls_rules.values() for o in ops) == sorted(OPN[:OP[PRINTOPS[0]] + 6]), 'every non-object op in one class'
FREQ = ['PUSHI', 'LOADG', 'JZ', 'MOD', 'EQ', 'JMP', 'ADD', 'STOREG', 'LE', 'PRINTLN', 'LOADL']   # FizzBuzz's most frequent first
opcls = {o: CLS[c] for c, (ops, _) in cls_rules.items() for o in ops}
cls_of = "if(" + " ".join(f"style(--op: {OP[o]}): {opcls[o]};" for o in FREQ + [o for o in opcls if o not in FREQ]) + " else: 0)"

# the ROM's words (instruction fetch only), two-level on the pc
ROMW = image['rom']
rom_table = "if(" + " ".join(f"style(--rh: {h}): if(" + " ".join(f"style(--rl: {l}): {ROMW[32 * h + l]};" for l in range(32) if ROMW[32 * h + l]) + " else: 0);"
                            for h in range(ROM // 32) if any(ROMW[32 * h:32 * h + 32])) + " else: 0)"

ABL = os.environ.get('ABL', '').split(',')     # timing ablations: norom (the ROM table empty), ...
if 'norom' in ABL: rom_table = "0"
# ---------------- the page's CSS
P = ["pc", "rsp", "rfp", "sp", "fp", "optr", "pst", "steps", "halt", "pend", "init", "k", "par", "tprev", "first", "fresh", "go", "chan", "nk", "npar",
     "fon", "fb", "fs", "fv", "fk", "fT", "fd", "fvb", "fk1", "pend0", "rb", "rbh", "rbl", "gs", "gv", "gk", "gT", "gabs", "gk1", "qb", "qbh", "qbl", "rbhot", "qbhot",
     "t", "stop", "cw", "op", "imm", "simm", "cls", "rom", "rh", "rl", "vf", "mf", "ok", "mb", "npc", "nsp", "nfp", "nsteps", "nstop", "nhalt",
     "wval", "wz", "nT0", "nT1", "pout", "ncw", "noptr", "npst", "prLN", "prSP", "prB", "pp", "isStr", "isBool", "isNum", "pq", "pdone", "pj0",
     "mpp", "pa", "pneg", "pL", "ptot", "pph", "pbase", "pe", "pvE", "pbE", "ptNul", "ptNL", "pn", "pfin", "pnl"]
P += [r[0] for r in regs if r[0] not in P]
P += [f"{x}{w}" for w in range(WB) for x in ("fwd", "wA", "wD", "cA", "cD", "nwA", "nwD", "pi", "dp", "pw")] + [f"mval{i}" for i in range(2 * WB)]
P += [f"{x}{i}" for i in range(4) for x in ("pg", "pnb", "pb", "pc", "pr", "pch")] + [f"n{i}" for i in range(8)]
P += [f"n{r[0]}" for r in WREGS]
P += [x + n for n in READS for x in LOOKUP] + [f"v{n}" for n in READS if n not in ("w", "p")]
P = list(dict.fromkeys(P))
props = [lbl.section('Registered properties', 'registers, the chain\'s state and temps: integers')]
# temps that only the element declaring them reads (.x's reads and PRINT scratch) don't inherit
LOCAL = {x + n for n in READS if n != "f" for x in LOOKUP} | {f"v{n}" for n in ("s1", "s2", "ra", "rb")} | {"uf", "zf", "hf", "Hf", "vf", "rom", "rh", "rl"}
LOCAL |= {"pp", "isStr", "isBool", "isNum", "pq", "pdone", "pj0", "mpp", "pa", "pneg", "pL", "ptot", "pph", "pbase", "pe", "pvE", "pbE",
          "ptNul", "ptNL", "pn", "pfin", "pnl", "prLN", "prSP", "prB"}
LOCAL |= {f"{x}{i}" for i in range(4) for x in ("pg", "pnb", "pb", "pc", "pr", "pch", "pw", "pi", "dp")}
props += [f'@property --{n} {{ syntax: "<integer>"; inherits: {"false" if n in LOCAL else "true"}; initial-value: 0; }}' for n in P]
props += [f'@property --sR{i} {{ syntax: "<custom-ident>"; inherits: false; initial-value: --c0; }}' for i in range(2 * WB)]   # a port's leaf name

css = [lbl.section('CPU: clock, registers, frame gate, the fill\'s victims', 'on #cpu: the registers are view timelines (gen_fvm4.py)'),
       "#clk { animation: wc 100s linear infinite; }\n@keyframes wc { from { --t: 0; } to { --t: 60000; } }",
       "#cpu {\n  timeline-scope: " + ", ".join(f"--{r[0]}" for r in regs if r[0] not in WNAMES) +
       ";\n  animation-name: " + ", ".join(f"r-{r[0]}" for r in regs) + ";\n  animation-timeline: " + ", ".join(f"--{r[0]}" for r in regs) +
       ";\n  animation-duration: auto;\n  animation-timing-function: linear;\n  animation-fill-mode: both;\n  " + "\n  ".join(cpu) + "\n}"]
css.append(lbl.group('Register keyframes', 'each register\'s view timeline mapped onto its value range'))
css += [f"@keyframes r-{n} {{ from {{ --{n}: {H - OFF}; }} to {{ --{n}: {-1 - OFF}; }} }}" for n, H, OFF, _ in regs]

# a read port's leaf name: a two-level if() on the block's 64-block group (h) and place in it (l). An if() costs ~70 ns per
# entry it contains, taken or not (README), so a 4,352-block mux costs ~0.3 ms wherever it is evaluated: each port
# evaluates it itself (not #cpu, which restyles every pass), only on passes that fill, and from a mux of the 512 blocks
# runs mostly read (HOT) unless the block is outside them.
def mux(p, blocks, leaf, default):
    groups = sorted({b // 64 for b in blocks}); outer = []
    for j in groups:
        inner = " ".join(f"style(--{p}l: {i}): {leaf(j * 64 + i)};" for i in range(64) if j * 64 + i in blocks)
        outer.append(f"style(--{p}h: {j}): if({inner} else: {default});")
    return f"if({' '.join(outer)} else: {default})"
ROMNZ = {a for a, x in enumerate(image['rom']) if x}
def leafname(a): return f"--r{a}" if a < ROM else f"--c{a - ROM}"
css.append(lbl.group(f'Read ports: one per bank ({WB}) for the pending block (rb) and one for the next (qb)',
                     'a two-level if() picks the leaf, anchor-size() reads it'))
for i in range(2 * WB):
    w, q, on = i % WB, "rb" if i < WB else "qb", "fon" if i < WB else "gk1"
    leaf = lambda b, w=w: leafname(4 * b + w)
    css.append(f".rp{i} {{ width: anchor-size(var(--sR{i}) width, {WOFF}px); }} .vp{i} {{ --mval{i}: calc(100cqi / 1px - {WOFF}); }}")
    if 'nomux' in ABL: continue
    css.append(f"@container style(--{q}hot: 1) {{ .rp{i} {{ --sR{i}: {mux(q, set(HOT), leaf, f'--c{w}')}; }} }}")
    css.append(f"@container style(--{q}hot: 0) and (not style(--{on}: 0)) {{ .rp{i} {{ --sR{i}: {mux(q, set(range(BLKS)) - set(HOT), leaf, f'--c{w}')}; }} }}")

css.append(lbl.section('The fill', 'the victim line takes the pending block (a dirty victim\'s words are the pass\'s RAM write set), and the prefetch line the next'))
css.append(".fl { --stop: calc(1 - var(--go) * (1 - var(--halt))); --pend: var(--pend0); --cw: 0;\n  " +
           " ".join(f"--wA{w}: calc(var(--fd) * (var(--fvb) - {RB0 - 1})); --wD{w}: var(--fwd{w}); --cA{w}: 0; --cD{w}: 0;" for w in range(WB)) + " }")
css += [f"@container style(--fk1: {k + 1}) {{ .fl {{ --T{k}: calc(2 * var(--fb) + 2); --F{k // 2}: {1 - k % 2}; " +
        " ".join(f"--W{k}_{j}: var(--mval{j});" for j in range(4)) + " } }" for k in range(NL)]
css += [f"@container style(--gk1: {k + 1}) {{ .fl {{ --T{k}: calc(2 * var(--fb) + 4); --F{k // 2}: {1 - k % 2}; " +
        " ".join(f"--W{k}_{j}: var(--mval{WB + j});" for j in range(4)) + " } }" for k in range(NL)]

css.append(lbl.section('Instructions', f'{K} levels of .f (fetch, decode) > .x (execute) > .c (commit), display: contents'))
css.append(lbl.group('.f: fetch the word at pc unless the chain has stopped', 'ROM from a static table, RAM through the cache; a miss stalls'))
css.append(".f { --op: 255; --cls: 0; --ok: 2; --pout: 0; --wz: 0; }")
css.append("@container style(--stop: 0) { .f { " + " ".join(lookup("f", pc)) +
           f" --rom: clamp(0, {ROM} - var(--pc), 1); --rh: round(down, var(--pc) / 32); --rl: mod(var(--pc), 32);"
           f" --vf: if(style(--rom: 1): {rom_table}; else: " + sel("zf", NSET, lambda s: f"if(style(--Hf: 1): {word('f', 2 * s + 1)}; else: {word('f', 2 * s)})") + ");"
           f" --mf: calc((1 - var(--rom)) * {miss('f')}); --ok: calc(2 - 2 * var(--mf)); --mb: var(--bf);"
           " --op: calc(var(--mf) * 255 + (1 - var(--mf)) * round(down, var(--vf) / 8192)); --imm: mod(var(--vf), 8192);"
           f" --simm: calc(var(--imm) - 8192 * min(1, round(down, var(--imm) / 4096))); --cls: {cls_of}; }} }}")
css.append(lbl.group('.x: execute', 'one rule per instruction class; if() on --op inside it'))
css += [f"@container style(--cls: {CLS[c]}) {{ .x {{ {' '.join(d)} }} }}" for c, (_, d) in cls_rules.items()]
css.append(lbl.group('.c: commit', 'registers on success; the stall (stop, the missing block); output; the written word\'s cache set'))
css.append("@container style(--ok: 1) { .c { --pc: var(--npc); --sp: var(--nsp); --fp: var(--nfp); --steps: var(--nsteps); --stop: var(--nstop); --halt: var(--nhalt); } }")
css.append("@container style(--ok: 0) { .c { --stop: 1; --pend: calc(var(--mb) + 1); } }")
css.append("@container style(--pout: 1) { .c { --optr: var(--noptr); --pst: var(--npst); --cw: var(--ncw); " +
           " ".join(f"--cA{w}: var(--nwA{w}); --cD{w}: var(--nwD{w});" for w in range(WB)) + " } }")
css += [f"@container style(--wz: {s + 1}) {{ .c {{ " + " ".join(f"--W{2 * s + i // 4}_{i % 4}: var(--n{i});" for i in range(8)) +
        f" --T{2 * s}: var(--nT0); --T{2 * s + 1}: var(--nT1); }} }}" for s in range(NSET)]

css.append(lbl.section('Export', 'the write set into the RAM channels (gen_fvm4.py\'s rotation); the registers\' subjects'))
# (it holds its cell until it takes another, rather than being cleared: a channel change restyles the tree). Rotation: a
# channel written in a frame is not taken again until its leaf's remembered size has been recorded at that frame's end
# (gen_fvm4.py); a cell written again releases the channel that held it.
ex = []
for w in range(WB):
    for i, c in enumerate(CH):
        for p_, A_, D_ in (("", f"wA{w}", f"wD{w}"), ("k", f"cA{w}", f"cD{w}")):
            s_ = f"var(--go) * {eq('var(--chan)', i)} * min(1, var(--{A_}))"
            rel = f"min(1, var(--{A_})) * {eq(f'var(--{A_})', f'var(--wa{p_}{w}{c})')}"
            ex += [f"--nwa{p_}{w}{c}: calc({s_} * var(--{A_}) + (1 - {s_}) * (1 - {rel}) * var(--wa{p_}{w}{c}));",
                   f"--nwd{p_}{w}{c}: calc({s_} * var(--{D_}) + (1 - {s_}) * var(--wd{p_}{w}{c}));"]
css.append(".ex { " + " ".join(ex) + " }")

css.append(lbl.section('RAM', f'memtree.py: {len(CH)} write channels per bank, each a decode tree over the bank\'s cells'))
css.append(memtree.scope(WNAMES))
_sp, _sc = memtree.shared(); props += [lbl.group('RAM write channels')] + _sp; css += _sc
for w in range(WB):
    _mp, _mc = memtree.css(CH, {n: (H, OFF) for n, H, OFF, _ in WREGS if n[2:] in (f"{w}{c}" for c in CH)}, BANKN, WOFF, prefix=str(w))
    props += _mp; css += [lbl.group(f'Bank {w}')] + _mc
for w in range(WB):
    _mp, _mc = memtree.css(CH, {n: (H, OFF) for n, H, OFF, _ in WREGS if n[2:] in (f"k{w}{c}" for c in CH)}, KN, WOFF, prefix=f"k{w}")
    props += _mp; css += [lbl.group(f'Console bank {w}')] + _mc
css.append(lbl.section('Console', f'one reader per console cell ({COLS} x {ROWS}), drawn with the ascii counter style'))
for i in range(OUT_SIZE):
    r_, c_ = divmod(i, COLS)
    css.append(f".oc{i} {{ width: anchor-size(--c{OUT_BASE - ROM + i} width, {WOFF}px); left: calc(24px + {c_} * 11px); top: calc(24px + {r_} * 20px); }}")
css.append('@counter-style ascii { system: fixed 32; symbols: ' + " ".join('"\\""' if c == 34 else '"\\\\"' if c == 92 else f'"{chr(c)}"' for c in range(32, 127)) + '; fallback: blank; }')
css.append('@counter-style blank { system: cyclic; symbols: " "; }')

static = f"""
  {lbl.section('Page and machine layout', 'hand-written')}
  body {{ font: 15px/1.5 system-ui, sans-serif; margin: 0; color: #222; background: #fff; }}
  h1 {{ font-size: 1.1rem; font-weight: 600; margin: 0 0 .3rem; }}
  .head {{ position: fixed; left: {COLS * 11 + 48}px; top: 16px; width: 34rem; }}
  .head p {{ margin: .3rem 0; color: #444; }}
  .head pre {{ font: 12px/1.35 ui-monospace, monospace; background: #f4f4f4; padding: .5rem .7rem; border-radius: 4px; margin: .4rem 0; }}
  .status {{ font-family: ui-monospace, monospace; color: #666; font-size: 13px; }} .status b {{ color: #222; margin-right: .8em; font-weight: 600; }}
  .num {{ counter-set: v var(--v); }} .num::after {{ content: counter(v); }}
  .mem {{ height: 0; overflow: hidden; }}
  .w {{ width: fit-content; height: 1px; }}
  .cell {{ display: block; content-visibility: hidden; width: fit-content; height: 1px; contain-intrinsic-size: auto {WOFF}px; }}
  .rom {{ display: block; height: 1px; }}
  .rp {{ position: fixed; top: 0; left: 0; visibility: hidden; height: 1px; container-type: inline-size; }}
  .vp {{ visibility: visible; }}
  .f, .x, .c {{ display: contents; }}
  .regs {{ height: 0; overflow: hidden; }}
  .reg {{ position: relative; overflow: hidden; width: 1px; }}
  .sub {{ position: absolute; left: 0; width: 1px; height: 1px; }}
  .con {{ position: fixed; left: 16px; top: 16px; width: {COLS * 11 + 16}px; height: {ROWS * 20 + 16}px; background: #151515; border-radius: 6px; }}
  .oc {{ position: fixed; height: 20px; container-type: inline-size; visibility: hidden; font: 16px/20px ui-monospace, monospace; color: #eee; }}
  .oc > b {{ --code: calc(100cqi / 1px - {WOFF}); counter-set: ch var(--code); font-weight: 400; visibility: visible; display: inline-block; width: 11px; }}
  .oc > b::after {{ content: counter(ch, ascii); }}
"""
# DUP=a,b: every declaration of --a, --b gets a copy under --dup<name> (registered alike): its cost, results unchanged
def dup_decl(text, nm):
    out, i, key = [], 0, f"--{nm}: "
    while True:
        j = text.find(key, i)
        if j < 0 or (j > 0 and text[j - 1] not in ' {;'): out.append(text[i:] if j < 0 else text[i:j + 1]); i = j + 1 if j >= 0 else None
        else:
            d, k = 0, j + len(key)
            while d or text[k] != ';': d += {'(': 1, ')': -1}.get(text[k], 0); k += 1
            out.append(text[i:k + 1] + f" --dup{nm}: " + text[j + len(key):k] + ";"); i = k + 1
        if i is None: return "".join(out)
if os.environ.get('DUP'):
    for nm in os.environ['DUP'].split(','):
        css = [dup_decl(c, nm) for c in css]
        props.append(f'@property --dup{nm} {{ syntax: "<integer>"; inherits: {"false" if nm in LOCAL else "true"}; initial-value: 0; }}')
# ---------------- BENCH=1: the chain alone (chainbench.js), started from the state of the first pass sim.py runs with all
# K levels executing (STALL=1: the chain stopped at its top). The root's inline style holds the state.
if os.environ.get('BENCH'):
    import copy, sim, ref
    sm = sim.Sim(ref.load(os.environ['PROG']))
    while True:
        before = copy.deepcopy(sm); n, why = sm.run_pass(K)
        if why == 'K' or sm.st['halt']: break
    assert why == 'K', 'no pass runs all K levels'
    b0 = before; cw = b0.fill(b0.pending, 0) if b0.pending is not None else 0; b0.pending = None
    st = b0.st; stall = int(os.environ.get('STALL', '0'))
    tval = lambda k: 0 if b0.tag[k // 2][k % 2] is None else 2 * (b0.tag[k // 2][k % 2] + 1) + b0.dirty[k // 2][k % 2]
    root = ([f"--pc: {st['pc']}", f"--sp: {st['sp']}", f"--fp: {st['fp']}", f"--optr: {st['optr']}", f"--pst: {st['pst']}", f"--steps: {st['steps']}",
             f"--stop: {stall}", f"--cw: {cw}"] + [f"--T{k}: {tval(k)}" for k in range(NL)] + [f"--F{s_}: {b0.fifo[s_]}" for s_ in range(NSET)] +
            [f"--W{k}_{j}: {b0.words[k // 2][k % 2][j]}" for k in range(NL) for j in range(4)])
    chain = '<i class="end"></i>'
    for _ in range(K): chain = f'<i class="f"><i class="x"><i class="c">{chain}</i></i></i>'
    css = [c for c in css if not c.startswith('#cpu')]
    page = (f'<!doctype html><html lang="en"><meta charset="utf-8"><title>CSS CPU chain bench</title><style>{static}' + "\n".join(props + css) +
            f'</style><div id="root" style="{"; ".join(root)}">{chain}</div></html>')
    end = sm.st if not stall else st
    json.dump({'pc': end['pc'], 'sp': end['sp'], 'fp': end['fp'], 'steps': end['steps'], 'K': K, 'stall': stall}, open(outp + '.json', 'w'))
    open(outp, 'w').write(page); print(outp, len(page), 'bytes; bench pass', sm.passes, 'K', K, 'stall', stall); sys.exit()

# ---------------- HTML
STATIC_CELLS = set(range(R.LAYOUT['data_base'] + R.SDATA - ROM, image.get('init', R.LAYOUT['init']) + R.SDATA - ROM))
LIVE = STATIC_CELLS
mem_html = "" if 'nomem' in ABL else "".join(memtree.html(image["ram"], list(range(w, RAMN, WB)), WOFF, prefix=str(w), live=LIVE) for w in range(WB))
mem_html += "".join(memtree.html(image["ram"], list(range(OUT_BASE - ROM + w, OUT_BASE - ROM + OUT_SIZE, WB)), WOFF, prefix=f"k{w}") for w in range(WB))
rom_html = '<div class="mem">' + "".join(f'<div class="w" style="anchor-name: --r{a}"><i class="rom" style="width: {image["rom"][a] + WOFF}px"></i></div>' for a in sorted(ROMNZ)) + '</div>\n'
console = "" if 'nocon' in ABL else "\n".join(f'<div class="oc oc{i}"><b></b></div>' for i in range(OUT_SIZE))
subj = "".join(f'<div class="reg" style="height: {H}px"><div class="sub" style="view-timeline-name: --{n}; top: calc(({e} + {OFF}) * 1px)"></div></div>' for n, H, OFF, e in regs)
chain = f'<div class="ex"><div class="regs" aria-hidden="true">{subj}</div></div>'
for _ in range(K): chain = f'<i class="f"><i class="x"><i class="c">{chain}</i></i></i>'
ports = "".join(f'<div class="rp rp{i}"><div class="vp vp{i}">' for i in range(2 * WB))
blurb = (f"<p>No font: style alone runs the bytecode. Each layout pass runs up to {K} instructions as a chain of nested elements "
         f"(fetch and decode, execute, commit) out of a 2-way, 32-line cache of RAM held in custom properties. The first cache "
         f"miss stops the chain; the next pass fills the line, and prefetches the next, through anchor-size() read ports.</p>"
         f"<pre>{_h.escape(image.get('source', ''))}</pre>")
page = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>JavaScript on a CSS CPU</title>
<style>
{lbl.header('js-minus-js/exp/csscpu/gencpu.py', 'js-minus-js/exp/csscpu/README.md')}
{static}
{chr(10).join(props)}
{chr(10).join(css)}
</style>
{mem_html}{rom_html}<div class="con"></div>
{console}
<div id="clk"><div id="cpu">
<div class="head"{' hidden' if 'nohead' in ABL else ''}>
<h1>JavaScript on a pure-CSS CPU</h1>
{blurb}
<div class="status">steps <b class="num" style="--v: var(--steps)"></b> pc <b class="num" style="--v: var(--pc)"></b> sp <b class="num" style="--v: var(--sp)"></b>
 halt <b class="num" style="--v: var(--halt)"></b></div>
</div>
{ports}<div class="fl">{chain}</div>{'</div></div>' * (2 * WB)}
</div></div>
</html>
"""
import re, collections
_dup = [n for n, c in collections.Counter(re.findall(r'@property (--[\w-]+)', page)).items() if c > 1]
assert not _dup, f'properties registered twice (memtree.py has its own): {_dup}'
open(outp, 'w').write(page)
print(outp, len(page), 'bytes; K', K, 'ISSUE', ISSUE, '; registers', len(regs), '; properties', len(P))
