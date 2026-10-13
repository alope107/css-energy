#!/usr/bin/env python3
"""gen_fvm4.py image.json fcpu4 out.html [--issue=K] — the HarfBuzz-CPU page for the 4-word-line font (cpu4.py).

RAM is four banks (address mod 4), each its own decode tree with its own write channels, so a whole cache line
(one aligned block) is written back or filled in one service: four bank read ports and up to four writes per issue.
A read port picks a cell's anchor name with a two-level if() (high digit, then low), then reads it with one
anchor-size(). Per cache line the page reads back 8 spans (tag + victim flag, 7 x three value nibbles; the
last also carries the four word states).

(gen_fvm.py notes follow.)
gen_fvm.py image.json fcpu out.html [--issue=K] — the CSS VM with HarfBuzz as the CPU. No script in the page.

Memory, write channels, console and clock are gen_vm.py's. The CPU is a font (fcpu.woff2 from fvm_build.py):
each layout pass renders the machine state as one line of text (a counter per state digit), Blink shapes it
with feature cv01 (S micro-cycles of a cached CPU in GSUB), and the widths of ~60 spans are the next state.
Between shapings CSS services the trap the font stopped on: cache miss (one RAM read port), dirty write-back
(one write channel), MUL/DIV/MOD/SHL13, PUTC.
"""
import json, sys, base64, html as _h, os
UI = os.environ.get('UI') == '1'     # typed-program page: editor + scan readback + compile chain (ccpage5) + Run/Edit
import zoomfix, memtree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uarch import PRINTOPS, STRTAG, STR_LO, STR_HI, PRINT_CHUNK

image = json.load(open(sys.argv[1])); pre = sys.argv[2]; outp = sys.argv[3]
meta = json.load(open(pre + '.json')); font64 = base64.b64encode(open(pre + '.woff2', 'rb').read()).decode()
K = int(next((a.split('=')[1] for a in sys.argv if a.startswith('--issue=')), 2))
RAMMODE = 'tree'
N, S = meta['N'], meta['S']
ROM, RAMN, WOFF = 4096, image['ramSize'], 1 << 20
WB = meta['B']; assert WB == 4
BANKN = RAMN // WB
OUT_BASE, ROWS, COLS = image['outBase'], image['rows'], image['cols']
OUT_SIZE = ROWS * COLS
CH = 'ABCD'[:2 * K]
CV = [tuple(v) for v in meta['cvals']]
ci = lambda *v: CV.index(tuple(v))
I_START, I_MISS, I_WFAIL, I_PUTC, I_HALT = ci('S'), ci('T', 'MISS'), ci('T', 'WFAIL'), ci('T', 'PUTC'), ci('T', 'HALT')
I_EXT = {op: ci('T', 'EXT_' + op) for op in ['MUL', 'DIV', 'MOD', 'SHL13']}
I_PR = {op: ci('T', 'EXT_' + op) for op in PRINTOPS}     # the PRINT family: serviced below, up to PRINT_CHUNK console cells per shaping
assert PRINT_CHUNK == 4

def eq(x, c): return f"calc(1 - min(1, max(({x}) - ({c}), ({c}) - ({x}))))"     # 1 iff x == c (integers; both may be compound expressions)
def prop(name, init=0): return f'@property --{name} {{ syntax: "<integer>"; inherits: true; initial-value: {init}; }}'
def sgn20(x): return f"calc({x} - {1 << 20} * min(1, max(0, {x} - {(1 << 19) - 1})))"
M20 = 1 << 20

