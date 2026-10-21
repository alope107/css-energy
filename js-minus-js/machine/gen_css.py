#!/usr/bin/env python3
"""gen_css.py image.json out.html — the pure-CSS CPU: a CPU-only page, or with UI=1 the editor page. Style alone runs
the instructions; layout only fills the cache and moves the registers. The design is csssim.py's, which is its oracle.

A pass (ISSUE passes per frame, the font CPU's frame gate):
  #cpu      the registers (view timelines), the frame gate, the pending miss's victim lines
  .fl       the fill: the victim line takes the block the last pass missed, whose words the read ports left in registers
            (a dirty victim's words go to the write set first); the next block is prefetched if it is absent and its
            victim is clean
  K levels  .f fetch (ROM from a static table, RAM through the cache) and decode > .x execute > .c commit. An instruction
            runs only if every word it touches is cached (and, for output, the write set is free); the first that can't
            stops the chain, noting its missing block (--pend) for the next pass's fill
  .ex       the registers' view-timeline subjects at the chain's final state; the write set goes to the RAM channels;
            eight read ports (readers, like the font CPU's) read the missing block's words and the next block's (one port
            per bank and block) from the ROM and RAM leaves into registers for the next pass's fill
Nothing above the chain is a size container, so a pass styles the chain once. (Ports above it, as first built, restyled
the whole chain once per port whose size changed: 7 times in a fill pass.)
Cache: 16 sets x 2 ways x 4 words, set (b + b / 16 + b / 256) mod 16 of block b; --T<line> = 2 * (block + 1) + dirty
(0: empty), --F<set> the next victim way, --W<line>_<word> the words, line = 2 * set + way. RAM is memtree.py's, the
console the font CPU's.

Cost model (measured: exp/csscpu/README.md): a container-query test ~2 us, a declaration ~1.3 us, an if() branch ~0.3 us, per element.
So .x dispatches on 7 instruction classes (one container test each) and selects within a class by if(); .c commits a
whole cache set (16 rules) rather than a word (128).
Env: K (levels, default 32), ISSUE (passes per frame, default 2), UI=1: the editor page (XHTML; the image's RAM is
empty: the compile chain's overlays hold the program): Run starts the scan, the compiler, then the CPU;
Edit zeroes the registers and RAM."""
import sys, os, json, html as _h
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, "machine"), os.path.join(ROOT, "compiler"), os.path.join(ROOT, "readback"), os.path.join(ROOT, "..", "shared", "py"), HERE]
UI = os.environ.get("UI") == "1"
import memtree, csslabel as lbl, cc_ref as R
from uarch import OPN, PRINTOPS, STRTAG, STR_LO, STRP_HI
OP = {n: i for i, n in enumerate(OPN)}

image = json.load(open(sys.argv[1])); outp = sys.argv[2]
K = int(os.environ.get('K', 32)); ISSUE = int(os.environ.get('ISSUE', 2))
ROM, RAMN, WB = image['romSize'], image['ramSize'], 4
BANKN = RAMN // WB; BLKS = (ROM + RAMN) // WB; RB0 = ROM // WB
OUT_BASE, ROWS, COLS = image['outBase'], image['rows'], image['cols']; OUT_SIZE = ROWS * COLS
assert OUT_BASE % 4 == 0 and ROM % 4 == 0
WOFF = M20 = 1 << 20; A15 = 32768
NSET, NWAY = 16, 2; NL = NSET * NWAY
CH = 'ABCDEFGHIJKL'[:2 * ISSUE]; sp0 = image['sp0']

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

