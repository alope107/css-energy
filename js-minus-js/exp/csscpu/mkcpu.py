#!/usr/bin/env python3
"""mkcpu.py prog.js L out.xhtml — a pure-CSS CPU toy: L instructions of the real ISA executed by style alone, one
instruction per pair of nested display: contents elements, no layout. Measures what an instruction costs in style.

State: PC, SP, FP and a fully associative cache of 16 lines x 4 words (tags fixed: the lines the run touches are
preloaded, so nothing misses). Each instruction:
  .f (fetch)    mem[pc] -> op, imm; speculative reads of mem[sp-1], mem[sp-2]
  .x (execute)  @container style(--op: k) picks the op's addresses and results; up to two more reads; one write;
                every cache word and register redeclared under the other parity's name (A <-> B)
A read: 16 tag compares, the line's 4 words, the word. The page starts the program after the lib's startup (globals
copied) at code_base; the root's inline style holds the start state, so a harness can change it and time the recalc.
Writes build/... files next to OUT: OUT.json with the expected final state (a Python stepper of the same ops)."""
import sys, os, json
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.join(ROOT, 'compiler'), os.path.join(ROOT, 'machine')]
import cc_ref as R
from uarch import OPN
OP = {n: i for i, n in enumerate(OPN)}

src, L, out = open(sys.argv[1]).read(), int(sys.argv[2]), sys.argv[3]
COMMIT = os.environ.get('MODE', 'commit') == 'commit'   # parity: every word redeclared each instruction (A <-> B)
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
LA = R.LAYOUT; AMASK = 32767; M20 = 1 << 20
c = R.Compiler(LA['data_base'], LA['code_base'], lib); words, data = c.compile(src)
assert not c.err, c.err
mem = dict(R.image_mem(c, words, data, lib['init']))
init = lib['init']
for i in range(mem.get(init - 1, 0) + 1): mem[LA['data_base'] + i] = mem.get(init + i, 0)   # what the lib's __init leaves

def s20(x): return (x + (1 << 19)) % M20 - (1 << 19)
def tdiv(a, b): return 0 if b == 0 else int(a / b)
def tmod(a, b): return 0 if b == 0 else a - b * int(a / b)
BIN = {'ADD': lambda a, b: s20(a + b), 'SUB': lambda a, b: s20(a - b), 'MUL': lambda a, b: s20(a * b), 'DIV': tdiv, 'MOD': tmod,
       'LT': lambda a, b: int(a < b), 'GT': lambda a, b: int(a > b), 'LE': lambda a, b: int(a <= b), 'GE': lambda a, b: int(a >= b),
       'EQ': lambda a, b: int(a == b), 'NE': lambda a, b: int(a != b), 'AND': lambda a, b: int(a != 0 and b != 0), 'OR': lambda a, b: int(a != 0 or b != 0)}