# ---------------- registers: (name, H, OFF). Value range [-OFF, H-OFF)
# 20-bit machine words are kept SIGNED (|v| < 2^19) in every property that crosses a var(): Chrome substitutes a
# registered <integer> by its serialization, which has 6 significant digits, so 1048575 (= -1) became 1048580.
regs = [("CR", 512, 0), ("PC", 8192, 0), ("SP", 8192, 0), ("FP", 8192, 0), ("MAR", 8192, 0), ("T1", M20, M20 // 2), ("T2", M20, M20 // 2),
        ("RES", M20, M20 // 2), ("init", 2, 0), ("optr", 256, 0), ("pst", 8192, 0), ("k", 16, 0), ("par", 2, 0), ("tprev", 65536, 0), ("steps", 1 << 21, 0), ("fok", 2, 0), ("nsh", 1 << 21, 0)]
regs += [(f"A{k}", 32768, 0) for k in range(N)] + [(f"V{k}_{s}", 32768, 0) for k in range(N) for s in range(7)]   # one H: a pair shares a scroller
if UI: regs.append(("ccok", 2, 0))
regs += [(f"wa{w}{c}", BANKN + 1, 0) for w in range(WB) for c in CH] + [(f"wd{w}{c}", 1 << 21, 1 << 20) for w in range(WB) for c in CH]
readback = {"CR": ["CR"], "PC": ["HPC"], "SP": ["HSP"], "FP": ["HFP"], "MAR": ["HMAR"], "T1": ["HT1lo", "HT1hi"], "T2": ["HT2lo", "HT2hi"]}
for k in range(N):
    readback[f"A{k}"] = [f"L{k}A"]
    for s in range(7): readback[f"V{k}_{s}"] = [f"L{k}V{s}"]

scalar = ["t", "fresh", "go", "chan", "kind", "resvin", "isMISS", "isWFAIL", "isPUTC", "isHALT", "isEXT", "isMUL", "isDIV", "isMOD", "isSHL",
          "v0", "v1", "vtag", "ch", "nl", "a2", "b1", "bs", "q", "ext", "mblk", "thany", "victim", "missv",
          "resT", "resvT", "rb", "rbh", "rbl", "ni", "first", "PCe", "SPe", "FPe", "RESe", "rbv", "rblo", "rbhi",
          # PRINT service (see svc / svc_inner below)
          "isPR", "prLN", "prSP", "prB", "pv", "pp", "isStr", "isBool", "isNum", "pq", "pdone", "pj0", "pa", "pneg", "pL", "ptot", "pph", "pbase",
          "pe", "pvE", "pbE", "ptNul", "ptNL", "pn", "pfin", "pnl", "pstT", "isOut"]
scalar += [f"{x}{i}" for i in range(4) for x in ["pg", "pnb", "pb", "pc", "pr", "pch"]]
scalar += [f"{x}{w}" for w in range(WB) for x in ["vval", "vdirty", "doWB", "doWrite", "waddr", "wval", "Wb", "mval", "pi", "doPut", "pchw"]]
scalar += [f"{x}{k}" for k in range(N) for x in ["Ae", "vf", "vd", "tag", "st", "present", "th", "isv", "fillv", "fillh", "clean", "tagT", "vdT", "vfT"]]
scalar += [f"Ve{k}_{s}" for k in range(N) for s in range(7)]
scalar += [f"{x}{k}_{w}" for k in range(N) for w in range(WB) for x in ["ws", "val", "dirty", "wsT", "valT"]]
props = [zoomfix.css()] + [prop(n) for n, _, _ in regs] + [prop(f"next-{n}") for n, _, _ in regs] + [prop(x) for x in scalar]
# per input cell counter values
for c in meta['cells']:
    if c['input']: props.append(prop(f"i{c['pos']}"))

# ---------------- effective state (initial values before the first committed pass)
sp0 = image['sp0']
eff = [f"--first: calc(1 - var(--init));",
       f"--PCe: calc(var(--init) * var(--PC));", f"--SPe: calc(var(--init) * var(--SP) + var(--first) * {sp0});",
       f"--FPe: calc(var(--init) * var(--FP) + var(--first) * {sp0});", "--RESe: calc(var(--init) * var(--RES));",
       f"--kind: calc(var(--init) * mod(var(--CR), 256) + var(--first) * {I_START});",
       "--resvin: calc(var(--init) * round(down, var(--CR) / 256));"]
def nib(k, i): return f"mod(round(down, var(--Ve{k}_{i // 3}) / {16 ** (i % 3)}), 16)"
for k in range(N):
    eff += [f"--Ae{k}: calc(var(--init) * var(--A{k}) + var(--first) * {2048 if k == 0 else 0});",
            f"--vf{k}: round(down, var(--Ae{k}) / 2048);", f"--tag{k}: mod(var(--Ae{k}), 2048);"]
    eff += [f"--Ve{k}_{s}: calc(var(--init) * var(--V{k}_{s}));" for s in range(7)]
    eff.append(f"--st{k}: round(down, var(--Ve{k}_6) / 256);")
    for w in range(WB):
        eff += [f"--ws{k}_{w}: mod(round(down, var(--st{k}) / {3 ** w}), 3);", f"--dirty{k}_{w}: {eq(f'var(--ws{k}_{w})', 2)};",
                f"--val{k}_{w}: " + sgn20("calc(" + " + ".join(f"{nib(k, 4 * j + w)} * {16 ** j}" for j in range(5)) + ")") + ";"]
    eff += [f"--present{k}: min(1, calc(" + " + ".join(f"var(--ws{k}_{w})" for w in range(WB)) + "));",
            f"--vd{k}: calc(var(--present{k}) + min(1, calc(" + " + ".join(f"var(--dirty{k}_{w})" for w in range(WB)) + ")));"]
# ---------------- frame gate (gen_vm)
gate = ["--fresh: calc(min(1, max(var(--t) - var(--tprev), var(--tprev) - var(--t))));",
        f"--go: calc(var(--fok){' * var(--ccok) * var(--run)' if UI else ''} * min(1, var(--fresh) + min(1, max(0, {K} - var(--k)))));",
        f"--chan: calc({K} * var(--par) + (1 - var(--fresh)) * var(--k));"]
# ---------------- trap service
svc = [f"--isMISS: {eq('var(--kind)', I_MISS)};", f"--isWFAIL: {eq('var(--kind)', I_WFAIL)};", f"--isPUTC: {eq('var(--kind)', I_PUTC)};",
       f"--isHALT: {eq('var(--kind)', I_HALT)};",
       f"--isMUL: {eq('var(--kind)', I_EXT['MUL'])};", f"--isDIV: {eq('var(--kind)', I_EXT['DIV'])};",
       f"--isMOD: {eq('var(--kind)', I_EXT['MOD'])};", f"--isSHL: {eq('var(--kind)', I_EXT['SHL13'])};",
       "--isEXT: calc(var(--isMUL) + var(--isDIV) + var(--isMOD) + var(--isSHL));",
       "--v0: calc(" + " + ".join(f"{k} * var(--vf{k})" for k in range(N)) + ");",
       f"--v1: mod(calc(var(--v0) + 1), {N});"]
for k in range(N): svc.append(f"--isv{k}: {eq('var(--v0)', k)};")
svc += ["--vtag: calc(" + " + ".join(f"var(--isv{k}) * var(--tag{k})" for k in range(N)) + ");"]
# ---- PRINT family (uarch.PRINTOPS): pop a value; a tagged string pointer prints its bytes, 0 / 1 with the B flag print
# false / true, anything else prints in decimal; SP / LN add a space / newline. One service writes up to 4 console cells
# (one write channel per bank); a string chunk also ends at its block (one block read per service) or at a newline. RESV is
# raised when the whole value is out; until then the CPU re-traps with the same value and the register --pst carries the
# position (a string's next byte address, or the chunks done for a number). Mirrors uarch.Machine.print_service.
pv = "var(--pv)"
svc += [f"--isPR: calc({' + '.join(eq('var(--kind)', I_PR[op]) for op in PRINTOPS)});",
        f"--prLN: calc({eq('var(--kind)', I_PR['PRINTLN'])} + {eq('var(--kind)', I_PR['PRINTBLN'])});",
        f"--prSP: calc({eq('var(--kind)', I_PR['PRINTSP'])} + {eq('var(--kind)', I_PR['PRINTBSP'])});",
        f"--prB: calc({eq('var(--kind)', I_PR['PRINTB'])} + {eq('var(--kind)', I_PR['PRINTBSP'])} + {eq('var(--kind)', I_PR['PRINTBLN'])});",
        "--pv: var(--b1);", f"--pp: calc({pv} + {STRTAG});",
        f"--isStr: calc(var(--isPR) * clamp(0, var(--pp) - {STR_LO - 1}, 1) * clamp(0, {STR_HI} - var(--pp), 1));",
        f"--isBool: calc(var(--isPR) * (1 - var(--isStr)) * var(--prB) * ({eq(pv, 0)} + {eq(pv, 1)}));",
        "--isNum: calc(var(--isPR) * (1 - var(--isStr)) * (1 - var(--isBool)));",
        # strings: the position is --pst once a chunk has been printed, else the pointer; its block goes to the read ports
        "--pq: calc(min(1, var(--pst)) * var(--pst) + (1 - min(1, var(--pst))) * var(--pp));",
        f"--pdone: calc(var(--isStr) * {eq('var(--pq)', STR_LO)});",          # the lib's DONE marker: prints nothing
        "--pj0: mod(var(--pq), 4);",
        "--mblk: calc(var(--isStr) * round(down, var(--pq) / 4) + (1 - var(--isStr)) * round(down, var(--MAR) / 4));",
        # numbers and booleans: the text is sign, digits (or true / false), then the space if SP; --pst counts chunks done
        f"--pa: max({pv}, -1 * {pv});", f"--pneg: clamp(0, -1 * {pv}, 1);",
        "--pL: calc(1 + " + " + ".join(f"clamp(0, var(--pa) - {10 ** d - 1}, 1)" for d in range(1, 6)) + ");",
        f"--ptot: calc(var(--isNum) * (var(--pneg) + var(--pL)) + var(--isBool) * (5 - {pv}) + var(--prSP));",
        "--pph: calc((1 - var(--isStr)) * var(--pst));", "--pbase: calc(4 * var(--pph));"]
for i in range(4):
    g = f"var(--pg{i})"
    inum = f"clamp(0, var(--pneg) + var(--pL) - {g}, 1)"; ineg = f"clamp(0, var(--pneg) - {g}, 1)"
    digit = f"mod(round(down, var(--pa) / pow(10, var(--pneg) + var(--pL) - 1 - {g})), 10)"
    numc = f"({ineg} * 45 + ({inum} - {ineg}) * (48 + {digit}))"
    T, F = [ord(c) for c in 'true'], [ord(c) for c in 'false']
    boolc = " + ".join(f"{eq(g, k)} * ({pv} * {T[k] if k < 4 else 0} + (1 - {pv}) * {F[k]})" for k in range(5))
    svc += [f"--pg{i}: calc(var(--pbase) + {i});",
            f"--pnb{i}: calc(var(--isNum) * {numc} + var(--isBool) * ({boolc}) + (1 - var(--isStr)) * var(--prSP) * {eq(g, 'var(--ptot) - 1')} * 32);"]
for k in range(N): svc.append(f"--th{k}: calc(var(--present{k}) * {eq(f'var(--tag{k})', 'var(--mblk)')});")
svc += ["--thany: calc(" + " + ".join(f"var(--th{k})" for k in range(N)) + ");",
        "--missv: calc(var(--isMISS) * (1 - var(--thany)));",          # miss on an absent block: the victim takes it
        "--victim: calc(var(--missv) + var(--isWFAIL));",
        "--ch: mod(var(--T1), 256);", f"--nl: {eq('var(--ch)', 10)};", "--isOut: calc(var(--isPUTC) + var(--isPR));"]
for w in range(WB):
    svc += [f"--vval{w}: calc(" + " + ".join(f"var(--isv{k}) * var(--val{k}_{w})" for k in range(N)) + ");",
            f"--vdirty{w}: calc(" + " + ".join(f"var(--isv{k}) * var(--dirty{k}_{w})" for k in range(N)) + ");",
            f"--doWB{w}: calc(var(--victim) * var(--vdirty{w}));"]
svc += [# EXT: a = T2, b = T1 (signed); SHL13 uses T1
        f"--a2: {sgn20('var(--T2)')};", f"--b1: {sgn20('var(--T1)')};",
        f"--bs: calc(var(--b1) + {eq('var(--b1)', 0)});", "--q: round(to-zero, var(--a2) / var(--bs));",
        f"--ext: calc(var(--isMUL) * var(--a2) * var(--b1) + (1 - {eq('var(--b1)', 0)}) * (var(--isDIV) * var(--q) + var(--isMOD) * (var(--a2) - var(--b1) * var(--q))) + var(--isSHL) * var(--b1) * 8192);",
        f"--resT: calc(var(--isEXT) * var(--ext) + (1 - var(--isEXT)) * var(--RESe));",
        # read ports (block fill on MISS): RAM block mblk, one port per bank
        f"--rb: calc(min({BANKN - 1}, max(0, var(--mblk) - {ROM // 4})));",
        "--rbh: round(down, var(--rb) / 64);", "--rbl: calc(var(--rb) - 64 * var(--rbh));"]
for k in range(N):
    svc += [f"--fillv{k}: calc(var(--missv) * var(--isv{k}));", f"--fillh{k}: calc(var(--isMISS) * var(--th{k}));",
            f"--clean{k}: calc(var(--victim) * var(--isv{k}));",
            f"--tagT{k}: calc(var(--fillv{k}) * var(--mblk) + (1 - var(--fillv{k})) * var(--tag{k}));"]
    for w in range(WB):
        ws = f"var(--ws{k}_{w})"
        svc.append(f"--wsT{k}_{w}: calc(var(--fillv{k}) + (1 - var(--fillv{k})) * (var(--fillh{k}) * max({ws}, 1) + (1 - var(--fillh{k})) * "
                   f"(var(--clean{k}) * min({ws}, 1) + (1 - var(--clean{k})) * {ws})));")
    svc += [f"--vdT{k}: calc(min(1, calc(" + " + ".join(f"var(--wsT{k}_{w})" for w in range(WB)) + ")) + min(1, calc(" +
            " + ".join(f"{eq(f'var(--wsT{k}_{w})', 2)}" for w in range(WB)) + ")));",
            f"--vfT{k}: calc(var(--missv) * {eq('var(--v1)', k)} + (1 - var(--missv)) * var(--isv{k}));"]
# these need the port values: computed inside the innermost port
svc_inner = []
for k in range(N):
    for w in range(WB):
        f_ = f"(var(--fillv{k}) + var(--fillh{k}) * {eq(f'var(--ws{k}_{w})', 0)})"
        svc_inner.append(f"--valT{k}_{w}: calc({f_} * var(--mval{w}) + (1 - {f_}) * var(--val{k}_{w}));")
# PRINT, string chunk: bytes pb_i at block offsets pj0 + i (0 past the block); the run of printable bytes pr_i stops at a
# NUL (ptNul: the value is out, the separator follows), a newline (ptNL: taken, the chunk ends) or the block's end.
for i in range(4):
    inb = f"clamp(0, 4 - var(--pj0) - {i}, 1)"
    svc_inner += [f"--pb{i}: calc({inb} * (" + " + ".join(f"{eq(f'var(--pj0) + {i}', j)} * var(--mval{j})" for j in range(WB)) + "));",
                  f"--pc{i}: calc({inb} * (1 - {eq(f'var(--pb{i})', 0)}) * (1 - {eq(f'var(--pb{i})', 10)}));",
                  f"--pr{i}: " + ("var(--pc0);" if i == 0 else f"calc(var(--pr{i - 1}) * var(--pc{i}));")]
svc_inner += ["--pe: calc((1 - var(--pdone)) * (var(--pr0) + var(--pr1) + var(--pr2) + var(--pr3)));",
              "--pvE: clamp(0, 4 - var(--pj0) - var(--pe), 1);",
              "--pbE: calc(" + " + ".join(f"{eq('var(--pe)', i)} * var(--pb{i})" for i in range(4)) + ");",
              f"--ptNul: calc(var(--pdone) + (1 - var(--pdone)) * var(--pvE) * {eq('var(--pbE)', 0)});",
              f"--ptNL: calc((1 - var(--pdone)) * var(--pvE) * {eq('var(--pbE)', 10)});",
              # this service: pn cells written, pnl a newline after them, pfin the value (and separator) is out, pstT the next --pst
              "--pn: calc(var(--isStr) * (var(--pe) + var(--ptNul) * var(--prSP)) + (1 - var(--isStr)) * clamp(0, var(--ptot) - var(--pbase), 4) + var(--isPUTC) * (1 - var(--nl)));",
              "--pfin: calc(var(--isStr) * var(--ptNul) + (1 - var(--isStr)) * clamp(0, var(--pbase) + 5 - var(--ptot), 1));",
              "--pnl: calc(var(--isStr) * (var(--ptNL) + var(--ptNul) * var(--prLN)) + (1 - var(--isStr)) * var(--pfin) * var(--prLN) + var(--isPUTC) * var(--nl));",
              "--pstT: calc(var(--isStr) * (1 - var(--ptNul)) * (var(--pq) + var(--pe) + var(--ptNL)) + (1 - var(--isStr)) * (1 - var(--pfin)) * (var(--pph) + 1));",
              "--resvT: min(1, calc(var(--resvin) + var(--isEXT) + var(--isPUTC) + var(--isPR) * var(--pfin)));"]
for i in range(4):
    svc_inner.append(f"--pch{i}: calc(var(--isStr) * (var(--pr{i}) * var(--pb{i}) + {eq('var(--pe)', i)} * var(--ptNul) * var(--prSP) * 32)"
                     f" + (1 - var(--isStr)) * clamp(0, var(--pn) - {i}, 1) * var(--pnb{i}) + var(--isPUTC) * {eq(i, 0)} * var(--ch));")
# console cell i of the chunk goes to optr + i, i.e. bank (optr + i) mod 4: bank w takes cell pi_w = (w - optr) mod 4
for w in range(WB):
    svc_inner += [f"--pi{w}: mod({w} - var(--optr), 4);", f"--doPut{w}: clamp(0, var(--pn) - var(--pi{w}), 1);",
                  f"--pchw{w}: calc(" + " + ".join(f"{eq(f'var(--pi{w})', i)} * var(--pch{i})" for i in range(4)) + ");",
                  f"--doWrite{w}: calc(var(--doWB{w}) + var(--doPut{w}));",
                  f"--waddr{w}: calc(var(--doWB{w}) * (4 * var(--vtag) + {w}) + var(--doPut{w}) * ({OUT_BASE} + mod(var(--optr) + var(--pi{w}), {OUT_SIZE})));",
                  f"--wval{w}: calc(var(--doWB{w}) * {sgn20(f'var(--vval{w})')} + var(--doPut{w}) * var(--pchw{w}));",
                  f"--Wb{w}: calc(var(--go) * var(--doWrite{w}) * (round(down, (var(--waddr{w}) - {ROM}) / 4) + 1));"]
# counter inputs for the text
inp = []
for c in meta['cells']:
    if not c['input']: continue
    r, kind_, j = c['input']
    src = {'PC': 'PCe', 'SP': 'SPe', 'FP': 'FPe', 'RES': 'resT', 'RESV': 'resvT'}.get(r)
    if kind_ == 'digit': e = (f"mod(round(down, mod(var(--{src}), {M20}) / {16 ** j}), 16)" if src == 'resT' else f"mod(round(down, var(--{src}) / {16 ** j}), 16)")
    elif kind_ == 'value': e = f"var(--{src})"
    else:
        k = int(r[1:])
        e = {'vf': lambda: f"var(--vfT{k})", 'vd': lambda: f"var(--vdT{k})",
             'tag': lambda: f"mod(round(down, var(--tagT{k}) / {[1, 4, 64, 1024][j]}), {[4, 16, 16, 16][j]})",
             'ws': lambda: f"var(--wsT{k}_{j})",
             'val': lambda: f"mod(round(down, mod(var(--valT{k}_{j // 8}), {M20}) / {16 ** (j % 8)}), 16)"}[kind_]()
    inp.append(f"--i{c['pos']}: {e};")

# ---------------- next-state (inside readback readers for the font outputs)
g = "var(--go)"
RUN = ' * var(--run)' if UI else ''   # Edit (run = 0) clears everything held, so the next Run starts from the initial state
def hold(name, expr): return f"--next-{name}: calc({g} * ({expr}) + (1 - {g}){RUN} * var(--{name}));"
nx = ["--next-tprev: var(--t);", "--next-nsh: calc(var(--nsh) + var(--go));",
      f"--next-k: calc(var(--fresh) + (1 - var(--fresh)) * min({K}, var(--k) + 1));",  # saturates: once the K issues are done nothing changes, so Blink stops re-running layout this frame,
      "--next-par: calc(var(--fresh) * (1 - var(--par)) + (1 - var(--fresh)) * var(--par));",
      hold("init", "1"), hold("RES", "var(--resT)"),
      # after pn cells the cursor is at optr + pn; a newline moves it to the next row's start (as the simulator does)
      hold("optr", f"var(--isOut) * mod(var(--pnl) * (round(down, (var(--optr) + var(--pn)) / {COLS}) + 1) * {COLS} + (1 - var(--pnl)) * (var(--optr) + var(--pn)), {OUT_SIZE}) + (1 - var(--isOut)) * var(--optr)"),
      hold("pst", "var(--isPR) * var(--pstT) + (1 - var(--isPR)) * var(--pst)")]
for w in range(WB):
    for i, c in enumerate(CH):
        sel = f"var(--go) * {eq('var(--chan)', i)}"
        rel = f"min(1, var(--Wb{w})) * {eq(f'var(--Wb{w})', f'var(--wa{w}{c})')}"
        nx.append(f"--next-wa{w}{c}: calc({sel} * var(--Wb{w}) + (1 - {sel}) * (1 - {rel}){RUN} * var(--wa{w}{c}));")
        nx.append(f"--next-wd{w}{c}: calc({sel} * var(--doWrite{w}) * var(--wval{w}) + (1 - {sel}) * var(--wd{w}{c}));")

def mux(p, n, leaf, default):
    outer = []
    for j in range((n + 63) // 64):
        inner = " ".join(f"style(--{p}l: {i}): {leaf(j * 64 + i)};" for i in range(64) if j * 64 + i < n)
        outer.append(f"style(--{p}h: {j}): if({inner} else: {default});")
    return f"if({' '.join(outer)} else: {default})"

isline = lambda n: n[0] in 'AV' and n[1:2].isdigit()
aregs = regs
names = ", ".join(f"--{n}" for n, _, _ in aregs)
anims = ", ".join(f"r-{n}" for n, _, _ in aregs)
WNAMES = [f"wa{w}{c}" for w in range(WB) for c in CH] + [f"wd{w}{c}" for w in range(WB) for c in CH]
inner_names = names if False else ", ".join(f"--{n}" for n, _, _ in regs if n not in WNAMES)
css = ["#clk { animation: wc 100s linear infinite; }\n@keyframes wc { from { --t: 0; } to { --t: 60000; } }",
       "#cpu {\n  timeline-scope: " + inner_names + ";\n  animation-name: " + anims + ";\n  animation-timeline: " + names +
       ";\n  animation-duration: auto;\n  animation-timing-function: linear;\n  animation-fill-mode: both;\n  " + "\n  ".join(gate + eff + svc) + "\n}"]
css += [f"@keyframes r-{n} {{ from {{ --{n}: {H - OFF}; }} to {{ --{n}: {-1 - OFF}; }} }}" for n, H, OFF in regs]
for w in range(WB):
    css.append(f"#cpu {{ --sR{w}: " + mux("rb", BANKN, lambda b, w=w: f"--c{4 * b + w}", f"--c{w}") + "; }")
    css.append(f".rp{w} {{ width: anchor-size(var(--sR{w}) width); }} .vp{w} {{ --mval{w}: calc(100cqi / 1px - {WOFF}); }}")
css.append(".vp3 { " + "\n  ".join(svc_inner + inp + nx) + " }")
# writes
if RAMMODE == 'flat':   # one rule per cell per channel
    for k in range(RAMN):
        for c in CH:
            css.append(f"@container style(--wa{c}: {k + 1}) {{ .cell.c{k} {{ content-visibility: visible; width: calc((var(--wd{c}) + {WOFF}) * 1px); }} }}")
else:
    if UI:
        ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, 'compiler'), os.path.join(ROOT, 'readback')]
        import ccpage5, ui_rb
        UIL, UIP, UIT = (int(os.environ.get(k, d)) for k, d in (('UIL', 24), ('UIP', 64), ('UIT', 400)))
        lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
        ui_css, ui_chain, ui_tls, ui_info = ccpage5.build(lib, UIL, UIP, UIT, short=os.environ.get('SHORT', '1') == '1')
        print('compile chain', ui_info)
        css.append("body { timeline-scope: " + ", ".join(["--" + n for n in WNAMES] + ui_tls + ['--rbrdT']) + "; }")
    else:
        css.append(memtree.scope(WNAMES))
    _sp, _sc = memtree.shared(); props += _sp; css += _sc
    for w in range(WB):
        _mp, _mc = memtree.css(CH, {n: (H, OFF) for n, H, OFF in regs if n in (f"wa{w}{c}" for c in CH) or n in (f"wd{w}{c}" for c in CH)}, BANKN, WOFF, prefix=str(w))
        props += _mp; css += _mc
# console readers
for i in range(OUT_SIZE):
    r, c = divmod(i, COLS)
    css.append(f".oc{i} {{ width: anchor-size(--c{OUT_BASE - ROM + i} width); left: calc(24px + {c} * 11px); top: calc(24px + {r} * 20px); }}")
css.append('@counter-style ascii { system: fixed 32; symbols: ' + " ".join('"\\""' if c == 34 else '"\\\\"' if c == 92 else f'"{chr(c)}"' for c in range(32, 127)) + '; fallback: blank; }')
css.append('@counter-style blank { system: cyclic; symbols: " "; }')

# ---------------- the state line: one span per readback field, anonymous spans for the rest
cells = meta['cells']
groups = []
for c in cells:
    key = c['span']
    if groups and groups[-1][0] == key: groups[-1][1].append(c)
    else: groups.append((key, [c]))
styles = {}
spans_html = []
for gi, (name, cs) in enumerate(groups):
    parts, sets = [], []
    for c in cs:
        if c['input']:
            sty = 'st-' + c['type'].replace('.', '-')
            styles[sty] = c['symbols']
            sets.append(f"c{c['pos']} var(--i{c['pos']})"); parts.append(f"counter(c{c['pos']}, {sty})")
        else:
            parts.append('"\\%X "' % c['static'])
    rule = f".s{gi}::before {{ content: {' '.join(parts)}; }}"
    if sets: rule += f" .s{gi} {{ counter-set: {' '.join(sets)}; }}"
    css.append(rule)
    an = f' style="anchor-name: --a-{name}"' if name else ''
    spans_html.append(f'<span class="s{gi}"{an}></span>')
for sty, syms in styles.items():
    css.append(f"@counter-style {sty} {{ system: fixed 0; symbols: {' '.join(chr(34) + chr(92) + '%X ' % s + chr(34) for s in syms)}; }}")

# ---------------- readback readers. A reader is a fixed element whose width (and height, for a pair) is anchor-size(span), and a
# size container. Inside it, one scroller (.reg: height H, overflow hidden) holds absolutely positioned view-timeline subjects at
# (value + OFF) px, where the value is read as 100cqi / 1px on the subject itself. So a reader restyles only its subjects during
# layout: the earlier chain (.rv with the value, .reg, .sp spacer, .sub, .pad) cost about 1,300 style resolutions per pass.
# The scroller's height is exactly H: a subject at y with height 1 in an H-tall scrollport has view progress (H - y) / (H + 1),
# and the keyframes from H - OFF to -1 - OFF turn that into y - OFF.
RD = lambda unit: f"round(100cq{unit} / 1px * var(--R))"          # the span's width in font units (device pixels / R)
def sub_html(n, OFF, expr):
    return f'<div class="sub" style="view-timeline-name: --{n}; top: calc(({expr} + {OFF}) * 1px)"></div>'
def rdhold(n, val): return f"var(--go) * {val} + (1 - var(--go)) * var(--{n})"     # passes without an issue keep the register
def reader(cls, style, H, subs): return f'<div class="{cls}" style="{style}"><div class="reg" style="height: {H}px">{"".join(subs)}</div></div>'
Hof = {r[0]: r[1] for r in regs}
rb_html = []
for n, H, OFF in regs:
    if n not in readback: continue
    sp = readback[n]
    if isline(n):
        # line spans are read two per reader: width = one span, height = the next (container-type: size)
        k_ = n[1:].split('_')[0]
        names_k = [f"A{k_}"] + [f"V{k_}_{s}" for s in range(7)]
        i_ = names_k.index(n)
        if i_ % 2: continue
        n2 = names_k[i_ + 1]; assert Hof[n2] == H
        rb_html.append(reader('rb rb2', f"width: anchor-size(--a-{sp[0]} width); height: anchor-size(--a-{readback[n2][0]} width)", H,
                              [sub_html(n, OFF, rdhold(n, RD('w'))), sub_html(n2, 0, rdhold(n2, RD('h')))]))
    elif len(sp) == 1:
        rb_html.append(reader('rb', f"width: anchor-size(--a-{sp[0]} width)", H, [sub_html(n, OFF, rdhold(n, RD('i')))]))
    else:      # T1 / T2: two spans, lo + 4096 * hi, read as the width and height of one pair reader
        rb_html.append(reader('rb rb2', f"width: anchor-size(--a-{sp[0]} width); height: anchor-size(--a-{sp[1]} width)", H,
                              [sub_html(n, OFF, rdhold(n, sgn20(f"({RD('w')} + 4096 * {RD('h')})")))]))
# steps: += instructions completed (NI span)
rb_html.append(reader('rb', "width: anchor-size(--a-NI width)", 1 << 21, [sub_html('steps', 0, f"var(--steps){RUN} + var(--go) * {RD('i')}")]))
# font-ready sentinel: SP digits of the initial state shaped with cv02 (export only) must measure sp0 units
rb_html.append(reader('rb', "width: anchor-size(--a-SENT width)", 2, [sub_html('fok', 0, eq(RD('i'), sp0))]))
if UI:   # compiled without error (an in-flow anchor at the end of the token chain)
    rb_html.append(reader('rb', "width: anchor-size(--ccdone width, 0px)", 2, [sub_html('ccok', 0, "min(1, round(100cqi / 1px))")]))
sent = ''.join('&#x%X;' % c['symbols'][(sp0 >> (4 * c['input'][2])) & 15] for c in meta['cells'] if c['span'] == 'HSP')
local_regs = [r for r in regs if r[0] not in readback and r[0] not in ('steps', 'fok', 'ccok')]

static = f"""
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
  .rd, .rp, .rb {{ position: fixed; top: 0; left: 0; visibility: hidden; }}
  .rp {{ height: 1px; container-type: inline-size; }}
  .rb {{ height: 1px; container-type: inline-size; }}
  .rb.rb2 {{ container-type: size; }}
  .reg {{ position: relative; overflow: hidden; width: 1px; }}
  .sub {{ position: absolute; left: 0; width: 1px; height: 1px; }}
  .vp {{ visibility: visible; }}
  @font-face {{ font-family: FontCPU; src: url(data:font/woff2;base64,{font64}); }}
  #state {{ position: fixed; top: 0; left: 0; font: 1024px/1 FontCPU; font-size: calc(1024px / var(--R)); font-feature-settings: "cv01" var(--go); white-space: pre; width: max-content; visibility: hidden; }}  /* no CPU cycles in passes that will not commit */
  #sent {{ position: fixed; top: 0; left: 0; font: 1024px/1 FontCPU; font-size: calc(1024px / var(--R)); font-feature-settings: "cv02" 1; white-space: pre; width: max-content; visibility: hidden; }}
  .zw {{ display: if(style(--Rok: 0): block; else: none); color: #b00; font-weight: 600; }}
  .con {{ position: fixed; left: 16px; top: 16px; width: {COLS * 11 + 16}px; height: {ROWS * 20 + 16}px; background: #151515; border-radius: 6px; }}
  .oc {{ position: fixed; height: 20px; container-type: inline-size; visibility: hidden; font: 16px/20px ui-monospace, monospace; color: #eee; }}
  .oc > b {{ --code: calc(100cqi / 1px - {WOFF}); counter-set: ch var(--code); font-weight: 400; visibility: visible; display: inline-block; width: 11px; }}
  .oc > b::after {{ content: counter(ch, ascii); }}
  .regs {{ height: 0; overflow: hidden; }}
"""
cells_html = "\n".join(f'<div class="w" style="anchor-name: --c{k}"><i class="cell c{k}" style="contain-intrinsic-size: auto {image["ram"][k] + WOFF}px"></i></div>' for k in range(RAMN))
console = "\n".join(f'<div class="oc oc{i}"><b></b></div>' for i in range(OUT_SIZE))
src_html = _h.escape(image.get("source", ""))
blurb = (f"<p>The CPU is a font. Each layout pass, the machine state is rendered as a line of text and Blink's HarfBuzz runs "
         f"{S} micro-cycles of a bytecode CPU implemented in GSUB (a {N}-line cache of RAM inside the glyph string, four words per line); the widths of the "
         f"state's spans are read back as the next state. CSS handles what the font traps on: cache misses, write-backs, MUL/DIV/MOD, output. "
         f"The ROM is the self-hosted JavaScript-subset compiler; it compiles the program below and runs it.</p><pre>{src_html}</pre>")
local_html = "\n".join(f'<div class="reg" style="height: {H}px">{sub_html(n, OFF, f"var(--next-{n})")}</div>' for n, H, OFF in local_regs)
CC = os.environ.get('CC')      # prefix of a CSS compile chain (ccpage4.py): its overlays supply code and data in RAM
cc_css = open(CC + '.css').read() if CC else ''
cc_html = open(CC + '.html').read() if CC else ''
if CC:
    blurb = (f"<p>The CPU is a font; the compiler is the stylesheet. The program below sits in the page as one nested element per character. "
             f"Style resolution runs a lexer on every element and, on the element after each completed token, the parser variant for its "
             f"(mode, token), selected by container queries. Each emitted bytecode word is a fixed-position element named after its RAM cell, "
             f"so the font CPU's memory reads find it. Then HarfBuzz runs it: each layout pass shapes the machine state as a line of text "
             f"({S} micro-cycles of a bytecode CPU in GSUB, a {N}-line cache of RAM, four words per line) and the widths of its spans are the next state. "
             f"The ROM holds only the runtime library.</p><pre>{src_html}</pre>")
mem_outer, mem_inner = "".join(memtree.html(image["ram"], list(range(w, RAMN, WB)), WOFF, prefix=str(w)) for w in range(WB)), ""
page = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>JavaScript on a HarfBuzz CPU</title>
<style>
{static}
/* ---------- generated ---------- */
{chr(10).join(props)}
{chr(10).join(css)}
{cc_css}
</style>
{mem_outer}{cc_html}<div class="con"></div>
{console}
<div id="clk"><div id="cpu">
{mem_inner}
<div class="rp rp0"><div class="vp vp0"><div class="rp rp1"><div class="vp vp1"><div class="rp rp2"><div class="vp vp2"><div class="rp rp3"><div class="vp vp3">
<div id="sent"><span style="anchor-name: --a-SENT">{sent}</span></div>
<div id="state">{''.join(spans_html)}</div>
{''.join(rb_html)}
<div class="head">
<h1>{"JavaScript, compiled by a stylesheet and run by a font" if CC else "JavaScript, compiled and run by a font"}</h1>
<p class="zw">This screen scale / zoom level isn't one the page recognises, so the machine won't start. Reset the zoom (Cmd/Ctrl + 0).</p>
{blurb}
<div class="status">steps <b class="num" style="--v: var(--steps)"></b> pc <b class="num" style="--v: var(--PC)"></b> sp <b class="num" style="--v: var(--SP)"></b>
 trap <b class="num" style="--v: var(--kind)"></b></div>
</div>
<div class="regs" aria-hidden="true">
{local_html}
</div>
</div></div></div></div></div></div></div></div>
</div></div>
</html>
"""

if UI:
    GS = 8
    TOPS = ROWS * 20 + 48
    ui_static = f"""
  :root {{ --paper: #f3f5f7; --sheet: #fff; --ink: #17212b; --muted: #5b6875; --rule: #c9d1d9; --accent: #2456c9; }}
  body {{ background: var(--paper); color: var(--ink); }}
  #app {{ position: relative; overflow: hidden; margin: 0 0 0 {COLS * 11 + 72}px; padding: 20px 24px 48px 0; width: {UIP * 10 + 60}px; display: grid; gap: 1rem; align-content: start;
    contain: strict; height: {UIL * 24 + 560}px;   /* the scan relayouts stay inside #app (the CPU's fixed readers are not touched) */
    will-change: transform; }}   /* its own compositor layer: the CPU's per-pass paint invalidations then don't re-record the editor and notes */
  #app h1 {{ font-size: 1.15rem; margin: 0; }}
  .lede {{ margin: .3rem 0 0; color: var(--muted); }}
  .bar {{ display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }}
  .label {{ font: 600 .72rem/1 ui-monospace, monospace; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }}
  .scanpos {{ font: .8rem ui-monospace, monospace; color: var(--muted); }}
  #run:checked ~ #app .scanpos {{ visibility: hidden; }}
  .frame {{ background: var(--sheet); border: 1px solid var(--rule); border-radius: 6px; overflow: auto; }}
  .frame:focus-within {{ border-color: var(--accent); }}
  #ed {{ background: linear-gradient(to right, transparent {14 + UIP * 10}px, var(--rule) 0, var(--rule) {15 + UIP * 10}px, transparent 0); }}
  .runbtn {{ position: relative; display: inline-block; cursor: pointer; font: 600 .9rem/1 system-ui, sans-serif; color: #fff; background: var(--accent);
    border-radius: 6px; padding: .55rem 1rem; user-select: none; }}
  .runcb {{ position: absolute; left: 0; top: 0; width: 1px; height: 1px; opacity: 0; margin: 0; }}
  #run:focus-visible ~ #app .runbtn {{ outline: 2px solid var(--ink); outline-offset: 2px; }}
  .runbtn span::before {{ content: "\\25B6  Run"; }}
  #run:checked ~ #app .runbtn {{ background: #5b6875; }}
  #run:checked ~ #app .runbtn span::before {{ content: "\\270E  Edit"; }}
  .limit {{ display: none; margin: 0; font-size: .85rem; color: var(--muted); }}
  .notes {{ color: var(--muted); font-size: .9rem; display: grid; gap: .5rem; }}
  .notes p {{ margin: 0; }}
  .notes code {{ font: .82rem ui-monospace, monospace; color: var(--ink); }}
  .head {{ left: 16px; top: {TOPS + 56}px; width: {COLS * 11 + 40}px; }}
  .head .status {{ display: grid; gap: .1rem; }}
  .cst, .cst2 {{ position: fixed; left: 16px; height: 1px; visibility: hidden; }}
  .cst {{ top: {TOPS}px; container-type: inline-size; width: anchor-size(--ccinfo width, 0px); }}
  .cst2 {{ top: {TOPS + 36}px; width: anchor-size(--cctoo width, 0px); overflow: hidden; }}
  .cst2 > b {{ visibility: visible; white-space: nowrap; font: 12px ui-monospace, monospace; color: #b00; }}
  .cstv {{ position: absolute; left: 0; top: 0; width: {COLS * 11 + 40}px; visibility: visible; font: 13px/1.35 ui-monospace, monospace;
    --csi: round(100cqi / 1px); --csd: mod(var(--csi), 2); --cse: mod(round(down, var(--csi) / 2), 512); --csn: round(down, var(--csi) / 1024);
    counter-set: csn var(--csn) cse var(--cse); }}
  .cstv::before {{ content: "edit the program, then Run"; color: var(--muted); }}
  #run:checked ~ .cst .cstv::before {{ color: var(--ink);
    content: if(style(--csd: 0): "compiling\\2026"; style(--cse: 0): "compiled: " counter(csn) " words";
      style(--cse: 4): "error: undefined variable"; style(--cse: 5): "error: undefined variable"; style(--cse: 6): "error: undefined variable";
      style(--cse: 7): "error: undefined variable"; style(--cse: 20): "error: too many labels"; style(--cse: 21): "error: blocks nested too deeply";
      style(--cse: 22): "error: expression too deep"; style(--cse: 23): "error: too many functions"; style(--cse: 24): "error: too many variables";
      style(--cse: 41): "error: nested function"; style(--cse: 61): "error: statement too long"; style(--cse: 62): "error: program too long";
      style(--cse: 40): "error: missing }}"; style(--cse: 54): "error: unexpected }}"; style(--cse: 56): "error: break outside a loop";
      style(--cse: 57): "error: return outside a function"; style(--cse: 60): "error: undefined function";
      style(--cse: 25): "error: too many globals / array elements"; style(--cse: 26): "error: too much string data"; style(--cse: 63): "error: strings can only be joined in console.log";
      else: "syntax error (" counter(cse) ")"); }}
"""
    ui_props = ['@property --run { syntax: "<integer>"; inherits: true; initial-value: 0; }',
                '#run:checked ~ #clkw { --run: 1; }',
                f'#run:not(:checked) ~ .mem .cell {{ content-visibility: visible; width: {WOFF}px; }}   /* Edit: RAM back to zeros */',
                '#clkw > .oc { display: if(style(--ccgo: 1): block; else: none); }',
                # no CPU at all until Run's final scan sweep is done (its registers restart from zero on every Run)
                '#clkw { display: contents; animation: kccgo auto linear both; animation-timeline: --rbrdT; } #clk { display: if(style(--ccgo: 1): block; else: none); }'] + \
               [f'@property --{n} {{ syntax: "<integer>"; inherits: true; initial-value: 0; }}' for n in ('csi', 'csd', 'cse', 'csn')]
    editor = ui_rb.editor_html(image.get('source', ''))
    notes = (f"<p>Everything below the editor happens in CSS. A font reads your text back: a variable axis makes HarfBuzz copy the code of one "
             f"column into an invisible glyph's width, and a scan sweeps the columns, one per frame, latching each character into a "
             f"custom property. When you press Run, the compiler (a stylesheet) runs over those characters: a lexer on a chain of one "
             f"element per character, then a parser on a chain of one element per token, with each parser rule picked by a container query. "
             f"Every bytecode word it emits is an element named after its RAM cell. Then the CPU, which is another font, runs the program: each "
             f"layout pass shapes the machine state as text and HarfBuzz executes {S} micro-cycles in GSUB. Output appears in the console on the left.</p>"
             f"<p>The language is a small JavaScript subset: <code>var</code>, <code>function</code>, <code>if</code>/<code>else</code>, "
             f"<code>while</code>, <code>for</code>, <code>return</code>, integer arithmetic, string literals, array literals, "
             f"<code>console.log(x)</code> and <code>putc(c)</code>. Up to {UIL} lines of {UIP} columns (the faint line marks the edge); "
             f"paste as plain text. Run waits for one more scan of the editor, then compiles; Edit clears the machine.</p>")
    page = f"""<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
<meta charset="utf-8"/>
<title>JavaScript in CSS</title>
<style><![CDATA[
{static}
{ui_static}
/* ---------- generated ---------- */
{chr(10).join(props)}
{chr(10).join(ui_props)}
{chr(10).join(css)}
{ui_rb.css(UIL, UIP, GS)}
{ui_css}
]]></style>
</head>
<body>
<input type="checkbox" id="run" class="runcb" aria-label="Run"/>
{mem_outer}{ui_chain}<div class="con"></div><div class="cst"><div class="cstv"></div></div><div class="cst2"><b>more than {UIT} tokens</b></div>
<main id="app">
<div class="width-reader"></div>{ui_rb.regs_html()}
<header><h1>JavaScript, compiled by a stylesheet and run by a font</h1>
<p class="lede">Type a program and press Run. No JavaScript runs on this page.</p></header>
<section class="pane">
<div class="bar"><span class="label" id="in-label">Program</span><label class="runbtn" for="run"><span></span></label><span class="scanpos"></span></div>
<div class="frame"><div id="ed" contenteditable="true" spellcheck="false" autocapitalize="off" autocorrect="off" role="textbox" aria-multiline="true" aria-labelledby="in-label">{editor}</div></div>
<div class="rbout"></div>
<p class="limit">Lines past {UIL} are not read.</p>
</section>
<section class="notes">{notes}</section>
{ui_rb.probes_html(UIL, UIP, GS)}
</main>
<div id="clkw">
{console}
<div id="clk"><div id="cpu">
{mem_inner}
<div class="rp rp0"><div class="vp vp0"><div class="rp rp1"><div class="vp vp1"><div class="rp rp2"><div class="vp vp2"><div class="rp rp3"><div class="vp vp3">
<div id="sent"><span style="anchor-name: --a-SENT">{sent}</span></div>
<div id="state">{''.join(spans_html)}</div>
{''.join(rb_html)}
<div class="head">
<p class="zw">This screen scale / zoom level isn't one the page recognises, so the machine won't start. Reset the zoom (Cmd/Ctrl + 0).</p>
<div class="status"><span>steps <b class="num" style="--v: var(--steps)"></b></span><span>pc <b class="num" style="--v: var(--PC)"></b> sp <b class="num" style="--v: var(--SP)"></b></span></div>
</div>
<div class="regs" aria-hidden="true">
{local_html}
</div>
</div></div></div></div></div></div></div></div>
</div></div></div>
</body>
</html>
"""
open(outp, 'w').write(page)
print(len(page), 'bytes', len(css), 'rules', K, 'shapings/frame max')