LATCH = {"f": 1, "s1": 2, "s2": 4, "ra": 8, "rb": 16, "p": 32, "s3": 64, "rc": 128}    # the latchable reads and their bits (reads, below)
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
# the read ports' words (their subjects sit in the ports, so no expression here), and a miss on the block this pass writes
# back (its leaf isn't written until the next pass, so the ports read it stale: the fill waits a pass; csssim.py)
regs += [(f"mv{i}", M20, M20 // 2, None) for i in range(2 * WB)]
if UI: regs.append(("ccok", 2, 0, None))     # compiled without error: a reader of the compile chain's done anchor, in .ex
regs += [("rLm", 256, 0, "var(--Lm)")] + [(f"rL{n}", M20, M20 // 2, f"var(--L{n})") for n in LATCH if n != "p"] + \
        [(f"rLp{j}", M20, M20 // 2, f"var(--Lp{j})") for j in range(4)]
regs += [("stale", 2, 0, f"calc(var(--fd) * {eq('var(--pend) - 1', 'var(--fvb)')} * min(1, var(--pend)))"),
         ("pstale", 2, 0, f"calc(var(--fd) * {eq('var(--pend)', 'var(--fvb)')} * min(1, var(--pend)))")]
# NET: the request a waiting NET leaves at the chain's end (the modem iframe's height), and the passes this request has
# waited (go passes only, so a frame settles; a new request starts again from 0: consecutive words always differ, by the
# sequence bit, even when a read() loop's next NET stalls in the pass the last one completed); NWAIT passes without an
# answer give -1 (no gateway: a file: URL, a static server)
NWAIT = 2400
regs += [("rreq", 16384, 0, "var(--req)"),
         ("rnwt", NWAIT + 1, 0, f"calc(var(--go) * min(1, var(--req)) * {eq('var(--req)', 'var(--rreq)')} * min({NWAIT}, var(--rnwt) + 1) + (1 - var(--go)) * var(--rnwt))")]
regs += WREGS
WNAMES = [r[0] for r in WREGS]

# ---------------- #cpu: effective state, frame gate, the fill's victims (all from the registers)
cpu = ["--first: calc(1 - var(--init));",
       f"--sp: calc(var(--init) * var(--rsp) + var(--first) * {sp0});", f"--fp: calc(var(--init) * var(--rfp) + var(--first) * {sp0});",
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
       "--fd: calc(var(--fon) * mod(var(--fT), 2));", "--fvb: calc(round(down, var(--fT) / 2) - 1);",
       "--fk1: calc(var(--fon) * (var(--fk) + 1));", "--pend0: calc((1 - var(--fon)) * var(--pend));",
       # the prefetch: block fb + 1 into its set's victim way (line gk), if absent there and the victim is clean
       f"--gs: {setof('(var(--fb) + 1)')};", "--gv: " + sel("gs", NSET, lambda s: f"var(--F{s})") + ";", "--gk: calc(2 * var(--gs) + var(--gv));",
       "--gT: " + sel("gk", NL, lambda k: f"var(--T{k})") + ";",
       "--gabs: " + sel("gs", NSET, lambda s: f"calc(1 - {eq(f'round(down, var(--T{2 * s}) / 2)', 'var(--fb) + 2')} - {eq(f'round(down, var(--T{2 * s + 1}) / 2)', 'var(--fb) + 2')})") + ";",
       f"--gk1: calc(var(--fon) * (1 - var(--pstale)) * var(--gabs) * (1 - mod(var(--gT), 2)) * clamp(0, {BLKS - 1} - var(--fb), 1) * (var(--gk) + 1));"]
cpu += [f"--fwd{w}: " + sel("fk", NL, lambda k, w=w: f"var(--W{k}_{w})") + ";" for w in range(WB)]
cpu += [f"--Lb{n}: mod(round(down, var(--rLm) / {b}), 2);" for n, b in LATCH.items()]
HOT = range(R.LAYOUT["data_base"] // 4, (R.LAYOUT["data_base"] + 2048) // 4)     # the blocks runs mostly read: globals, strings, code, the bottom of the stack (read ports, below)

# ---------------- reads: a word through the cache. For read n of address A: block b, word u, set z, hits h (way 0) and
# H (way 1), each one if() over the set comparing that way's tag, and the word v (set, then way, then word).
def lookup(n, A):
    b = f"var(--b{n})"
    hit = lambda way: sel(f"q{n}", NSET, lambda s: eq(f"round(down, var(--T{2 * s + way}) / 2)", f"{b} + 1"))
    return [f"--b{n}: round(down, ({A}) / 4);", f"--u{n}: mod({A}, 4);", f"--q{n}: {setof(b)};", f"--h{n}: {hit(0)};", f"--H{n}: {hit(1)};"]
def word(n, k): return sel(f"u{n}", 4, lambda j: f"var(--W{k}_{j})")
# A stalled instruction's operands are kept (latches: registers rL<n>, valid if bit n of rLm) for its re-execution as the
# next pass's first instruction (--lat: 1 until the first commit), so it needs only its written line resident at the end
# (csssim.py: without them three blocks in one set evicted each other forever). The write's own lookup (w) isn't latched.
def latched(n, e): return f"if(style(--lat: 1) and style(--Lb{n}: 1): var(--rL{n}); else: {e})"
def read(n, A):
    return lookup(n, A) + [f"--v{n}: " + latched(n, sel(f"q{n}", NSET, lambda s: f"if(style(--H{n}: 1): {word(n, 2 * s + 1)}; else: {word(n, 2 * s)})")) + ";"]
def miss(n):
    return f"(1 - var(--h{n}) - var(--H{n}))" + (f" * (1 - var(--lat) * var(--Lb{n}))" if n in LATCH else "")
LOOKUP = ("b", "u", "q", "h", "H")
READS = ("f", "s1", "s2", "ra", "rb", "w", "p", "s3", "rc")

# a write of value V through lookup n (a read of the same address, or the write's own): the set's 8 new words and 2 tags,
# and --wz = set + 1, which picks the commit rule on .c (0: no write, as on a stall)
def write(n, V, en="1"):
    d = [f"--wval: {V};"]
    for i in range(8):
        way, j = divmod(i, 4)
        old = sel(f"q{n}", NSET, lambda s: f"var(--W{2 * s + way}_{j})")
        d.append(f"--n{i}: if(style(--H{n}: {way}) and style(--u{n}: {j}): var(--wval); else: {old});")
    for way in range(2):
        d.append(f"--nT{way}: if(style(--H{n}: {way}): calc(2 * var(--b{n}) + 3); else: {sel(f'q{n}', NSET, lambda s: f'var(--T{2 * s + way})')});")
    return d + [f"--wz: calc(var(--ok) * {en} * (var(--q{n}) + 1));"]

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
from uarch import HP, GCLIM, GCSP, KEYCELL, RETCELL, HEAP0, OBJTAG, GCVEC, PUTVEC, GETXVEC, SETXVEC, DYNVEC, PRINTVEC, ARRTAG, HEAP_HI
pst_ = v("pst")
def below(n): return f"clamp(0, {RB0} - var(--b{n}), 1)"       # the access is below RAM (object instructions: reads 0, writes dropped)
RA0 = f"calc((1 - {below('ra')}) * var(--vra))"                 # an object instruction's read through ra
scan_key = by_op({'SCAN': "var(--vrb)"}, imm)
scan_found = f"min(1, calc({eq(RA0, scan_key)} + {eq(RA0, 0)}))"
putv_nz = f"(1 - {eq(RA0, 0)})"
new_lt = f"clamp(0, -1 * {s20('var(--vra) - var(--vrb) - 3065')}, 1)"   # NEW: HP - (GCLIM + heap_size - 7) < 0, a chunk is free (GCLIM: the space's offset)
# a class: ops; reads [(name, address, ops needing it or None for all)]; the write (address or None to reuse read `reuse`,
# value, reuse, enable); next registers {pc, sp, fp, steps, pst}; latch dependencies {read: [(read, ops or None)]}: a read
# is kept only if the reads its address came from were good (exactly those: a spurious dependency can block progress)
CLASSES = {
    # ENTER: the frame (--pst 0), then one execution per local zeroing it (--pst 1 .. imm): locals are the collector's roots
    'push': dict(ops=['PUSHI', 'CALL', 'ENTER', 'PUSHS'], reads=[],
                 pre=["--epk: min(1, var(--pst));", f"--emore: clamp(0, {imm} - var(--pst), 1);"],
                 write=(by_op({'ENTER': f"calc((1 - var(--epk)) * {sp} + var(--epk) * ({fp} + var(--pst)))"}, sp),
                        by_op({'CALL': f"calc({pc} + 1)", 'ENTER': f"calc((1 - var(--epk)) * {fp})", 'PUSHS': f"calc({imm} - {STRTAG})"}, imm), None, "1"),
                 nx={'sp': by_op({'ENTER': f"calc((1 - var(--epk)) * ({sp} + 1 + {imm}) + var(--epk) * {sp})"}, f"calc({sp} + 1)"),
                     'pc': by_op({'CALL': imm, 'ENTER': f"calc({pc} + 1 - var(--emore))"}, f"calc({pc} + 1)"),
                     'fp': by_op({'ENTER': f"calc((1 - var(--epk)) * {sp} + var(--epk) * {fp})"}, fp),
                     'steps': by_op({'ENTER': "calc(var(--steps) + 1 - var(--emore))"}, "calc(var(--steps) + 1)"),
                     'pst': by_op({'ENTER': "calc(var(--emore) * (var(--pst) + 1))"}, pst_)}),
    'load': dict(ops=['LOADG', 'LOADL', 'DUP', 'INCG', 'INCL', 'OVER'], reads=[("ra", by_op({'LOADL': fpo, 'INCL': fpo, 'DUP': f"{sp} - 1", 'OVER': f"{sp} - 2"}, imm), None)],
                 write=(by_op({'INCG': imm, 'INCL': fpo}, sp), by_op({'INCG': s20("var(--vra) + 1"), 'INCL': s20("var(--vra) + 1")}, "var(--vra)"), None, "1"),
                 nx={'sp': by_op({'INCG': sp, 'INCL': sp}, f"calc({sp} + 1)")}),
    'bin': dict(ops=BINOPS, reads=[("s1", f"{sp} - 1", None), ("s2", f"{sp} - 2", None)],
                write=(None, by_op({o: BINE[o] for o in BINOPS[:-1]}, BINE[BINOPS[-1]]), "s2", "1"), nx={'sp': f"calc({sp} - 1)"}),
    'jump': dict(ops=['JMP', 'POP', 'JMPI', 'NOP', 'HALT', 'JNEG'], reads=[("s1", f"{sp} - 1", ['JMPI']), ("s2", f"{sp} - 2", ['JNEG'])], write=None,
                 nx={'sp': by_op({'POP': f"calc({sp} - 1)", 'JMPI': f"calc({sp} - 1)"}, sp),
                     'pc': by_op({'JMP': imm, 'JMPI': "mod(var(--vs1), 32768)", 'HALT': pc,
                                  'JNEG': f"calc(clamp(0, -1 * var(--vs2), 1) * {imm} + (1 - clamp(0, -1 * var(--vs2), 1)) * ({pc} + 1))"},
                                 f"calc({pc} + 1)")}),
    # JZ / JNZ: 0 and the empty string are false (a string's length: the word before its address, ra, read only for a string)
    'test': dict(ops=['JZ', 'JNZ'], pre=["--tstr: " + f"calc(clamp(0, var(--vs1) - {STR_LO - STRTAG - 1}, 1) * clamp(0, {STRP_HI - STRTAG} - var(--vs1), 1));",
                                         f"--tz: calc(var(--tstr) * {eq('var(--vra)', 0)} + (1 - var(--tstr)) * {z1});"],
                 reads=[("s1", f"{sp} - 1", None), ("ra", f"calc(var(--tstr) * mod(var(--vs1) - 1, 32768) + (1 - var(--tstr)) * ({sp} - 1))", "var(--tstr)")], write=None,
                 nx={'sp': f"calc({sp} - 1)", 'pc': by_op({'JZ': f"calc(var(--tz) * {imm} + (1 - var(--tz)) * ({pc} + 1))"}, f"calc((1 - var(--tz)) * {imm} + var(--tz) * ({pc} + 1))")},
                 deps={'ra': [('s1', None)]}),
    # ENDK writes its two zeros in two executions (--pst 0, then 1)
    'store': dict(ops=['STOREG', 'STOREL', 'STOREI', 'SETF', 'ENDK'], reads=[("s1", f"{sp} - 1", None), ("s2", f"{sp} - 2", ['STOREI', 'SETF'])],
                  write=(by_op({'STOREL': fpo, 'STOREI': "mod(var(--vs2), 32768)", 'SETF': f"mod(var(--vs2) + {imm}, 32768)",
                                'ENDK': f"mod(var(--vs1) + {imm} + {pst_}, 32768)"}, imm), by_op({'ENDK': 0}, "var(--vs1)"), None,
                         f"(1 - ({eq('var(--op)', OP['SETF'])} + {eq('var(--op)', OP['ENDK'])}) * {below('w')})"),
                  nx={'sp': by_op({'STOREI': f"calc({sp} - 2)", 'ENDK': sp}, f"calc({sp} - 1)"), 'pc': by_op({'ENDK': f"calc({pc} + {pst_})"}, f"calc({pc} + 1)"),
                      'steps': by_op({'ENDK': f"calc(var(--steps) + {pst_})"}, "calc(var(--steps) + 1)"), 'pst': by_op({'ENDK': f"calc(1 - {pst_})"}, pst_)},
                  deps={'s2': []}),
    # indirect reads and the object instructions. SCANI / SCAN repeat until the key or a free pair; PUTV calls the ROM's append
    # routine when the key is missing; NEW writes its two words in two executions (--pst 0, then 1) and calls the GC when full
    'index': dict(ops=['LOADI', 'IDX', 'IDXL', 'RET', 'NOT', 'NEG', 'SHL13', 'LDF', 'SCANI', 'SCAN', 'PUTV', 'NEW'],
                  reads=[("s1", f"{sp} - 1", ['LOADI', 'IDX', 'IDXL', 'RET', 'NOT', 'NEG', 'SHL13', 'LDF', 'SCANI', 'SCAN', 'PUTV']), ("s2", f"{sp} - 2", ['PUTV']),
                         ("ra", by_op({'LOADI': "mod(var(--vs1), 32768)", 'IDXL': fpo, 'RET': fp, 'NOT': f"calc(var(--nstr) * mod(var(--vs1) - 1, 32768) + (1 - var(--nstr)) * ({sp} - 1))", 'LDF': f"mod(var(--vs1) + {imm}, 32768)", 'SCANI': "mod(var(--vs1), 32768)",
                                       'SCAN': "mod(var(--vs1), 32768)", 'PUTV': "mod(var(--vs2), 32768)", 'NEW': HP}, imm),
                          f"(({' + '.join(eq('var(--op)', OP[o]) for o in ['LOADI', 'IDX', 'IDXL', 'RET', 'LDF', 'SCANI', 'SCAN', 'PUTV', 'NEW'])}) - "
                          f"({' + '.join(eq('var(--op)', OP[o]) for o in ['LDF', 'SCANI', 'SCAN', 'PUTV'])}) * {below('ra')} + {eq('var(--op)', OP['NOT'])} * var(--nstr))"),
                         ("rb", by_op({'RET': f"{fp} - 1", 'SCAN': KEYCELL, 'NEW': GCLIM}, "mod(var(--vra) + var(--vs1), 32768)"), ['IDX', 'IDXL', 'RET', 'SCAN', 'NEW'])],
                  write=(by_op({'RET': f"{fp} - 1 - {imm}", 'PUTV': "mod(var(--vs2) + 1, 32768)",
                                'NEW': f"calc({pst_} * ({new_lt} * {HP} + (1 - {new_lt}) * {RETCELL}) + (1 - {pst_}) * ({new_lt} * {sp} + (1 - {new_lt}) * {GCSP}))"}, f"{sp} - 1"),
                         by_op({'LOADI': "var(--vra)", 'RET': "var(--vs1)", 'NOT': f"calc(var(--nstr) * {eq('var(--vra)', 0)} + (1 - var(--nstr)) * {z1})", 'NEG': s20("-1 * var(--vs1)"), 'SHL13': s20("var(--vs1) * 8192"), 'LDF': RA0,
                                'SCANI': f"calc(clamp(0, -1 * {RA0}, 1) * {RA0} + (1 - clamp(0, -1 * {RA0}, 1)) * {s20('var(--vs1) + 2')})",
                                'SCAN': f"calc(clamp(0, -1 * {RA0}, 1) * {RA0} + (1 - clamp(0, -1 * {RA0}, 1)) * {s20('var(--vs1) + 2')})",
                                'PUTV': f"calc({putv_nz} * var(--vs1) + (1 - {putv_nz}) * {pc})",
                                'NEW': f"calc({pst_} * ({new_lt} * (var(--vra) + 8) + (1 - {new_lt}) * {pc}) + (1 - {pst_}) * ({new_lt} * (var(--vra) + {HEAP0 - OBJTAG}) + (1 - {new_lt}) * {sp}))"},
                               "var(--vrb)"), None,
                         f"(1 - ({eq('var(--op)', OP['SCANI'])} + {eq('var(--op)', OP['SCAN'])}) * {scan_found} - {eq('var(--op)', OP['PUTV'])} * {below('w')})"),
                  nx={'sp': by_op({'RET': f"calc({fp} - {imm})", 'PUTV': f"calc({sp} - 2 * {putv_nz})", 'NEW': f"calc({sp} + {pst_})"}, sp),
                      'fp': by_op({'RET': "var(--vra)"}, fp),
                      'pc': by_op({'RET': "mod(var(--vrb), 32768)", 'SCANI': f"calc({pc} + {scan_found})", 'SCAN': f"calc({pc} + {scan_found})",
                                   'PUTV': f"calc({putv_nz} * ({pc} + 1) + (1 - {putv_nz}) * {PUTVEC})",
                                   'NEW': f"calc((1 - {pst_}) * {pc} + {pst_} * ({new_lt} * ({pc} + 1) + (1 - {new_lt}) * {GCVEC}))"}, f"calc({pc} + 1)"),
                      'steps': by_op({'NEW': f"calc(var(--steps) + {pst_})"}, "calc(var(--steps) + 1)"), 'pst': by_op({'NEW': f"calc(1 - {pst_})"}, pst_)},
                  pre=["--nstr: " + f"calc({eq('var(--op)', OP['NOT'])} * clamp(0, var(--vs1) - {STR_LO - STRTAG - 1}, 1) * clamp(0, {STRP_HI - STRTAG} - var(--vs1), 1));"],
                  deps={'ra': [('s1', ['LOADI', 'LDF', 'SCANI', 'SCAN', 'NOT']), ('s2', ['PUTV'])], 'rb': [('s1', ['IDX', 'IDXL']), ('ra', ['IDX', 'IDXL'])]}),
}
# arrays and the dynamic operators (uarch.py): IDXA / STOREX index an array inside its length (IDXA reads 0 past it) and DYN
# computes a number result; anything else traps (the return address written at sp, pc to the ROM routine). xA / xk: the
# array and the index; ra = its ptr word, rb = its length word, rc = the element (only read when they matter)
vs1, vs2, vs3 = "var(--vs1)", "var(--vs2)", "var(--vs3)"
def isstr_v(x): return f"calc(clamp(0, {x} - {STR_LO - STRTAG - 1}, 1) * clamp(0, {STRP_HI - STRTAG} - {x}, 1))"
def isref_v(x):
    """a string, array or object value (1 / 0)"""
    return (f"calc({isstr_v(x)} + clamp(0, {x} - {ARRTAG + HEAP0 - 1}, 1) * clamp(0, {ARRTAG + HEAP_HI} - {x}, 1)"
            f" + clamp(0, {x} + {OBJTAG - HEAP0 + 1}, 1) * clamp(0, {HEAP_HI - OBJTAG} - {x}, 1))")
ARR_PRE = [f"--xA: {by_op({'STOREX': vs3}, vs2)};", f"--xk: {by_op({'STOREX': vs2}, vs1)};",
           f"--xarr: calc(clamp(0, var(--xA) - {ARRTAG + HEAP0 - 1}, 1) * clamp(0, {ARRTAG + HEAP_HI} - var(--xA), 1));",
           f"--xa: calc(var(--xarr) * mod(var(--xA), 32768) + (1 - var(--xarr)) * ({sp} - 1));",
           "--xin: calc(var(--xarr) * clamp(0, var(--xk) + 1, 1) * clamp(0, var(--vrb) - var(--xk), 1));",
           f"--xrd: calc({eq('var(--op)', OP['IDXA'])} * var(--xin));",
           f"--xtrap: {by_op({'IDXA': 'calc(1 - var(--xarr))'}, 'calc(1 - var(--xin))')};"]
# DYN, a class of its own (the arr class's reads are wasted on it, and its result if() on them)
DYN_PRE = ["--df: mod(var(--imm), 64);",
           # DYN's slow path: == / != with two strings, the others with a string, array or object on either side
           f"--dtr: if(style(--df: {OP['EQ']}) or style(--df: {OP['NE']}): calc({isstr_v(vs1)} * {isstr_v(vs2)}); else: min(1, calc({isref_v(vs1)} + {isref_v(vs2)})));",
           "--dres: if(" + " ".join(f"style(--df: {OP[o]}): {BINE[o]};" for o in ('ADD', 'EQ', 'NE', 'LT', 'GT', 'LE')) + f" else: {BINE['GE']});"]
CLASSES['arr'] = dict(ops=['IDXA', 'STOREX'], pre=ARR_PRE,
    reads=[("s1", f"{sp} - 1", None), ("s2", f"{sp} - 2", None), ("s3", f"{sp} - 3", ['STOREX']),
           ("ra", "var(--xa)", "var(--xarr)"), ("rb", "calc(var(--xa) - var(--xarr))", "var(--xarr)"),
           ("rc", "mod(var(--vra) + var(--xin) * var(--xk), 32768)", "var(--xrd)")],
    write=(f"calc(var(--xtrap) * {sp} + (1 - var(--xtrap)) * {by_op({'STOREX': 'mod(var(--vra) + var(--xk), 32768)'}, f'calc({sp} - 2)')})",
           f"calc(var(--xtrap) * ({pc} + 1) + (1 - var(--xtrap)) * {by_op({'IDXA': 'calc(var(--xin) * var(--vrc))'}, vs1)})", None, "1"),
    nx={'sp': f"calc(var(--xtrap) * ({sp} + 1) + (1 - var(--xtrap)) * {by_op({'STOREX': f'calc({sp} - 3)'}, f'calc({sp} - 1)')})",
        'pc': f"calc(var(--xtrap) * {by_op({'IDXA': GETXVEC}, SETXVEC)} + (1 - var(--xtrap)) * ({pc} + 1))"},
    deps={'ra': [('s2', ['IDXA']), ('s3', ['STOREX'])], 'rb': [('s2', ['IDXA']), ('s3', ['STOREX'])], 'rc': [('s1', None), ('ra', None), ('rb', None)]})
CLASSES['dyn'] = dict(ops=['DYN'], pre=DYN_PRE, reads=[("s1", f"{sp} - 1", None), ("s2", f"{sp} - 2", None)],
    write=(f"calc(var(--dtr) * {sp} + (1 - var(--dtr)) * ({sp} - 2))", f"calc(var(--dtr) * ({pc} + 1) + (1 - var(--dtr)) * var(--dres))", None, "1"),
    nx={'sp': f"calc(var(--dtr) * ({sp} + 1) + (1 - var(--dtr)) * ({sp} - 1))", 'pc': f"calc(var(--dtr) * {DYNVEC} + (1 - var(--dtr)) * ({pc} + 1))"})
# NET (net/server.js has the modem's protocol): a stall without a miss until the modem's answer for this word has come.
# The answer R = valid + 2 seq + 4 (value mod 2^18) is the modem slot's scrollLeft, read by the scroll timeline --nans on
# #cpu; it counts when it is valid and its seq is the word's bit 12 (the lib alternates it). While it waits, the class
# leaves --req = 1 + (word mod 8192) for the chain's end (the register rreq: the iframe's height, the request).
from net_slot import SLOT, NW
NET_PRE = ["--nR: var(--nans);", "--nvalid: mod(var(--nR), 2);", "--nrseq: mod(round(down, var(--nR) / 2), 2);",
           "--nws: mod(round(down, var(--vs1) / 4096), 2);", "--nd: round(down, var(--nR) / 4);",
           f"--ndata: calc(var(--nd) - {1 << 18} * clamp(0, var(--nd) - {(1 << 17) - 1}, 1));",
           f"--nmatch: calc(var(--nvalid) * {eq('var(--nrseq)', 'var(--nws)')});",
           f"--ntime: clamp(0, var(--rnwt) - {NWAIT - 1}, 1);", "--nok: min(1, calc(var(--nmatch) + var(--ntime)));",
           "--nval: calc(var(--nmatch) * var(--ndata) - (1 - var(--nmatch)) * var(--ntime));"]
CLASSES['net'] = dict(ops=['NET'], pre=NET_PRE, reads=[("s1", f"{sp} - 1", None)], write=(None, "var(--nval)", "s1", "1"), nx={})
def first_miss(acc):
    """the block of the first missing access (dependency order) among [(name, mask)], -1 for none"""
    e = "-1"
    for n, m in reversed(acc): e = f"calc({m}{miss(n)} * var(--b{n}) + (1 - {m}{miss(n)}) * {e})"
    return e
def need(ops):
    if ops is None: return ""
    if isinstance(ops, str): return ops + " * "
    return "(" + " + ".join(eq("var(--op)", OP[o]) for o in ops) + ") * "
def nexts(nx, done="1"):
    return [f"--npc: {nx.get('pc', f'calc({pc} + {done})')};", f"--nsp: {nx.get('sp', sp)};", f"--nfp: {nx.get('fp', fp)};",
            f"--nsteps: {nx.get('steps', f'calc(var(--steps) + {done})')};"] + ([f"--npst: {nx['pst']};"] if 'pst' in nx else [])
cls_rules = {}
for c, k in CLASSES.items():
    d, acc = list(k.get('pre', [])), []
    for n, A, ops_n in k['reads']: d += read(n, A); acc.append((n, need(ops_n)))
    good = {}
    for n, _, _ in k['reads']:
        g = f"(1 - {miss(n)})"
        for m, ops_m in k.get('deps', {}).get(n, []): g += f" * (1 - {need(ops_m)}{miss(m)})"
        good[n] = g
    d.append("--hm: calc(1 - var(--mf)" + "".join(f" + {LATCH[n]} * {g}" for n, g in good.items()) + ");")
    if k['write']:
        A, V, reuse, en = k['write']
        if reuse is None: d += lookup("w", A); acc.append(("w", "" if en == "1" else en + " * ")); wn = "w"
        else: wn = reuse
        d += write(wn, V, en)
    d += [f"--ok: calc(1 - min(1, calc({' + '.join(f'{m}{miss(n)}' for n, m in acc)})));" if acc else "--ok: 1;",
          f"--mb: {first_miss(acc)};" if acc else "--mb: -1;"] + nexts(k['nx'])
    if c == 'jump': d += [f"--nstop: {eq('var(--op)', OP['HALT'])};", f"--nhalt: {eq('var(--op)', OP['HALT'])};"]
    if c == 'net': d += [f"--ok: calc((1 - {miss('s1')}) * var(--nok));",      # (replaces the generic --ok above: it waits)
                         f"--req: calc((1 - var(--nok)) * (1 - {miss('s1')}) * (1 + mod(var(--vs1), 8192)));"]
    cls_rules[c] = (k['ops'], d)

# 'out': the PRINT family and PUTC (the font CPU's print service): up to 4 console cells per execution,
# one per bank; a string chunk ends at its block (the block's line must be cached), at a NUL (the value is out) or a
# newline (taken); until the value is out the instruction repeats (npc = pc) and --pst carries the position. Output needs
# the pass's write set free. PUTC writes one cell or a newline.
pv = "var(--vs1)"
isputc = eq("var(--op)", OP['PUTC'])
pr = read("s1", f"{sp} - 1") + [
    "--prLN: " + by_op({o: 1 for o in PRINTOPS if o.endswith('LN')}, 0) + ";", "--prSP: " + by_op({o: 1 for o in PRINTOPS if o.endswith('SP')}, 0) + ";",
    "--prB: " + by_op({o: 1 for o in PRINTOPS if o.startswith('PRINTB')}, 0) + ";",
    f"--pp: calc({pv} + {STRTAG});",
    f"--isStr: calc((1 - {isputc}) * clamp(0, var(--pp) - {STR_LO - 1}, 1) * clamp(0, {STRP_HI} - var(--pp), 1));",
    f"--isBool: calc((1 - var(--isStr)) * var(--prB) * ({eq(pv, 0)} + {eq(pv, 1)}));",
    "--isNum: calc((1 - var(--isStr)) * (1 - var(--isBool)));",
    "--pq: calc(min(1, var(--pst)) * var(--pst) + (1 - min(1, var(--pst))) * var(--pp));",
    f"--pdone: calc(var(--isStr) * {eq('var(--pq)', STR_LO)});", "--pj0: mod(var(--pq), 4);"]
pr += lookup("p", "var(--pq)")
pr += [f"--pw{j}: if(style(--lat: 1) and style(--Lbp: 1): var(--rLp{j}); else: " + sel("qp", NSET, lambda s, j=j: f"if(style(--Hp: 1): var(--W{2 * s + 1}_{j}); else: var(--W{2 * s}_{j}))") + ");" for j in range(4)]
pr.append(f"--hm: calc(1 - var(--mf) + 2 * (1 - {miss('s1')}) + 32 * (1 - {miss('p')}) * (1 - {miss('s1')}));")
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
       "--npst: calc((1 - var(--isRef)) * (var(--isStr) * (1 - var(--ptNul)) * (var(--pq) + var(--pe) + var(--ptNL)) + (1 - var(--isStr)) * (1 - var(--pfin)) * (var(--pph) + 1)));"]
for i in range(4):
    pr.append(f"--pch{i}: " + (f"if(style(--op: {OP['PUTC']}): {pv}; else: " if i == 0 else "") +
              f"calc(var(--isStr) * (var(--pr{i}) * var(--pb{i}) + {eq('var(--pe)', i)} * var(--ptNul) * var(--prSP) * 32)"
              f" + (1 - var(--isStr)) * clamp(0, var(--pn) - {i}, 1) * var(--pnb{i}))" + (")" if i == 0 else "") + ";")
# an array or object (isRef) traps instead: the return address written at sp, pc to the ROM's print routine (no output here)
pr += [f"--isRef: calc((1 - {isputc}) * (clamp(0, {pv} - {ARRTAG + HEAP0 - 1}, 1) * clamp(0, {ARRTAG + HEAP_HI} - {pv}, 1)"
       f" + clamp(0, {pv} + {OBJTAG - HEAP0 + 1}, 1) * clamp(0, {HEAP_HI - OBJTAG} - {pv}, 1)));"]
pr += lookup("w", sp) + write("w", f"calc({pc} + 1)", "var(--isRef)")
pr += [f"--ok: calc(var(--isRef) * (1 - min(1, calc({miss('s1')} + {miss('w')}))) + (1 - var(--isRef)) * (1 - min(1, calc({miss('s1')} + var(--mpp)))) * (1 - var(--cw)));",
       f"--mb: calc({miss('s1')} * var(--bs1) + (1 - {miss('s1')}) * (var(--isRef) * ({miss('w')} * var(--bw) + (1 - {miss('w')}) * -1)"
       f" + (1 - var(--isRef)) * (var(--mpp) * var(--bp) + (1 - var(--mpp)) * -1)));"]
pr += nexts({'pc': f"calc(var(--isRef) * {PRINTVEC} + (1 - var(--isRef)) * ({pc} + var(--pfin)))", 'sp': f"calc(var(--isRef) * ({sp} + 1) + (1 - var(--isRef)) * ({sp} - var(--pfin)))"},
            "max(var(--isRef), var(--pfin))")
# cell i of the chunk goes to optr + i, bank (optr + i) mod 4 (OUT_BASE is a multiple of 4)
pr += ["--pout: calc(var(--ok) * (1 - var(--isRef)));", "--ncw: min(1, var(--pn));",
       f"--noptr: mod(var(--pnl) * (round(down, (var(--optr) + var(--pn)) / {COLS}) + 1) * {COLS} + (1 - var(--pnl)) * (var(--optr) + var(--pn)), {OUT_SIZE});"]
for w in range(WB):
    pr += [f"--pi{w}: mod({w} - var(--optr), 4);", f"--dp{w}: clamp(0, var(--pn) - var(--pi{w}), 1);",
           f"--nwA{w}: calc(var(--dp{w}) * (round(down, mod(var(--optr) + var(--pi{w}), {OUT_SIZE}) / 4) + 1));",
           f"--nwD{w}: calc(" + " + ".join(f"{eq(f'var(--pi{w})', i)} * var(--pch{i})" for i in range(4)) + ");"]
cls_rules['out'] = (PRINTOPS + ['PUTC'], pr)
CLS = {c: i + 1 for i, c in enumerate(cls_rules)}
assert sorted(OPN) == sorted(o for ops, _ in cls_rules.values() for o in ops), 'every instruction in one class'
FREQ = ['PUSHI', 'LOADG', 'JZ', 'MOD', 'EQ', 'JMP', 'ADD', 'STOREG', 'LE', 'PRINTLN', 'LOADL']   # FizzBuzz's most frequent first
opcls = {o: CLS[c] for c, (ops, _) in cls_rules.items() for o in ops}
cls_of = "if(" + " ".join(f"style(--op: {OP[o]}): {opcls[o]};" for o in FREQ + [o for o in opcls if o not in FREQ]) + " else: 0)"

# the ROM's words (instruction fetch only), two-level on the pc
ROMW = [w or 0 for w in image['rom']] + [0] * (ROM - len(image['rom']))
def rom_table(lo, hi):
    return "if(" + " ".join(f"style(--rh: {h}): if(" + " ".join(f"style(--rl: {l}): {ROMW[32 * h + l]};" for l in range(32) if ROMW[32 * h + l]) + " else: 0);"
                            for h in range(lo // 32, hi // 32) if any(ROMW[32 * h:32 * h + 32])) + " else: 0)"
# An if() costs ~70 ns per entry it holds wherever it is evaluated, so the ROM's words are split into tiers of ROMTIER, each a
# rule of its own matched by --rom = 1 + the tier (0: not in ROM): a ROM instruction evaluates one tier's table
ROMTIER = int(os.environ.get('ROMTIER', 1024)) or ROM
TIERS = [t for t in range(ROM // ROMTIER) if any(ROMW[t * ROMTIER:(t + 1) * ROMTIER])]
def rom_of(x): return f"calc(clamp(0, {ROM} - {x}, 1) * (1 + round(down, {x} / {ROMTIER})))"

ABL = os.environ.get('ABL', '').split(',')     # timing ablations: norom (the ROM table empty), ...
if 'norom' in ABL: rom_table = lambda lo, hi: "0"
# ---------------- the page's CSS
P = ["pc", "rsp", "rfp", "sp", "fp", "optr", "pst", "steps", "halt", "pend", "init", "k", "par", "tprev", "first", "fresh", "go", "chan", "nk", "npar",
     "fon", "fb", "fs", "fv", "fk", "fT", "fd", "fvb", "fk1", "pend0", "gs", "gv", "gk", "gT", "gabs", "gk1", "xon", "xb", "xbh", "xbl", "xbhot", "yb", "ybh", "ybl", "ybhot",
     "t", "stop", "cw", "op", "imm", "simm", "cls", "rom", "rh", "rl", "vf", "mf", "ok", "mb", "npc", "nsp", "nfp", "nsteps", "nstop", "nhalt",
     "wval", "wz", "nT0", "nT1", "pout", "ncw", "noptr", "npst", "prLN", "prSP", "prB", "pp", "isStr", "isBool", "isNum", "pq", "pdone", "pj0", "xA", "xk", "xarr", "xa", "xin", "xrd", "xtrap", "df", "dres", "isRef", "dtr", "tstr", "tz", "nstr", "epk", "emore",
     "mpp", "pa", "pneg", "pL", "ptot", "pph", "pbase", "pe", "pvE", "pbE", "ptNul", "ptNL", "pn", "pfin", "pnl", "lat", "hm", "Lm", "isHALT",
     "req", "nans", "nlive", "nR", "nvalid", "nrseq", "nws", "nd", "ndata", "nmatch", "ntime", "nok", "nval"]
P += [r[0] for r in regs if r[0] not in P] + [f"L{n}" for n in LATCH if n != "p"] + [f"Lp{j}" for j in range(4)] + [f"Lb{n}" for n in LATCH]
P += [f"{x}{w}" for w in range(WB) for x in ("fwd", "wA", "wD", "cA", "cD", "nwA", "nwD", "pi", "dp", "pw")]
P += [f"{x}{i}" for i in range(4) for x in ("pg", "pnb", "pb", "pc", "pr", "pch")] + [f"n{i}" for i in range(8)]
P += [f"n{r[0]}" for r in WREGS]
P += [x + n for n in READS for x in LOOKUP] + [f"v{n}" for n in READS if n not in ("w", "p")]
P = list(dict.fromkeys(P))
props = [lbl.section('Registered properties', 'registers, the chain\'s state and temps: integers')]
# temps that only the element declaring them reads (.x's reads and PRINT scratch) don't inherit
LOCAL = {x + n for n in READS if n != "f" for x in LOOKUP} | {"uf", "qf", "hf", "Hf", "rh", "rl"}
LOCAL |= {"xA", "xk", "xarr", "xa", "xin", "xrd", "xtrap", "df", "dres", "isRef", "dtr", "tstr", "tz", "nstr", "epk", "emore"}
LOCAL |= {"nR", "nvalid", "nrseq", "nws", "nd", "ndata", "nmatch", "ntime", "nok", "nval"}
LOCAL |= {"pp", "isStr", "isBool", "isNum", "pq", "pdone", "pj0", "mpp", "pa", "pneg", "pL", "ptot", "pph", "pbase", "pe", "pvE", "pbE",
          "ptNul", "ptNL", "pn", "pfin", "pnl", "prLN", "prSP", "prB"}
LOCAL |= {f"{x}{i}" for i in range(4) for x in ("pg", "pnb", "pb", "pc", "pr", "pch", "pi", "dp")}
props += [f'@property --{n} {{ syntax: "<integer>"; inherits: {"false" if n in LOCAL else "true"}; initial-value: 0; }}' for n in P]
props += [f'@property --sR{i} {{ syntax: "<custom-ident>"; inherits: false; initial-value: --c0; }}' for i in range(2 * WB)]   # a port's leaf name

css = [lbl.section('CPU: clock, registers, frame gate, the fill\'s victims', 'on #cpu: the registers are view timelines'),
       "#clk { animation: wc 100s linear infinite; }\n@keyframes wc { from { --t: 0; } to { --t: 60000; } }",
       "#cpu {\n  timeline-scope: " + ", ".join([f"--{r[0]}" for r in regs if r[0] not in WNAMES] + ["--nans"]) +
       ";\n  animation-name: " + ", ".join([f"r-{r[0]}" for r in regs] + ["r-nans"]) + ";\n  animation-timeline: " + ", ".join([f"--{r[0]}" for r in regs] + ["--nans"]) +
       ";\n  animation-duration: auto;\n  animation-timing-function: linear;\n  animation-fill-mode: both;\n  " + "\n  ".join(cpu) + "\n}"]
css.append(lbl.group('Register keyframes', 'each register\'s view timeline mapped onto its value range'))
css += [f"@keyframes r-{n} {{ from {{ --{n}: {H - OFF}; }} to {{ --{n}: {-1 - OFF}; }} }}" for n, H, OFF, _ in regs]
css += [lbl.group('NET: the modem', 'its slot\'s scrollLeft is the answer (the scroll timeline --nans); its height is the request (rreq)'),
        f"@keyframes r-nans {{ from {{ --nans: 0; }} to {{ --nans: {NW - SLOT}; }} }}",
        # live from the first waiting NET on (a transition latch: 0 s to take it, a 1,000,000 s delay to hold it)
        ".nlatch { height: 0; --nlive: min(1, var(--rreq)); transition: --nlive 0s calc((1 - min(1, var(--rreq))) * 1000000s); }",
        f".nslot {{ display: if(style(--nlive: 1): block; else: none); position: fixed; left: 0; top: 0; width: {SLOT}px; height: 1px;"
        " overflow: hidden; visibility: hidden; scroll-timeline: --nans x; }",
        f".modem {{ display: block; border: 0; width: {NW}px; height: calc((1 + var(--rreq)) * 1px); }}"]

# a read port's leaf name: a two-level if() on the block's 64-block group (h) and place in it (l). An if() costs ~70 ns per
# entry it contains, taken or not (exp/csscpu/README.md), so a 4,352-block mux costs ~0.3 ms wherever it is evaluated: each port
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
css.append(lbl.group(f'Read ports (readers at the chain\'s end): one per bank ({WB}) for the missing block (xb) and one for the next (yb)',
                     'a two-level if() picks the leaf, anchor-size() reads it, a view-timeline subject keeps it for the next pass'))
for i in range(2 * WB):
    w, q = i % WB, "xb" if i < WB else "yb"
    leaf = lambda b, w=w: leafname(4 * b + w)
    css.append(f".rp{i} {{ width: anchor-size(var(--sR{i}) width, {WOFF}px); }}")
    if 'nomux' in ABL: continue
    css.append(f"@container style(--xon: 1) and style(--{q}hot: 1) {{ .rp{i} {{ --sR{i}: {mux(q, set(HOT), leaf, f'--c{w}')}; }} }}")
    css.append(f"@container style(--xon: 1) and style(--{q}hot: 0) {{ .rp{i} {{ --sR{i}: {mux(q, set(range(RB0, BLKS)) - set(HOT), leaf, '--rom')}; }} }}")   # (ROM: no leaf, reads 0)

css.append(lbl.section('The fill', 'the victim line takes the pending block (a dirty victim\'s words are the pass\'s RAM write set), and the prefetch line the next'))
css.append(".fl { --stop: calc(1 - var(--go) * (1 - var(--halt))); --pend: var(--pend0); --cw: 0; --lat: 1; --req: 0;"
           f" --rom: {rom_of('var(--pc)')}; --Lm: calc((1 - var(--go)) * var(--rLm));"
           + " ".join(f"--L{n}: var(--rL{n});" for n in LATCH if n != "p") + " ".join(f" --Lp{j}: var(--rLp{j});" for j in range(4)) + "\n  " +
           " ".join(f"--wA{w}: calc(var(--fd) * (var(--fvb) - {RB0 - 1})); --wD{w}: var(--fwd{w}); --cA{w}: 0; --cD{w}: 0;" for w in range(WB)) + " }")
css += [f"@container style(--fk1: {k + 1}) {{ .fl {{ --T{k}: calc(2 * var(--fb) + 2); --F{k // 2}: {1 - k % 2}; " +
        " ".join(f"--W{k}_{j}: var(--mv{j});" for j in range(4)) + " } }" for k in range(NL)]
css += [f"@container style(--gk1: {k + 1}) {{ .fl {{ --T{k}: calc(2 * var(--fb) + 4); --F{k // 2}: {1 - k % 2}; " +
        " ".join(f"--W{k}_{j}: var(--mv{WB + j});" for j in range(4)) + " } }" for k in range(NL)]

css.append(lbl.section('Instructions', f'{K} levels of .f (fetch, decode) > .x (execute) > .c (commit), display: contents'))
css.append(lbl.group('.f: fetch the word at pc unless the chain has stopped', 'ROM from a static table, RAM through the cache; a miss stalls'))
css.append(".f { --op: 255; --cls: 0; --ok: 2; --pout: 0; --wz: 0; }")
css.append("@container style(--stop: 0) { .f { " + " ".join(lookup("f", pc)) +
           f" --vf: " + latched("f", sel("qf", NSET, lambda s: f"if(style(--Hf: 1): {word('f', 2 * s + 1)}; else: {word('f', 2 * s)})")) + ";"
           f" --mf: calc({miss('f')}); --ok: calc(2 - 2 * var(--mf)); --mb: var(--bf); --hm: calc(1 - var(--mf)); --npst: var(--pst);"
           " --op: calc(var(--mf) * 255 + (1 - var(--mf)) * round(down, var(--vf) / 8192)); --imm: mod(var(--vf), 8192);"
           f" --simm: calc(var(--imm) - 8192 * min(1, round(down, var(--imm) / 4096))); --cls: {cls_of}; }} }}")
# (a large if() costs its whole text wherever it is evaluated, so the ROM table gets a rule of its own: README)
css += [f"@container style(--stop: 0) and style(--rom: {t + 1}) {{ .f {{ --rh: round(down, var(--pc) / 32); --rl: mod(var(--pc), 32);"
        f" --vf: {rom_table(t * ROMTIER, (t + 1) * ROMTIER)}; --mf: 0; }} }}" for t in TIERS]
css.append(lbl.group('.x: execute', 'one rule per instruction class; if() on --op inside it'))
css += [f"@container style(--cls: {CLS[c]}) {{ .x {{ {' '.join(d)} }} }}" for c, (_, d) in cls_rules.items()]
css.append(lbl.group('.c: commit', 'registers on success; the stall (stop, the missing block); output; the written word\'s cache set'))
css.append("@container style(--ok: 1) { .c { --pc: var(--npc); --sp: var(--nsp); --fp: var(--nfp); --steps: var(--nsteps); --stop: var(--nstop); --halt: var(--nhalt); --pst: var(--npst);"
           f" --lat: 0; --rom: {rom_of('var(--npc)')}; }} }}")
css.append("@container style(--ok: 0) { .c { --stop: 1; --pend: calc(var(--mb) + 1); --Lm: var(--hm);"
           + " ".join(f" --L{n}: var(--v{n});" for n in LATCH if n != "p") + " ".join(f" --Lp{j}: var(--pw{j});" for j in range(4)) + " } }")
css.append("@container style(--pout: 1) { .c { --optr: var(--noptr); --cw: var(--ncw); " +
           " ".join(f"--cA{w}: var(--nwA{w}); --cD{w}: var(--nwD{w});" for w in range(WB)) + " } }")
css += [f"@container style(--wz: {s + 1}) {{ .c {{ " + " ".join(f"--W{2 * s + i // 4}_{i % 4}: var(--n{i});" for i in range(8)) +
        f" --T{2 * s}: var(--nT0); --T{2 * s + 1}: var(--nT1); }} }}" for s in range(NSET)]

css.append(lbl.section('Export', 'the write set into the RAM channels; the registers\' subjects'))
# (it holds its cell until it takes another, rather than being cleared: a channel change restyles the tree). Rotation: a
# channel written in a frame is not taken again until its leaf's remembered size has been recorded at that frame's end
# (the font CPU's rotation); a cell written again releases the channel that held it.
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
    ui_css, ui_chain, ui_tls, ui_info = ccpage5.build(json.load(open(os.path.join(ROOT, 'compiler', 'lib.json'))), UIL, UIP, UIT, short=os.environ.get('SHORT', '1') == '1')
    print('compile chain', ui_info)
    css.append(lbl.group('Timeline scope: the RAM channels, the compiler\'s registers, the scan\'s done flag'))
    css.append("body { timeline-scope: " + ", ".join(["--" + n for n in WNAMES] + ui_tls + ['--rbrdT']) + "; }")
else: css.append(memtree.scope(WNAMES))
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
  .rom {{ display: block; height: 1px; }}
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
# ---------------- BENCH=1: the chain alone (chainbench.js), started from the state of the first pass sim.py runs with all
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
STATIC_CELLS = set(range(R.LAYOUT['data_base'] + R.SDATA - ROM, image.get('init', R.LAYOUT['init']) + R.SDATA - ROM)) | {R.LAYOUT['data_base'] - ROM}
LIVE = set() if UI else STATIC_CELLS     # on the editor page the compile chain's overlays hold code, strings and staging
mem_html = "" if 'nomem' in ABL else "".join(memtree.html(image["ram"], list(range(w, RAMN, WB)), WOFF, prefix=str(w), live=LIVE) for w in range(WB))
# the console's trees and readers in one contain: strict box: a pass that doesn't write the console doesn't lay it out
con_html = "".join(memtree.html(image["ram"], list(range(OUT_BASE - ROM + w, OUT_BASE - ROM + OUT_SIZE, WB)), WOFF, prefix=f"k{w}") for w in range(WB))
# no ROM leaves: instructions come from the fetch table, and a data read below RAM gives 0 (a read port's leaf name --rom
# names nothing). ~6,000 leaves cost ~8 ms a frame, which the readback scan (one column per frame) and every pass pay
rom_html = ''
console = "" if 'nocon' in ABL else "\n".join(f'<div class="oc oc{i}"><b></b></div>' for i in range(OUT_SIZE))
RUNX = lambda n, e: f"({e}) * var(--run)" if UI and n not in ('k', 'par', 'tprev') else e     # Edit (run = 0) zeroes the registers
subj = "".join(f'<div class="reg" style="height: {H}px"><div class="sub" style="view-timeline-name: --{n}; top: calc(({RUNX(n, e)} + {OFF}) * 1px)"></div></div>' for n, H, OFF, e in regs if e)
if UI: subj += ('<div class="rp" style="width: anchor-size(--ccdone width, 0px)"><div class="reg" style="height: 2px">'
                '<div class="sub" style="view-timeline-name: --ccok; top: calc(min(1, round(100cqi / 1px)) * 1px)"></div></div></div>')
subj += "".join(f'<div class="rp rp{i}"><div class="reg" style="height: {M20}px"><div class="sub" style="view-timeline-name: --mv{i}; top: calc(100cqi - {WOFF - M20 // 2}px)"></div></div></div>' for i in range(2 * WB))
if 'dupsubs' in ABL: subj += subj.replace('view-timeline-name: --', 'view-timeline-name: --dup')
chain = f'<div class="ex"><div class="regs" aria-hidden="true">{subj}</div></div>'
for _ in range(K): chain = f'<i class="f"><i class="x"><i class="c">{chain}</i></i></i>'
blurb = (f"<p>No font: style alone runs the bytecode. Each layout pass runs up to {K} instructions as a chain of nested elements "
         f"(fetch and decode, execute, commit) out of a 2-way, 32-line cache of RAM held in custom properties. The first cache "
         f"miss stops the chain; the next pass fills the line, and prefetches the next, through anchor-size() read ports.</p>"
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
    {mem_html}{rom_html}<div class="cons">{con_html}<div class="con"></div>
    {console}</div>
    <div id="clk"><div id="cpu">
    <div class="head"{' hidden' if 'nohead' in ABL else ''}>
    <h1>JavaScript on a pure-CSS CPU</h1>
    {blurb}
    <div class="status">steps <b class="num" style="--v: var(--steps)"></b> pc <b class="num" style="--v: var(--pc)"></b> sp <b class="num" style="--v: var(--sp)"></b>
     halt <b class="num" style="--v: var(--halt)"></b></div>
    </div>
    <div class="nlatch"><div class="nslot"><iframe class="modem" loading="lazy" src="/net/m0.html#t" title="network modem" aria-hidden="true"></iframe></div></div>
    <div class="fl">{chain}</div>
    </div></div>
    </html>
    """
else:
    ui_props = uipage.props(WOFF) + [f'#run:not(:checked) ~ #clkw .cons .cell {{ content-visibility: visible; width: {WOFF}px; }}',
                                     '.cons .oc { display: if(style(--ccgo: 1): block; else: none); }']
    notes = (f"<p>Everything below the editor happens in CSS. When you press Run, a font reads your text back (a variable axis makes HarfBuzz "
             f"copy the code of one column into an invisible glyph's width, and a scan sweeps the columns, one per frame). Then the compiler, a "
             f"stylesheet, runs over those characters: a lexer on a chain of one element per character, then a parser on a chain of one element "
             f"per token, each parser rule picked by a container query. Every bytecode word it emits is an element named after its RAM cell. Then "
             f"the CPU, also a stylesheet, runs the program: each layout pass executes up to {K} instructions as a chain of nested elements, out of a "
             f"cache of RAM held in custom properties. Output appears in the console on the left.</p>"
             f"<p>The language is a small JavaScript subset: <code>var</code>, <code>function</code>, <code>if</code>/<code>else</code>, "
             f"<code>while</code>, <code>for</code>, <code>switch</code>, <code>return</code>, integer arithmetic, strings, arrays, objects, "
             f"<code>console.log(x)</code> and <code>putc(c)</code>. Up to {UIL} lines of {UIP} columns (the faint line marks the edge); "
             f"paste as plain text. Run scans the editor once (about a second), then compiles; Edit clears the machine.</p>")
    page = f"""<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
<meta charset="utf-8"/>
<title>JavaScript in CSS</title>
<style><![CDATA[
{lbl.header('js-minus-js/machine/gen_css.py (page, CPU, RAM), compiler/ccpage5.py (compiler), readback/ui_rb.py (editor scan)', 'js-minus-js/docs/ARCHITECTURE.md')}
{static}
{uipage.static(COLS, ROWS, UIL, UIP, WOFF)}
{chr(10).join(props)}
{chr(10).join(ui_props)}
{chr(10).join(css)}
{lbl.section('Editor scan', 'a font reads the editor back one column per frame and latches each character into a register')}
{ui_rb.css(UIL, UIP, 8)}
{lbl.section('Compiler', 'the lexer on a chain of one element per character, the parser on a chain of one element per token')}
{ui_css}
]]></style>
</head>
<body>
<input type="checkbox" id="run" class="runcb" aria-label="Run"/>
{mem_html}{rom_html}{ui_chain}<div class="cst"><div class="cstv"></div></div><div class="cst2"><b>more than {UIT} tokens</b></div>
<main id="app">
<div class="width-reader"></div>{ui_rb.regs_html()}
<header><h1>JavaScript, compiled and run by a stylesheet</h1>
<p class="lede">Type a program and press Run. No JavaScript runs on this page.</p></header>
<section class="pane">
<div class="bar"><span class="label" id="in-label">Program</span><label class="runbtn" for="run"><span></span></label><span class="scanpos"></span></div>
<div class="frame"><div id="ed" contenteditable="true" spellcheck="false" autocapitalize="off" autocorrect="off" role="textbox" aria-multiline="true" aria-labelledby="in-label">{ui_rb.editor_html(image.get('source', ''))}</div></div>
<div class="rbout"></div>
<p class="limit">Lines past {UIL} are not read.</p>
<p class="nested">Chrome nested some lines inside another, so they show and run as one line. Undo (Ctrl+Z), then press Enter or paste at the start of the next line instead.</p>
</section>
<section class="notes">{notes}</section>
{ui_rb.probes_html(UIL, UIP, 8)}
</main>
<div id="clkw">
<div class="cons">{con_html}<div class="con"></div>
{console}</div>
<div id="clk"><div id="cpu">
<div class="head">
<div class="status"><span>steps <b class="num" style="--v: var(--steps)"></b></span><span>pc <b class="num" style="--v: var(--pc)"></b> sp <b class="num" style="--v: var(--sp)"></b></span></div>
</div>
<div class="nlatch"><div class="nslot"><iframe class="modem" loading="lazy" src="/net/m0.html#t" title="network modem" aria-hidden="true"></iframe></div></div>
<div class="fl">{chain}</div>
</div></div></div>
</body>
</html>
"""
import re, collections
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
_dup = [n for n, c in collections.Counter(re.findall(r'@property (--[\w-]+)', page)).items() if c > 1]
assert not _dup, f'properties registered twice (memtree.py, the compile chain and the scan have their own): {_dup}'
if UI: lbl.check(page, outp)
open(outp, 'w').write(page)
print(outp, len(page), 'bytes; K', K, 'ISSUE', ISSUE, '; registers', len(regs), '; properties', len(P))