def step(st, m, touched):
    """one instruction of cc_ref.run's semantics (the ops this toy implements); m: dict memory"""
    pc, sp, fp = st
    rd = lambda a: (touched.add(a // 4), m.get(a, 0))[1]
    def wr(a, v): touched.add(a // 4); m[a] = v
    w = rd(pc); op, imm = OPN[w // 8192], w % 8192; simm = imm - 8192 if imm >= 4096 else imm; pc += 1
    if op == 'NOP': pass
    elif op == 'PUSHI': wr(sp, imm); sp += 1
    elif op == 'LOADG': wr(sp, rd(imm)); sp += 1
    elif op == 'STOREG': sp -= 1; wr(imm, rd(sp))
    elif op == 'LOADL': wr(sp, rd(fp + simm)); sp += 1
    elif op == 'STOREL': sp -= 1; wr(fp + simm, rd(sp))
    elif op == 'LOADI': wr(sp - 1, rd(rd(sp - 1) & AMASK))
    elif op == 'STOREI': b = rd(sp - 1); a = rd(sp - 2); sp -= 2; wr(a & AMASK, b)
    elif op in BIN: b = rd(sp - 1); a = rd(sp - 2); sp -= 1; wr(sp - 1, BIN[op](a, b))
    elif op == 'NOT': wr(sp - 1, int(rd(sp - 1) == 0))
    elif op == 'NEG': wr(sp - 1, s20(-rd(sp - 1)))
    elif op == 'JMP': pc = imm
    elif op == 'JZ': sp -= 1; pc = imm if rd(sp) == 0 else pc
    elif op == 'JNZ': sp -= 1; pc = imm if rd(sp) != 0 else pc
    elif op == 'CALL': wr(sp, pc); sp += 1; pc = imm
    elif op == 'ENTER': wr(sp, fp); fp = sp; sp = sp + 1 + imm
    elif op == 'RET': v = rd(sp - 1); ofp = rd(fp); ret = rd(fp - 1); nsp = fp - 1 - imm; wr(nsp, v); sp = nsp + 1; fp = ofp; pc = ret
    elif op == 'POP': sp -= 1
    elif op == 'DUP': wr(sp, rd(sp - 1)); sp += 1
    elif op == 'HALT': pc -= 1
    elif op == 'SHL13': wr(sp - 1, s20(rd(sp - 1) * 8192))
    elif op == 'INCG': wr(imm, s20(rd(imm) + 1))
    elif op == 'INCL': wr(fp + simm, s20(rd(fp + simm) + 1))
    elif op == 'IDX': wr(sp - 1, rd((rd(imm) + rd(sp - 1)) & AMASK))
    elif op == 'IDXL': wr(sp - 1, rd((rd(fp + simm) + rd(sp - 1)) & AMASK))
    else: raise SystemExit(f'op {op} not in the toy')
    return (pc, sp, fp)

# the run: L instructions from code_base; the lines it touches are the cache's preloaded lines
start = (LA['code_base'], LA['sp0'], LA['sp0'])
m = dict(mem); st = start; touched = set()
for _ in range(L): st = step(st, m, touched)
lines = sorted(touched); assert len(lines) <= 16, f'{len(lines)} lines touched'
DIRECT = os.environ.get('MAP', 'assoc') == 'direct'
if DIRECT:   # li = (blk * HA + floor(blk / 16) * HC) mod 16, collision-free over this run's lines (a toy's shortcut)
    hsh = lambda b, a, c, e: (b * a + b // 16 * c + b // 256 * e) % 16
    HA, HC, HE = next(((a, c, e) for a in range(1, 16, 2) for c in range(16) for e in range(16) if len({hsh(b, a, c, e) for b in lines}) == len(lines)), (None,) * 3)
    assert HA is not None, f'no collision-free hash for blocks {lines}'
    slot = {hsh(b, HA, HC, HE): b for b in lines}
    lines = [slot.get(k, 2000 + k) for k in range(16)]                     # line k holds the block hashing to k
else:
    lines += [b for b in range(1, 1000) if b not in touched][:16 - len(lines)]      # unused lines: other tags
TWEAK = 1548        # the code word PUSHI 3 of s = s + 3: trials change its immediate, so every state after it changes
assert mem[TWEAK] == 8192 + 3, 'loop.js layout changed'
def endstate(v):
    """the state after L instructions with the loop's increment v (None: as compiled)"""
    mm = dict(mem)
    if v is not None: mm[TWEAK] = 8192 + v
    st = start; t = set()
    for _ in range(L): st = step(st, mm, t)
    return {'pc': st[0], 'sp': st[1], 'fp': st[2], 'mem': {str(4 * b + w): mm.get(4 * b + w, 0) for b in sorted(touched) for w in range(4)}}
TRIALS = list(range(4, 29))         # increments the harness sets, one recalc each
json.dump({**endstate(None), 'tweak': TWEAK, 'trials': [[v, endstate(v)] for v in TRIALS]}, open(out + '.json', 'w'))

# ---------------- CSS
K = 16
def eq(x, y): return f"calc(1 - min(1, max(({x}) - ({y}), ({y}) - ({x}))))"
props = ["pc", "sp", "fp"] + [f"w{k}_{w}" for k in range(K) for w in range(4)]
regs = lambda P: {n: f"--{n}{P}" for n in props}
tmp = (["slot", "op", "imm", "simm", "s1", "s2", "ra", "rb", "Ra", "Rb", "we", "wa", "wv", "npc", "nsp", "nfp", "wo"] +
       [f"{r}{x}" for r in ("hf", "hs1", "hs2", "hra", "hrb", "hw") for x in range(K)] + [f"{r}{n}" for r in "boigm" for n in ("f", "s1", "s2", "ra", "rb")] +
       [f"{r}{w}" for r in ("lf", "ls1", "ls2", "lra", "lrb", "eo") for w in range(4)] + ["vf", "fw"])
css = [f'@property --{n}{P} {{ syntax: "<integer>"; inherits: true; initial-value: 0; }}' for n in props for P in "AB"]
css += [f'@property --{n} {{ syntax: "<integer>"; inherits: true; initial-value: 0; }}' for n in tmp]
css += [f'@property --t{k} {{ syntax: "<integer>"; inherits: true; initial-value: 0; }}' for k in range(K)]   # tags (fixed)

ABL = os.environ.get('ABL', '').split(',')   # timing ablations (results wrong): noreads, nodisp, empty
def read(name, addr, P):
    """declarations reading the cache word at addr (an expression) into --{name}; P: the parity being read"""
    if 'noreads' in ABL and name != 'f': return [f"--{ {'ra': 'Ra', 'rb': 'Rb'}.get(name, name)}: 0;"]
    d = [f"--b{name}: round(down, ({addr}) / 4);", f"--o{name}: mod({addr}, 4);"]   # the block and word, once
    blk = f"var(--b{name})"
    if DIRECT:
        d += [f"--i{name}: mod(calc(var(--b{name}) * {HA} + round(down, var(--b{name}) / 16) * {HC} + round(down, var(--b{name}) / 256) * {HE}), 16);"]
        d += [f"--l{name}{w}: if(" + " ".join(f"style(--i{name}: {k}): var(--w{k}_{w}{P});" for k in range(1, K)) + f" else: var(--w0_{w}{P}));" for w in range(4)]
        d += [f"--g{name}: if(" + " ".join(f"style(--i{name}: {k}): var(--t{k});" for k in range(1, K)) + " else: var(--t0));",
              f"--m{name}: calc(1 - {eq(f'var(--g{name})', blk)});"]   # a miss (never, in the toy)
        d.append(f"--{ {'ra': 'Ra', 'rb': 'Rb'}.get(name, name)}: if(style(--o{name}: 1): var(--l{name}1); style(--o{name}: 2): var(--l{name}2); style(--o{name}: 3): var(--l{name}3); else: var(--l{name}0));")
        return d
    d += [f"--h{name}{k}: {eq(f'var(--t{k})', blk)};" for k in range(K)] if 'notag' not in ABL else [f"--h{name}{k}: {int(k == 0)};" for k in range(K)]
    d += ([f"--l{name}{w}: calc(" + " + ".join(f"var(--h{name}{k}) * var(--w{k}_{w}{P})" for k in range(K)) + ");" for w in range(4)]
          if 'nosum' not in ABL else [f"--l{name}{w}: calc(var(--h{name}0) * var(--w0_{w}{P}));" for w in range(4)])
    d.append(f"--{ {'ra': 'Ra', 'rb': 'Rb'}.get(name, name)}: calc(" + " + ".join(f"{eq(f'var(--o{name})', w)} * var(--l{name}{w})" for w in range(4)) + ");")
    return d

for P, Q in ((("", ""),) if COMMIT else (("A", "B"), ("B", "A"))):
    v = lambda n: f"var(--{n}{P})"
    # fetch
    f = read("f", v("pc"), P)
    f[-1] = f[-1].replace("--f:", "--fw:")
    f += ["--op: round(down, var(--fw) / 8192);", "--imm: mod(var(--fw), 8192);", "--simm: calc(var(--imm) - 8192 * min(1, round(down, var(--imm) / 4096)));"]
    if os.environ.get('LAZY', '1') != '1': f += read("s1", f"{v('sp')} - 1", P) + read("s2", f"{v('sp')} - 2", P)
    css.append(f".f.p{P} {{ " + " ".join(f) + " }")
    # execute: defaults, then per-op rules (later in the sheet, so they win)
    x = ["--ra: 0;", "--rb: 0;", "--we: 0;", "--wa: 0;", "--wv: 0;", f"--npc: calc({v('pc')} + 1);", f"--nsp: {v('sp')};", f"--nfp: {v('fp')};"]
    LAZY = os.environ.get('LAZY', '1') == '1'   # Ra / Rb read inside the rules of the ops that need them
    if not LAZY: x += read("ra", "var(--ra)", P) + read("rb", "var(--rb)", P)
    # the write: line hits and word, then every word under the other parity
    x += ["--wo: mod(var(--wa), 4);"] + [f"--eo{w}: {eq('var(--wo)', w)};" for w in range(4)]
    x += [f"--hw{k}: calc(var(--we) * {eq(f'var(--t{k})', 'round(down, var(--wa) / 4)')});" for k in range(K)]
    if COMMIT and DIRECT:
        x[x.index(next(e for e in x if e.startswith("--hw0:"))):] = []
        x.append(f"--slot: calc(var(--we) * (1 + 4 * mod(calc(round(down, var(--wa) / 4) * {HA} + round(down, var(--wa) / 64) * {HC} + round(down, var(--wa) / 1024) * {HE}), 16) + var(--wo)));")
    elif COMMIT:   # the slot (1 + 4 * line + word) the write lands in, 0 for none: .c below declares that one word
        x.append("--slot: calc(" + " + ".join(f"var(--hw{k}) * {4 * k + 1}" for k in range(K)) + " + var(--we) * var(--wo));")
    else:
        x += [f"--w{k}_{w}{Q}: calc(var(--w{k}_{w}{P}) + var(--hw{k}) * var(--eo{w}) * (var(--wv) - var(--w{k}_{w}{P})));" for k in range(K) for w in range(4)]
        x += [f"--pc{Q}: var(--npc);", f"--sp{Q}: var(--nsp);", f"--fp{Q}: var(--nfp);"]
    css.append(f".x.p{P} {{ " + " ".join(x) + " }")
    sp, fp, pc = v("sp"), v("fp"), v("pc")
    s20 = lambda e: f"calc(mod({e} + {1 << 19}, {M20}) - {1 << 19})"
    W = lambda a, val: f"--we: 1; --wa: {a}; --wv: {val};"
    B = {'ADD': s20("var(--s2) + var(--s1)"), 'SUB': s20("var(--s2) - var(--s1)"), 'MUL': s20("var(--s2) * var(--s1)"),
         'DIV': f"calc((1 - {eq('var(--s1)', 0)}) * round(to-zero, var(--s2) / (var(--s1) + {eq('var(--s1)', 0)})))",
         'MOD': f"calc((1 - {eq('var(--s1)', 0)}) * (var(--s2) - var(--s1) * round(to-zero, var(--s2) / (var(--s1) + {eq('var(--s1)', 0)}))))",
         'LT': "clamp(0, var(--s1) - var(--s2), 1)", 'GT': "clamp(0, var(--s2) - var(--s1), 1)",
         'LE': "clamp(0, var(--s1) - var(--s2) + 1, 1)", 'GE': "clamp(0, var(--s2) - var(--s1) + 1, 1)",
         'EQ': eq("var(--s1)", "var(--s2)"), 'NE': f"calc(1 - {eq('var(--s1)', 'var(--s2)')})",
         'AND': f"calc((1 - {eq('var(--s1)', 0)}) * (1 - {eq('var(--s2)', 0)}))", 'OR': f"min(1, calc((1 - {eq('var(--s1)', 0)}) + (1 - {eq('var(--s2)', 0)})))"}
    rules = {'NOP': "",
             'PUSHI': W(sp, "var(--imm)") + f" --nsp: calc({sp} + 1);",
             'LOADG': "--ra: var(--imm); " + W(sp, "var(--Ra)") + f" --nsp: calc({sp} + 1);",
             'STOREG': W("var(--imm)", "var(--s1)") + f" --nsp: calc({sp} - 1);",
             'LOADL': f"--ra: calc({fp} + var(--simm)); " + W(sp, "var(--Ra)") + f" --nsp: calc({sp} + 1);",
             'STOREL': W(f"calc({fp} + var(--simm))", "var(--s1)") + f" --nsp: calc({sp} - 1);",
             'LOADI': "--ra: mod(var(--s1), 32768); " + W(f"calc({sp} - 1)", "var(--Ra)"),
             'STOREI': W("mod(var(--s2), 32768)", "var(--s1)") + f" --nsp: calc({sp} - 2);",
             'NOT': W(f"calc({sp} - 1)", eq("var(--s1)", 0)), 'NEG': W(f"calc({sp} - 1)", s20("-1 * var(--s1)")),
             'JMP': "--npc: var(--imm);",
             'JZ': f"--nsp: calc({sp} - 1); --npc: calc({eq('var(--s1)', 0)} * var(--imm) + (1 - {eq('var(--s1)', 0)}) * ({pc} + 1));",
             'JNZ': f"--nsp: calc({sp} - 1); --npc: calc((1 - {eq('var(--s1)', 0)}) * var(--imm) + {eq('var(--s1)', 0)} * ({pc} + 1));",
             'CALL': W(sp, f"calc({pc} + 1)") + f" --nsp: calc({sp} + 1); --npc: var(--imm);",
             'ENTER': W(sp, fp) + f" --nfp: {sp}; --nsp: calc({sp} + 1 + var(--imm));",
             'RET': f"--ra: {fp}; --rb: calc({fp} - 1); " + W(f"calc({fp} - 1 - var(--imm))", "var(--s1)") +
                    f" --nsp: calc({fp} - var(--imm)); --nfp: var(--Ra); --npc: var(--Rb);",
             'POP': f"--nsp: calc({sp} - 1);", 'DUP': W(sp, "var(--s1)") + f" --nsp: calc({sp} + 1);",
             'HALT': f"--npc: {pc};", 'SHL13': W(f"calc({sp} - 1)", s20("var(--s1) * 8192")),
             'INCG': "--ra: var(--imm); " + W("var(--imm)", s20("var(--Ra) + 1")),
             'INCL': f"--ra: calc({fp} + var(--simm)); " + W(f"calc({fp} + var(--simm))", s20("var(--Ra) + 1")),
             'IDX': "--ra: var(--imm); --rb: mod(var(--Ra) + var(--s1), 32768); " + W(f"calc({sp} - 1)", "var(--Rb)"),
             'IDXL': f"--ra: calc({fp} + var(--simm)); --rb: mod(var(--Ra) + var(--s1), 32768); " + W(f"calc({sp} - 1)", "var(--Rb)")}
    for op, e in B.items(): rules[op] = W(f"calc({sp} - 2)", e) + f" --nsp: calc({sp} - 1);"
    for op, d in rules.items():
        if d and LAZY:
            if '--s1' in d: d += " " + " ".join(read("s1", f"{v('sp')} - 1", P))     # the stack words too, where used
            if '--s2' in d: d += " " + " ".join(read("s2", f"{v('sp')} - 2", P))
            if '--Ra' in d or '--ra' in d: d += " " + " ".join(read("ra", "var(--ra)", P))
            if '--Rb' in d or '--rb' in d: d += " " + " ".join(read("rb", "var(--rb)", P))
        if d and 'nodisp' not in ABL: css.append(f"@container style(--op: {OP[op]}) {{ .x.p{P} {{ {d} }} }}")
if COMMIT:
    css.append(".c { --pc: var(--npc); --sp: var(--nsp); --fp: var(--nfp); }")
    css += [f"@container style(--slot: {4 * k + w + 1}) {{ .c {{ --w{k}_{w}: var(--wv); }} }}" for k in range(K) for w in range(4)]
if 'empty' in ABL: css = [c for c in css if c.startswith('@property')] + [".c { --pc: calc(var(--pc) + 0); }", ".f { --sp: calc(var(--fp) + 1); } .x { --fp: calc(var(--sp) + 1); }"]
css.append(".f, .x, .c { display: contents; }")

PA = "" if COMMIT else "A"
init_style = "; ".join([f"--pc{PA}: {start[0]}", f"--sp{PA}: {start[1]}", f"--fp{PA}: {start[2]}"] +
                       [f"--t{k}: {b}" for k, b in enumerate(lines)] +
                       [f"--w{k}_{w}{PA}: {mem.get(4 * b + w, 0)}" for k, b in enumerate(lines) for w in range(4)])
body = '<i class="end"></i>'
for j in range(L - 1, -1, -1):
    P = "" if COMMIT else "AB"[j % 2]
    body = (f'<i class="f p{P}"><i class="x p{P}"><i class="c">{body}</i></i></i>' if COMMIT else f'<i class="f p{P}"><i class="x p{P}">{body}</i></i>')
html = (f'<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/><title>CSS CPU toy</title><style><![CDATA[\n'
        + "\n".join(css) + f'\n]]></style></head><body><div id="root" style="{init_style}">{body}</div></body></html>')
open(out, 'w').write(html)
print(out, len(html), 'bytes;', L, 'instructions; final pc', st[0], 'sp', st[1], '; parity', "AB"[L % 2])
