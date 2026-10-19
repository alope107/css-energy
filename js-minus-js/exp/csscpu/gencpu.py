#!/usr/bin/env python3
"""gencpu.py image.json out.html — the pure-CSS CPU: a CPU-only page (gen_fvm4.py's role) with no font. Style alone runs
the instructions; layout only fills the cache and moves the registers. The design is sim.py's, which is its oracle.

A pass (ISSUE passes per frame, gen_fvm4's frame gate):
  #cpu      the registers (view timelines, as gen_fvm4's), the frame gate, and the pending miss's victim line
  .rp/.vp   four read ports (one per bank) read the pending block's words from the ROM and RAM leaves
  .fl       the fill: the victim line takes the block (a dirty victim's words go to the write set first)
  K levels  .f fetch and decode > .x execute (@container style(--op: k)) > .c commit; an instruction runs only if every
            word it touches is cached (and, for output, the write set is free); the first that can't stops the chain,
            noting its missing block (--pend) for the next pass's fill
  .ex       the registers' view-timeline subjects at the chain's final state; the write set goes to the RAM channels
Cache: 16 sets x 2 ways x 4 words, set (b + b / 16 + b / 256) mod 16 of block b; --T<line> = 2 * (block + 1) + dirty
(0: empty), --F<set> the next victim way, --W<line>_<word> the words. RAM is memtree.py's, the console gen_fvm4's.
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

# ---------------- registers: (name, H, OFF), value range [-OFF, H - OFF); the subject's expression at the chain's end
regs = [("pc", A15, 0, "var(--pc)"), ("rsp", A15, 0, "var(--sp)"), ("rfp", A15, 0, "var(--fp)"), ("optr", 256, 0, "var(--optr)"),
        ("pst", A15, 0, "var(--pst)"), ("steps", 1 << 21, 0, "var(--steps)"), ("halt", 2, 0, "var(--halt)"), ("pend", 8192, 0, "var(--pend)"),
        ("init", 2, 0, "1"), ("k", 16, 0, "var(--nk)"), ("par", 2, 0, "var(--npar)"), ("tprev", 65536, 0, "var(--t)")]
regs += [(f"T{k}", 16384, 0, f"var(--T{k})") for k in range(NL)] + [(f"F{s}", 2, 0, f"var(--F{s})") for s in range(NSET)]
regs += [(f"W{k}_{j}", M20, M20 // 2, f"var(--W{k}_{j})") for k in range(NL) for j in range(4)]
WREGS = [(f"wa{w}{c}", BANKN + 1, 0, f"var(--nwa{w}{c})") for w in range(WB) for c in CH] + \
        [(f"wd{w}{c}", 1 << 21, 1 << 20, f"var(--nwd{w}{c})") for w in range(WB) for c in CH]
regs += WREGS
WNAMES = [r[0] for r in WREGS]

# ---------------- #cpu: effective state, frame gate, the fill's victim (all from the registers)
cpu = ["--first: calc(1 - var(--init));",
       f"--sp: calc(var(--init) * var(--rsp) + var(--first) * {sp0});", f"--fp: calc(var(--init) * var(--rfp) + var(--first) * {sp0});",
       "--fresh: calc(min(1, max(var(--t) - var(--tprev), var(--tprev) - var(--t))));",
       f"--go: calc(min(1, var(--fresh) + min(1, max(0, {ISSUE} - var(--k)))));",
       f"--chan: calc({ISSUE} * var(--par) + (1 - var(--fresh)) * var(--k));",
       f"--nk: calc(var(--fresh) + (1 - var(--fresh)) * min({ISSUE}, var(--k) + 1));",   # saturates, so frames settle (ENGINE_NOTES 16)
       "--npar: calc(var(--fresh) * (1 - var(--par)) + (1 - var(--fresh)) * var(--par));",
       # the fill: block fb into set fs's victim way fv (line fk); a dirty victim (block fvb) is written back
       "--fon: calc(var(--go) * min(1, var(--pend)));", "--fb: max(0, var(--pend) - 1);",
       "--fs: mod(var(--fb) + round(down, var(--fb) / 16) + round(down, var(--fb) / 256), 16);",
       "--fv: " + sel("fs", NSET, lambda s: f"var(--F{s})") + ";", "--fk: calc(2 * var(--fs) + var(--fv));",
       "--fT: " + sel("fk", NL, lambda k: f"var(--T{k})") + ";",
       "--fd: calc(var(--fon) * mod(var(--fT), 2));", "--fvb: calc(round(down, var(--fT) / 2) - 1);",
       "--fk1: calc(var(--fon) * (var(--fk) + 1));", "--pend0: calc((1 - var(--fon)) * var(--pend));",
       f"--rb: clamp(0, var(--fb), {BLKS - 1});", "--rbh: round(down, var(--rb) / 64);", "--rbl: calc(var(--rb) - 64 * var(--rbh));"]
cpu += [f"--fwd{w}: " + sel("fk", NL, lambda k, w=w: f"var(--W{k}_{w})") + ";" for w in range(WB)]

# ---------------- reads: a word through the cache. Declarations for read n of address A: block b, word o, set s, the two
# ways' tags g / G, hits h / H, miss m, slot q = 4 * line + word u, and (unless tags only) the word v<n> by a two-level if().
def lookup(n, A):
    b = f"var(--b{n})"
    return [f"--b{n}: round(down, ({A}) / 4);", f"--u{n}: mod({A}, 4);",
            f"--z{n}: mod({b} + round(down, {b} / 16) + round(down, {b} / 256), 16);",
            f"--g{n}: " + sel(f"z{n}", NSET, lambda s: f"var(--T{2 * s})") + ";",
            f"--G{n}: " + sel(f"z{n}", NSET, lambda s: f"var(--T{2 * s + 1})") + ";",
            f"--h{n}: {eq(f'round(down, var(--g{n}) / 2)', f'{b} + 1')};", f"--H{n}: {eq(f'round(down, var(--G{n}) / 2)', f'{b} + 1')};",
            f"--m{n}: calc(1 - var(--h{n}) - var(--H{n}));", f"--q{n}: calc(8 * var(--z{n}) + 4 * var(--H{n}) + var(--u{n}));"]
def read(n, A):
    inner = lambda hi: "if(" + " ".join(f"style(--ql{n}: {lo}): var(--W{(16 * hi + lo) // 4}_{lo % 4});" for lo in range(15)) + f" else: var(--W{(16 * hi + 15) // 4}_3))"
    return lookup(n, A) + [f"--qh{n}: round(down, var(--q{n}) / 16);", f"--ql{n}: mod(var(--q{n}), 16);",
                           f"--v{n}: " + sel(f"qh{n}", NL * 4 // 16, inner) + ";"]
LOOKUP = ("b", "u", "z", "g", "G", "h", "H", "m", "q")
READ_PROPS = lambda n: [x + n for x in LOOKUP + ("qh", "ql", "v")]

# ---------------- instructions
pc, sp, fp, imm, simm = v("pc"), v("sp"), v("fp"), v("imm"), v("simm")
z1 = eq("var(--vs1)", 0)
BINE = {'ADD': s20("var(--vs2) + var(--vs1)"), 'SUB': s20("var(--vs2) - var(--vs1)"), 'MUL': s20("var(--vs2) * var(--vs1)"),
        'DIV': f"calc((1 - {z1}) * round(to-zero, var(--vs2) / (var(--vs1) + {z1})))",
        'MOD': f"calc((1 - {z1}) * (var(--vs2) - var(--vs1) * round(to-zero, var(--vs2) / (var(--vs1) + {z1}))))",
        'LT': "clamp(0, var(--vs1) - var(--vs2), 1)", 'GT': "clamp(0, var(--vs2) - var(--vs1), 1)",
        'LE': "clamp(0, var(--vs1) - var(--vs2) + 1, 1)", 'GE': "clamp(0, var(--vs2) - var(--vs1) + 1, 1)",
        'EQ': eq("var(--vs1)", "var(--vs2)"), 'NE': f"calc(1 - {eq('var(--vs1)', 'var(--vs2)')})",
        'AND': f"calc((1 - {z1}) * (1 - {eq('var(--vs2)', 0)}))", 'OR': f"min(1, calc((1 - {z1}) + (1 - {eq('var(--vs2)', 0)})))"}
S1, S2 = ("s1", f"{sp} - 1"), ("s2", f"{sp} - 2")
# op: (reads [(name, address)], write (address, value, a read whose slot it reuses or None), {register: next value})
OPS = {'NOP': ([], None, {}),
       'PUSHI': ([], (sp, imm, None), {'sp': f"calc({sp} + 1)"}),
       'LOADG': ([("ra", imm)], (sp, "var(--vra)", None), {'sp': f"calc({sp} + 1)"}),
       'STOREG': ([S1], (imm, "var(--vs1)", None), {'sp': f"calc({sp} - 1)"}),
       'LOADL': ([("ra", f"{fp} + {simm}")], (sp, "var(--vra)", None), {'sp': f"calc({sp} + 1)"}),
       'STOREL': ([S1], (f"{fp} + {simm}", "var(--vs1)", None), {'sp': f"calc({sp} - 1)"}),
       'LOADI': ([S1, ("ra", "mod(var(--vs1), 32768)")], (None, "var(--vra)", "s1"), {}),
       'STOREI': ([S1, S2], ("mod(var(--vs2), 32768)", "var(--vs1)", None), {'sp': f"calc({sp} - 2)"}),
       'NOT': ([S1], (None, z1, "s1"), {}), 'NEG': ([S1], (None, s20("-1 * var(--vs1)"), "s1"), {}),
       'SHL13': ([S1], (None, s20("var(--vs1) * 8192"), "s1"), {}),
       'JMP': ([], None, {'pc': imm}),
       'JZ': ([S1], None, {'sp': f"calc({sp} - 1)", 'pc': f"calc({z1} * {imm} + (1 - {z1}) * ({pc} + 1))"}),
       'JNZ': ([S1], None, {'sp': f"calc({sp} - 1)", 'pc': f"calc((1 - {z1}) * {imm} + {z1} * ({pc} + 1))"}),
       'CALL': ([], (sp, f"calc({pc} + 1)", None), {'sp': f"calc({sp} + 1)", 'pc': imm}),
       'ENTER': ([], (sp, fp, None), {'fp': sp, 'sp': f"calc({sp} + 1 + {imm})"}),
       'RET': ([S1, ("ra", fp), ("rb", f"{fp} - 1")], (f"{fp} - 1 - {imm}", "var(--vs1)", None),
               {'sp': f"calc({fp} - {imm})", 'fp': "var(--vra)", 'pc': "mod(var(--vrb), 32768)"}),
       'POP': ([], None, {'sp': f"calc({sp} - 1)"}),
       'DUP': ([S1], (sp, "var(--vs1)", None), {'sp': f"calc({sp} + 1)"}),
       'HALT': ([], None, {'pc': pc}),
       'JMPI': ([S1], None, {'sp': f"calc({sp} - 1)", 'pc': "mod(var(--vs1), 32768)"}),
       'INCG': ([("ra", imm)], (None, s20("var(--vra) + 1"), "ra"), {}),
       'INCL': ([("ra", f"{fp} + {simm}")], (None, s20("var(--vra) + 1"), "ra"), {}),
       'IDX': ([S1, ("ra", imm), ("rb", "mod(var(--vra) + var(--vs1), 32768)")], (None, "var(--vrb)", "s1"), {}),
       'IDXL': ([S1, ("ra", f"{fp} + {simm}"), ("rb", "mod(var(--vra) + var(--vs1), 32768)")], (None, "var(--vrb)", "s1"), {})}
for o, e in BINE.items(): OPS[o] = ([S1, S2], (None, e, "s2"), {'sp': f"calc({sp} - 1)"})

def first_miss(names):
    """the block of the first missing access in names (dependency order), -1 for none"""
    e = "-1"
    for n in reversed(names): e = f"calc(var(--m{n}) * var(--b{n}) + (1 - var(--m{n})) * {e})"
    return e
def commit(nx, done="1"):
    return [f"--npc: {nx.get('pc', f'calc({pc} + {done})')};", f"--nsp: {nx.get('sp', sp)};", f"--nfp: {nx.get('fp', fp)};",
            f"--nsteps: calc(var(--steps) + {done});"]
op_rules = []
for o, (rds, wr, nx) in OPS.items():
    d = []
    for n, A in rds: d += read(n, A)
    acc = [n for n, _ in rds]
    if wr:
        A, val, reuse = wr
        if reuse is None: d += lookup("w", A); acc.append("w"); wn = "w"
        else: wn = reuse
        d += [f"--slot: calc(var(--ok) * (1 + var(--q{wn})));", f"--wval: {val};", f"--wT: calc(2 * var(--b{wn}) + 3);"]
    if acc: d += [f"--ok: calc(1 - min(1, calc({' + '.join(f'var(--m{n})' for n in acc)})));", f"--mb: {first_miss(acc)};"]
    else: d.append("--ok: 1;")
    d += commit(nx)
    if o == 'HALT': d += ["--nstop: 1;", "--nhalt: 1;"]
    op_rules.append((OP[o], d))

# PRINT family (uarch.Machine.print_service, gen_fvm4's service): up to 4 console cells per execution, one per bank; a string
# chunk ends at its block (the block's line must be cached), at a NUL (the value is out) or a newline (taken); until the
# value is out the instruction repeats (npc = pc) and --pst carries the position. Output needs the pass's write set free.
pv = "var(--vs1)"
pr = read("s1", f"{sp} - 1") + [
    f"--pp: calc({pv} + {STRTAG});",
    f"--isStr: calc(clamp(0, var(--pp) - {STR_LO - 1}, 1) * clamp(0, {STR_HI} - var(--pp), 1));",
    f"--isBool: calc((1 - var(--isStr)) * var(--prB) * ({eq(pv, 0)} + {eq(pv, 1)}));",
    "--isNum: calc((1 - var(--isStr)) * (1 - var(--isBool)));",
    "--pq: calc(min(1, var(--pst)) * var(--pst) + (1 - min(1, var(--pst))) * var(--pp));",
    f"--pdone: calc(var(--isStr) * {eq('var(--pq)', STR_LO)});", "--pj0: mod(var(--pq), 4);"]
pr += lookup("p", "var(--pq)") + ["--pln: calc(2 * var(--zp) + var(--Hp));"]
pr += [f"--pw{j}: " + sel("pln", NL, lambda k, j=j: f"var(--W{k}_{j})") + ";" for j in range(4)]
pr += ["--mpp: calc(var(--isStr) * (1 - var(--pdone)) * var(--mp));",
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
       "--pn: calc(var(--isStr) * (var(--pe) + var(--ptNul) * var(--prSP)) + (1 - var(--isStr)) * clamp(0, var(--ptot) - var(--pbase), 4));",
       "--pfin: calc(var(--isStr) * var(--ptNul) + (1 - var(--isStr)) * clamp(0, var(--pbase) + 5 - var(--ptot), 1));",
       "--pnl: calc(var(--isStr) * (var(--ptNL) + var(--ptNul) * var(--prLN)) + (1 - var(--isStr)) * var(--pfin) * var(--prLN));",
       "--npst: calc(var(--isStr) * (1 - var(--ptNul)) * (var(--pq) + var(--pe) + var(--ptNL)) + (1 - var(--isStr)) * (1 - var(--pfin)) * (var(--pph) + 1));"]
for i in range(4):
    pr.append(f"--pch{i}: calc(var(--isStr) * (var(--pr{i}) * var(--pb{i}) + {eq('var(--pe)', i)} * var(--ptNul) * var(--prSP) * 32)"
              f" + (1 - var(--isStr)) * clamp(0, var(--pn) - {i}, 1) * var(--pnb{i}));")
pr += ["--ok: calc((1 - min(1, calc(var(--ms1) + var(--mpp)))) * (1 - var(--cw)));",
       "--mb: calc(var(--ms1) * var(--bs1) + (1 - var(--ms1)) * (var(--mpp) * var(--bp) + (1 - var(--mpp)) * -1));"]
pr += commit({'pc': f"calc({pc} + var(--pfin))", 'sp': f"calc({sp} - var(--pfin))"}, "var(--pfin)")
PR_FLAGS = {o: (int(o.endswith('LN')), int(o.endswith('SP')), int(o.startswith('PRINTB'))) for o in PRINTOPS}
# PUTC: one cell, or a newline
putc = read("s1", f"{sp} - 1") + [f"--pnl: {eq(pv, 10)};", "--pn: calc(1 - var(--pnl));", f"--pch0: {pv};", "--npst: var(--pst);",
                                  "--ok: calc((1 - var(--ms1)) * (1 - var(--cw)));", "--mb: calc(var(--ms1) * var(--bs1) - (1 - var(--ms1)));"]
putc += commit({'sp': f"calc({sp} - 1)"})
op_rules.append((OP['PUTC'], putc))
# output (PRINT or PUTC): cell i of the chunk goes to optr + i, bank (optr + i) mod 4 (OUT_BASE is a multiple of 4)
out = ["--pout: var(--ok);", "--ncw: min(1, var(--pn));",
       f"--noptr: mod(var(--pnl) * (round(down, (var(--optr) + var(--pn)) / {COLS}) + 1) * {COLS} + (1 - var(--pnl)) * (var(--optr) + var(--pn)), {OUT_SIZE});"]
for w in range(WB):
    out += [f"--pi{w}: mod({w} - var(--optr), 4);", f"--dp{w}: clamp(0, var(--pn) - var(--pi{w}), 1);",
            f"--nwA{w}: calc(var(--dp{w}) * (round(down, ({OUT_BASE - ROM} + mod(var(--optr) + var(--pi{w}), {OUT_SIZE})) / 4) + 1));",
            f"--nwD{w}: calc(" + " + ".join(f"{eq(f'var(--pi{w})', i)} * var(--pch{i})" for i in range(4)) + ");"]

# ---------------- the page's CSS
P = ["pc", "rsp", "rfp", "sp", "fp", "optr", "pst", "steps", "halt", "pend", "init", "k", "par", "tprev", "first", "fresh", "go", "chan", "nk", "npar",
     "fon", "fb", "fs", "fv", "fk", "fT", "fd", "fvb", "fk1", "pend0", "rb", "rbh", "rbl", "t", "stop", "cw",
     "op", "imm", "simm", "ispr", "isout", "ok", "mb", "npc", "nsp", "nfp", "nsteps", "nstop", "nhalt", "slot", "wval", "wT", "pout", "ncw",
     "noptr", "npst", "prLN", "prSP", "prB", "pp", "isStr", "isBool", "isNum", "pq", "pdone", "pj0", "pln", "mpp", "pa", "pneg", "pL", "ptot",
     "pph", "pbase", "pe", "pvE", "pbE", "ptNul", "ptNL", "pn", "pfin", "pnl"]
P += [r[0] for r in regs if r[0] not in P]
P += [f"{x}{w}" for w in range(WB) for x in ("fwd", "mval", "wA", "wD", "nwA", "nwD", "pi", "dp", "pw")]
P += [f"{x}{i}" for i in range(4) for x in ("pg", "pnb", "pb", "pc", "pr", "pch")]
P += [f"n{r[0]}" for r in WREGS]
for n in ("f", "s1", "s2", "ra", "rb"): P += READ_PROPS(n)
P += [x + n for n in ("w", "p") for x in LOOKUP]
P = list(dict.fromkeys(P))
props = [lbl.section('Registered properties', 'registers, the chain\'s state and temps: integers, inherited')]
# temps that only the element declaring them reads (.x's reads and PRINT scratch) don't inherit: an inherited registered
# property is carried by every element below (ENGINE_NOTES 4)
LOCAL = set()
for n in ("s1", "s2", "ra", "rb"): LOCAL |= set(READ_PROPS(n))
LOCAL |= {x + n for n in ("w", "p") for x in LOOKUP} | {"vf", "qhf", "qlf", "uf", "zf", "gf", "Gf", "hf", "Hf", "qf"}
LOCAL |= {"pp", "isStr", "isBool", "isNum", "pq", "pdone", "pj0", "pln", "mpp", "pa", "pneg", "pL", "ptot", "pph", "pbase", "pe", "pvE", "pbE",
          "ptNul", "ptNL", "pn", "pfin", "pnl", "prLN", "prSP", "prB"}
LOCAL |= {f"{x}{i}" for i in range(4) for x in ("pg", "pnb", "pb", "pc", "pr", "pch", "pw", "pi", "dp")}
if os.environ.get('NONINH', '1') != '1': LOCAL = set()
props += [f'@property --{n} {{ syntax: "<integer>"; inherits: {"false" if n in LOCAL else "true"}; initial-value: 0; }}' for n in P]

css = [lbl.section('CPU: clock, registers, frame gate, the fill\'s victim', 'on #cpu: the registers are view timelines (gen_fvm4.py)'),
       "#clk { animation: wc 100s linear infinite; }\n@keyframes wc { from { --t: 0; } to { --t: 60000; } }",
       "#cpu {\n  timeline-scope: " + ", ".join(f"--{r[0]}" for r in regs if r[0] not in WNAMES) +
       ";\n  animation-name: " + ", ".join(f"r-{r[0]}" for r in regs) + ";\n  animation-timeline: " + ", ".join(f"--{r[0]}" for r in regs) +
       ";\n  animation-duration: auto;\n  animation-timing-function: linear;\n  animation-fill-mode: both;\n  " + "\n  ".join(cpu) + "\n}"]
css.append(lbl.group('Register keyframes', 'each register\'s view timeline mapped onto its value range'))
css += [f"@keyframes r-{n} {{ from {{ --{n}: {H - OFF}; }} to {{ --{n}: {-1 - OFF}; }} }}" for n, H, OFF, _ in regs]

def mux(p, n, leaf, default):
    outer = []
    for j in range((n + 63) // 64):
        inner = " ".join(f"style(--{p}l: {i}): {leaf(j * 64 + i)};" for i in range(64) if j * 64 + i < n)
        outer.append(f"style(--{p}h: {j}): if({inner} else: {default});")
    return f"if({' '.join(outer)} else: {default})"
ROMNZ = {a for a, x in enumerate(image['rom']) if x}
def leafname(a): return f"--r{a}" if a < ROM else f"--c{a - ROM}"
css.append(lbl.group(f'Read ports: one per bank ({WB})', 'the pending block\'s word in this bank: a two-level if() picks the leaf, anchor-size() reads it'))
for w in range(WB):
    css.append(f"#cpu {{ --sR{w}: " + mux("rb", BLKS, lambda b, w=w: leafname(4 * b + w), f"--c{w}") + "; }")
    css.append(f".rp{w} {{ width: anchor-size(var(--sR{w}) width, {WOFF}px); }} .vp{w} {{ --mval{w}: calc(100cqi / 1px - {WOFF}); }}")

css.append(lbl.section('The fill', 'the victim line takes the pending block; a dirty victim\'s words are the pass\'s write set'))
css.append(".fl { --stop: calc(1 - var(--go) * (1 - var(--halt))); --pend: var(--pend0); --cw: var(--fd);\n  " +
           " ".join(f"--wA{w}: calc(var(--fd) * (var(--fvb) - {RB0 - 1})); --wD{w}: var(--fwd{w});" for w in range(WB)) + " }")
css += [f"@container style(--fk1: {k + 1}) {{ .fl {{ --T{k}: calc(2 * var(--fb) + 2); --F{k // 2}: {1 - k % 2}; " +
        " ".join(f"--W{k}_{j}: var(--mval{j});" for j in range(4)) + " } }" for k in range(NL)]

css.append(lbl.section('Instructions', f'{K} levels of .f (fetch, decode) > .x (execute) > .c (commit), display: contents'))
css.append(lbl.group('.f: fetch the word at pc unless the chain has stopped'))
css.append(".f { --op: 255; --mf: 0; --bf: 0; --ispr: 0; --isout: 0; }")
P0 = OP[PRINTOPS[0]]; assert [OP[o] for o in PRINTOPS] == list(range(P0, P0 + 6))
css.append("@container style(--stop: 0) { .f { " + " ".join(read("f", pc)) +
           " --op: calc(var(--mf) * 255 + (1 - var(--mf)) * round(down, var(--vf) / 8192)); --imm: mod(var(--vf), 8192);"
           " --simm: calc(var(--imm) - 8192 * min(1, round(down, var(--imm) / 4096)));"
           f" --ispr: calc(clamp(0, var(--op) - {P0 - 1}, 1) * clamp(0, {P0 + 6} - var(--op), 1)); --isout: calc(var(--ispr) + {eq('var(--op)', OP['PUTC'])}); }} }}")
css.append(lbl.group('.x: execute', 'defaults (no instruction: nothing commits; a fetch miss stalls), then one rule per opcode'))
css.append(".x { --ok: calc(2 - 2 * var(--mf)); --mb: var(--bf); --slot: 0; --pout: 0; --nstop: 0; --nhalt: var(--halt); }")
css += [f"@container style(--op: {k}) {{ .x {{ {' '.join(d)} }} }}" for k, d in op_rules]
css += [f"@container style(--op: {OP[o]}) {{ .x {{ --prLN: {a}; --prSP: {b}; --prB: {c}; }} }}" for o, (a, b, c) in PR_FLAGS.items()]
css.append(f"@container style(--ispr: 1) {{ .x {{ {' '.join(pr)} }} }}")
css.append(f"@container style(--isout: 1) {{ .x {{ {' '.join(out)} }} }}")
css.append(lbl.group('.c: commit', 'registers on success; the stall (stop, the missing block); output; the one written word'))
css.append("@container style(--ok: 1) { .c { --pc: var(--npc); --sp: var(--nsp); --fp: var(--nfp); --steps: var(--nsteps); --stop: var(--nstop); --halt: var(--nhalt); } }")
css.append("@container style(--ok: 0) { .c { --stop: 1; --pend: calc(var(--mb) + 1); } }")
css.append("@container style(--pout: 1) { .c { --optr: var(--noptr); --pst: var(--npst); --cw: var(--ncw); " +
           " ".join(f"--wA{w}: var(--nwA{w}); --wD{w}: var(--nwD{w});" for w in range(WB)) + " } }")
css += [f"@container style(--slot: {4 * k + j + 1}) {{ .c {{ --W{k}_{j}: var(--wval); --T{k}: var(--wT); }} }}" for k in range(NL) for j in range(4)]
ABL = os.environ.get('ABL', '').split(',')     # timing ablations (results wrong): noslot, noops
if 'noslot' in ABL: css = [c for c in css if not c.startswith('@container style(--slot:')]
if 'noops' in ABL: css = [c for c in css if not c.startswith('@container style(--op:')]

css.append(lbl.section('Export', 'the write set into the RAM channels (gen_fvm4.py\'s rotation); the registers\' subjects'))
ex = []
for w in range(WB):
    for i, c in enumerate(CH):
        s_ = f"var(--go) * {eq('var(--chan)', i)}"
        rel = f"min(1, var(--wA{w})) * {eq(f'var(--wA{w})', f'var(--wa{w}{c})')}"
        ex += [f"--nwa{w}{c}: calc({s_} * var(--wA{w}) + (1 - {s_}) * (1 - {rel}) * var(--wa{w}{c}));",
               f"--nwd{w}{c}: calc({s_} * var(--wD{w}) + (1 - {s_}) * var(--wd{w}{c}));"]
css.append(".ex { " + " ".join(ex) + " }")

css.append(lbl.section('RAM', f'memtree.py: {len(CH)} write channels per bank, each a decode tree over the bank\'s cells'))
css.append(memtree.scope(WNAMES))
_sp, _sc = memtree.shared(); props += [lbl.group('RAM write channels')] + _sp; css += _sc
for w in range(WB):
    _mp, _mc = memtree.css(CH, {n: (H, OFF) for n, H, OFF, _ in WREGS if n[2] == str(w)}, BANKN, WOFF, prefix=str(w))
    props += _mp; css += [lbl.group(f'Bank {w}')] + _mc
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
# ---------------- BENCH=1: the chain alone (chainbench.js), started from the state of FizzBuzz-class pass sim.py runs with
# all K levels executing (STALL=1: the chain stopped at its top). The root's inline style holds the state.
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
LIVE = set(range(OUT_BASE - ROM, OUT_BASE - ROM + OUT_SIZE)) | STATIC_CELLS
mem_html = "".join(memtree.html(image["ram"], list(range(w, RAMN, WB)), WOFF, prefix=str(w), live=LIVE) for w in range(WB))
rom_html = '<div class="mem">' + "".join(f'<div class="w" style="anchor-name: --r{a}"><i class="rom" style="width: {image["rom"][a] + WOFF}px"></i></div>' for a in sorted(ROMNZ)) + '</div>\n'
console = "\n".join(f'<div class="oc oc{i}"><b></b></div>' for i in range(OUT_SIZE))
subj = "".join(f'<div class="reg" style="height: {H}px"><div class="sub" style="view-timeline-name: --{n}; top: calc(({e} + {OFF}) * 1px)"></div></div>' for n, H, OFF, e in regs)
chain = f'<div class="ex"><div class="regs" aria-hidden="true">{subj}</div></div>'
for _ in range(K): chain = f'<i class="f"><i class="x"><i class="c">{chain}</i></i></i>'
ports = "".join(f'<div class="rp rp{w}"><div class="vp vp{w}">' for w in range(WB))
blurb = (f"<p>No font: style alone runs the bytecode. Each layout pass runs up to {K} instructions as a chain of nested elements "
         f"(fetch and decode, execute by <code>@container style(--op)</code>, commit), out of a 2-way, 32-line cache of RAM held in custom "
         f"properties; the first cache miss stops the chain, and the next pass fills the line through anchor-size() read ports.</p>"
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
<div class="head">
<h1>JavaScript on a pure-CSS CPU</h1>
{blurb}
<div class="status">steps <b class="num" style="--v: var(--steps)"></b> pc <b class="num" style="--v: var(--pc)"></b> sp <b class="num" style="--v: var(--sp)"></b>
 halt <b class="num" style="--v: var(--halt)"></b></div>
</div>
{ports}<div class="fl">{chain}</div>{'</div></div>' * WB}
</div></div>
</html>
"""
import re, collections
_dup = [n for n, c in collections.Counter(re.findall(r'@property (--[\w-]+)', page)).items() if c > 1]
assert not _dup, f'properties registered twice (memtree.py has its own): {_dup}'
open(outp, 'w').write(page)
print(outp, len(page), 'bytes; K', K, 'ISSUE', ISSUE, '; registers', len(regs), '; properties', len(P))
