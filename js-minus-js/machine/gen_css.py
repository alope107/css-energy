#!/usr/bin/env python3
"""gen_css.py image.json out.html — the pure-CSS CPU: a CPU-only page, or with UI=1 the editor page. Style alone runs
the instructions; layout only fills the cache and moves the registers. The design is csssim.py's, which is its oracle.

A pass (ISSUE passes per frame):
  #cpu      the registers (view timelines), the frame gate, the pending miss's victim lines
  .fl       the fill: the victim line takes the block the last pass missed, whose words the read ports left in registers
            (a dirty victim's words go to the write set first); the next block is prefetched if it is absent and its
            victim is clean. A fetch's miss fills the code cache instead (and prefetches the next line there)
  K levels  .f fetch (ROM from a static table, user code through the code cache) and decode > .x execute > .c commit. An instruction
            runs only if every word it touches is cached (and, for output, the write set is free); the first that can't
            stops the chain, noting its missing block (--pend) for the next pass's fill
  .ex       the registers' view-timeline subjects at the chain's final state; the write set goes to the RAM channels;
            eight read ports (readers) read the missing block's words and the next block's (one port per bank and block)
            from the RAM leaves into registers for the next pass's fill
Nothing above the chain is a size container, so a pass styles the chain once. (Ports above it, as first built, restyled
the whole chain once per port whose size changed: 7 times in a fill pass.)
Cache: 16 sets x 2 ways x 4 words, set (b + b / 16 + b / 256) mod 16 of block b; --T<line> = 2 * (block + 1) + dirty
(0: empty), --F<set> the next victim way, --W<line>_<word> the words, line = 2 * set + way. RAM is memtree.py's. Code
cache: ISET (16) direct-mapped lines, line b mod ISET, --IT<i> = block + 1, --IW<i>_<word>.

The instructions (compiler/cc_ref.py) are two words at an even address, so .f takes both from one cache lookup (or the ROM
table). A class per group of instructions (alu, mov, jump, test, call, mem, dyn, arr, obj, out, the runtime's primitives:
alloc, apush, mcpy, mcmp; and the cat class), each reading only what its instructions read, and the class is arithmetic on
the opcode (cc_ref orders them by class; a DADD's or GETX / SETX's pst hands over to the cat or obj class). An operand is a global, an fp slot or a constant; pc starts at
code_base, fp at sp0.

Cost model (measured: exp/csscpu/README.md): a container-query test ~2 us, a declaration ~1.3 us, an if() branch ~0.3 us, per
element. A rule evaluates every declaration in it whether the instruction needs it or not, so a class reads only what its
instructions read; .c commits a whole cache set (16 rules) rather than a word (128).
Env: K (levels, default 32), ISSUE (passes per frame, default 2), NOCAT=1 (a string's + in the ROM), UI=1: the editor page (XHTML; the image's RAM is
empty: the compile chain's overlays hold the program): Run starts the scan, the compiler, then the CPU;
Edit zeroes the registers and RAM. BENCH=1 PROG=prog.js (STALL=1): the chain alone, for exp/csscpu/chainbench.js."""
import sys, os, json, re, html as _h
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, "machine"), os.path.join(ROOT, "compiler"), os.path.join(ROOT, "readback"), os.path.join(ROOT, "..", "shared", "py"), HERE]
UI = os.environ.get("UI") == "1"
import memtree, csslabel as lbl, cc_ref as R
from uarch import STRTAG, STR_LO, STRP_HI, HEAP0, HEAP_HI, OBJTAG, ARRTAG, HP
OP = R.OP; RC = R

image = json.load(open(sys.argv[1])); outp = sys.argv[2]
K = int(os.environ.get('K', 32)); ISSUE = int(os.environ.get('ISSUE', 2))
ROM, RAMN, WB = image['romSize'], image['ramSize'], 4
BANKN = RAMN // WB; BLKS = (ROM + RAMN) // WB; RB0 = ROM // WB
OUT_BASE, ROWS, COLS = image['outBase'], image['rows'], image['cols']; OUT_SIZE = ROWS * COLS
assert OUT_BASE % 4 == 0 and ROM % 4 == 0
WOFF = M20 = 1 << 20; A15 = 32768
NSET, NWAY = 16, 2; NL = NSET * NWAY
CH = 'ABCDEFGHIJKL'[:2 * ISSUE]; sp0 = image['sp0']; CODE0 = image['codeBase']; DB = R.LAYOUT['data_base']

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
def opin(lo, hi): return f"clamp(0, var(--op) - {OP[lo] - 1}, 1) * clamp(0, {OP[hi] + 1} - var(--op), 1)"     # lo <= op <= hi

# the latchable reads and their bits: the fetch (f, and g, its second word, under the same bit), the operands B (x) and C (y),
# a third word (z: RET's return word, a string's length; h: the word after it, under the same bit), a string chunk (p), a fourth
# word (e: an array's element, SETX's C)
LATCH = {"f": 1, "g": 1, "x": 2, "y": 4, "z": 8, "h": 8, "p": 16, "e": 32, "k": 64, "j": 64, "s": 128}
# ---------------- registers: (name, H, OFF), value range [-OFF, H - OFF); the subject's expression at the chain's end
regs = [("rpc", A15, 0, "var(--pc)"), ("rfp", A15, 0, "var(--fp)"), ("optr", 256, 0, "var(--optr)"),
        ("pst", A15, 0, "var(--pst)"), ("steps", 1 << 21, 0, "var(--steps)"), ("halt", 2, 0, "var(--halt)"), ("pend", 8192, 0, "var(--pend)"),
        ("init", 2, 0, "1"), ("k", 16, 0, "var(--nk)"), ("par", 2, 0, "var(--npar)"), ("tprev", 65536, 0, "var(--t)")]
regs += [(f"T{k}", 16384, 0, f"var(--T{k})") for k in range(NL)] + [(f"F{s}", 2, 0, f"var(--F{s})") for s in range(NSET)]
regs += [(f"W{k}_{j}", M20, M20 // 2, f"var(--W{k}_{j})") for k in range(NL) for j in range(4)]
WREGS = [(f"wa{w}{c}", BANKN + 1, 0, f"var(--nwa{w}{c})") for w in range(WB) for c in CH] + \
        [(f"wd{w}{c}", 1 << 21, 1 << 20, f"var(--nwd{w}{c})") for w in range(WB) for c in CH]
KN = OUT_SIZE // WB
WREGS += [(f"wak{w}{c}", KN + 1, 0, f"var(--nwak{w}{c})") for w in range(WB) for c in CH] + \
         [(f"wdk{w}{c}", 256, 0, f"var(--nwdk{w}{c})") for w in range(WB) for c in CH]
regs += [(f"mv{i}", M20, M20 // 2, None) for i in range(2 * WB)]
if UI: regs.append(("ccok", 2, 0, None))     # compiled without error: a reader of the compile chain's done anchor, in .ex
regs += [("rLm", 256, 0, "var(--Lm)")] + [(f"rL{n}", M20, M20 // 2, f"var(--L{n})") for n in LATCH if n != "p"] + \
        [(f"rLp{j}", M20, M20 // 2, f"var(--Lp{j})") for j in range(4)]
# the code cache (csssim.py): user code (code_base .. init) is fetched through ISET direct-mapped lines of its own (line b mod
# ISET), --IT<i> = block + 1 (0: empty), --IW<i>_<word>; a fetch's miss fills it (--pic: the pending miss is a fetch's) and
# prefetches the next line. Data never evicts code, and code isn't written
ISET, _IW = (int(x) for x in os.environ.get('ICACHE', '16,1').split(','))
assert _IW == 1 and ISET % 8 == 0
CODE1 = R.LAYOUT['init'] // 4
regs += [(f"IT{i}", 8192, 0, f"var(--IT{i})") for i in range(ISET)] + [(f"IW{i}_{j}", M20, M20 // 2, f"var(--IW{i}_{j})") for i in range(ISET) for j in range(4)]
regs += [("pic", 2, 0, "var(--pic)")]
def isel(key, val):
    """if() over a code line --<key>hi * 8 + --<key>lo (two levels of at most 8: an if() costs per entry)"""
    lo = lambda h: sel(f"{key}lo", 8, lambda l: val(8 * h + l))
    return lo(0) if ISET == 8 else "if(" + " ".join(f"style(--{key}hi: {h}): {lo(h)};" for h in range(ISET // 8 - 1)) + f" else: {lo(ISET // 8 - 1)})"
regs += [("stale", 2, 0, f"calc(var(--fd) * {eq('var(--pend) - 1', 'var(--fvb)')} * min(1, var(--pend)))"),
         ("pstale", 2, 0, f"calc(var(--fd) * {eq('var(--pend)', 'var(--fvb)')} * min(1, var(--pend)))")]
# NET: the request a waiting NET leaves at the chain's end (the modem iframe's height), and the clock (--t, 600 a second)
# when this request began: a new request takes the time (consecutive words always differ, by the sequence bit, even when
# a read() loop's next NET stalls in the pass the last one completed). NWAIT ticks without an answer give -1 (no gateway:
# a file: URL, a static server). (Counting passes was too slow a clock: a waiting page settles to ~10 passes a second.)
NWAIT = 12000          # 20 s
regs += [("rreq", 524290, 0, "calc(var(--go) * var(--req) + (1 - var(--go)) * var(--rreq))"),    # (held on passes that don't run the chain)
         ("rlive", 2, 0, "calc(var(--go) * max(var(--rlive), min(1, var(--req))) + (1 - var(--go)) * var(--rlive))"),   # a NET has waited this run
         ("rnt0", 60000, 0, f"calc(var(--go) * (min(1, var(--req)) * {eq('var(--req)', 'var(--rreq)')} * var(--rnt0) + (1 - min(1, var(--req)) * {eq('var(--req)', 'var(--rreq)')}) * mod(var(--t), 60000)) + (1 - var(--go)) * var(--rnt0))")]
regs += WREGS
WNAMES = [r[0] for r in WREGS]

# ---------------- #cpu: effective state, frame gate, the fill's victims (all from the registers)
cpu = ["--first: calc(1 - var(--init));",
       f"--pc: calc(var(--init) * var(--rpc) + var(--first) * {CODE0});", f"--fp: calc(var(--init) * var(--rfp) + var(--first) * {sp0});",
       "--fresh: calc(min(1, max(var(--t) - var(--tprev), var(--tprev) - var(--t))));",
       f"--go: calc({'var(--ccok) * var(--run) * ' if UI else ''}min(1, var(--fresh) + min(1, max(0, {ISSUE} - var(--k)))));", "--isHALT: var(--halt);",
       f"--chan: calc({ISSUE} * var(--par) + (1 - var(--fresh)) * var(--k));",
       f"--nk: calc(var(--fresh) + (1 - var(--fresh)) * min({ISSUE}, var(--k) + 1));",   # saturates, so frames settle (ENGINE_NOTES 16)
       "--npar: calc(var(--fresh) * (1 - var(--par)) + (1 - var(--fresh)) * var(--par));",
       # the fill: block fb into set fs's victim way fv (line fk); a dirty victim (block fvb) is written back
       "--fon: calc(var(--go) * min(1, var(--pend)) * (1 - var(--stale)));", "--fb: max(0, var(--pend) - 1);",
       f"--fs: {setof('var(--fb)')};",
       "--fv: " + sel("fs", NSET, lambda s: f"var(--F{s})") + ";", "--fk: calc(2 * var(--fs) + var(--fv));",
       "--fT: " + sel("fk", NL, lambda k: f"var(--T{k})") + ";",
       "--dfon: calc(var(--fon) * (1 - var(--pic)));", "--ifon: calc(var(--fon) * var(--pic));",
       # (no fill when the block is already in its set: a pending miss seen again after its fill, as a register can land a
       # frame late under load, would put it in the other way too, and a lookup that matches both ways neither hits nor
       # misses: the CPU stalls with nothing pending. csssim's passes are atomic, so it never sees one)
       "--fabs: " + sel("fs", NSET, lambda s: f"calc(1 - {eq(f'round(down, var(--T{2 * s}) / 2)', 'var(--fb) + 1')} - {eq(f'round(down, var(--T{2 * s + 1}) / 2)', 'var(--fb) + 1')})") + ";",
       "--fd: calc(var(--dfon) * var(--fabs) * mod(var(--fT), 2));", "--fvb: calc(round(down, var(--fT) / 2) - 1);",
       "--fk1: calc(var(--dfon) * var(--fabs) * (var(--fk) + 1));", "--pend0: calc((1 - var(--fon)) * var(--pend));",
       # a fetch's miss: its line in the code cache, and the next (if absent there, and code)
       f"--ik1: calc(var(--ifon) * (mod(var(--fb), {ISET}) + 1));", "--igb: calc(var(--fb) + 1);",
       "--igblo: mod(var(--igb), 8);", f"--igbhi: mod(round(down, var(--igb) / 8), {ISET // 8});",
       "--igp: " + isel("igb", lambda i: eq(f"var(--IT{i})", "var(--igb) + 1")) + ";",
       f"--ig1: calc(var(--ifon) * clamp(0, {CODE1} - var(--igb), 1) * (1 - var(--igp)) * (mod(var(--igb), {ISET}) + 1));",
       # the prefetch: block fb + 1 into its set's victim way (line gk), if absent there and the victim is clean
       f"--gs: {setof('(var(--fb) + 1)')};", "--gv: " + sel("gs", NSET, lambda s: f"var(--F{s})") + ";", "--gk: calc(2 * var(--gs) + var(--gv));",
       "--gT: " + sel("gk", NL, lambda k: f"var(--T{k})") + ";",
       "--gabs: " + sel("gs", NSET, lambda s: f"calc(1 - {eq(f'round(down, var(--T{2 * s}) / 2)', 'var(--fb) + 2')} - {eq(f'round(down, var(--T{2 * s + 1}) / 2)', 'var(--fb) + 2')})") + ";",
       f"--gk1: calc(var(--dfon) * (1 - var(--pstale)) * var(--gabs) * (1 - mod(var(--gT), 2)) * clamp(0, {BLKS - 1} - var(--fb), 1) * (var(--gk) + 1));"]
cpu += [f"--fwd{w}: " + sel("fk", NL, lambda k, w=w: f"var(--W{k}_{w})") + ";" for w in range(WB)]
cpu += [f"--Lb{n}: mod(round(down, var(--rLm) / {b}), 2);" for n, b in LATCH.items()]
HOT = range(R.LAYOUT["data_base"] // 4, (R.LAYOUT["data_base"] + 2048) // 4)     # the blocks runs mostly read: globals, strings, code (read ports, below)

# ---------------- reads: a word through the cache. For read n of address A: block b, word u, set z, hits h (way 0) and
# H (way 1), each one if() over the set comparing that way's tag, and the word v (set, then way, then word).
def lookup(n, A):
    b = f"var(--b{n})"
    hit = lambda way: sel(f"q{n}", NSET, lambda s: eq(f"round(down, var(--T{2 * s + way}) / 2)", f"{b} + 1"))
    return [f"--b{n}: round(down, ({A}) / 4);", f"--u{n}: mod({A}, 4);", f"--q{n}: {setof(b)};", f"--h{n}: {hit(0)};", f"--H{n}: {hit(1)};"]
def word(n, k): return sel(f"u{n}", 4, lambda j: f"var(--W{k}_{j})")
def word2(n, k): return f"if(style(--u{n}: 0): var(--W{k}_1); else: var(--W{k}_3))"     # the word after an even one
# A stalled instruction's operands are kept (latches: registers rL<n>, valid if bit n of rLm) for its re-execution as the
# next pass's first instruction (--lat: 1 until the first commit), so it needs only its written line resident at the end
# (csssim.py: without them three blocks in one set evicted each other forever). The write's own lookup (w) isn't latched.
def latched(n, e): return f"if(style(--lat: 1) and style(--Lb{n}: 1): var(--rL{n}); else: {e})"
def read(n, A):
    return lookup(n, A) + [f"--v{n}: " + latched(n, sel(f"q{n}", NSET, lambda s: f"if(style(--H{n}: 1): {word(n, 2 * s + 1)}; else: {word(n, 2 * s)})")) + ";"]
def miss(n):
    return f"(1 - var(--h{n}) - var(--H{n}))" + (f" * (1 - var(--lat) * var(--Lb{n}))" if n in LATCH else "")
LOOKUP = ("b", "u", "q", "h", "H")
READS = ("f", "x", "y", "z", "e", "k", "s", "w", "p", "r", "l")      # (r: the map's word, l: MCMP's second line; neither latched)
def read_pair(n, A, m):
    """read n of an even address A and the word after it (latch m)"""
    return read(n, A) + [f"--v{m}: " + latched(m, sel(f"q{n}", NSET, lambda s: f"if(style(--H{n}: 1): {word2(n, 2 * s + 1)}; else: {word2(n, 2 * s)})")) + ";"]

def line_read(n, A):
    """a whole line through lookup n: --<n>w0 .. 3 (p: --pw0 .. 3, latched like PRINT's; l isn't latched)"""
    words = lambda j: sel(f"q{n}", NSET, lambda s: f"if(style(--H{n}: 1): var(--W{2 * s + 1}_{j}); else: var(--W{2 * s}_{j}))")
    return lookup(n, A) + [f"--{n}w{j}: " + (f"if(style(--lat: 1) and style(--Lb{n}: 1): var(--rL{n}{j}); else: {words(j)})" if n in LATCH else words(j)) + ";"
                           for j in range(4)]
def pick(n, ix):
    """word var(--<ix>) (0 .. 3) of line n"""
    return f"if(style(--{ix}: 0): var(--{n}w0); style(--{ix}: 1): var(--{n}w1); style(--{ix}: 2): var(--{n}w2); else: var(--{n}w3))"
def write_line(n, val, en, k):
    """a write through lookup n of words u<n> .. u<n> + k - 1 of its line, word j taking val(j) (k may be 0: nothing)"""
    d = [f"--wm{j}: calc(clamp(0, {j} - var(--u{n}) + 1, 1) * clamp(0, var(--u{n}) + {k} - {j}, 1));" for j in range(4)]
    d += [f"--wv{j}: {val(j)};" for j in range(4)]
    for i in range(8):
        way, j = divmod(i, 4)
        old = sel(f"q{n}", NSET, lambda s: f"var(--W{2 * s + way}_{j})")
        d.append(f"--n{i}: if(style(--H{n}: {way}) and style(--wm{j}: 1): var(--wv{j}); else: {old});")
    for way in range(2):
        d.append(f"--nT{way}: if(style(--H{n}: {way}): calc(2 * var(--b{n}) + 3); else: {sel(f'q{n}', NSET, lambda s: f'var(--T{2 * s + way})')});")
    return d + [f"--wz: calc(var(--ok) * {en} * (var(--q{n}) + 1));"]
# a write of value V through lookup n (a read of the same address, or the write's own): the set's 8 new words and 2 tags,
# and --wz = set + 1, which picks the commit rule on .c (0: no write, as on a stall). V2: also the next word (an even address;
# --w2 = 1 when it is written)
def write(n, V, en="1", V2=None):
    d = [f"--wval: {V};"] + ([f"--wval2: {V2};"] if V2 else [])
    for i in range(8):
        way, j = divmod(i, 4)
        old = sel(f"q{n}", NSET, lambda s: f"var(--W{2 * s + way}_{j})")
        two = f"style(--w2: 1) and style(--H{n}: {way}) and style(--u{n}: {j - 1}): var(--wval2); " if V2 and j % 2 else ""
        d.append(f"--n{i}: if(style(--H{n}: {way}) and style(--u{n}: {j}): var(--wval); {two}else: {old});")
    for way in range(2):
        d.append(f"--nT{way}: if(style(--H{n}: {way}): calc(2 * var(--b{n}) + 3); else: {sel(f'q{n}', NSET, lambda s: f'var(--T{2 * s + way})')});")
    return d + [f"--wz: calc(var(--ok) * {en} * (var(--q{n}) + 1));"]

# ---------------- instruction classes: (ops, reads [(name, address, the ops needing it or None for all)], write (address
# or None to reuse read `reuse`, value, reuse, enable) or None, next registers {pc, fp, steps, pst}). A class is one rule on .x.
pc, fp = v("pc"), v("fp")
xB, yC = "var(--xB)", "var(--yC)"
def oaddr(o):
    """an operand's cell: data_base + o for a global (o < 256), else fp + o - 256"""
    g = f"clamp(0, 256 - {o}, 1)"
    return f"calc({g} * ({DB} + {o}) + (1 - {g}) * mod({fp} + {o} - 256, 32768))"
# operands B and C: constant (o >= 768: o - 896, and from 1016 the specials, cc_ref.kval) or a cell's value (read x / y)
SPK = R.SPV0 - (1016 - 896)
def kconst(o): return f"(var(--{o}) - 896 + {SPK} * clamp(0, var(--{o}) - 1015, 1))"
OPND = ["--kB: clamp(0, var(--B) - 767, 1);", "--kC: clamp(0, var(--C) - 767, 1);", f"--aB: {oaddr('var(--B)')};", f"--aC: {oaddr('var(--C)')};",
        f"--xB: calc(var(--kB) * {kconst('B')} + (1 - var(--kB)) * var(--vx));",
        f"--yC: calc(var(--kC) * {kconst('C')} + (1 - var(--kC)) * var(--vy));"]
# user code (pc at code_base or above) has JavaScript's semantics; the runtime library's words are raw
user = f"clamp(0, {pc} - {CODE0 - 1}, 1)"
z1 = eq(yC, 0)
BINE = {'ADD': s20(f"{xB} + {yC}"), 'SUB': s20(f"{xB} - {yC}"), 'MUL': s20(f"{xB} * {yC}"),
        'DIV': f"calc((1 - {z1}) * round(to-zero, {xB} / ({yC} + {z1})))",
        'MOD': f"calc((1 - {z1}) * ({xB} - {yC} * round(to-zero, {xB} / ({yC} + {z1}))))",
        'LT': f"clamp(0, {yC} - {xB}, 1)", 'GT': f"clamp(0, {xB} - {yC}, 1)",
        'LE': f"clamp(0, {yC} - {xB} + 1, 1)", 'GE': f"clamp(0, {xB} - {yC} + 1, 1)",
        'EQ': eq(xB, yC), 'NE': f"calc(1 - {eq(xB, yC)})"}
BINOPS = ['MOD', 'ADD', 'SUB', 'MUL', 'LT', 'EQ', 'LE', 'GT', 'GE', 'NE', 'DIV']    # the suite's most frequent first
def isstr_v(x): return f"calc(clamp(0, {x} - {STR_LO - STRTAG - 1}, 1) * clamp(0, {STRP_HI - STRTAG} - {x}, 1))"
def isarr_v(x): return f"calc(clamp(0, {x} - {ARRTAG + HEAP0 - 1}, 1) * clamp(0, {ARRTAG + HEAP_HI} - {x}, 1))"
def isobj_v(x): return f"calc(clamp(0, {x} + {OBJTAG - HEAP0 + 1}, 1) * clamp(0, {HEAP_HI - OBJTAG} - {x}, 1))"
def isdbl_v(x): return f"calc(clamp(0, {x} + {R.DBLTAG + 1}, 1) * clamp(0, {32768 - R.DBLTAG} - {x}, 1))"     # (cc_ref.isdbl)
def isfun_v(x): return f"calc(clamp(0, {x} + {R.FUNTAG + 1}, 1) * clamp(0, {32768 - R.FUNTAG} - {x}, 1))"     # (cc_ref.isfun)
def isref_v(x): return f"calc({isstr_v(x)} + {isarr_v(x)} + {isobj_v(x)} + {isdbl_v(x)} + {isfun_v(x)})"
def own_v(x): return f"calc(clamp(0, {x} + {STRTAG - R.STRP0 + 1}, 1) * clamp(0, {R.SEND - STRTAG} - {x}, 1))"     # (a string: the program's own)
def special_v(x): return f"clamp(0, {x} - {R.SPV0 - 1}, 1)"
def smi_v(x): return f"calc(clamp(0, {x} - {R.SMI_LO - 1}, 1) * clamp(0, {R.SMI_HI + 1} - {x}, 1))"
def catv_v(x):
    """cc_ref.catv: a special as its name (a built-in string; -0 as "0"), anything else as it is"""
    return f"calc({x} + {special_v(x)} * ({R.BSTRV(0)} + 12 * ({x} - {R.SPV0} + {eq(x, R.MZERO)}) - {x}))"
XBACK = 512                    # a SETX's pst: its probe found the chunk full, so the arr class's trap (setx), from its first step
ENT = image.get('entries') or json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))['entries']
TRAPOFF, HS = R.TRAPOFF, R.LAYOUT['heap_size']
def kv(o, n):
    """operand o's value: a constant, or read n's word"""
    return f"calc(var(--k{o}) * {kconst(o)} + (1 - var(--k{o})) * var(--v{n}))"
OPNDA = ["--kA: clamp(0, var(--A) - 767, 1);", f"--aA: {oaddr('var(--A)')};"]
# A trap writes its frame one word per execution (csssim.py): with n arguments, step s (pst, but SETP's first is in its probe)
# writes argument n - 1 - s at F + n - s, and step n the return word at F, fp = F, pc = the routine (tr: a trap's execution,
# tlast: its last). ARGS(s): the argument step s writes
def trap(tr, s, n, F, args, retw):
    return [f"--tr: {tr};", f"--ts: {s};", f"--tlast: calc(var(--tr) * {eq('var(--ts)', n)});", f"--tF: {F};",
            f"--taddr: mod(var(--tF) + {n} - var(--ts), 32768);", f"--tval: if(style(--tlast: 1): {retw}; else: {args});"]
# The dynamic operators (cc_ref.dyn_fast): two integers here (a result in range, not -0), DEQ / DNE identities, DLEQ / DLNE
# that and null == undefined and booleans as 1 / 0; a string's + to the cat class; anything else traps to the library, its
# frame at TRAPDEF, and returns to the instruction with pst WBACK, which moves the routine's value (read z) into A
DYNOPS = list(R.DYNOPS)
TRAPDEF, WBACK = R.TRAPDEF, R.WBACK
bothstr = f"calc({isstr_v(xB)} * {isstr_v(yC)})"
anydbl = f"min(1, calc({isdbl_v(xB)} + {isdbl_v(yC)}))"
# A string's + (no array or object, pst 0) goes to the cat class: pst CAT0 from the next execution (dcat)
CATT, CAT0 = 1024, 2048
NOCAT = os.environ.get('NOCAT') == '1'     # (measurement only: a string's + traps to the ROM's cat, as before the cat class)
anyao = f"min(1, calc({isarr_v(xB)} + {isobj_v(xB)} + {isarr_v(yC)} + {isobj_v(yC)} + {anydbl} + {isfun_v(xB)} + {isfun_v(yC)}))"     # (a double or a function too: the library)
def neg_v(x): return f"clamp(0, -1 * {x}, 1)"
def nz_v(x): return f"calc({x} * (1 - {eq(x, R.MZERO)}))"                    # -0 as 0
def nul_v(x): return f"calc({eq(x, R.NULL)} + {eq(x, R.UNDEF)})"
def norm_v(x): return f"calc({x} - ({x} - 1) * {eq(x, R.TRUE)} - {x} * ({eq(x, R.FALSE)} + {eq(x, R.MZERO)}))"   # booleans as 1 / 0
# the comparisons user code makes (D... and J...): (fast: the machine decides, the condition 0 / 1), by the operator's suffix;
# they read --dix / --diy (integers), --cqs (a string on either side), --cao (an array or object on one side only)
CMP_SUFFIX = ['LT', 'GT', 'LE', 'GE', 'EQ', 'NE', 'LEQ', 'LNE']
_ceq = f"calc((1 - {eq(xB, R.NAN)}) * {eq(nz_v(xB), nz_v(yC))})"
_cleq = (f"calc(min(1, calc({nul_v(xB)} + {nul_v(yC)})) * {nul_v(xB)} * {nul_v(yC)} + (1 - min(1, calc({nul_v(xB)} + {nul_v(yC)})))"
         f" * (1 - {eq(xB, R.NAN)}) * {eq(norm_v(xB), norm_v(yC))})")
CMP_FAST = {**{o: "calc(var(--dix) * var(--diy))" for o in ('LT', 'GT', 'LE', 'GE')}, 'EQ': "calc((1 - var(--cbs)) * (1 - var(--cdb)))",
            'NE': "calc((1 - var(--cbs)) * (1 - var(--cdb)))",
            'LEQ': "calc((1 - var(--cqs)) * (1 - var(--cao)) * (1 - var(--cdb)))", 'LNE': "calc((1 - var(--cqs)) * (1 - var(--cao)) * (1 - var(--cdb)))"}
CMP_COND = {**{o: BINE[o] for o in ('LT', 'GT', 'LE', 'GE')}, 'EQ': _ceq, 'NE': f"calc(1 - {_ceq})", 'LEQ': _cleq, 'LNE': f"calc(1 - {_cleq})"}
# the jumps: J<suffix>, and JN<relation>, the relation's negation (NaN: false either way)
JFAST = {**{'J' + o: CMP_FAST[o] for o in CMP_SUFFIX}, **{'JN' + o: CMP_FAST[o] for o in ('LT', 'GT', 'LE', 'GE')}}
JCOND = {**{'J' + o: CMP_COND[o] for o in CMP_SUFFIX}, **{'JN' + o: f"calc(1 - {CMP_COND[o]})" for o in ('LT', 'GT', 'LE', 'GE')}}
CMP_PRE = [f"--dix: {smi_v(xB)};", f"--diy: {smi_v(yC)};", f"--cbs: {bothstr};", f"--cdb: {anydbl};", f"--cqs: min(1, calc({isstr_v(xB)} + {isstr_v(yC)}));",
           f"--cao: max(calc({isarr_v(xB)} + {isobj_v(xB)} - {isarr_v(yC)} - {isobj_v(yC)}), calc({isarr_v(yC)} + {isobj_v(yC)} - {isarr_v(xB)} - {isobj_v(xB)}));"]
zy = eq(yC, 0)
# DBIT (A's 1024s: the operator k) of two integers: their bits from the two's complement, an integer's 19 (bit 18 its sign)
_dk = "round(down, var(--A) / 1024)"
def _bit(x, i): return f"mod(round(down, {x} / {2 ** i}), 2)"
_dand = "calc(" + " + ".join(f"{2 ** i} * {_bit(xB, i)} * {_bit(yC, i)}" for i in range(18)) + f" - {2 ** 18} * {_bit(xB, 18)} * {_bit(yC, 18)})"
_dsh = f"pow(2, mod({yC}, 32))"
_dbit = (f"calc(clamp(0, 3 - {_dk}, 1) * (({_dand}) * (1 - 2 * min(1, {_dk}) - {eq(_dk, 2)}) + ({xB} + {yC}) * min(1, {_dk}))"     # & | ^
         f" + {eq(_dk, 3)} * {xB} * {_dsh} + {eq(_dk, 4)} * round(down, {xB} / {_dsh})"
         f" + {eq(_dk, 5)} * round(down, ({xB} + 4294967296 * clamp(0, -1 * {xB}, 1)) / {_dsh}))")
_dr = {'DADD': f"calc({xB} + {yC})", 'DSUB': f"calc({xB} - {yC})", 'DMUL': f"calc({xB} * {yC})",
       'DDIV': f"calc(({xB}) / ({yC} + {zy}))", 'DMOD': f"rem({xB}, {yC} + {zy})", 'DBIT': _dbit, 'DNEG': f"calc(-1 * {xB})"}
_dsb = "calc(var(--dix) * var(--diy))"
_dok = {'DADD': f"calc({_dsb} * {smi_v('var(--dr)')})", 'DSUB': f"calc({_dsb} * {smi_v('var(--dr)')})",
        'DMUL': f"calc({_dsb} * {smi_v('var(--dr)')} * (1 - {eq('var(--dr)', 0)} * min(1, calc({neg_v(xB)} + {neg_v(yC)}))))",
        'DDIV': f"calc({_dsb} * (1 - {zy}) * {eq(f'rem({xB}, {yC} + {zy})', 0)} * (1 - {eq(xB, 0)} * {neg_v(yC)}))",
        'DMOD': f"calc({_dsb} * (1 - {zy}) * (1 - {eq('var(--dr)', 0)} * {neg_v(xB)}))",
        'DNEG': f"calc(var(--dix) * (1 - {eq(xB, 0)}) * {smi_v('var(--dr)')})", 'DBIT': f"calc({_dsb} * {smi_v('var(--dr)')} * clamp(0, 6 - {_dk}, 1))",
        **{'D' + o: CMP_FAST[o] for o in CMP_SUFFIX}}
_dval = {**{o: "var(--dr)" for o in _dr}, **{'D' + o: f"calc({R.FALSE} - {CMP_COND[o]})" for o in CMP_SUFFIX}}
# NUMLIT A, word1 (a number literal: A its cache, a global): A read as x; defined, it stays (written back as it is); undefined, the library's
# numlit parses the string word1 (the trap's arguments: word1, 0) and the instruction moves its value into A; word1 >= 16 (a function
# expression's value) always traps
DYNC = DYNOPS + ['NUMLIT']
_dok['NUMLIT'] = "calc((1 - " + eq('var(--vx)', R.UNDEF) + ") * clamp(0, 16 - var(--vg), 1))"; _dval['NUMLIT'] = "var(--vx)"     # (word1 >= 16: a function's value, always made)
DYN_PRE = (OPND + CMP_PRE + [f"--aA: {oaddr('mod(var(--A), 1024)')};", f"--dwb: {eq('var(--pst)', WBACK)};", f"--dnl: {eq('var(--op)', OP['NUMLIT'])};",
                   f"--dr: {by_op({o: _dr[o] for o in list(_dr)[:-1]}, _dr['DNEG'])};", f"--dok: {by_op({o: _dok[o] for o in DYNC[:-1]}, _dok[DYNC[-1]])};",
                   f"--dcat: calc({eq('var(--op)', OP['DADD'])} * (1 - min(1, var(--pst))) * (1 - var(--dok)) * var(--cqs) * (1 - {anyao}) * {0 if NOCAT else 1});",
                   f"--dval: {by_op({o: _dval[o] for o in DYNC[:-1]}, _dval[DYNC[-1]])};"] +
           trap("calc((1 - var(--dwb)) * min(1, calc(var(--pst) + (1 - var(--dok)) * (1 - var(--dcat)))))", "var(--pst)", 2,
                f"mod({fp} + {TRAPDEF}, 32768)", f"if(style(--dnl: 1): if(style(--pst: 0): 0; else: var(--vg)); style(--pst: 0): {yC}; else: {xB})",
                f"calc({TRAPDEF * 8192} + {pc} / 2)"))
DYN_NX = {'pc': f"if(style(--dcat: 1): {pc}; style(--tr: 0): calc({pc} + 2); style(--tlast: 1): {by_op({**{o: ENT[R.TRAPS[o]] for o in DYNOPS}, 'NUMLIT': ENT['numlit']}, 0)}; else: {pc})",
          'fp': f"if(style(--tlast: 1): var(--tF); else: {fp})", 'steps': "calc(var(--steps) + 1 - var(--tr) + var(--tlast) - var(--dcat))",
          'pst': f"if(style(--dcat: 1): {CAT0}; style(--tr: 0): 0; style(--tlast: 1): 0; else: calc(var(--pst) + 1))"}
# the collector's map of block starts (cc_ref.MAP): a block's word and bit, and the word with the bit set
pst = "var(--pst)"
MAPB = R.MAP
def mapword(base): return f"calc({MAPB} + round(down, ({base} - {HEAP0}) / 128))"
def mapbitv(base): return f"pow(2, mod(round(down, ({base} - {HEAP0}) / 8), 16))"
def mapset(v, bit): return f"calc({v} + {bit} * (1 - mod(round(down, {v} / {bit}), 2)))"     # (bit set: unchanged)
# The cat class (DADD with pst >= CATT; csssim.Sim.cat): pst CAT0 + k: k 0 HP += nw (the heap full: the ROM's
# gccat through a trap, pst CATT + its step), 1 the header and the length, 2 + i the characters from i (a line of them, from X or
# from Y: to the end of the source, of the written line, of a string's line; the NUL with the last if it fits), n + 2 the NUL,
# n + 3 the map's bit, n + 4 A. Reads: x, y; z, e: X's and Y's length words (strings); k, j: HP and GCLIM; line p: a string's
# characters; r: the map's word
def ndig(v): return f"calc(clamp(0, -1 * {v}, 1) + 1" + "".join(f" + clamp(0, max({v}, -1 * {v}) - {10 ** d - 1}, 1)" for d in range(1, 6)) + ")"
def numch(v, g):
    """character g of number v's decimal form"""
    a = f"max({v}, -1 * {v})"; ng = f"clamp(0, -1 * {v}, 1)"
    return (f"calc({ng} * {eq(g, 0)} * 45 + (1 - {ng} * {eq(g, 0)}) * (48 + mod(round(down, {a} / pow(10, {ndig(v)} - 1 - {g})), 10)))")
CAT_PRE = OPND + [f"--aA: {oaddr('var(--A)')};", f"--cX: {catv_v(xB)};", f"--cY: {catv_v(yC)};",
    "--csx: " + isstr_v("var(--cX)") + ";", "--csy: " + isstr_v("var(--cY)") + ";",
    f"--cla: if(style(--csx: 1): var(--vz); else: {ndig('var(--cX)')});",
    f"--clb: if(style(--csy: 1): var(--ve); else: {ndig('var(--cY)')});",
    "--ctn: calc(var(--cla) + var(--clb));", "--cnw: calc(round(down, (var(--ctn) + 10) / 8) * 8);",
    f"--cfull: clamp(0, var(--vk) + var(--cnw) - var(--vj) - {HS}, 1);",
    f"--ck: calc(var(--pst) - {CAT0});", f"--cbase: calc({HEAP0} + var(--vk) - var(--cnw));",
    # the characters from i = k - 2: of X (i < la), or of Y from i - la; a chunk of cc to the written line's end (uw), X's or Y's end
    # and a string's line's end (up); cnul: the NUL too
    "--ci: calc(var(--ck) - 2);", "--cfx: clamp(0, var(--cla) - var(--ci), 1);", "--cj: calc(var(--ci) - (1 - var(--cfx)) * var(--cla));",
    "--cvv: if(style(--cfx: 1): var(--cX); else: var(--cY));", "--cvs: if(style(--cfx: 1): var(--csx); else: var(--csy));",
    "--clv: if(style(--cfx: 1): var(--cla); else: var(--clb));",
    "--cin: calc(clamp(0, var(--ck) - 1, 1) * clamp(0, var(--ctn) - var(--ci), 1));",
    "--cc: max(0, min(var(--clv) - var(--cj), 4 - var(--uw), 4 - var(--cvs) * var(--up)));",
    "--cnul: calc(var(--cin) * " + eq('var(--ci) + var(--cc)', 'var(--ctn)') + " * clamp(0, 4 - var(--uw) - var(--cc), 1));"] + \
    [f"--cq{j}: clamp(0, {j} - var(--uw) + var(--up), 3);" for j in range(4)] + \
    trap(f"calc(clamp(0, {CAT0} - var(--pst), 1) + {eq('var(--pst)', CAT0)} * var(--cfull))", f"calc(clamp(0, {CAT0} - var(--pst), 1) * (var(--pst) - {CATT}))",
         2, f"mod({fp} + {R.TRAPDEF}, 32768)", f"if(style(--ts: 0): {yC}; else: {xB})", f"calc({R.TRAPDEF * 8192} + {pc} / 2)") + [
    "--cnull: calc((1 - var(--tr)) * " + eq('var(--ci)', 'var(--ctn)') + ");",
    "--cmap: calc((1 - var(--tr)) * " + eq('var(--ci)', 'var(--ctn) + 1') + ");",
    "--clast: calc((1 - var(--tr)) * " + eq('var(--ci)', 'var(--ctn) + 2') + ");",
    "--cmw: " + mapword('var(--cbase)') + ";", "--cmb: " + mapbitv('var(--cbase)') + ";",
    f"--caddr: if(style(--tr: 1): var(--taddr); style(--ck: 0): {HP}; style(--ck: 1): var(--cbase); style(--cin: 1): calc(var(--cbase) + 2 + var(--ci));"
    " style(--cnull: 1): calc(var(--cbase) + 2 + var(--ctn)); style(--cmap: 1): var(--cmw); else: var(--aA));",
    "--ckk: if(style(--ck: 1): 2; style(--cin: 1): calc(var(--cc) + var(--cnul)); else: 1);"]
def cat_val(j):
    r = f"({j} - var(--uw))"; g = f"(var(--cj) + {r})"
    ch = f"calc(clamp(0, var(--cc) - {r}, 1) * if(style(--cvs: 1): {pick('p', f'cq{j}')}; else: {numch('var(--cvv)', g)}))"
    hdr = ["calc(-2 - var(--cnw))", "var(--ctn)", "0", "0"][j]
    return (f"if(style(--tr: 1): var(--tval); style(--ck: 0): calc(var(--vk) + var(--cnw)); style(--ck: 1): {hdr}; style(--cin: 1): {ch};"
            f" style(--cnull: 1): 0; style(--cmap: 1): {mapset('var(--vr)', 'var(--cmb)')}; else: calc(var(--cbase) + {2 - STRTAG}))")
CAT_NX = {'pc': f"if(style(--clast: 1): calc({pc} + 2); style(--tlast: 1): {ENT['gccat']}; else: {pc})",
          'fp': f"if(style(--tlast: 1): var(--tF); else: {fp})", 'steps': "calc(var(--steps) + var(--clast) + var(--tlast))",
          'pst': f"if(style(--clast: 1): 0; style(--tlast: 1): 0; style(--tr: 1): calc({CATT} + var(--ts) + 1);"
                 " else: calc(var(--pst) + if(style(--cin: 1): calc(var(--cc) + var(--cnul)); else: 1)))"}
CAT_CLASS = dict(ops=[], pre=CAT_PRE,
                 reads=[("x", "var(--aB)", "1 - var(--kB)"), ("y", "var(--aC)", "1 - var(--kC)"),
                        ("z", f"mod(var(--cX) + {STRTAG - 1}, 32768)", "var(--csx)"), ("e", f"mod(var(--cY) + {STRTAG - 1}, 32768)", "var(--csy)"),
                        ("k", HP, "1"), ("r", "var(--cmw)", "var(--cmap)")],
                 lines=[("p", f"mod(var(--cvv) + {STRTAG} + var(--cj), 32768)", "calc(var(--cin) * var(--cvs) * (1 - var(--tr)))")],
                 pair={'k': 'j'}, write=("var(--caddr)", None, None, "1"), wline=("var(--ckk)", cat_val), nx=CAT_NX,
                 deps={'z': [('x', None)], 'e': [('y', None)], 'p': [('x', None), ('y', None), ('z', None)]})
# GETX / SETX: X the array (B / A), Y the index (C / B); z its length and h its ptr (the words before and at its value's address,
# read only for an array); e the element (GETX, inside the length) or C (SETX)
_xgtrap = f"calc(1 - var(--xarr) * {smi_v('var(--Y)')})"     # GETX: no array and an integer index: the library
ARR_PRE = OPND + OPNDA + [
    f"--X: {by_op({'GETX': kv('B', 'x')}, kv('A', 'x'))};", f"--Y: {by_op({'GETX': kv('C', 'y')}, kv('B', 'y'))};",
    f"--xarr: calc((1 - min(1, var(--pst))) * {isarr_v('var(--X)')});",
    "--xin: calc(var(--xarr) * clamp(0, var(--Y) + 1, 1) * clamp(0, var(--vz) - var(--Y), 1));",
    f"--E: {by_op({'GETX': f'calc(var(--xin) * var(--ve) + (1 - var(--xin)) * {R.UNDEF})'}, kv('C', 'e'))};",
    f"--xhand: calc({eq(pst, 0)} * {isobj_v('var(--X)')} * min(1, calc({smi_v('var(--Y)')} + {own_v('var(--Y)')})));"] + \
    trap(f"calc((1 - var(--xhand)) * {by_op({'GETX': _xgtrap}, 'calc(1 - var(--xin))')})", f"mod({pst}, {XBACK})", by_op({'GETX': 2}, 3),
         by_op({'GETX': "var(--aA)"}, f"mod({fp} + {TRAPOFF}, 32768)"),
         by_op({'GETX': "if(style(--ts: 0): var(--Y); else: var(--X))"}, "if(style(--ts: 0): var(--E); style(--ts: 1): var(--Y); else: var(--X))"),
         f"calc({by_op({'GETX': 'calc((var(--A) - 256) * 8192)'}, TRAPOFF * 8192)} + ({pc} + 2) / 2)")
ARR_NX = {'pc': f"if(style(--xhand: 1): {pc}; style(--tr: 0): calc({pc} + 2); style(--tlast: 1): {by_op({'GETX': ENT['getx']}, ENT['setx'])}; else: {pc})",
          'fp': DYN_NX['fp'], 'steps': "calc(var(--steps) + 1 - var(--tr) + var(--tlast) - var(--xhand))",
          'pst': f"if(style(--xhand: 1): mod(var(--X) + {OBJTAG}, 32768); style(--tr: 0): 0; style(--tlast: 1): 0; else: calc(var(--ts) + 1))"}
# GETP / SETP / NEW. A probe reads the pair at q (z: the key, h: the value): pst the pair's address, 0 the object's first. The
# case oc: GETP 1 done (the value or 0), 2 the next pair, 3 a string's (the library's getps: its frame at A, no arguments);
# SETP 3 a trap's execution (pst 1 ... 3, or the first: a full chunk),
# 4 the new pair (pst: its address + 1; the terminator is written), 5 not an object, 6 the key's value, 7 the new pair's
# terminator, 8 the next pair; NEW 9 the heap is full (the collector, NEW again), 10 one of its four writes (pst 0 the key word, 1
# A, 2 the map's bit, 3 HP); 11 SETX's chunk is full (back to the arr class's trap: pst XBACK). GETX and SETX come here (cls_of,
# pst a pair's address) for an object with a number or the program's own string as its key, and probe as GETP and SETP do
oq = "var(--oq)"
OBJ_PRE = OPND + OPNDA + [
    f"--O: {by_op({'GETP': kv('B', 'x'), 'GETX': kv('B', 'x')}, kv('A', 'x'))};", f"--ob: {isobj_v('var(--O)')};",
    f"--okey: {by_op({'GETX': s20(kv('C', 'y') + f' + {STRTAG}'), 'SETX': s20(kv('B', 'y') + f' + {STRTAG}')}, f'calc({DB} + var(--C))')};",
    f"--sst: calc({eq('var(--op)', OP['SETP'])} * min(1, var(--pst)) * clamp(0, {HEAP0} - var(--pst), 1));",
    f"--oq: {by_op({'NEW': HP}, f'calc(min(1, var(--pst)) * (var(--pst) - mod(var(--pst), 2)) + (1 - min(1, var(--pst))) * mod(var(--O) + {OBJTAG}, 32768))')};",
    f"--ohit: {eq('var(--vz)', 'var(--okey)')};",
    f"--oend: calc({eq('var(--vz)', 0)} + {by_op({'SETP': 1, 'SETX': 1}, 0)} * clamp(0, {-OBJTAG} - var(--vz), 1));",     # (SETP / SETX: a prototype's link ends the keys too)
    f"--onext: calc(clamp(0, -1 * var(--vz), 1) * mod(var(--vz) + {OBJTAG}, 32768) + (1 - clamp(0, -1 * var(--vz), 1)) * ({oq} + 2));",
    "--oc: " + by_op({'GETP': f"calc(1 + var(--ob) * (1 - var(--ohit) - var(--oend)) + 2 * {isstr_v('var(--O)')})", 'GETX': "calc(1 + var(--ob) * (1 - var(--ohit) - var(--oend)))",
                      'NEW': f"calc(10 - {eq('var(--pst)', 0)} * clamp(0, var(--vz) - var(--vh) - {HS - 8}, 1))"},
                     "if(style(--sst: 1): 3; style(--sodd: 1): 4; style(--ob: 0): 5; style(--ohit: 1): 6;"
                     f" style(--oend: 1): calc(3 + 4 * var(--oroom) + 8 * (1 - var(--oroom)) * {eq('var(--op)', OP['SETX'])}); else: 8)") + ";",
    f"--sodd: calc({opin('SETP', 'SETP')} * (1 - var(--sst)) * mod(var(--pst), 2) + {eq('var(--op)', OP['SETX'])} * mod(var(--pst), 2));",
    f"--oroom: clamp(0, 6 - mod({oq} - {HEAP0}, 8), 1);", f"--V: {by_op({'SETX': kv('C', 'e')}, kv('B', 'y'))};",
    f"--omw: {mapword(f'({HEAP0} + var(--vz))')};"] + \
    trap(f"{eq('var(--oc)', 3)}", "calc(var(--sst) * var(--pst))", by_op({'GETP': 0}, 3), by_op({'GETP': "var(--aA)"}, f"mod({fp} + {TRAPOFF}, 32768)"),
         "if(style(--ts: 0): var(--V); style(--ts: 1): var(--okey); else: var(--O))",
         by_op({'GETP': f"calc((var(--A) - 256) * 8192 + ({pc} + 2) / 2)"}, f"calc({TRAPOFF * 8192} + ({pc} + 2) / 2)")) + [
    f"--oaddr: if(style(--oc: 1): var(--aA); style(--oc: 3): var(--taddr); style(--oc: 4): {oq}; style(--oc: 6): calc({oq} + 1);"
    f" style(--oc: 7): calc({oq} + 2); style(--oc: 9) or style(--oc: 11): var(--aA); style(--pst: 0): calc({HEAP0} + var(--vz)); style(--pst: 1): var(--aA);"
    f" style(--pst: 2): var(--omw); else: {HP});",
    f"--oval: if(style(--oc: 1): calc(var(--ob) * var(--ohit) * var(--vh) + (1 - var(--ob) * var(--ohit)) * {R.UNDEF}); style(--oc: 3): var(--tval); style(--oc: 4): var(--okey);"
    f" style(--oc: 6): var(--V); style(--oc: 7): var(--vz); style(--oc: 9): calc((var(--A) - 256) * 8192 + {pc} / 2); style(--pst: 0): 0;"
    f" style(--pst: 1): calc(var(--vz) + {HEAP0 - OBJTAG}); style(--pst: 2): {mapset('var(--vr)', mapbitv(f'({HEAP0} + var(--vz))'))}; else: calc(var(--vz) + 8));",
    "--oen: if(style(--oc: 2) or style(--oc: 5) or style(--oc: 8) or style(--oc: 11): 0; else: 1);", f"--w2: {eq('var(--oc)', 4)};",
    f"--odone: calc({eq('var(--oc)', 1)} + {eq('var(--oc)', 4)} + {eq('var(--oc)', 5)} + {eq('var(--oc)', 6)} + {eq('var(--oc)', 10)} * {eq('var(--pst)', 3)});",
    f"--ojump: calc(var(--tlast) + {eq('var(--oc)', 9)});"]
OBJ_NX = {'pc': f"if(style(--odone: 1): calc({pc} + 2); style(--ojump: 1): if(style(--oc: 9): {ENT['gcnew']}; else: {by_op({'GETP': ENT['getps']}, ENT['setp'])}); else: {pc})",
          'fp': f"if(style(--ojump: 1): if(style(--oc: 9): var(--aA); else: var(--tF)); else: {fp})",
          'steps': "calc(var(--steps) + var(--odone) + var(--ojump))",
          'pst': "if(style(--oc: 2) or style(--oc: 8): var(--onext); style(--oc: 7): calc(var(--oq) + 1); style(--oc: 3): if(style(--tlast: 1): 0;"
                 f" else: calc(var(--ts) + 1)); style(--oc: 10): if(style(--pst: 3): 0; else: calc(var(--pst) + 1)); style(--oc: 11): {XBACK}; else: 0)"}
# KIND A, B, k: k (--kk) picks the test of B (cc_ref.KINDS): its kind's code, string, array, object, array or object, a string
# not the program's own, its decimal length, any reference, a heap string
_own = own_v(xB)
KINDE = ("if(" + " ".join(f"style(--kk: {i}): {e};" for i, e in enumerate([
    f"calc({isstr_v(xB)} + 2 * {isarr_v(xB)} + 3 * {isobj_v(xB)})", isstr_v(xB), isarr_v(xB), isobj_v(xB), f"calc({isarr_v(xB)} + {isobj_v(xB)})",
    f"calc({isstr_v(xB)} * (1 - {_own}))", ndig(xB), isref_v(xB), f"calc({isstr_v(xB)} * clamp(0, {xB} + {STRTAG - HEAP0 + 1}, 1))",
    # typeof: its name, BSTRS[BS_TYPE + type code] (cc_ref.typecode)
    f"calc({R.BSTRV(R.BS_TYPE)} + 12 * (4 * {isstr_v(xB)} + {isarr_v(xB)} + {isobj_v(xB)} + {eq(xB, R.NULL)} + 2 * ({eq(xB, R.TRUE)} + {eq(xB, R.FALSE)})"
    f" + 5 * {isfun_v(xB)} + 3 * (1 - {isstr_v(xB)} - {isarr_v(xB)} - {isobj_v(xB)} - {eq(xB, R.NULL)} - {eq(xB, R.UNDEF)} - {eq(xB, R.TRUE)} - {eq(xB, R.FALSE)}"
    f" - {isfun_v(xB)})))",
    special_v(xB), smi_v(xB), isdbl_v(xB), isfun_v(xB)])) +
    f" else: calc({smi_v(xB)} + {eq(xB, R.INF)} + {eq(xB, R.NINF)} + {eq(xB, R.NAN)} + {eq(xB, R.MZERO)} + {isdbl_v(xB)}))")     # (num)
# JZ / JNZ / NOT: 0 and the empty string are false (a string's length, the word before its address: read z, only for a string);
# in user code also false, null, undefined, NaN and -0 (the specials from FALSE on)
FALSY = ["--tz: calc(var(--tstr) * " + eq("var(--vz)", 0) + f" + (1 - var(--tstr)) * ({eq(xB, 0)} + {user} * clamp(0, {xB} - {R.FALSE - 1}, 1)));"]
# A class's rule evaluates all its declarations whether an instruction needs them or not, and a read costs a cache lookup,
# so each class reads only what its instructions read: x (B), y (C), z (a third word), w (the written word's set)
CLASSES = {
    'alu': dict(ops=BINOPS, pre=OPND + [f"--aA: {oaddr('var(--A)')};"],
                reads=[("x", "var(--aB)", "1 - var(--kB)"), ("y", "var(--aC)", "1 - var(--kC)")],
                write=("var(--aA)", by_op({o: BINE[o] for o in BINOPS[:-1]}, BINE[BINOPS[-1]]), None, "1"), nx={'pc': f"calc({pc} + 2)"}),
    'mov': dict(ops=['MOV', 'NEG', 'LOADK', 'GETFP', 'KIND'], pre=OPND[0:1] + OPND[2:3] + OPND[4:5] + [f"--aA: {oaddr('var(--A)')};", "--kk: calc(var(--C) - 896);"],
                reads=[("x", "var(--aB)", f"(1 - var(--kB)) * (1 - {eq('var(--op)', OP['LOADK'])} - {eq('var(--op)', OP['GETFP'])})")],
                write=("var(--aA)", by_op({'MOV': xB, 'LOADK': "var(--vg)", 'GETFP': fp, 'KIND': KINDE}, s20(f"-1 * {xB}")), None, "1"), nx={'pc': f"calc({pc} + 2)"}),
    # JLT ... JLNE in user code: two integers (and the identities of JEQ ... JLNE) here (CMP_FAST); else --jho hands off to the
    # jtrap class (pst CATT), which calls the library's jcmp; the runtime library's jumps compare raw words
    'jump': dict(ops=['JMP', 'JNE', 'JLT', 'JGE', 'JLE', 'JGT', 'JEQ', 'JLEQ', 'JLNE', 'JNLT', 'JNGT', 'JNLE', 'JNGE', 'HALT'], pre=OPND + CMP_PRE +
                 [f"--juser: {user};", "--jcr: " + by_op({'JMP': 1, **{f'J{o}': BINE[o] for o in ('LT', 'GT', 'LE', 'GE', 'EQ')}}, BINE['NE']) + ";",
                  f"--jok: {by_op({o: JFAST[o] for o in list(JFAST)[:-1]}, JFAST['JNGE'])};",
                  f"--jcu: {by_op({o: JCOND[o] for o in list(JCOND)[:-1]}, JCOND['JNGE'])};",
                  f"--jho: calc(var(--juser) * {opin('JLT', 'JNGE')} * (1 - var(--jok)));",
                  "--jc: if(style(--juser: 1) and style(--jok: 1): var(--jcu); else: var(--jcr));"],
                 reads=[("x", "var(--aB)", f"(1 - var(--kB)) * {opin('JLT', 'JNGE')}"), ("y", "var(--aC)", f"(1 - var(--kC)) * {opin('JLT', 'JNGE')}")],
                 write=None,
                 nx={'pc': by_op({'HALT': pc, 'JMP': "calc(2 * var(--A))"}, f"if(style(--jho: 1): {pc}; else: calc(var(--jc) * 2 * var(--A) + (1 - var(--jc)) * ({pc} + 2)))"),
                     'steps': "calc(var(--steps) + 1 - var(--jho))", 'pst': f"calc(var(--jho) * {CATT})"}),
    'test': dict(ops=['JZ', 'JNZ'], pre=OPND[0:1] + OPND[2:3] + OPND[4:5] + [f"--tstr: {isstr_v(xB)};"] + FALSY +
                 [f"--jc: {by_op({'JZ': 'var(--tz)'}, 'calc(1 - var(--tz))')};"],
                 reads=[("x", "var(--aB)", "1 - var(--kB)"), ("z", f"mod({xB} - 1, 32768)", "var(--tstr)")], write=None,
                 nx={'pc': f"calc(var(--jc) * 2 * var(--A) + (1 - var(--jc)) * ({pc} + 2))"}, deps={'z': [('x', None)]}),
    # CALL A, off: the return word (off * 8192 + the return address / 2) at fp + off, fp += off, pc = 2 A (code targets and return
    # addresses count instruction pairs). RET B: B over the return word
    # (the caller's slot for the value), fp -= off. NOT A, B (reads a string's length, z, as JZ does). TENTER A: CALL A with
    # off TRAPOFF and the return address pst + 2 (PRINT's trap, through pstub)
    'call': dict(ops=['CALL', 'RET', 'NOT', 'TENTER'], pre=OPND[0:1] + OPND[2:3] + OPND[4:5] + [f"--aA: {oaddr('var(--A)')};",
                 f"--tstr: calc({eq('var(--op)', OP['NOT'])} * {isstr_v(xB)});"] + FALSY,
                 reads=[("x", "var(--aB)", f"(1 - {eq('var(--op)', OP['CALL'])} - {eq('var(--op)', OP['TENTER'])}) * (1 - var(--kB))"),
                        ("z", by_op({'NOT': f"mod({xB} - 1, 32768)"}, fp), f"calc({eq('var(--op)', OP['RET'])} + var(--tstr))")],
                 write=(by_op({'CALL': f"mod({fp} + var(--vg), 32768)", 'NOT': "var(--aA)", 'TENTER': f"mod({fp} + {TRAPOFF}, 32768)"}, fp),
                        by_op({'CALL': f"calc(var(--vg) * 8192 + ({pc} + 2) / 2)", 'NOT': f"calc(var(--tz) + {user} * ({R.FALSE} - 2 * var(--tz)))",
                               'TENTER': f"calc({TRAPOFF * 8192} + (var(--pst) + 2) / 2)"}, xB), None, "1"),
                 nx={'pc': by_op({'CALL': "calc(2 * var(--A))", 'RET': "calc(2 * mod(var(--vz), 8192))", 'TENTER': "calc(2 * var(--A))"}, f"calc({pc} + 2)"),
                     'fp': by_op({'CALL': f"calc({fp} + var(--vg))", 'RET': f"calc({fp} - round(down, var(--vz) / 8192))", 'TENTER': f"calc({fp} + {TRAPOFF})"}, fp),
                     'pst': by_op({'RET': f"calc({WBACK} * {eq('round(down, var(--vz) / 8192)', TRAPDEF)})"}, "0")},
                 deps={'z': [('x', ['NOT'])]}),
    # LDI A, B, C: A = mem[B + C] (z); STI A, B, C: mem[A + B] = C (z: A's value). The runtime library's raw memory
    'mem': dict(ops=['LDI', 'STI'], pre=OPND + OPNDA + [f"--zA: {kv('A', 'z')};"],
                reads=[("x", "var(--aB)", "1 - var(--kB)"), ("y", "var(--aC)", "1 - var(--kC)"),
                       ("z", by_op({'LDI': f"mod({xB} + {yC}, 32768)"}, "var(--aA)"), by_op({'LDI': 1}, "calc(1 - var(--kA))"))],
                write=(by_op({'LDI': "var(--aA)"}, f"mod(var(--zA) + {xB}, 32768)"), by_op({'LDI': "var(--vz)"}, yC), None, "1"),
                nx={'pc': f"calc({pc} + 2)"}, deps={'z': [('x', ['LDI']), ('y', ['LDI'])]}),
    'dyn': dict(ops=DYNC, pre=DYN_PRE, reads=[("x", "if(style(--dnl: 1): var(--aA); else: var(--aB))", "(1 - (1 - var(--dnl)) * var(--kB)) * (1 - var(--dwb))"),
                                              ("y", "var(--aC)", "(1 - var(--kC)) * (1 - var(--dwb)) * (1 - var(--dnl))"),
                                              ("z", f"mod({fp} + {TRAPDEF}, 32768)", "var(--dwb)")],
                write=("if(style(--tr: 1): var(--taddr); else: var(--aA))", "if(style(--tr: 1): var(--tval); style(--dwb: 1): var(--vz); else: var(--dval))", None,
                       "calc(1 - var(--dcat))"),                 # (the hand-off to the cat class writes nothing)
                nx=DYN_NX),
    'arr': dict(ops=['GETX', 'SETX'], pre=ARR_PRE,
                reads=[("x", by_op({'GETX': "var(--aB)"}, "var(--aA)"), by_op({'GETX': "calc(1 - var(--kB))"}, "calc(1 - var(--kA))")),
                       ("y", by_op({'GETX': "var(--aC)"}, "var(--aB)"), by_op({'GETX': "calc(1 - var(--kC))"}, "calc(1 - var(--kB))")),
                       ("z", f"mod(var(--X) - {ARRTAG + 1}, 32768)", "var(--xarr)"),
                       ("e", by_op({'GETX': "mod(var(--vh) + var(--Y), 32768)"}, "var(--aC)"), by_op({'GETX': "var(--xin)"}, "calc(1 - var(--kC))"))],
                pair={'z': 'h'},
                write=("if(style(--tr: 1): var(--taddr); else: " + by_op({'GETX': "var(--aA)"}, "mod(var(--vh) + var(--Y), 32768)") + ")",
                       "if(style(--tr: 1): var(--tval); else: var(--E))", None, "calc(1 - var(--xhand))"),
                nx=ARR_NX, deps={'z': [('x', None)], 'e': [('z', ['GETX']), ('y', ['GETX'])]}),
    'obj': dict(ops=['GETP', 'SETP', 'NEW'], pre=OBJ_PRE,
                reads=[("x", by_op({'GETP': "var(--aB)", 'GETX': "var(--aB)"}, "var(--aA)"),
                        by_op({'GETP': "calc(1 - var(--kB))", 'GETX': "calc(1 - var(--kB))", 'NEW': 0}, "calc(1 - var(--kA))")),
                       ("y", by_op({'GETX': "var(--aC)"}, "var(--aB)"), by_op({'SETP': "calc(1 - var(--kB))", 'SETX': "calc(1 - var(--kB))", 'GETX': "calc(1 - var(--kC))"}, 0)),
                       ("e", "var(--aC)", f"calc({eq('var(--op)', OP['SETX'])} * (1 - var(--kC)))"),
                       ("z", "var(--oq)", by_op({'GETP': "var(--ob)", 'SETP': "calc(var(--ob) * (1 - var(--sst)))"}, 1)),
                       ("r", "var(--omw)", f"calc({eq('var(--op)', OP['NEW'])} * {eq(pst, 2)})")],
                pair={'z': 'h'},
                write=("var(--oaddr)", "var(--oval)", None, "var(--oen)", "var(--V)"),
                nx=OBJ_NX, deps={'z': [('x', ['GETP', 'SETP'])]}),
}
JTRAP_CLASS = dict(ops=[], pre=OPND + trap("1", f"calc(var(--pst) - {CATT})", 2, f"mod({fp} + {TRAPOFF}, 32768)",
                                             f"if(style(--ts: 0): {yC}; else: {xB})", f"calc({TRAPOFF * 8192} + ({pc} + 2) / 2)"),
                   reads=[("x", "var(--aB)", "1 - var(--kB)"), ("y", "var(--aC)", "1 - var(--kC)")],
                   write=("var(--taddr)", "var(--tval)", None, "1"),
                   nx={'pc': f"if(style(--tlast: 1): {ENT['jcmp']}; else: {pc})", 'fp': f"if(style(--tlast: 1): var(--tF); else: {fp})",
                       'steps': "calc(var(--steps) + var(--tlast))", 'pst': "if(style(--tlast: 1): 0; else: calc(var(--pst) + 1))"})
def first_miss(acc):
    """the block of the first missing access (dependency order) among [(name, mask)], -1 for none"""
    e = "-1"
    for n, m in reversed(acc): e = f"calc({m}{miss(n)} * var(--b{n}) + (1 - {m}{miss(n)}) * {e})"
    return e
def need(ops):
    if ops is None: return ""
    if isinstance(ops, str): return f"({ops}) * "
    return "(" + " + ".join(eq("var(--op)", OP[o]) for o in ops) + ") * "
def nexts(nx, done="1"):
    return [f"--npc: {nx.get('pc', f'calc({pc} + 2 * {done})')};", f"--nfp: {nx.get('fp', fp)};",
            f"--nsteps: {nx.get('steps', f'calc(var(--steps) + {done})')};"] + ([f"--npst: {nx['pst']};"] if 'pst' in nx else [])
cls_rules = {}
def build_class(c, k):
    """reads (single words, after them lines: (name, address, need)), then the write; a latched read is kept only if the reads
    its address came from (deps) were good"""
    d, acc = list(k.get('pre', [])), []
    for n, A, ops_n in k['reads']:
        d += read_pair(n, A, k['pair'][n]) if n in k.get('pair', {}) else read(n, A); acc.append((n, need(ops_n)))
    for n, A, ops_n in k.get('lines', []): d += line_read(n, A); acc.append((n, need(ops_n)))
    good = {}
    for n, _, _ in k['reads'] + k.get('lines', []):
        if n not in LATCH: continue
        g = f"(1 - {miss(n)})"
        for m, ops_m in k.get('deps', {}).get(n, []): g += f" * (1 - {need(ops_m)}{miss(m)})"
        good[n] = g
    d.append("--hm: calc(1 - var(--mf)" + "".join(f" + {LATCH[n]} * {g}" for n, g in good.items()) + ");")
    if k['write']:
        A, V, reuse, en = k['write'][:4]
        if reuse is None: d += lookup("w", A); acc.append(("w", "" if en == "1" else f"({en}) * ")); wn = "w"
        else: wn = reuse
        d += write_line(wn, k['wline'][1], en, k['wline'][0]) if 'wline' in k else write(wn, V, en, *k['write'][4:])
    d += [f"--ok: calc(1 - min(1, calc({' + '.join(f'{m}{miss(n)}' for n, m in acc)})));" if acc else "--ok: 1;",
          f"--mb: {first_miss(acc)};" if acc else "--mb: -1;"] + nexts(k['nx'])
    if c == 'jump': d += [f"--nstop: {eq('var(--op)', OP['HALT'])};", f"--nhalt: {eq('var(--op)', OP['HALT'])};"]
    if c == 'net': d += [f"--ok: calc((1 - min(1, calc((1 - var(--kB)) * {miss('x')} + {miss('w')}))) * var(--nok));",      # (replaces the generic --ok: it waits)
                         f"--req: calc((1 - var(--ok) * var(--nfin)) * (1 - (1 - var(--kB)) * {miss('x')}) * (1 + mod({xB}, 524288)));"]
    cls_rules[c] = (k['ops'], d)
for c, k in CLASSES.items():
    if c != 'alu': build_class(c, k)          # (the alu class's opcodes come last: only the runtime library uses them)

# 'out': PRINT B, PRINTK (the value in word1) and PUTC B, as gen_css.py's print service: up to 4 console cells per execution,
# one per bank; a string chunk ends at its block (the block's line must be cached), at a NUL (the value is out) or a newline
# (taken); until the value is out the instruction repeats (npc = pc) and --pst carries the position. Output needs the pass's
# write set free. A = separator * 2 (rc_ref SEP) + 8 for a + chain's piece; a special prints its name (a built-in string). PRINT of an array or an object (ptrap)
# prints nothing here: it jumps to pstub with its own address in pst (TENTER, then the library's ptrap)
pv = "var(--pv)"
isputc = eq("var(--op)", OP['PUTC'])
pr = OPND + read("x", "var(--aB)") + [
    f"--mx: calc((1 - var(--kB)) * (1 - {eq('var(--op)', OP['PRINTK'])}) * {miss('x')});",
    f"--pv: {by_op({'PRINTK': 'var(--vg)'}, xB)};",
    f"--prLN: {eq('round(down, mod(var(--A), 8) / 2)', 2)};", f"--prSP: {eq('round(down, mod(var(--A), 8) / 2)', 1)};",
    f"--ptrap: calc({eq('var(--op)', OP['PRINT'])} * ({isarr_v(pv)} + {isobj_v(pv)} + {isdbl_v(pv)} + {isfun_v(pv)}));",
    f"--pp: calc({pv} + {STRTAG} + {special_v(pv)} * ({R.BSTR + 1 - 12 * R.SPV0 - STRTAG} + 11 * {pv}"
    f" + 12 * clamp(0, mod(var(--A), 16) - 7, 1) * {eq(pv, R.MZERO)}));",       # (a special: its name; a + chain's piece's -0: "0")
    f"--isStr: calc((1 - {isputc}) * clamp(0, var(--pp) - {STR_LO - 1}, 1) * clamp(0, {STRP_HI} - var(--pp), 1));",
    "--isNum: calc(1 - var(--isStr));",
    "--pq: calc(min(1, var(--pst)) * var(--pst) + (1 - min(1, var(--pst))) * var(--pp));",
    f"--pdone: calc(var(--isStr) * {eq('var(--pq)', STR_LO)});", "--pj0: mod(var(--pq), 4);"]
pr += lookup("p", "var(--pq)")
pr += [f"--pw{j}: if(style(--lat: 1) and style(--Lbp: 1): var(--rLp{j}); else: " + sel("qp", NSET, lambda s, j=j: f"if(style(--Hp: 1): var(--W{2 * s + 1}_{j}); else: var(--W{2 * s}_{j}))") + ");" for j in range(4)]
pr.append(f"--hm: calc(1 - var(--mf) + 2 * (1 - {miss('x')}) + 16 * (1 - {miss('p')}) * (1 - var(--mx)));")
pr += [f"--mpp: calc(var(--isStr) * (1 - var(--pdone)) * {miss('p')});",
       f"--pa: max({pv}, -1 * {pv});", f"--pneg: clamp(0, -1 * {pv}, 1);",
       "--pL: calc(1 + " + " + ".join(f"clamp(0, var(--pa) - {10 ** dd - 1}, 1)" for dd in range(1, 6)) + ");",
       "--ptot: calc(var(--isNum) * (var(--pneg) + var(--pL)) + var(--prSP));",
       "--pbase: calc((1 - var(--isStr)) * var(--pst));"]          # (a number's characters out so far)
for i in range(4):
    g = f"var(--pg{i})"
    inum = f"clamp(0, var(--pneg) + var(--pL) - {g}, 1)"; ineg = f"clamp(0, var(--pneg) - {g}, 1)"
    digit = f"mod(round(down, var(--pa) / pow(10, var(--pneg) + var(--pL) - 1 - {g})), 10)"
    pr += [f"--pg{i}: calc(var(--pbase) + {i});",
           f"--pnb{i}: calc(var(--isNum) * ({ineg} * 45 + ({inum} - {ineg}) * (48 + {digit})) + (1 - var(--isStr)) * var(--prSP) * {eq(g, 'var(--ptot) - 1')} * 32);"]
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
       # the console banks this pass has written (cw, a mask): the run of free ones from optr's (pf) takes a chunk, cut there
       # (pcut: a string's characters, or its separator, past it; a number's, by pf alone)
       ] + [f"--pfr{j}: calc(1 - mod(round(down, var(--cw) / pow(2, mod(var(--optr) + {j}, 4))), 2));" for j in range(4)] + [
       "--pf: calc(var(--pfr0) * (1 + var(--pfr1) * (1 + var(--pfr2) * (1 + var(--pfr3)))));",
       f"--pcut: calc(var(--isStr) * (clamp(0, var(--pe) - var(--pf), 1) + {eq('var(--pe)', 'var(--pf)')} * var(--ptNul) * var(--prSP)));",
       f"--pn0: if(style(--op: {OP['PUTC']}): calc(1 - {eq(pv, 10)}); else: calc(var(--isStr) * (var(--pe) + var(--ptNul) * var(--prSP)) + (1 - var(--isStr)) * clamp(0, var(--ptot) - var(--pbase), 4)));",
       f"--pn: if(style(--op: {OP['PUTC']}): var(--pn0); else: calc(var(--pcut) * min(var(--pe), var(--pf)) + (1 - var(--pcut)) * min(var(--pn0), var(--pf))));",
       f"--pfin: if(style(--op: {OP['PUTC']}): 1; else: calc(var(--isStr) * (1 - var(--pcut)) * var(--ptNul) + (1 - var(--isStr)) * clamp(0, var(--pbase) + min(4, var(--pf)) + 1 - var(--ptot), 1)));",
       f"--pnl: if(style(--op: {OP['PUTC']}): {eq(pv, 10)}; else: calc(var(--isStr) * (1 - var(--pcut)) * (var(--ptNL) + var(--ptNul) * var(--prLN)) + (1 - var(--isStr)) * var(--pfin) * var(--prLN)));",
       f"--npst: if(style(--ptrap: 1): {pc}; else: calc(var(--isStr) * (var(--pcut) * (var(--pq) + min(var(--pe), var(--pf))) + (1 - var(--pcut)) * (1 - var(--ptNul)) * (var(--pq) + var(--pe) + var(--ptNL)))"
       " + (1 - var(--isStr)) * (1 - var(--pfin)) * (var(--pbase) + var(--pn))));",
       # nothing fits this pass: the chain stops (no fill)
       f"--pblk: calc((1 - var(--ptrap)) * if(style(--op: {OP['PUTC']}): clamp(0, var(--pn0) - var(--pf), 1); else: calc((1 - min(1, var(--pn))) * (1 - var(--pfin)) * (1 - var(--pnl)))));"]
for i in range(4):
    pr.append(f"--pch{i}: " + (f"if(style(--op: {OP['PUTC']}): {pv}; else: " if i == 0 else "") +
              f"calc(var(--isStr) * (var(--pr{i}) * var(--pb{i}) + {eq('var(--pe)', i)} * var(--ptNul) * var(--prSP) * (1 - var(--pcut)) * 32)"
              f" + (1 - var(--isStr)) * clamp(0, var(--pn) - {i}, 1) * var(--pnb{i}))" + (")" if i == 0 else "") + ";")
pr += ["--ok: calc((1 - min(1, calc(var(--mx) + var(--mpp)))) * (1 - var(--pblk)));",
       "--mb: calc(var(--mx) * var(--bx) + (1 - var(--mx)) * (var(--mpp) * var(--bp) + (1 - var(--mpp)) * -1));"]
pr += nexts({'pc': f"if(style(--ptrap: 1): {ENT['pstub']}; else: calc({pc} + 2 * var(--pfin)))",
             'steps': "calc(var(--steps) + max(var(--pfin), var(--ptrap)))"})
# cell i of the chunk goes to optr + i, bank (optr + i) mod 4 (OUT_BASE is a multiple of 4)
pr += ["--pout: calc(var(--ok) * (1 - var(--ptrap)));",
       "--ncw: calc(" + " + ".join(f"{1 << w} * max(mod(round(down, var(--cw) / {1 << w}), 2), var(--dp{w}))" for w in range(WB)) + ");",
       f"--noptr: mod(var(--pnl) * (round(down, (var(--optr) + var(--pn)) / {COLS}) + 1) * {COLS} + (1 - var(--pnl)) * (var(--optr) + var(--pn)), {OUT_SIZE});"]
for w in range(WB):
    pr += [f"--pi{w}: mod({w} - var(--optr), 4);", f"--dp{w}: clamp(0, var(--pn) - var(--pi{w}), 1);",
           f"--nwA{w}: calc(var(--dp{w}) * (round(down, mod(var(--optr) + var(--pi{w}), {OUT_SIZE}) / 4) + 1));",
           f"--nwD{w}: calc(" + " + ".join(f"{eq(f'var(--pi{w})', i)} * var(--pch{i})" for i in range(4)) + ");"]
cls_rules['out'] = (['PRINT', 'PRINTK', 'PUTC'], pr)
# ---------------- the runtime's primitives (cc_ref.OPN's comment; csssim.py has them execution by execution). --pst holds the
# progress; MCPY's and MCMP's families take a line per execution (write_line: words u .. u + k - 1 of the write's line; line
# reads p, latched like PRINT's, and l, not latched: it is the one read that can miss last). The map's word (read r) isn't
# latched either: the execution that reads it writes it, so a miss there fills the written line
# ALLOC A, n, k: pst = the phase (cc_ref.AP_*): 0 HP += the words (the heap full: the trap, CATT + its step: galloc, then
# ALLOC again), 1 the header's line, 2 a string's NUL past it, 3 the map's bit, 4 A. Each phase re-derives the block from HP
AL_PRE = OPND + OPNDA + [
    "--ak: calc(var(--C) - 896);",
    f"--anw: calc(8 * round(up, ({xB} + if(style(--ak: 0): 3; style(--ak: 1): 4; style(--ak: 4): 8; else: 0)) / 8));",
    f"--afull: calc({eq(pst, 0)} * clamp(0, var(--vk) + var(--anw) - var(--vj) - {HS}, 1));",
    f"--abase: calc({HEAP0} + var(--vk) - clamp(0, {pst}, 1) * var(--anw));",
    f"--amw: {mapword('var(--abase)')};", f"--amb: {mapbitv('var(--abase)')};", f"--amap: {mapset('var(--vr)', 'var(--amb)')};",
    f"--ares: if(style(--ak: 0): calc(var(--abase) + {2 - STRTAG}); style(--ak: 1): calc(var(--abase) + {3 + ARRTAG});"
    f" style(--ak: 4): calc(var(--abase) + {4 - R.DBLTAG}); else: var(--abase));",
    f"--anext: if(style(--pst: 0): if(style(--ak: 2): 4; style(--ak: 3): 3; else: 1); style(--pst: 1): calc(3 - {eq('var(--ak)', 0)} * clamp(0, {xB} - 1, 1));"
    " style(--pst: 2): 3; else: 4);"] + \
    trap(f"calc(clamp(0, {pst} - {CATT - 1}, 1) + var(--afull))", f"calc(clamp(0, {pst} - {CATT - 1}, 1) * ({pst} - {CATT}))", 1, "var(--aA)",
         "var(--anw)", f"calc((var(--A) - 256) * 8192 + {pc} / 2)") + [
    f"--adone: calc((1 - var(--tr)) * {eq(pst, 4)});",
    f"--aaddr: if(style(--tr: 1): var(--taddr); style(--pst: 0): {HP}; style(--pst: 1): var(--abase); style(--pst: 2): calc(var(--abase) + 2 + {xB});"
    " style(--pst: 3): var(--amw); else: var(--aA));",
    f"--akk: calc(1 + 3 * (1 - var(--tr)) * {eq(pst, 1)});"]
def alloc_val(j):
    hdr = [f"calc(-2 - var(--anw) - {eq('var(--ak)', 1)} - 2 * {eq('var(--ak)', 4)})", xB, "0", f"calc({eq('var(--ak)', 1)} * (var(--abase) + 4))"][j]
    return (f"if(style(--tr: 1): var(--tval); style(--pst: 0): calc(var(--vk) + var(--anw)); style(--pst: 1): {hdr}; style(--pst: 2): 0;"
            " style(--pst: 3): var(--amap); else: var(--ares))")
TRAP_NX = lambda routine, done: {'pc': f"if(style(--tlast: 1): {routine}; style(--{done}: 1): calc({pc} + 2); else: {pc})",
                                 'fp': f"if(style(--tlast: 1): var(--tF); else: {fp})", 'steps': f"calc(var(--steps) + var(--tlast) + var(--{done}))"}
NEWCLASSES = {}
# CALLV A, off: x the callee (fp + off), l its block's first line [hdr code meta env] when it is a function: one whose meta is A
# (or A - 32: a this given to one that doesn't use it; cc_ref callv_end) is entered (the return word over x); an inner one's
# (meta + 16) first takes an execution (pst 0 -> 2) to put its env (lw3) in its local 1, past the A % 32 parameters; anything
# else traps to callv (frame at TRAPOFF, its argument x)
# (gdl, gdc, gs (inner), gb (the env's execution): pooled names, the fdig class's)
CV_PRE = [f"--gdl: {isfun_v('var(--vx)')};", f"--gs: calc(var(--gdl) * clamp(0, 64 - var(--lw2), 1) * clamp(0, mod(var(--lw2), 32) - 15, 1));",
          f"--gdc: calc(var(--gdl) * ({eq('var(--lw2) - 16 * var(--gs)', 'var(--A)')} + {eq('var(--lw2) - 16 * var(--gs) + 32', 'var(--A)')})"
          f" * ({eq(pst, 0)} + {eq(pst, 2)}));", f"--gb: calc(var(--gdc) * var(--gs) * {eq(pst, 0)});"] + \
    trap("calc(1 - var(--gdc))", "var(--pst)", 1, f"mod({fp} + {TRAPOFF}, 32768)", "var(--vx)", f"calc({TRAPOFF * 8192} + ({pc} + 2) / 2)")
NEWCLASSES['callv'] = dict(ops=['CALLV'], pre=CV_PRE,
    reads=[("x", f"mod({fp} + var(--vg), 32768)", "1")], lines=[("l", f"mod(var(--vx) + {R.FUNTAG - 1}, 32768)", "var(--gdl)")],
    write=("if(style(--tr: 1): var(--taddr); style(--gb: 1): mod(" + fp + " + var(--vg) + 2 + mod(var(--A), 32), 32768); else: mod(" + fp + " + var(--vg), 32768))",
           f"if(style(--tr: 1): var(--tval); style(--gb: 1): var(--lw3); else: calc(var(--vg) * 8192 + ({pc} + 2) / 2))", None, "1"),
    nx={'pc': f"if(style(--tr: 0) and style(--gb: 0): calc(2 * var(--lw1)); style(--tlast: 1): {ENT['callv']}; else: {pc})",
        'fp': f"if(style(--tr: 0) and style(--gb: 0): calc({fp} + var(--vg)); style(--tlast: 1): var(--tF); else: {fp})",
        'steps': "calc(var(--steps) + (1 - var(--tr)) * (1 - var(--gb)) + var(--tlast))",
        'pst': "if(style(--tr: 0): calc(2 * var(--gb)); style(--tlast: 1): 0; else: calc(var(--pst) + 1))"},
    deps={'l': [('x', None)]})
NEWCLASSES['alloc'] = dict(ops=['ALLOC'], pre=AL_PRE,
    reads=[("x", "var(--aB)", "1 - var(--kB)"), ("k", HP, "1"), ("r", "var(--amw)", f"calc((1 - var(--tr)) * {eq(pst, 3)})")], pair={'k': 'j'},
    write=("var(--aaddr)", None, None, "1"), wline=("var(--akk)", alloc_val),
    nx=dict(TRAP_NX(ENT['galloc'], 'adone'),
            pst=f"if(style(--tr: 1): if(style(--tlast: 1): 0; else: calc({CATT} + var(--ts) + 1)); style(--adone: 1): 0; else: var(--anext))"))
# APUSH 0, x, v (the ROM's push routine's first instruction): pst 0 the element at ptr + len (no array, or a full one: on to the
# next instruction), 1 len + 1, 2 the length over the return word at fp, and return (as RET). The array's first line [hdr cap len
# ptr] is line p; z the return word
NEWCLASSES['apush'] = dict(ops=['APUSH'], pre=OPND + [
    f"--uarr: {isarr_v(xB)};", "--uok: calc(var(--uarr) * clamp(0, var(--pw1) - var(--pw2), 1));", f"--ufall: calc({eq(pst, 0)} * (1 - var(--uok)));",
    f"--uaddr: if(style(--pst: 0): mod(var(--pw3) + var(--pw2), 32768); style(--pst: 1): mod({xB} - 1, 32768); else: {fp});",
    f"--uval: if(style(--pst: 0): {yC}; style(--pst: 1): calc(var(--pw2) + 1); else: var(--pw2));"],
    reads=[("x", "var(--aB)", "1 - var(--kB)"), ("y", "var(--aC)", "1 - var(--kC)"), ("z", fp, eq(pst, 2))],
    lines=[("p", f"mod({xB} - 3, 32768)", "var(--uarr)")],
    write=("var(--uaddr)", "var(--uval)", None, "calc(1 - var(--ufall))"),
    nx={'pc': f"if(style(--ufall: 1): calc({pc} + 2); style(--pst: 2): calc(2 * mod(var(--vz), 8192)); else: {pc})",
        'fp': f"if(style(--pst: 2): calc({fp} - round(down, var(--vz) / 8192)); else: {fp})",
        'steps': f"calc(var(--steps) + var(--ufall) + {eq(pst, 2)})", 'pst': "if(style(--ufall: 1): 0; style(--pst: 0): 1; style(--pst: 1): 2; else: 0)"},
    deps={'p': [('x', None)]})
# MCPY / MUPPER / MLOWER A, B, C: C words from B to A; MFILL A, B, C: B into C words at A; NPUT A, B: B's digits at A. pst: the words
# done; k words an execution (to the end of the run, of A's line and, copying, of B's line)
def declen(x, pa, pn, pl):
    """--pa = |x|, --pn = x < 0, --pl = its digits: x in decimal is pn + pl characters"""
    return [f"--{pa}: max({x}, -1 * {x});", f"--{pn}: clamp(0, -1 * {x}, 1);",
            f"--{pl}: calc(1 + " + " + ".join(f"clamp(0, var(--{pa}) - {10 ** dd - 1}, 1)" for dd in range(1, 6)) + ");"]
def mcpy_val(j):
    c = f"var(--mc{j})"
    inr = f"clamp(0, {c} - var(--mlo) + 1, 1) * clamp(0, var(--mlo) + 26 - {c}, 1)"
    g = f"(var(--mo) + {j} - var(--uw))"
    nch = f"(clamp(0, var(--mpn) - {g}, 1) * 45 + (1 - clamp(0, var(--mpn) - {g}, 1)) * (48 + mod(round(down, var(--mpa) / pow(10, var(--mpn) + var(--mpl) - 1 - {g})), 10)))"
    return f"calc(var(--isn) * {nch} + var(--ifl) * {xB} + var(--icp) * ({c} + var(--mdl) * {inr}))"
NEWCLASSES['mcpy'] = dict(ops=['MCPY', 'MUPPER', 'MLOWER', 'MFILL', 'NPUT'], pre=OPND + OPNDA + [f"--zA: {kv('A', 'z')};",
    f"--mo: {pst};", f"--isn: {eq('var(--op)', OP['NPUT'])};", f"--ifl: {eq('var(--op)', OP['MFILL'])};", "--icp: calc(1 - var(--isn) - var(--ifl));",
    "--mlo: if(style(--op: " + str(OP['MUPPER']) + "): 97; else: 65);",
    "--mdl: if(style(--op: " + str(OP['MUPPER']) + "): -32; style(--op: " + str(OP['MLOWER']) + "): 32; else: 0);"] + declen(xB, "mpa", "mpn", "mpl") + [
    f"--mn: calc(var(--isn) * (var(--mpn) + var(--mpl)) + (1 - var(--isn)) * {yC});",
    "--mk: max(0, min(var(--mn) - var(--mo), 4 - var(--uw), 4 - var(--icp) * var(--up)));",
    "--mdone: clamp(0, var(--mo) + var(--mk) - var(--mn) + 1, 1);"] +
    [f"--mi{j}: clamp(0, {j} - var(--uw) + var(--up), 3);" for j in range(4)] + [f"--mc{j}: {pick('p', f'mi{j}')};" for j in range(4)],
    reads=[("x", "var(--aB)", "1 - var(--kB)"), ("y", "var(--aC)", f"(1 - var(--kC)) * (1 - {eq('var(--op)', OP['NPUT'])})"), ("z", "var(--aA)", "1 - var(--kA)")],
    lines=[("p", f"mod({xB} + var(--mo), 32768)", "calc(var(--icp) * clamp(0, var(--mn) - var(--mo), 1))")],
    write=("mod(var(--zA) + var(--mo), 32768)", None, None, "clamp(0, var(--mk), 1)"), wline=("var(--mk)", mcpy_val),
    nx={'pc': f"calc({pc} + 2 * var(--mdone))", 'steps': "calc(var(--steps) + var(--mdone))", 'pst': "calc((1 - var(--mdone)) * (var(--mo) + var(--mk)))"},
    deps={'p': [('x', None)]})
# MCMP / MFEQ / MFREF A, B, C: A = the first i < A where B[i] differs from C[i] / equals C / refers into the from-space at C, else
# A (a line of B, line p, and for MCMP of C, line l, per execution; pst: the words done). MWALK A, B, C: the offset from B of
# the first [len][bytes][0] string of length A, or of the first at or past C (a string per execution, read e: its length word)
H_ = HS
def isfref_v(w, flo):
    return (f"min(1, calc(clamp(0, {w} + {OBJTAG + 1} - {flo}, 1) * clamp(0, {flo} + {H_ - OBJTAG} - {w}, 1)"
            f" + clamp(0, {w} + {STRTAG - 1} - {flo}, 1) * clamp(0, {flo} + {H_ - STRTAG} - {w}, 1)"
            f" + clamp(0, {w} - {ARRTAG + 2} - {flo}, 1) * clamp(0, {flo} + {H_ + ARRTAG} - {w}, 1)"
            f" + clamp(0, {w} + {R.DBLTAG - 3} - {flo}, 1) * clamp(0, {flo} + {H_ - R.DBLTAG} - {w}, 1)"
            f" + clamp(0, {w} + {R.FUNTAG} - {flo}, 1) * clamp(0, {flo} + {H_ - R.FUNTAG} - {w}, 1)"
            f" + clamp(0, {w} + {R.ENVTAG} - {flo}, 1) * clamp(0, {flo} + {H_ - R.ENVTAG} - {w}, 1)))")
isw = eq('var(--op)', OP['MWALK'])
NEWCLASSES['mcmp'] = dict(ops=['MCMP', 'MFEQ', 'MFREF', 'MWALK'], pre=OPND + OPNDA + [f"--zA: {kv('A', 'z')};", f"--mo: {pst};",
    f"--mk: max(0, min(var(--zA) - var(--mo), 4 - var(--up), 4 - {eq('var(--op)', OP['MCMP'])} * var(--ul)));"] +
    [f"--mi{j}: clamp(0, {j} + var(--up), 3);" for j in range(4)] + [f"--mj{j}: clamp(0, {j} + var(--ul), 3);" for j in range(4)] +
    [f"--mc{j}: {pick('p', f'mi{j}')};" for j in range(4)] +
    [f"--mh{j}: calc(clamp(0, var(--mk) - {j}, 1) * if(style(--op: {OP['MCMP']}): calc(1 - {eq(f'var(--mc{j})', pick('l', f'mj{j}'))});"
     f" style(--op: {OP['MFEQ']}): {eq(f'var(--mc{j})', yC)}; else: {isfref_v(f'var(--mc{j})', yC)}));" for j in range(4)] +
    ["--mr0: calc(1 - var(--mh0));"] + [f"--mr{j}: calc(var(--mr{j - 1}) * (1 - var(--mh{j})));" for j in range(1, 4)] +
    ["--me: min(var(--mk), calc(var(--mr0) + var(--mr1) + var(--mr2) + var(--mr3)));",
     # MWALK: live (B + o < C), a hit (the length word is A), the next string's offset
     f"--mlive: clamp(0, {yC} - {xB} - var(--mo), 1);", "--mhit: calc(var(--mlive) * " + eq('var(--ve)', 'var(--zA)') + ");",
     "--mnext: calc(var(--mo) + var(--ve) + 2);",
     f"--mdone: if(style(--op: {OP['MWALK']}): min(1, calc(1 - var(--mlive) + var(--mhit) + clamp(0, {xB} + var(--mnext) - {yC} + 1, 1)));"
     " else: max(clamp(0, var(--mk) - var(--me), 1), clamp(0, var(--mo) + var(--mk) - var(--zA) + 1, 1)));",
     f"--mres: if(style(--op: {OP['MWALK']}): calc(var(--mo) + var(--mlive) * (1 - var(--mhit)) * (var(--ve) + 2)); else: calc(var(--mo) + var(--me)));"],
    reads=[("x", "var(--aB)", "1 - var(--kB)"), ("y", "var(--aC)", "1 - var(--kC)"), ("z", "var(--aA)", "1 - var(--kA)"),
           ("e", f"mod({xB} + var(--mo), 32768)", f"calc({isw} * var(--mlive))")],
    lines=[("p", f"mod({xB} + var(--mo), 32768)", f"calc((1 - {isw}) * clamp(0, var(--zA) - var(--mo), 1))"),
           ("l", f"mod({yC} + var(--mo), 32768)", f"calc({eq('var(--op)', OP['MCMP'])} * clamp(0, var(--zA) - var(--mo), 1))")],
    write=("var(--aA)", "var(--mres)", None, "var(--mdone)"),
    nx={'pc': f"calc({pc} + 2 * var(--mdone))", 'steps': "calc(var(--steps) + var(--mdone))",
        'pst': f"calc((1 - var(--mdone)) * if(style(--op: {OP['MWALK']}): var(--mnext); else: calc(var(--mo) + var(--mk))))"},
    deps={'p': [('x', None)], 'e': [('x', None)]})
# NET A, B (net/server.js and net/device.py have the protocol): a stall without a miss until every modem part's answer to
# the word B has come. Part j's answer R = valid + 2 seq + 4 value is a slot's scroll offset (slot j / 2; scrollLeft for an
# even j, scrollTop for an odd one), read by the scroll timeline --nans<j> on #cpu; it counts when it is valid and its seq
# is the word's bit 0 (the lib alternates it). While it waits, the class leaves --req = 1 + word for the chain's end (the
# register rreq: the modems' extra height, the request). Then it runs once per write (--pst): each part's answer d
# unpacked into its two bytes, RBUF0 … RBUF(2P-1) (byte k: (d >> 8k) & 255 if d >> 16 > k, else -1: cc_ref.netw), then
# part 0's answer into A, which completes it
from net_slot import SLOT, NW
NETSHOW = os.environ.get('NETSHOW') == '1'      # a demo page: the modems show, with their request and answers
NP = R.LAYOUT['net_parts']
NS = (NP + 1) // 2      # modems: each document answers two parts, on its slot's two axes
NETTL = ["rreq", "rlive"] + [f"nans{j}" for j in range(NP)]     # the timelines the modems and #cpu share (scoped at body)
NET_PRE = OPND[0:1] + OPND[2:3] + OPND[4:5] + [f"--aA: {oaddr('var(--A)')};",
           f"--nws: mod({xB}, 2);", f"--nfin: {eq(pst, 2 * NP)};",
           f"--ntime: clamp(0, mod(var(--t) - var(--rnt0), 60000) - {NWAIT - 1}, 1);"]
for j in range(NP):
    NET_PRE += [f"--nd{j}: round(down, var(--nans{j}) / 4);",
                f"--nm{j}: calc(mod(var(--nans{j}), 2) * {eq('mod(round(down, var(--nans' + str(j) + ') / 2), 2)', 'var(--nws)')});"]
NET_PRE += ["--nmatch: calc(" + " * ".join(f"var(--nm{j})" for j in range(NP)) + ");", "--nok: min(1, calc(var(--nmatch) + var(--ntime)));",
            # this execution's write: byte pst (part pst / 2, byte pst mod 2), part 0's answer on the last
            "--nsel: " + sel("pst", 2 * NP + 1, lambda i: "var(--nd0)" if i == 2 * NP else
                             f"calc(clamp(0, round(down, var(--nd{i // 2}) / 65536) - {i % 2}, 1) * (mod(round(down, var(--nd{i // 2}) / {256 ** (i % 2)}), 256) + 1) - 1)") + ";",
            "--nval: calc(var(--nmatch) * var(--nsel) - (1 - var(--nmatch)) * var(--ntime));"]
NEWCLASSES['net'] = dict(ops=['NET'], pre=NET_PRE, reads=[("x", "var(--aB)", "1 - var(--kB)")],
                         write=(f"calc(var(--nfin) * var(--aA) + (1 - var(--nfin)) * ({R.RBUF0} + {pst}))", "var(--nval)", None, "1"),
                         nx={'pc': f"calc({pc} + 2 * var(--nfin))", 'steps': "calc(var(--steps) + var(--nfin))", 'pst': f"calc((1 - var(--nfin)) * ({pst} + 1))"})
# The FPU (cc_ref FLOPS / FVOPS; the runtime library's only): calc() computes in IEEE doubles within one declaration, so the
# operands' doubles and the result are written out inline in each declaration that needs them (a registered <integer> keeps 6
# digits across var(): only the words and small integers cross). B and C: a scratch line (the constants FSCR ...: their line at
# fpu_base), a boxed double (its number line: lines p and l), or the number itself (an integer, or the specials NaN, +-Infinity,
# -0). FLOPS write the line at A (a scratch line, or A's value: z) from the result's flags, exponent and mantissa; FVOPS write A
FB_ = R.LAYOUT['fpu_base']
def fopnd(o, val, ln):
    """operand o's (B / C) line flag, line address and kind/sign declarations: --f<ln>l (a line), --f<ln>a, --f<ln>k (0 finite from
    the line, 1 zero, 2 infinite, 3 NaN, 4 the integer itself), --f<ln>s (the sign)"""
    w = [f"var(--{ln}w{j})" for j in range(4)]
    sc = f"calc(var(--k{o}) * clamp(0, var(--{o}) - {896 + R.FSCR - 1}, 1) * clamp(0, {896 + R.FSCR + R.NFLINES} - var(--{o}), 1))"
    return [f"--f{ln}c: {sc};", f"--f{ln}l: min(1, calc(var(--f{ln}c) + {isdbl_v(val)}));",
            f"--f{ln}a: if(style(--f{ln}c: 1): calc({FB_} + 4 * (var(--{o}) - {896 + R.FSCR})); else: mod({val} + {R.DBLTAG}, 32768));",
            f"--f{ln}k: if(style(--f{ln}l: 1): calc({eq(f'abs({w[0]})', 1)} + 2 * {eq(f'abs({w[0]})', 3000)} + 3 * {eq(w[0], 4000)});"
            f" else: calc(4 - 3 * {eq(val, R.MZERO)} - 2 * ({eq(val, R.INF)} + {eq(val, R.NINF)}) - {eq(val, R.NAN)}));",
            f"--f{ln}s: if(style(--f{ln}l: 1): sign({w[0]}); else: calc(1 - 2 * ({eq(val, R.MZERO)} + {eq(val, R.NINF)})));"]
def fdouble(ln, val):
    """the operand's double, inline (from its line's words, or the integer / special)"""
    w = [f"var(--{ln}w{j})" for j in range(4)]
    fin = f"calc(var(--f{ln}s) * ({w[1]} * pow(2, 36) + {w[2]} * pow(2, 18) + {w[3]}) * pow(2, abs({w[0]}) - 1152))"
    return (f"if(style(--f{ln}k: 4): {val}; style(--f{ln}k: 0): {fin}; style(--f{ln}k: 1): calc(var(--f{ln}s) * 0);"
            f" style(--f{ln}k: 2): calc(var(--f{ln}s) * infinity); else: NaN)")
FX, FY = fdouble('p', xB), fdouble('l', yC)
def _split(a): return f"calc((134217729 * ({a})) - ((134217729 * ({a})) - ({a})))"
def _tplo(a, b):
    ah, bh = _split(a), _split(b); al, bl = f"calc(({a}) - {ah})", f"calc(({b}) - {bh})"
    return f"calc(((({ah}) * ({bh}) - ({a}) * ({b})) + ({ah}) * ({bl}) + ({al}) * ({bh})) + ({al}) * ({bl}))"
_FCV = {'pi': 'pi', 'e': 'e', 'ln2': 'log(2)', 'ln10': 'log(10)', 'log2e': 'calc(log(e) / log(2))', 'log10e': 'calc(log(e) / log(10))',
        'sqrt2': 'sqrt(2)', 'sqrt1_2': 'sqrt(0.5)'}
FLR = {'FLD': f"calc({FX})", 'FADD': f"calc(({FX}) + ({FY}))", 'FSUB': f"calc(({FX}) - ({FY}))", 'FMUL': f"calc(({FX}) * ({FY}))",
       'FDIV': f"calc(({FX}) / ({FY}))", 'FMOD': f"rem({FX}, {FY})", 'FPOW': f"pow({FX}, {FY})", 'FSQRT': f"sqrt({FX})",
       'FFLOOR': f"round(down, {FX})", 'FCEIL': f"round(up, {FX})", 'FROUND': f"round(nearest, {FX})", 'FTRUNC': f"round(to-zero, {FX})",
       'FABS': f"abs({FX})", 'FTPLO': _tplo(FX, FY),
       'FSCALE': f"calc(({FX}) * pow(2, round(down, {yC} / 2)) * pow(2, {yC} - round(down, {yC} / 2)))",
       'FP10': f"pow(10, {yC})", 'FCONST': "if(" + " ".join(f"style(--yC: {i}): {_FCV[n]};" for i, n in enumerate(R.FCONSTS)) + " else: 0)",
       'FEXP': f"exp({FX})", 'FLOG': f"log({FX})", 'FSIN': f"sin({FX})", 'FCOS': f"cos({FX})", 'FTAN': f"tan({FX})"}
assert list(FLR) == R.FLOPS
FR = by_op({o: FLR[o] for o in R.FLOPS[:-1]}, FLR[R.FLOPS[-1]])
def fenc_decls(R_, p):
    """a double's number line from its value R_ (inline): --<p>f finite, --<p>i (not finite) infinite, --<p>z zero, --<p>s the sign,
    --<p>e the exponent, --<p>m1 ... 3 the mantissa's words, --<p>w0 ... 3 the line"""
    aR = f"abs({R_})"
    d = [f"--{p}f: calc(({R_}) * 0 + 1);", f"--{p}i: calc(1 / ({R_}) * 0 + 1);",
         f"--{p}z: calc(1 - min(1, {aR} * pow(2, 537) * pow(2, 537)));",
         f"--{p}s: if(style(--{p}f: 1): sign(1 / ({R_})); else: sign({R_}));",
         f"--{p}e0: round(down, log({aR}, 2));",
         f"--{p}e: clamp(-1022, var(--{p}e0) + clamp(0, sign({aR} - pow(2, var(--{p}e0) + 1)) + 1, 1) - clamp(0, sign(pow(2, var(--{p}e0)) - {aR}), 1), 1023);",
         f"--{p}k1: round(down, (52 - var(--{p}e)) / 2);"]
    M = f"({aR} * pow(2, var(--{p}k1)) * pow(2, 52 - var(--{p}e) - var(--{p}k1)))"
    d += [f"--{p}m1: round(down, {M} / pow(2, 36));", f"--{p}m2: mod(round(down, {M} / pow(2, 18)), pow(2, 18));", f"--{p}m3: mod({M}, pow(2, 18));",
          f"--{p}w0: if(style(--{p}f: 1) and style(--{p}z: 1): var(--{p}s); style(--{p}f: 1): calc(var(--{p}s) * (var(--{p}e) + 1100));"
          f" style(--{p}i: 1): calc(var(--{p}s) * 3000); else: 4000);"]
    d += [f"--{p}w{j}: if(style(--{p}f: 1) and style(--{p}z: 0): var(--{p}m{j}); else: 0);" for j in (1, 2, 3)]
    return d
FPU_LINE = f"clamp(0, {OP['FNORM']} - var(--op), 1)"      # an FLOPS op (they precede FVOPS)
# the value ops (cc_ref.fval_op)
_fkx = "var(--fpk)"
_fint = f"calc(1 - clamp(0, sign(abs(rem({FX}, 1))), 1))"
_finr = f"calc(clamp(0, sign(({FX}) - {R.SMI_LO}) + 1, 1) * clamp(0, sign({R.SMI_HI} - ({FX})) + 1, 1))"
FVAL = {'FNORM': (f"if(style(--fpk: 3): {R.NAN}; style(--fpk: 2): if(style(--fps: 1): {R.INF}; else: {R.NINF}); style(--fpk: 1): if(style(--fps: 1): 0; else: {R.MZERO});"
                  f" style(--fpk: 4): {xB}; else: if(style(--fni: 1): round(to-zero, {FX}); else: {xB}))"),
        'FINT': f"if(style(--fpk: 0) or style(--fpk: 4): round(to-zero, {FX}); else: 0)",
        'FCMP': f"if(style(--fpk: 3) or style(--flk: 3): 2; else: sign(({FX}) - ({FY})))",
        'FEXPO': "var(--fve)",
        'FLOG10': (f"calc(round(down, log(abs({FX}), 10)) + clamp(0, sign(abs({FX}) - pow(10, round(down, log(abs({FX}), 10)) + 1)) + 1, 1)"
                   f" - clamp(0, sign(pow(10, round(down, log(abs({FX}), 10))) - abs({FX})), 1))"),
        'FDIGIT': f"calc((rem({FX}, pow(10, {yC} + 1)) - rem({FX}, pow(10, {yC}))) / pow(10, {yC}))"}
assert list(FVAL) == R.FVOPS
FPU_PRE = (OPND + OPNDA + [f"--zA: {kv('A', 'z')};"] + fopnd('B', xB, 'p') + fopnd('C', yC, 'l') +
           [f"--fdl: {FPU_LINE};", f"--fac: calc(var(--kA) * clamp(0, var(--A) - {896 + R.FSCR - 1}, 1) * clamp(0, {896 + R.FSCR + R.NFLINES} - var(--A), 1));",
            f"--fda: if(style(--fac: 1): calc({FB_} + 4 * (var(--A) - {896 + R.FSCR})); else: mod(var(--zA) + {R.DBLTAG}, 32768));",
            f"--fni: calc({_fint} * {_finr});"] +
           fenc_decls(FR, 'fr') +
           [f"--fve: var(--fxe);"] + fenc_decls(FX, 'fx')[4:6] +
           [f"--fval: {by_op({o: FVAL[o] for o in R.FVOPS[:-1]}, FVAL[R.FVOPS[-1]])};"])
# FCOK / FCDIG (numstr's search: cc_ref.fcand): B's number line (p: a scratch line or a boxed double), C the scale n; ok into A, or
# the candidate's 5-digit limbs into A's line. The candidate c = c_hi + c_lo exactly: c_hi a double, c_lo small (registered)
def _gt0(x): return f"clamp(0, sign({x}), 1)"
def _ge0(x): return f"clamp(0, sign({x}) + 1, 1)"
_pw = [f"var(--pw{j})" for j in range(4)]
_M = f"calc({_pw[1]} * pow(2, 36) + {_pw[2]} * pow(2, 18) + {_pw[3]})"
_F5 = f"pow(5, {yC})"
_NH = f"calc(({_M}) * {_F5})"; _NL = _tplo(_M, _F5)
_XH = f"calc(({_NH}) * pow(2, var(--gs0)))"; _XL = f"calc(({_NL}) * pow(2, var(--gs0)))"
_FL = f"round(down, {_XH})"; _HF = f"calc(0.5 - (({_XH}) - ({_FL})))"
_CHI = f"if(style(--gs: 1) or style(--gb: 1): {_XH}; else: calc({_FL} + var(--gu)))"
_CLO = "if(style(--gs: 1): 0; style(--gb: 1): var(--gr); else: 0)"
_D = f"calc((({_CHI}) * pow(2, 1 - var(--gs0)) - 2 * ({_NH})) + ({_CLO}) * pow(2, 1 - var(--gs0)) - 2 * ({_NL}))"
_CLOX = f"if(style(--gs: 1): {_XL}; else: {_CLO})"
def _limb(j): return f"calc((rem({_CHI}, pow(10, {5 * j + 5})) - rem({_CHI}, pow(10, {5 * j}))) / pow(10, {5 * j}))"
FD_PRE = (OPND + OPNDA + [f"--zA: {kv('A', 'z')};"] + fopnd('B', xB, 'p') +
          [f"--fac: calc(var(--kA) * clamp(0, var(--A) - {896 + R.FSCR - 1}, 1) * clamp(0, {896 + R.FSCR + R.NFLINES} - var(--A), 1));",
           f"--fda: if(style(--fac: 1): calc({FB_} + 4 * (var(--A) - {896 + R.FSCR})); else: mod(var(--zA) + {R.DBLTAG}, 32768));",
           f"--fdl: {eq('var(--op)', OP['FCDIG'])};",
           f"--gs0: calc(abs({_pw[0]}) - 1152 + {yC});", f"--gs: {_ge0('var(--gs0)')};", f"--gb: {_ge0(f'({_XH}) - pow(2, 52)')};",
           f"--gu: calc({_gt0(f'({_XL}) - ({_HF})')} + {eq(f'sign(({_XL}) - ({_HF}))', 0)} * rem({_FL}, 2));",
           f"--grf: round(down, {_XL});",
           f"--gr: calc(var(--grf) + {_gt0(f'({_XL}) - var(--grf) - 0.5')} + {eq(f'sign(({_XL}) - var(--grf) - 0.5)', 0)} * abs(rem(var(--grf), 2)));",
           f"--gdl: calc({eq(f'sign({_D})', -1)} * {eq(_pw[1], 65536)} * {eq(_pw[2], 0)} * {eq(_pw[3], 0)} * {_gt0(f'abs({_pw[0]}) - 78')});",
           f"--gdc: sign(abs({_D}) - {_F5} / (1 + var(--gdl)));",
           f"--gok: if(style(--gs: 1): 1; else: calc({eq('var(--gdc)', -1)} + {eq('var(--gdc)', 0)} * (1 - rem({_pw[3]}, 2))));",
           f"--gl0x: calc(rem({_CHI}, 100000) + ({_CLOX}));", "--gc0: round(down, var(--gl0x) / 100000);", "--gl0: calc(var(--gl0x) - 100000 * var(--gc0));",
           f"--gl1x: calc({_limb(1)} + var(--gc0));", "--gc1: round(down, var(--gl1x) / 100000);", "--gl1: calc(var(--gl1x) - 100000 * var(--gc1));",
           f"--gl2x: calc({_limb(2)} + var(--gc1));", "--gc2: round(down, var(--gl2x) / 100000);", "--gl2: calc(var(--gl2x) - 100000 * var(--gc2));",
           f"--gl3: calc({_limb(3)} + var(--gc2));"])
NEWCLASSES['fdig'] = dict(ops=list(R.FDOPS), pre=FD_PRE,
    reads=[("x", "var(--aB)", "1 - var(--kB)"), ("y", "var(--aC)", "1 - var(--kC)"), ("z", "var(--aA)", "calc(var(--fdl) * (1 - var(--kA)))")],
    lines=[("p", "var(--fpa)", "1")],
    write=("if(style(--fdl: 1): var(--fda); else: var(--aA))", None, None, "1"),
    wline=("calc(1 + 3 * var(--fdl))", lambda j: f"if(style(--fdl: 1): var(--gl{j}); else: var(--gok))"),
    nx={'pc': f"calc({pc} + 2)"}, deps={'p': [('x', None)]})
FD_NAMES = ["gs0", "gs", "gb", "gu", "grf", "gr", "gdl", "gdc", "gok", "gl0x", "gc0", "gl0", "gl1x", "gc1", "gl1", "gl2x", "gc2", "gl2", "gl3"]
NEWCLASSES['fpu'] = dict(ops=R.FLOPS + R.FVOPS, pre=FPU_PRE,
    reads=[("x", "var(--aB)", "1 - var(--kB)"), ("y", "var(--aC)", "1 - var(--kC)"), ("z", "var(--aA)", "calc(var(--fdl) * (1 - var(--kA)))")],
    lines=[("p", "var(--fpa)", "var(--fpl)"), ("l", "var(--fla)", "var(--fll)")],
    write=("if(style(--fdl: 1): var(--fda); else: var(--aA))", None, None, "1"),
    wline=("calc(1 + 3 * var(--fdl))", lambda j: f"if(style(--fdl: 1): var(--frw{j}); else: var(--fval))"),
    nx={'pc': f"calc({pc} + 2)"}, deps={'p': [('x', None)], 'l': [('y', None)]})
NEWCLASSES['fdig'] = NEWCLASSES.pop('fdig')       # (its opcodes follow the FPU's)
# FAND ... FUSHR (DBIT's trap, dbit): B and C as 32-bit integers in 16-bit halves (gs0 gs: B's high and low, gb gu: C's; grf gr:
# their & ; gdl gdc: & | ^'s), the result an exact double into A's line (the FPU's fr temps, fdouble's operands)
def _u32(ln, val): return f"if(style(--f{ln}k: 2) or style(--f{ln}k: 3): 0; else: mod(round(to-zero, {fdouble(ln, val)}), 4294967296))"
def _and16(a, b): return "calc(" + " + ".join(f"{2 ** i} * {_bit(a, i)} * {_bit(b, i)}" for i in range(16)) + ")"
_g = {n: f"var(--{n})" for n in ("gs0", "gs", "gb", "gu", "grf", "gr", "gdl", "gdc")}
_ua = f"calc({_g['gs0']} * 65536 + {_g['gs']})"; _bsh = f"pow(2, mod({_g['gu']}, 32))"
_shl = f"mod(({_ua}) * {_bsh}, 4294967296)"
FBR = by_op({'FSHL': f"calc({_shl} - 4294967296 * clamp(0, {_shl} - 2147483647, 1))",
             'FSHR': f"round(down, ({_ua} - 4294967296 * clamp(0, {_g['gs0']} - 32767, 1)) / {_bsh})",
             'FUSHR': f"round(down, ({_ua}) / {_bsh})"},
            f"calc({_g['gdl']} * 65536 + {_g['gdc']} - 4294967296 * clamp(0, {_g['gdl']} - 32767, 1))")
FB_PRE = (OPND + OPNDA + [f"--zA: {kv('A', 'z')};"] + fopnd('B', xB, 'p') + fopnd('C', yC, 'l') +
          [f"--fac: calc(var(--kA) * clamp(0, var(--A) - {896 + R.FSCR - 1}, 1) * clamp(0, {896 + R.FSCR + R.NFLINES} - var(--A), 1));",
           f"--fda: if(style(--fac: 1): calc({FB_} + 4 * (var(--A) - {896 + R.FSCR})); else: mod(var(--zA) + {R.DBLTAG}, 32768));",
           f"--gs0: round(down, {_u32('p', xB)} / 65536);", f"--gs: calc({_u32('p', xB)} - 65536 * var(--gs0));",
           f"--gb: round(down, {_u32('l', yC)} / 65536);", f"--gu: calc({_u32('l', yC)} - 65536 * var(--gb));",
           f"--grf: {_and16(_g['gs0'], _g['gb'])};", f"--gr: {_and16(_g['gs'], _g['gu'])};",
           f"--gdl: {by_op({'FAND': _g['grf'], 'FOR': f'calc({_g['gs0']} + {_g['gb']} - {_g['grf']})'}, f'calc({_g['gs0']} + {_g['gb']} - 2 * {_g['grf']})')};",
           f"--gdc: {by_op({'FAND': _g['gr'], 'FOR': f'calc({_g['gs']} + {_g['gu']} - {_g['gr']})'}, f'calc({_g['gs']} + {_g['gu']} - 2 * {_g['gr']})')};"] +
          fenc_decls(FBR, 'fr'))
NEWCLASSES['fbit'] = dict(ops=list(R.FBOPS), pre=FB_PRE,
    reads=[("x", "var(--aB)", "1 - var(--kB)"), ("y", "var(--aC)", "1 - var(--kC)"), ("z", "var(--aA)", "calc(1 - var(--kA))")],
    lines=[("p", "var(--fpa)", "var(--fpl)"), ("l", "var(--fla)", "var(--fll)")],
    write=("var(--fda)", None, None, "1"),
    wline=("4", lambda j: f"var(--frw{j})"),
    nx={'pc': f"calc({pc} + 2)"}, deps={'p': [('x', None)], 'l': [('y', None)]})
FPU_NAMES = (["fpc", "fpl", "fpa", "fpk", "fps", "flc", "fll", "fla", "flk", "fls", "fdl", "fac", "fda", "fni", "fve", "fval"] +
             [f"fr{x}" for x in ("f", "i", "z", "s", "e0", "e", "k1", "m1", "m2", "m3", "w0", "w1", "w2", "w3")] + ["fxe0", "fxe"])
for c_, k_ in NEWCLASSES.items(): build_class(c_, k_)
build_class('alu', CLASSES['alu'])
build_class('cat', CAT_CLASS)                 # (no opcode of its own: a DADD's pst picks it, cls_of)
build_class('jtrap', JTRAP_CLASS)             # (likewise: a slow jump's pst)
CLS = {c: i + 1 for i, c in enumerate(cls_rules)}
assert sorted(RC.OPN) == sorted(o for ops, _ in cls_rules.values() for o in ops), 'every instruction in one class'
opcls = {o: CLS[c] for c, (ops, _) in cls_rules.items() for o in ops}
assert [opcls[o] for o in RC.OPN] == sorted(opcls[o] for o in RC.OPN), 'rc_ref.OPN in class order'
# the class from the opcode's range (rc_ref.OPN is in class order); 0 for no instruction (--op 255: the fetch missed)
bounds = [i for i in range(1, len(RC.OPN)) if opcls[RC.OPN[i]] != opcls[RC.OPN[i - 1]]]
cls_of = (f"calc(clamp(0, {len(RC.OPN)} - var(--op), 1) * (1" + "".join(f" + clamp(0, var(--op) - {b - 1}, 1)" for b in bounds) +
          f") + {CLS['cat'] - CLS['dyn']} * {opin('DADD', 'DADD')} * clamp(0, var(--pst) - {CATT - 1}, 1)"
          f" + {CLS['jtrap'] - CLS['jump']} * {opin('JLT', 'JNGE')} * clamp(0, var(--pst) - {CATT - 1}, 1)"
          f" + {CLS['obj'] - CLS['arr']} * {opin('GETX', 'SETX')} * clamp(0, var(--pst) - {CATT - 1}, 1))")

# the ROM's instructions (fetch only), two-level on the pc: 32 instructions (64 words) per group. An if() costs ~70 ns per entry
# it holds wherever it is evaluated, so the ROM is split into tiers of ROMTIER words, each a rule of its own matched by
# --rom = 1 + the tier (0: not in ROM): a ROM instruction evaluates one tier's tables (one for each word)
ROMW = [w or 0 for w in image['rom']] + [0] * (ROM - len(image['rom']))
def rom_table(lo, hi, off):
    return "if(" + " ".join(f"style(--rh: {h}): if(" + " ".join(f"style(--rl: {l}): {ROMW[64 * h + 2 * l + off]};" for l in range(32) if ROMW[64 * h + 2 * l + off]) + " else: 0);"
                            for h in range(lo // 64, hi // 64) if any(ROMW[64 * h + off:64 * h + 64:2])) + " else: 0)"
ROMTIER = int(os.environ.get('ROMTIER', 1024)) or ROM
TIERS = [t for t in range(ROM // ROMTIER) if any(ROMW[t * ROMTIER:(t + 1) * ROMTIER])]
def rom_of(x): return f"calc(clamp(0, {ROM} - {x}, 1) * (1 + round(down, {x} / {ROMTIER})))"

# ---------------- the page's CSS
P = ["pc", "rpc", "rfp", "fp", "optr", "pst", "steps", "halt", "pend", "init", "k", "par", "tprev", "first", "fresh", "go", "chan", "nk", "npar",
     "fon", "fb", "fs", "fv", "fk", "fT", "fabs", "fd", "fvb", "fk1", "pend0", "gs", "gv", "gk", "gT", "gabs", "gk1", "xon", "xb", "xbh", "xbl", "xbhot", "yb", "ybh", "ybl", "ybhot",
     "t", "stop", "cw", "op", "A", "B", "C", "cls", "rom", "rh", "rl", "vf", "vg", "mf", "ok", "mb", "npc", "nfp", "nsteps", "nstop", "nhalt",
     "kB", "kC", "aB", "aC", "aA", "xB", "yC", "tstr", "tz", "jc", "mx", "pv",
     "wval", "wz", "nT0", "nT1", "pout", "ncw", "noptr", "npst", "prLN", "prSP", "pp", "isStr", "isNum", "pq", "pdone", "pj0",
     "mpp", "pa", "pneg", "pL", "ptot", "pbase", "pf", "pcut", "pn0", "pblk", "pfr0", "pfr1", "pfr2", "pfr3", "pe", "pvE", "pbE", "ptNul", "ptNL", "pn", "pfin", "pnl", "lat", "hm", "Lm", "isHALT", "ptrap",
     "wval2", "vh", "vj"]
# the new classes' scratch (.x only)
XNEW = FPU_NAMES + FD_NAMES + ["kA", "aA", "zA", "dcat", "dwb", "dnl", "dr", "dok", "dval", "dix", "diy", "cqs", "cao", "cbs", "cdb", "juser", "jcr", "jok", "jcu", "jho",
        "cX", "cY", "csx", "csy", "cla", "clb", "ctn", "cnw", "cfull", "ck", "cbase", "ci", "cfx", "cj",
        "cvv", "cvs", "cbyte", "cin", "clast", "caddr", "cval", "X", "Y", "xarr", "xin", "E", "tr", "ts", "tlast", "tF", "taddr", "tval", "O", "ob", "okey", "sst", "sodd",
        "oroom", "oq", "ohit", "oend", "onext", "oc", "V", "oaddr", "oval", "oen", "w2", "odone", "ojump"]
# the runtime's primitives' scratch (.x only), and write_line's
XNEW += ("kk ak anw afull abase amw amb amap ares anext adone aaddr akk uarr uok ufall uaddr uval isn ifl icp mlo mdl mpa mpn mpl mn mk mdone"
         " me mhit mlive mnext mres mo clv cc cnul cnull cmap cmb cmw ckk omw xhand").split() + \
        [f"{x}{j}" for j in range(4) for x in ("mi", "mc", "mj", "mh", "mr", "cq", "wm", "wv")]
P += ["req", "nlive", "nws", "nfin", "nmatch", "ntime", "nok", "nsel", "nval"] + [f"{x}{j}" for j in range(NP) for x in ("nans", "nd", "nm")]
P += XNEW + ["dfon", "ifon", "ik1", "igb", "igblo", "igbhi", "igp", "ig1", "ib", "iblo", "ibhi", "iu", "ih", "mic"]
P += [r[0] for r in regs if r[0] not in P] + [f"L{n}" for n in LATCH if n != "p"] + [f"Lp{j}" for j in range(4)] + [f"Lb{n}" for n in LATCH]
P += [f"{x}{w}" for w in range(WB) for x in ("fwd", "wA", "wD", "cA", "cD", "nwA", "nwD", "pi", "dp", "pw")]
P += [f"{x}{i}" for i in range(4) for x in ("pg", "pnb", "pb", "pc", "pr", "pch")] + [f"n{i}" for i in range(8)]
P += [f"n{r[0]}" for r in WREGS]
P += [x + n for n in READS for x in LOOKUP] + [f"v{n}" for n in READS if n not in ("w", "p", "l")] + [f"lw{j}" for j in range(4)]
P = list(dict.fromkeys(P))
_unreg = {m for _, d in cls_rules.values() for x in d for m in re.findall(r'(?:^|;\s*)--([\w-]+):', x)} - set(P)
assert not _unreg, f'declared by an instruction class but not registered: {sorted(_unreg)}'
props = [lbl.section('Registered properties', 'registers, the chain\'s state and temps: integers')]
# temps that only the element declaring them reads (.x's reads and scratch) don't inherit
LOCAL = {x + n for n in READS if n != "f" for x in LOOKUP} | {"uf", "qf", "hf", "Hf", "rh", "rl", "ib", "iblo", "ibhi", "iu", "ih"}
LOCAL |= {"nws", "nfin", "nmatch", "ntime", "nok", "nsel", "nval"} | {f"{x}{j}" for j in range(NP) for x in ("nd", "nm")}
LOCAL |= {"kB", "kC", "aB", "aC", "aA", "xB", "yC", "tstr", "tz", "jc", "mx", "pv", "ptrap"} | set(XNEW)
LOCAL |= {"pp", "isStr", "isNum", "pq", "pdone", "pj0", "mpp", "pa", "pneg", "pL", "ptot", "pbase", "pe", "pvE", "pbE", "pf", "pcut", "pn0", "pblk",
          "pfr0", "pfr1", "pfr2", "pfr3",
          "ptNul", "ptNL", "pn", "pfin", "pnl", "prLN", "prSP"}
LOCAL |= {f"{x}{i}" for i in range(4) for x in ("pg", "pnb", "pb", "pc", "pr", "pch", "pi", "dp")}
props += [f'@property --{n} {{ syntax: "<integer>"; inherits: {"false" if n in LOCAL else "true"}; initial-value: 0; }}' for n in P]
props += [f'@property --sR{i} {{ syntax: "<custom-ident>"; inherits: false; initial-value: --c0; }}' for i in range(2 * WB)]   # a port's leaf name

css = [lbl.section('CPU: clock, registers, frame gate, the fill\'s victims', 'on #cpu: the registers are view timelines'),
       "#clk { animation: wc 100s linear infinite; }\n@keyframes wc { from { --t: 0; } to { --t: 60000; } }",
       "#cpu {\n  timeline-scope: " + ", ".join([f"--{r[0]}" for r in regs if r[0] not in WNAMES and r[0] not in ("rreq", "rlive")]) +
       ";\n  animation-name: " + ", ".join([f"r-{r[0]}" for r in regs] + [f"r-nans{j}" for j in range(NP)]) + ";\n  animation-timeline: " + ", ".join([f"--{r[0]}" for r in regs] + [f"--nans{j}" for j in range(NP)]) +
       ";\n  animation-duration: auto;\n  animation-timing-function: linear;\n  animation-fill-mode: both;\n  " + "\n  ".join(cpu) + "\n}"]
css.append(lbl.group('Register keyframes', 'each register\'s view timeline mapped onto its value range'))
css += [f"@keyframes r-{n} {{ from {{ --{n}: {H - OFF}; }} to {{ --{n}: {-1 - OFF}; }} }}" for n, H, OFF, _ in regs]
css += [lbl.group(f'NET: the modems ({NS}, {NP} parts)', 'slot i\'s scrollLeft and scrollTop are parts 2i and 2i + 1 (the scroll timelines --nans0, --nans1, ...); the iframes\' extra height is the request (rreq)')]
css += [f"@keyframes r-nans{j} {{ from {{ --nans{j}: 0; }} to {{ --nans{j}: {NW - SLOT}; }} }}" for j in range(NP)]
css += [# outside #clk, which Edit hides: a hidden slot's scroll offset is saved and restored when it shows again, and the
        # last run's answers would come back with it (the first word's could match by its sequence bit). Out here they go
        # on loading through Edit, see the request idle (the register's timeline is inactive: 0) and scroll back to 0.
        # They read rreq through an animation of their own; its timeline and the answers' are scoped at body (NETTL).
        # The iframes show from the run's first waiting NET on: the register rlive (a transition latch fed by rreq didn't
        # hold: it followed rreq to 0 between words, hiding the iframes). The slots always show: hiding a slot would save
        # its scroll offset and bring a stale answer back with it; hiding its content (.nclip) only leaves it nothing to
        # scroll. The iframe is NW + rreq px tall in a box of NW x NW that clips it, so both axes scroll 2^20 px whatever
        # the request.
        ".nlatch { height: 0; animation-name: r-rreq, r-rlive; animation-timeline: --rreq, --rlive; animation-duration: auto;"
        " animation-timing-function: linear; animation-fill-mode: both; }",
        f".nslot {{ position: fixed; left: 0; top: 0; width: {SLOT}px; height: {SLOT}px; overflow: hidden; visibility: hidden; }}",
        f".nclip {{ display: if(style(--rlive: 1): block; else: none); width: {NW}px; height: {NW}px; overflow: clip; }}",
        f".modem {{ display: block; border: 0; width: {NW}px; height: calc(({NW} + var(--rreq)) * 1px); }}"]
css += [f".nslot.np{i} {{ scroll-timeline: " + ", ".join(f"--nans{j} {'xy'[j % 2]}" for j in (2 * i, 2 * i + 1) if j < NP) + "; }" for i in range(NS)]
if NETSHOW:     # the panel at the top right; modem 0's slot itself at 2.4x (a transform: its scroll offsets, the answers, are unchanged)
    css += [lbl.group('NETSHOW: the modems, visible', 'a demo of the fragment-scroll answers'),
            ".nshow { animation-name: r-rreq, " + ", ".join(f"r-nans{j}" for j in range(NP)) + "; animation-timeline: --rreq, " + ", ".join(f"--nans{j}" for j in range(NP)) +
            "; animation-duration: auto; animation-timing-function: linear; animation-fill-mode: both;"
            " position: fixed; right: 16px; top: 16px; width: 400px; height: 740px; box-sizing: border-box; padding: 12px 16px;"
            " background: #fff; border: 1px solid #c9d1d9; border-radius: 8px; font: 13px/1.45 system-ui, sans-serif; color: #17212b; z-index: 5; }",
            ".nshow h2 { font-size: 15px; margin: 0 0 6px; } .nshow p { margin: 0 0 8px; color: #5b6875; }",
            ".nshow .kv { font: 12px/1.6 ui-monospace, monospace; white-space: pre; } .nshow .kv b { font-weight: 600; }",
            # the word: 2 p + seq, p = op * 65536 + arg
            ".nword { --wp: round(down, max(0, var(--rreq) - 1) / 2); counter-set: nq var(--rreq) nop mod(var(--wp), 4)"
            " nb0 mod(round(down, var(--wp) / 4), 256) nb1 mod(round(down, var(--wp) / 1024), 256); }",
            ".nword::after { content: \"request \" counter(nq) \" = op \" counter(nop) \" '\" counter(nb0, ascii) counter(nb1, ascii) \"'\\A (op 0: two URL bytes, 1: GET, 2: READ)\"; }",
            ".ntape { position: relative; height: 18px; margin: 4px 0 2px; background: repeating-linear-gradient(90deg, #c9d1d9 0 1px, transparent 1px 36px), #f3f5f7; border-radius: 3px; }",
            ".nneedle { position: absolute; top: -3px; width: 3px; height: 24px; background: #e8590c; border-radius: 2px; transition: left .3s ease-out; }",
            ".ntapel { display: flex; justify-content: space-between; font: 11px ui-monospace, monospace; color: #5b6875; margin-bottom: 4px; }",
            ".nfilml { font: 11px ui-monospace, monospace; color: #5b6875; }",
            ".nslot.np0 { left: auto; right: 296px; top: 470px; visibility: visible; transform: scale(2.4); transform-origin: 0 0;"
            " outline: 1px solid #5b6875; background: #fff; z-index: 6; }",
            ".nwait { position: absolute; left: 16px; top: 462px; width: 230px; color: #5b6875; }"]     # (the slot, opaque, covers it once the modem shows)
    for j in range(NP):
        css += [f".npart{j} {{ counter-set: r{j} var(--nans{j}) n{j} mod(round(down, var(--nans{j}) / 262144), 4) a{j} mod(round(down, var(--nans{j}) / 4), 256)"
                f" c{j} mod(round(down, var(--nans{j}) / 1024), 256); }}",
                f".npart{j}::after {{ content: \"part {j}  \" counter(r{j}) \"  \" counter(n{j}) \" bytes '\" counter(a{j}, ascii) counter(c{j}, ascii) \"'\"; }}",
                f".nneedle{j} {{ left: calc(var(--nans{j}) * 365px / {1 << 20}); }}"]
NSHOW_HTML = ('<div class="nshow"><h2>The network modems</h2>'
              f"<p>No script. A NET word sets the height of {NS} modem iframes (the request). The gateway answers it with a new "
              "document for each: the orange #t at x, y = two parts of the answer, and the load scrolls to it. That scroll moves "
              f"the iframe's 100 px box on both axes, and scroll timelines read scrollLeft and scrollTop back. A READ brings 2 bytes per part.</p>"
              '<div class="kv nword"></div>' +
              "".join(f'<div class="kv npart{j}"></div><div class="ntape"><div class="nneedle nneedle{j}"></div></div>' for j in range(NP)) +
              '<div class="ntapel"><span>0</span><span>2^19</span><span>2^20 px</span></div>'
              '<div class="nwait">(the modems appear at the program\'s first fetch)</div>'
              '<div class="nfilml" style="position: absolute; left: 16px; top: 712px">modem 0\'s real box, 2.4&#215;: it ends on #t (parts 0, 1)</div></div>') if NETSHOW else ""

# a read port's leaf name: a two-level if() on the block's 64-block group (h) and place in it (l), evaluated on the port, only
# on passes that fill, from a mux of the 512 blocks runs mostly read (HOT) unless the block is outside them (gen_css.py)
def mux(p, blocks, leaf, default):
    groups = sorted({b // 64 for b in blocks}); outer = []
    for j in groups:
        inner = " ".join(f"style(--{p}l: {i}): {leaf(j * 64 + i)};" for i in range(64) if j * 64 + i in blocks)
        outer.append(f"style(--{p}h: {j}): if({inner} else: {default});")
    return f"if({' '.join(outer)} else: {default})"
def leafname(a): return f"--r{a}" if a < ROM else f"--c{a - ROM}"
css.append(lbl.group(f'Read ports (readers at the chain\'s end): one per bank ({WB}) for the missing block (xb) and one for the next (yb)',
                     'a two-level if() picks the leaf, anchor-size() reads it, a view-timeline subject keeps it for the next pass'))
for i in range(2 * WB):
    w, q = i % WB, "xb" if i < WB else "yb"
    leaf = lambda b, w=w: leafname(4 * b + w)
    css.append(f".rp{i} {{ width: anchor-size(var(--sR{i}) width, {WOFF}px); }}")
    css.append(f"@container style(--xon: 1) and style(--{q}hot: 1) {{ .rp{i} {{ --sR{i}: {mux(q, set(HOT), leaf, f'--c{w}')}; }} }}")
    css.append(f"@container style(--xon: 1) and style(--{q}hot: 0) {{ .rp{i} {{ --sR{i}: {mux(q, set(range(RB0, BLKS)) - set(HOT), leaf, '--rom')}; }} }}")

css.append(lbl.section('The fill', 'the victim line takes the pending block (a dirty victim\'s words are the pass\'s RAM write set), and the prefetch line the next'))
css.append(".fl { --stop: calc(1 - var(--go) * (1 - var(--halt))); --pend: var(--pend0); --pic: 0; --cw: 0; --lat: 1; --req: 0;"
           f" --rom: {rom_of('var(--pc)')}; --Lm: calc((1 - var(--go)) * var(--rLm));"
           + " ".join(f"--L{n}: var(--rL{n});" for n in LATCH if n != "p") + " ".join(f" --Lp{j}: var(--rLp{j});" for j in range(4)) + "\n  " +
           " ".join(f"--wA{w}: calc(var(--fd) * (var(--fvb) - {RB0 - 1})); --wD{w}: var(--fwd{w}); --cA{w}: 0; --cD{w}: 0;" for w in range(WB)) + " }")
css += [f"@container style(--fk1: {k + 1}) {{ .fl {{ --T{k}: calc(2 * var(--fb) + 2); --F{k // 2}: {1 - k % 2}; " +
        " ".join(f"--W{k}_{j}: var(--mv{j});" for j in range(4)) + " } }" for k in range(NL)]
css += [f"@container style(--gk1: {k + 1}) {{ .fl {{ --T{k}: calc(2 * var(--fb) + 4); --F{k // 2}: {1 - k % 2}; " +
        " ".join(f"--W{k}_{j}: var(--mv{WB + j});" for j in range(4)) + " } }" for k in range(NL)]

css += [f"@container style(--ik1: {i + 1}) {{ .fl {{ --IT{i}: calc(var(--fb) + 1); " + " ".join(f"--IW{i}_{j}: var(--mv{j});" for j in range(4)) + " } }" for i in range(ISET)]
css += [f"@container style(--ig1: {i + 1}) {{ .fl {{ --IT{i}: calc(var(--fb) + 2); " + " ".join(f"--IW{i}_{j}: var(--mv{WB + j});" for j in range(4)) + " } }" for i in range(ISET)]

css.append(lbl.section('Instructions', f'{K} levels of .f (fetch, decode) > .x (execute) > .c (commit), display: contents'))
css.append(lbl.group('.f: fetch the two words at pc unless the chain has stopped', 'one code-cache lookup (pc is even); a miss stalls'))
css.append(".f { --op: 255; --cls: 0; --ok: 2; --pout: 0; --wz: 0; }")
css.append(f"@container style(--stop: 0) {{ .f {{ --ib: round(down, {pc} / 4); --iblo: mod(var(--ib), 8); --ibhi: mod(round(down, var(--ib) / 8), {ISET // 8}); --iu: mod({pc}, 4);"
           " --ih: " + isel("ib", lambda i: eq(f"var(--IT{i})", "var(--ib) + 1")) + ";"
           " --vf: " + latched("f", isel("ib", lambda i: f"if(style(--iu: 0): var(--IW{i}_0); else: var(--IW{i}_2))")) + ";"
           " --vg: " + latched("g", isel("ib", lambda i: f"if(style(--iu: 0): var(--IW{i}_1); else: var(--IW{i}_3))")) + ";"
           " --mf: calc((1 - var(--ih)) * (1 - var(--lat) * var(--Lbf))); --mic: var(--mf);"
           " --ok: calc(2 - 2 * var(--mf)); --mb: var(--ib); --hm: calc(1 - var(--mf)); --npst: var(--pst);"
           " --op: calc(var(--mf) * 255 + (1 - var(--mf)) * round(down, var(--vf) / 8192)); --A: mod(var(--vf), 8192);"
           f" --B: calc(round(down, var(--vg) / 1024) + 512); --C: mod(var(--vg), 1024); --cls: {cls_of}; }} }}")
# (a large if() costs its whole text wherever it is evaluated, so the ROM table gets a rule of its own)
css += [f"@container style(--stop: 0) and style(--rom: {t + 1}) {{ .f {{ --rh: round(down, var(--pc) / 64); --rl: round(down, mod(var(--pc), 64) / 2);"
        f" --vf: {rom_table(t * ROMTIER, (t + 1) * ROMTIER, 0)}; --vg: {rom_table(t * ROMTIER, (t + 1) * ROMTIER, 1)}; --mf: 0; --mic: 0; }} }}" for t in TIERS]
css.append(lbl.group('.x: execute', 'one rule per instruction class; if() on --op inside it'))
css += [f"@container style(--cls: {CLS[c]}) {{ .x {{ {' '.join(d)} }} }}" for c, (_, d) in cls_rules.items()]
css.append(lbl.group('.c: commit', 'registers on success; the stall (stop, the missing block); output; the written word\'s cache set'))
css.append("@container style(--ok: 1) { .c { --pc: var(--npc); --fp: var(--nfp); --steps: var(--nsteps); --stop: var(--nstop); --halt: var(--nhalt); --pst: var(--npst);"
           f" --lat: 0; --rom: {rom_of('var(--npc)')}; }} }}")
css.append("@container style(--ok: 0) { .c { --stop: 1; --pend: calc(var(--mb) + 1); --pic: var(--mic); --Lm: var(--hm);"
           + " ".join(f" --L{n}: var(--v{n});" for n in LATCH if n != "p") + " ".join(f" --Lp{j}: var(--pw{j});" for j in range(4)) + " } }")
css.append("@container style(--pout: 1) { .c { --optr: var(--noptr); --cw: var(--ncw); } }")
# (bank by bank: an earlier output instruction of the pass keeps the banks it wrote)
css += [f"@container style(--pout: 1) and style(--dp{w}: 1) {{ .c {{ --cA{w}: var(--nwA{w}); --cD{w}: var(--nwD{w}); }} }}" for w in range(WB)]
css += [f"@container style(--wz: {s + 1}) {{ .c {{ " + " ".join(f"--W{2 * s + i // 4}_{i % 4}: var(--n{i});" for i in range(8)) +
        f" --T{2 * s}: var(--nT0); --T{2 * s + 1}: var(--nT1); }} }}" for s in range(NSET)]

css.append(lbl.section('Export', 'the write set into the RAM channels; the registers\' subjects'))
ex = []
for w in range(WB):
    for i, c in enumerate(CH):
        for p_, A_, D_ in (("", f"wA{w}", f"wD{w}"), ("k", f"cA{w}", f"cD{w}")):
            s_ = f"var(--go) * {eq('var(--chan)', i)} * min(1, var(--{A_}))"
            rel = f"min(1, var(--{A_})) * {eq(f'var(--{A_})', f'var(--wa{p_}{w}{c})')}"
            ex += [f"--nwa{p_}{w}{c}: calc({s_} * var(--{A_}) + (1 - {s_}) * (1 - {rel}) * var(--wa{p_}{w}{c}));",
                   f"--nwd{p_}{w}{c}: calc({s_} * var(--{D_}) + (1 - {s_}) * var(--wd{p_}{w}{c}));"]
ex += ["--xon: min(1, var(--pend));"] + [
    d for q, e in (("xb", f"clamp(0, var(--pend) - 1, {BLKS - 1})"), ("yb", f"clamp(0, var(--pend), {BLKS - 1})"))
    for d in (f"--{q}: {e};", f"--{q}h: round(down, var(--{q}) / 64);", f"--{q}l: calc(var(--{q}) - 64 * var(--{q}h));",
              f"--{q}hot: calc(clamp(0, var(--{q}) - {HOT.start - 1}, 1) * clamp(0, {HOT.stop} - var(--{q}), 1));")]
css.append(".ex { " + " ".join(ex) + " }")

css.append(lbl.section('RAM', f'memtree.py: {len(CH)} write channels per bank, each a decode tree over the bank\'s cells'))
if UI:
    import ccpage5, ui_rb, uipage
    UIL, UIP, UIT = (int(os.environ.get(k_, d_)) for k_, d_ in (('UIL', 24), ('UIP', 64), ('UIT', 400)))
    # the picker's sample programs (samples/<file>.js): (file, label, icon); #ed (the page's program) comes first
    SAMPLES = [('fizzbuzz', 'FizzBuzz', '\U0001F41D'), ('primes', 'primes', '\U0001F9EE'), ('fib', 'Fibonacci', '\U0001F41A'),
               ('stars', 'stars', '\u2728'), ('hanoi', 'Hanoi', '\U0001F5FC'), ('sort', 'sort', '\U0001F4CA'), ('tree', 'tree', '\U0001F333'),
               ('caesar', 'Caesar', '\U0001F510'), ('collatz', 'Collatz', '\U0001F300'), ('bank', 'bank', '\U0001F3E6'),
               ('counter', 'closures', '\u23F2'), ('animals', 'prototypes', '\U0001F43E')]
    if os.environ.get('NOPICK') == '1': SAMPLES = []     # (measurement: the page without the picker)
    SRC = [open(os.path.join(ROOT, 'samples', f + '.js')).read() for f, _, _ in SAMPLES]
    # (an editor's initial text starts at its line 0, so UIL lines of it are read)
    assert all(len(t.rstrip('\n').split('\n')) <= UIL and max(map(len, t.split('\n'))) <= UIP for t in SRC), 'a sample longer than the editor reads'
    EDS = 1 + len(SAMPLES)
    # each editor's radio button right before it in .frame: '.pkr:checked + .ed' is the editor that shows, for one set of
    # readback rules (ui_rb.css) and one display rule whatever the number of editors
    PKR = lambda e: f'<input type="radio" name="pk" id="pk{e}" class="pkr"{" checked=\"checked\"" if e == 0 else ""}/>'
    ui_css, ui_chain, ui_tls, ui_info = ccpage5.build(json.load(open(os.path.join(ROOT, 'compiler', 'lib.json'))), UIL, UIP, UIT, short=os.environ.get('SHORT', '1') == '1')
    print('compile chain', ui_info)
    css.append(lbl.group('Timeline scope: the RAM channels, the compiler\'s registers, the scan\'s done flag'))
    css.append("body { timeline-scope: " + ", ".join(["--" + n for n in WNAMES + NETTL] + ui_tls + ['--rbrdT']) + "; }")
else: css.append(memtree.scope(WNAMES + NETTL))
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
    css.append(f".oc{i} {{ width: anchor-size(--c{OUT_BASE - ROM + i} width, {WOFF}px); left: calc(8px + {c_} * 11px); top: calc(8px + {r_} * 20px); }}")
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
  .rp {{ position: fixed; top: 0; left: 0; visibility: hidden; height: 1px; container-type: inline-size; }}
  .f, .x, .c {{ display: contents; }}
  .regs {{ height: 0; overflow: hidden; }}
  .reg {{ position: relative; overflow: hidden; width: 1px; }}
  .sub {{ position: absolute; left: 0; width: 1px; height: 1px; }}
  .cons {{ position: fixed; left: 16px; top: 16px; width: {COLS * 11 + 16}px; height: {ROWS * 20 + 16}px; contain: strict; }}
  .con {{ position: absolute; inset: 0; background: #151515; border-radius: 6px; }}
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
# ---------------- BENCH=1: the chain alone (chainbench.js), started from the state of the first pass rsim.py runs with all
# K levels executing (STALL=1: the chain stopped at its top). The root's inline style holds the state.
if os.environ.get('BENCH'):
    import copy, csssim as sim, cssref as ref
    sm = sim.Sim(ref.load(os.environ['PROG']))
    while True:
        before = copy.deepcopy(sm); n, why = sm.run_pass(K)
        if why == 'K' or sm.st['halt']: break
    assert why == 'K', 'no pass runs all K levels'
    b0 = before; cw = b0.fill(b0.pending, 0) if b0.pending is not None else 0; b0.pending = None
    st = b0.st; stall = int(os.environ.get('STALL', '0'))
    tval = lambda k: 0 if b0.tag[k // 2][k % 2] is None else 2 * (b0.tag[k // 2][k % 2] + 1) + b0.dirty[k // 2][k % 2]
    root = ([f"--pc: {st['pc']}", f"--fp: {st['fp']}", f"--optr: {st['optr']}", f"--pst: {st['pst']}", f"--steps: {st['steps']}",
             f"--stop: {stall}", f"--cw: {cw}"] + [f"--T{k}: {tval(k)}" for k in range(NL)] + [f"--F{s_}: {b0.fifo[s_]}" for s_ in range(NSET)] +
            [f"--W{k}_{j}: {b0.words[k // 2][k % 2][j]}" for k in range(NL) for j in range(4)] +
            [f"--IT{i}: {0 if b0.itag[i][0] is None else b0.itag[i][0] + 1}" for i in range(ISET)] + [f"--IW{i}_{j}: {b0.iwords[i][0][j]}" for i in range(ISET) for j in range(4)])
    chain = '<i class="end"></i>'
    for _ in range(K): chain = f'<i class="f"><i class="x"><i class="c">{chain}</i></i></i>'
    css = [c for c in css if not c.startswith('#cpu')]
    page = (f'<!doctype html><html lang="en"><meta charset="utf-8"><title>Register CSS CPU chain bench</title><style>{static}' + "\n".join(props + css) +
            f'</style><div id="root" style="{"; ".join(root)}">{chain}</div></html>')
    end = sm.st if not stall else st
    json.dump({'pc': end['pc'], 'sp': 0, 'fp': end['fp'], 'steps': end['steps'], 'K': K, 'stall': stall}, open(outp + '.json', 'w'))
    open(outp, 'w').write(page); print(outp, len(page), 'bytes; bench pass', sm.passes, 'K', K, 'stall', stall); sys.exit()

# ---------------- HTML
# the modems: one slot + iframe per two parts; net/server.js gives the page's modems a group id as it serves the page
MODEMS = "".join(f'<div class="nslot np{i}"><div class="nclip"><iframe class="modem" loading="lazy" src="/net/m0.html?part={i}&amp;n={NP}{"&amp;show" if NETSHOW else ""}#t"'
                 f' title="network modem {i}" aria-hidden="true"></iframe></div></div>' for i in range(NS))
STATIC_CELLS = set(range(R.LAYOUT['data_base'] + R.SDATA - ROM, image.get('init', R.LAYOUT['init']) + R.SDATA - ROM)) | {R.LAYOUT['data_base'] - ROM}
LIVE = (set() if UI else STATIC_CELLS) | {a - ROM for a in R.GINIT}     # on the editor page the compile chain's overlays hold code, strings and staging; the globals start undefined
mem_html = "".join(memtree.html(image["ram"], list(range(w, RAMN, WB)), WOFF, prefix=str(w), live=LIVE) for w in range(WB))
# the console's trees and readers in one contain: strict box: a pass that doesn't write the console doesn't lay it out
con_html = "".join(memtree.html(image["ram"], list(range(OUT_BASE - ROM + w, OUT_BASE - ROM + OUT_SIZE, WB)), WOFF, prefix=f"k{w}") for w in range(WB))
# no ROM leaves: instructions come from the fetch table, and a data read below RAM gives 0 (a read port's leaf name --rom
# names nothing). ~6,000 leaves cost ~8 ms a frame, which the readback scan (one column per frame) and every pass pay
rom_html = ''
console = "\n".join(f'<div class="oc oc{i}"><b></b></div>' for i in range(OUT_SIZE))
RUNX = lambda n, e: f"({e}) * var(--run)" if UI and n not in ('k', 'par', 'tprev') else e     # Edit (run = 0) zeroes the registers
subj = "".join(f'<div class="reg" style="height: {H}px"><div class="sub" style="view-timeline-name: --{n}; top: calc(({RUNX(n, e)} + {OFF}) * 1px)"></div></div>' for n, H, OFF, e in regs if e)
if UI: subj += ('<div class="rp" style="width: anchor-size(--ccdone width, 0px)"><div class="reg" style="height: 2px">'
                '<div class="sub" style="view-timeline-name: --ccok; top: calc(min(1, round(100cqi / 1px)) * 1px)"></div></div></div>')
subj += "".join(f'<div class="rp rp{i}"><div class="reg" style="height: {M20}px"><div class="sub" style="view-timeline-name: --mv{i}; top: calc(100cqi - {WOFF - M20 // 2}px)"></div></div></div>' for i in range(2 * WB))
chain = f'<div class="ex"><div class="regs" aria-hidden="true">{subj}</div></div>'
for _ in range(K): chain = f'<i class="f"><i class="x"><i class="c">{chain}</i></i></i>'
blurb = (f"<p>No font: style alone runs the bytecode, a register machine's three-address instructions. Each layout pass runs up "
         f"to {K} instructions as a chain of nested elements (fetch and decode, execute, commit) out of a 2-way, 32-line cache of RAM "
         f"held in custom properties. The first cache miss stops the chain; the next pass fills the line, and prefetches the next, "
         f"through anchor-size() read ports.</p>"
         f"<pre>{_h.escape(image.get('source', ''))}</pre>")
if not UI:
    page = f"""<!doctype html>
    <html lang="en">
    <meta charset="utf-8">
    <title>JavaScript on a CSS CPU</title>
    <style>
    {lbl.header('js-minus-js/machine/gen_css.py', 'js-minus-js/docs/ARCHITECTURE.md')}
    {static}
    {chr(10).join(props)}
    {chr(10).join(css)}
    </style>
    {mem_html}{rom_html}{NSHOW_HTML}<div class="nlatch">{MODEMS}</div><div class="cons">{con_html}<div class="con"></div>
    {console}</div>
    <div id="clk"><div id="cpu">
    <div class="head">
    <h1>JavaScript on a pure-CSS CPU</h1>
    {blurb}
    <div class="status">steps <b class="num" style="--v: var(--steps)"></b> pc <b class="num" style="--v: var(--pc)"></b> fp <b class="num" style="--v: var(--fp)"></b>
     halt <b class="num" style="--v: var(--halt)"></b></div>
    </div>
    <div class="fl">{chain}</div>
    </div></div>
    </html>
    """
else:
    ui_props = uipage.props(WOFF) + [
        # (Edit: the globals back to undefined, as the CPU-only image starts them, cc_ref GINIT: hoisting, FCACHE's sentinel)
        f'#run:not(:checked) ~ .mem :is({", ".join(f".c{a - ROM}" for a in sorted(R.GINIT))}) {{ width: {R.UNDEF + WOFF}px; }}',
        f'#run:not(:checked) ~ #clkw .cons .cell {{ content-visibility: visible; width: {WOFF}px; }}',
                                     '.cons .oc { display: if(style(--ccgo: 1): block; else: none); }']
    notes = (f"<p>Everything below the editor happens in CSS. When you press Run, a font reads your text back (a variable axis makes HarfBuzz "
             f"copy the code of one column into an invisible glyph's width, and a scan sweeps the columns, one per frame). Then the compiler, a "
             f"stylesheet, runs over those characters: a lexer on a chain of one element per character, then a parser on a chain of one element "
             f"per token, each parser rule picked by a container query. Every instruction word it emits is an element named after its RAM cell. Then "
             f"the CPU, also a stylesheet, runs the program: each layout pass executes up to {K} instructions of a register machine as a chain of "
             f"nested elements, out of a cache of RAM held in custom properties. Output appears in the console on the left.</p>"
             f"<p>The language is a small JavaScript subset: <code>var</code>, <code>function</code>, <code>if</code>/<code>else</code>, "
             f"<code>while</code>, <code>for</code>, <code>switch</code>, <code>return</code>, integer arithmetic, strings, arrays, objects, "
             f"<code>console.log(x)</code> and <code>putc(c)</code>. Up to {UIL} lines of {UIP} columns (the faint line marks the edge); "
             f"paste as plain text. Run scans the editor once (about a second), then compiles; Edit clears the machine. The chips above the "
             f"editor switch to a sample program; each keeps your edits.</p>")
    page_css = f"""{static}
{uipage.static(COLS, ROWS, UIL, UIP, WOFF, EDS)}
{chr(10).join(props)}
{chr(10).join(ui_props)}
{chr(10).join(css)}
{lbl.section('Editor scan', 'a font reads the editor back one column per frame and latches each character into a register')}
{ui_rb.css(UIL, UIP, 8, EDS=EDS)}
{ui_css}
"""
    # the page's stylesheets: (file, the section it starts at, what writes it), in cascade order; each is a run of
    # consecutive sections, written to <page>/<file>.css beside the page (no file may pass Cloudflare's 25 MiB)
    SHEETS = ([('page', 'Page and machine layout', 'machine/gen_css.py, machine/uipage.py'),
               ('machine-properties', 'Registered properties', 'machine/gen_css.py, machine/memtree.py'),
               ('cpu', 'Run / Edit', 'machine/gen_css.py, machine/uipage.py'),
               ('memory', 'RAM', 'machine/gen_css.py, machine/memtree.py'),
               ('console', 'Console', 'machine/gen_css.py'),
               ('scan', 'Editor scan', 'readback/ui_rb.py'),
               ('compiler-properties', 'Compiler: registered properties', 'compiler/ccpage5.py'),
               ('lexer', 'Lexer', 'compiler/ccpage5.py'),
               ('parser', 'Parser', 'compiler/ccpage5.py')]
              + [(f'parser-{f}', f'Parser variants: {f}', 'compiler/ccpage5.py') for f, _, _ in ccpage5.FAMILIES])
    secs = [(m.start(), m.group(1)) for m in re.finditer(r'/\* === (.*?) ===', page_css)]
    starts = []
    for name, title, _ in SHEETS:
        at = [i for i, (_, t) in enumerate(secs) if t == title]
        assert len(at) == 1, f'sheet {name}: {len(at)} sections titled {title!r}'
        starts.append(at[0])
    assert starts[0] == 0 and starts == sorted(starts), f'the sheets\' sections are out of order: {starts}'
    cuts = [secs[i][0] for i in starts] + [len(page_css)]
    sheets = [(name, lbl.header(f'js-minus-js/{gen}', 'js-minus-js/docs/ARCHITECTURE.md') + '\n' + page_css[a:b].strip() + '\n')
              for (name, _, gen), a, b in zip(SHEETS, cuts, cuts[1:])]
    sheet_dir = os.path.splitext(outp)[0]
    links = '\n'.join(f'<link rel="stylesheet" href="{os.path.basename(sheet_dir)}/{name}.css"/>' for name, _ in sheets)
    page = f"""<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
<meta charset="utf-8"/>
<title>JavaScript in CSS</title>
{links}
</head>
<body>
<input type="checkbox" id="run" class="runcb" aria-label="Run"/>
{mem_html}{rom_html}{ui_chain}<div class="cst"><div class="cstv"></div></div><div class="cst2"><b>more than {UIT} tokens</b></div>
<main id="app">
<div class="width-reader"></div>{ui_rb.regs_html()}
<header><h1>JavaScript, compiled and run by a stylesheet</h1>
<p class="lede">Type a program and press Run. No JavaScript runs on this page.</p></header>
<section class="pane">
<div class="bar"><span class="label" id="in-label">Program</span><label class="runbtn" for="run"><span></span></label><span class="scanpos"></span><span class="unread">A line break from Shift+Enter or a paste isn't read: use Enter.</span></div>
<div class="picker" role="radiogroup" aria-label="Programs"><label for="pk0" data-icon="\u270E">yours</label>{"".join(f'<label for="pk{e + 1}" data-icon="{ic}">{_h.escape(lb)}</label>' for e, (_, lb, ic) in enumerate(SAMPLES))}</div>
<div class="frame">{PKR(0)}<div id="ed" class="ed ed0" contenteditable="true" spellcheck="false" autocapitalize="off" autocorrect="off" role="textbox" aria-multiline="true" aria-labelledby="in-label">{ui_rb.editor_html(image.get('source', ''))}</div>{"".join(f'{PKR(e + 1)}<div class="ed ed{e + 1}" contenteditable="true" spellcheck="false" autocapitalize="off" autocorrect="off" role="textbox" aria-multiline="true" aria-label="{_h.escape(lb)}">{ui_rb.editor_html(src)}</div>' for e, ((_, lb, _), src) in enumerate(zip(SAMPLES, SRC)))}</div>
<div class="rbout"></div>
<p class="limit">Lines past {UIL} are not read.</p>
<p class="merged">A pasted code block shows and runs as one line. If it had several, undo (Ctrl+Z, or ⌘Z on a Mac) and paste it as plain text: Ctrl+Shift+V, or ⌥⇧⌘V on a Mac.</p>
</section>
<section class="notes">{notes}</section>
{ui_rb.probes_html(UIL, UIP, 8)}
</main>
{NSHOW_HTML}<div class="nlatch">{MODEMS}</div>
<div id="clkw">
<div class="cons">{con_html}<div class="con"></div>
{console}</div>
<div id="clk"><div id="cpu">
<div class="head">
<div class="status"><span>steps <b class="num" style="--v: var(--steps)"></b></span><span>pc <b class="num" style="--v: var(--pc)"></b> fp <b class="num" style="--v: var(--fp)"></b></span></div>
</div>
<div class="fl">{chain}</div>
</div></div></div>
</body>
</html>
"""
import collections
def lint(text, ints):
    """a registered <integer> whose value isn't one term (a number, or one function: calc(), if(), var(), …) is invalid at
    computed-value time and silently takes its initial value, 0: `--m: (1 - a) * b` must be `calc((1 - a) * b)`"""
    bad = []
    for m in re.finditer(r'(?:[{;]|^)\s*--([\w-]+): ', text, re.M):     # declarations only (not style(--x: v) conditions)
        if m.group(1) not in ints: continue
        i, d = m.end(), 0
        while i < len(text) and (d or text[i] not in ';}'): d += {'(': 1, ')': -1}.get(text[i], 0); i += 1
        val = text[m.end():i].strip()
        if re.fullmatch(r'-?\d+', val): continue
        f = re.match(r'[a-z-]+\(', val)
        if not f: bad.append(f'--{m.group(1)}: {val[:60]}'); continue
        j, d = f.end(), 1
        while d: d += {'(': 1, ')': -1}.get(val[j], 0); j += 1
        if j != len(val): bad.append(f'--{m.group(1)}: {val[:60]}')
    return bad
_bad = lint("\n".join(css), set(re.findall(r'@property --([\w-]+) \{ syntax: "<integer>"', "\n".join(props))))
assert not _bad, f'registered integers with more than one term: {_bad[:5]}'
_dup = [n for n, c in collections.Counter(re.findall(r'@property (--[\w-]+)', page_css if UI else page)).items() if c > 1]
assert not _dup, f'properties registered twice (memtree.py, the compile chain and the scan have their own): {_dup}'
for path, text in [(outp, page)] + ([(f'{sheet_dir}/{n}.css', t) for n, t in sheets] if UI else []):
    assert len(text.encode()) < 20 << 20, f'{path} is {len(text.encode()) / 2**20:.1f} MiB: split it (Cloudflare serves at most 25 MiB per file)'
if UI:
    # the sheets first, then the page, so the page is the newest file (make's target)
    for name, text in sheets: lbl.check(text, f'{sheet_dir}/{name}.css')
    os.makedirs(sheet_dir, exist_ok=True)
    for f in os.listdir(sheet_dir):
        if f.endswith('.css') and f[:-4] not in {n for n, _ in sheets}: os.remove(os.path.join(sheet_dir, f))
    for name, text in sheets: open(os.path.join(sheet_dir, name + '.css'), 'w').write(text)
    print(' '.join(f'{name}.css {len(text) / 1e6:.2f} MB' for name, text in sheets))
open(outp, 'w').write(page)
print(outp, len(page), 'bytes; K', K, 'ISSUE', ISSUE, '; registers', len(regs), '; properties', len(P))
