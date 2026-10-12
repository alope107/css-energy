#!/usr/bin/env python3
"""gen_vm.py image.json out.html [--issue=K] — the CSS stack VM.

Word = op * 8192 + imm. ROM = the compiler, one if() branch per word. RAM = leaves whose remembered width
is the word (+ WOFF): a write makes the addressed leaf visible with width = data until the next write on
that channel, so its remembered size updates at the end of the frame. Reads are anchor-size() ports on
nested position:fixed readers; a port's address may depend on an outer port's value (LOADI, IDX). The
machine executes K instructions per frame (one per layout pass, K write channels), because remembered
sizes only update once per frame while timeline registers update every pass.
"""
import json, sys
import memtree

image = json.load(open(sys.argv[1]))
ROM, RAMN, WOFF = 4096, image["ramSize"], 1 << 20
OUT_BASE, ROWS, COLS = image["outBase"], image["rows"], image["cols"]
OUT_SIZE = ROWS * COLS
K = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--issue=")), 2))
CH = "ABCD"[:2 * K]                      # write channels: K per frame, alternating between two sets by frame parity

def eq(x, c): return f"(1 - min(1, max({x} - {c}, {c} - {x})))"
def prop(name, init=0): return f'@property --{name} {{ syntax: "<integer>"; inherits: true; initial-value: {init}; }}'

# registers: (name, H, OFF); value range is [-OFF, H-OFF)
regs = [("pcx", 8192, 0), ("pcf", 8192, 0), ("ir", 1 << 19, 0), ("valid", 2, 0), ("sp", 8192, 0), ("fp", 8192, 0),
        ("optr", 256, 0), ("k", 16, 0), ("par", 2, 0), ("tprev", 65536, 0), ("steps", 1 << 20, 0)]
regs += [(f"wa{c}", RAMN + 1, 0) for c in CH] + [(f"wd{c}", 1 << 21, 1 << 20) for c in CH]
OPS = {"PUSHI": 1, "LOADG": 2, "STOREG": 3, "LOADL": 4, "STOREL": 5, "LOADI": 6, "STOREI": 7, "NOT": 21, "NEG": 22, "JMP": 23,
       "JZ": 24, "JNZ": 25, "CALL": 26, "ENTER": 27, "RET": 28, "POP": 29, "DUP": 30, "PUTC": 31, "HALT": 32, "JMPI": 33,
       "SHL": 34, "INCG": 35, "INCL": 36, "IDX": 37, "IDXL": 38}

props = [prop(n) for n, _, _ in regs] + [prop(f"next-{n}") for n, _, _ in regs]
props += [prop(x) for x in ["t", "fresh", "go", "chan", "rom", "op", "imm", "simm", "isBIN", "a0", "a1", "a2", "a3", "a4",
                             "m0", "m1", "m2", "m3", "m4", "irF", "ex", "z", "nl", "bsafe", "dv", "bres", "ures", "pv", "doPush",
                             "doTop", "doWrite", "waddr", "wval", "W", "jump", "stall", "T", "spN", "fpN", "optrN", "first", "code"]]
props += [prop(f"is{k}") for k in OPS] + [prop(f"b{j}") for j in range(8, 21)]
for p in ["a0", "a1", "a2", "a3", "a4", "pcf"]:
    props += [prop(f"{p}h"), prop(f"{p}l")]

def clampA(expr): return f"min({RAMN - 1}, max(0, {expr} - {ROM}))"
hilo = lambda p: [f"--{p}h: calc(round(down, var(--{p}) / 64));", f"--{p}l: calc(var(--{p}) - 64 * var(--{p}h));"]

# ---------------- on #cpu: frame gate, decode, port addresses that only need registers
dec = ["--fresh: calc(min(1, max(var(--t) - var(--tprev), var(--tprev) - var(--t))));",
       f"--go: calc(min(1, var(--fresh) + min(1, max(0, {K} - var(--k)))));",
       "--chan: calc(" + str(K) + " * var(--par) + (1 - var(--fresh)) * var(--k));",
       "--op: calc(round(down, var(--ir) / 8192));",
       "--imm: calc(var(--ir) - var(--op) * 8192);",
       "--simm: calc(var(--imm) - 8192 * min(1, max(0, var(--imm) - 4095)));",
       "--isBIN: calc(min(1, max(0, var(--op) - 7)) * min(1, max(0, 21 - var(--op))));"]
dec += [f"--is{k}: calc({eq('var(--op)', v)});" for k, v in OPS.items()]
dec += [f"--a0: calc({clampA('var(--pcf)')});",                       # fetch (RAM part of the address space)
        f"--a1: calc({clampA('var(--sp) - 1')});",                    # top of stack
        f"--a2: calc({clampA('var(--sp) - 2')});"]                    # second
dec += hilo("a0") + hilo("a1") + hilo("a2") + hilo("pcf")
# port 3 (needs m1 for LOADI): LOADL/STOREL fp+n, LOADG/INCG a, INCL fp+n, RET fp, IDX a, IDXL fp+n, LOADI [top]
v0 = [f"--m0: calc(100cqi / 1px - {WOFF});", f"--m1: calc(100cqb / 1px - {WOFF});",
      "--a3: calc(" + clampA("(var(--isLOADL) + var(--isINCL) + var(--isIDXL)) * (var(--fp) + var(--simm)) + (var(--isLOADG) + var(--isINCG) + var(--isIDX)) * var(--imm)"
                            " + var(--isRET) * var(--fp) + var(--isLOADI) * var(--m1)") + ");"] + hilo("a3")
# port 4 (needs m3 for IDX): RET fp-1, IDX/IDXL base + index
v1 = [f"--m2: calc(100cqi / 1px - {WOFF});", f"--m3: calc(100cqb / 1px - {WOFF});",
      "--a4: calc(" + clampA("var(--isRET) * (var(--fp) - 1) + (var(--isIDX) + var(--isIDXL)) * (var(--m3) + var(--m1))") + ");"] + hilo("a4")
v2 = [f"--m4: calc(100cqi / 1px - {WOFF});"]

# ---------------- execute (on .v2)
ex = [
    f"--irF: calc(min(1, max(0, {ROM} - var(--pcf))) * var(--rom) + min(1, max(0, var(--pcf) - {ROM - 1})) * var(--m0));",
    "--ex: calc(var(--go) * var(--valid));",
    f"--z: calc({eq('var(--m1)', 0)});",
    f"--nl: calc({eq('var(--m1)', 10)});",
    f"--bsafe: calc(var(--m1) + {eq('var(--m1)', 0)});",
    "--dv: calc(round(to-zero, var(--m2) / var(--bsafe)));",
    # binary ops: a = m2 (below top), b = m1 (top)
    "--b8: calc(var(--m2) + var(--m1));",
    "--b9: calc(var(--m2) - var(--m1));",
    "--b10: calc(var(--m2) * var(--m1));",
    "--b11: var(--dv);",
    "--b12: calc(var(--m2) - var(--dv) * var(--m1));",
    "--b13: calc(min(1, max(0, var(--m1) - var(--m2))));",
    "--b14: calc(min(1, max(0, var(--m2) - var(--m1))));",
    "--b15: calc(1 - var(--b14));",
    "--b16: calc(1 - var(--b13));",
    f"--b17: calc({eq('var(--m2)', 'var(--m1)')});",
    "--b18: calc(1 - var(--b17));",
    "--b19: calc(min(1, max(var(--m2), -1 * var(--m2))) * min(1, max(var(--m1), -1 * var(--m1))));",
    "--b20: calc(min(1, max(var(--m2), -1 * var(--m2)) + max(var(--m1), -1 * var(--m1))));",
    "--bres: calc(" + " + ".join(f"{eq('var(--op)', j)} * var(--b{j})" for j in range(8, 21)) + ");",
    # ops that replace the top of the stack
    "--doTop: calc(var(--isNOT) + var(--isNEG) + var(--isSHL) + var(--isLOADI) + var(--isIDX) + var(--isIDXL));",
    "--ures: calc(var(--isNOT) * var(--z) + var(--isNEG) * (0 - var(--m1)) + var(--isSHL) * var(--m1) * 8192 + var(--isLOADI) * var(--m3) + (var(--isIDX) + var(--isIDXL)) * var(--m4));",
    # pushes
    "--doPush: calc(var(--isPUSHI) + var(--isLOADG) + var(--isLOADL) + var(--isDUP) + var(--isCALL) + var(--isENTER));",
    "--pv: calc(var(--isPUSHI) * var(--imm) + (var(--isLOADG) + var(--isLOADL)) * var(--m3) + var(--isDUP) * var(--m1) + var(--isCALL) * (var(--pcx) + 1) + var(--isENTER) * var(--fp));",
    # the memory write of this instruction, if any
    "--doWrite: calc(var(--doPush) + var(--isBIN) + var(--doTop) + var(--isSTOREG) + var(--isSTOREL) + var(--isSTOREI) + var(--isRET) + var(--isPUTC) * (1 - var(--nl)) + var(--isINCG) + var(--isINCL));",
    "--waddr: calc(var(--doPush) * var(--sp) + var(--isBIN) * (var(--sp) - 2) + var(--doTop) * (var(--sp) - 1) + (var(--isSTOREG) + var(--isINCG)) * var(--imm)"
    " + (var(--isSTOREL) + var(--isINCL)) * (var(--fp) + var(--simm)) + var(--isSTOREI) * var(--m2) + var(--isRET) * (var(--fp) - 1 - var(--imm))"
    f" + var(--isPUTC) * (1 - var(--nl)) * ({OUT_BASE} + var(--optr)));",
    "--wval: calc(var(--doPush) * var(--pv) + var(--isBIN) * var(--bres) + var(--doTop) * var(--ures) + (var(--isSTOREG) + var(--isSTOREL) + var(--isSTOREI) + var(--isRET) + var(--isPUTC)) * var(--m1)"
    " + (var(--isINCG) + var(--isINCL)) * (var(--m3) + 1));",
    # control
    "--jump: calc(var(--isJMP) + var(--isJZ) * var(--z) + var(--isJNZ) * (1 - var(--z)) + var(--isCALL) + var(--isRET) + var(--isJMPI));",
    "--stall: var(--isHALT);",
    "--T: calc((var(--isJMP) + var(--isJZ) + var(--isJNZ) + var(--isCALL)) * var(--imm) + var(--isRET) * var(--m4) + var(--isJMPI) * var(--m1));",
    "--spN: calc(var(--sp) + var(--doPush) - var(--isBIN) - var(--isSTOREG) - var(--isSTOREL) - 2 * var(--isSTOREI) - var(--isPOP) - var(--isJZ) - var(--isJNZ) - var(--isPUTC) - var(--isJMPI)"
    " + var(--isENTER) * var(--imm) + var(--isRET) * (var(--fp) - var(--imm) - var(--sp)));",
    "--fpN: calc(var(--isENTER) * var(--sp) + var(--isRET) * var(--m3) + (1 - var(--isENTER) - var(--isRET)) * var(--fp));",
    f"--optrN: calc(var(--isPUTC) * mod(var(--nl) * (round(down, var(--optr) / {COLS}) + 1) * {COLS} + (1 - var(--nl)) * (var(--optr) + 1), {OUT_SIZE}) + (1 - var(--isPUTC)) * var(--optr));",
    # the registers start at 0; the very first pass loads sp and fp
    f"--first: calc({eq('var(--steps)', 0)} * {eq('var(--valid)', 0)} * {eq('var(--pcf)', 0)});",
]
g = "var(--go)"
def hold(name, expr): return f"--next-{name}: calc({g} * ({expr}) + (1 - {g}) * var(--{name}));"
sp0 = image["sp0"]
nx = [
    "--next-tprev: var(--t);",
    f"--next-k: calc(var(--fresh) + (1 - var(--fresh)) * min({K}, var(--k) + 1));",  # saturates: once the K issues are done nothing changes, so Blink stops re-running layout this frame,
    "--next-par: calc(var(--fresh) * (1 - var(--par)) + (1 - var(--fresh)) * var(--par));",
    hold("steps", "var(--steps) + var(--ex)"),
    hold("sp", f"var(--first) * {sp0} + (1 - var(--first)) * (var(--ex) * var(--spN) + (1 - var(--ex)) * var(--sp))"),
    hold("fp", f"var(--first) * {sp0} + (1 - var(--first)) * (var(--ex) * var(--fpN) + (1 - var(--ex)) * var(--fp))"),
    hold("optr", "var(--ex) * var(--optrN) + (1 - var(--ex)) * var(--optr)"),
    # pipeline: a stall keeps everything; a jump refetches at T with a bubble; otherwise advance
    hold("pcf", "var(--ex) * var(--stall) * var(--pcf) + var(--ex) * var(--jump) * (1 - var(--stall)) * var(--T) + (1 - var(--ex) * (var(--stall) + var(--jump))) * (var(--pcf) + 1)"),
    hold("pcx", "var(--ex) * (var(--stall) + var(--jump)) * var(--pcx) + (1 - var(--ex) * (var(--stall) + var(--jump))) * var(--pcf)"),
    hold("ir", "var(--ex) * (var(--stall) + var(--jump)) * var(--ir) + (1 - var(--ex) * (var(--stall) + var(--jump))) * var(--irF)"),
    hold("valid", "var(--ex) * var(--stall) * var(--valid) + (1 - var(--ex) * (var(--stall) + var(--jump)))"),
]
ex.append(f"--W: calc(var(--ex) * var(--doWrite) * (var(--waddr) - {ROM} + 1));")     # cell index + 1 written this pass, 0 if none
for i, c in enumerate(CH):                 # write channel of this pass; an older channel holding the same cell is released
    sel = f"var(--go) * {eq('var(--chan)', i)}"
    rel = f"min(1, var(--W)) * {eq('var(--W)', f'var(--wa{c})')}"
    nx.append(f"--next-wa{c}: calc({sel} * var(--W) + (1 - {sel}) * (1 - {rel}) * var(--wa{c}));")
    nx.append(f"--next-wd{c}: calc({sel} * var(--ex) * var(--doWrite) * var(--wval) + (1 - {sel}) * var(--wd{c}));")

# ---------------- muxes: one if() per port and for the ROM, nested hi/lo so the scan is 64 + 64 deep
def mux(p, n, leaf, default):
    outer = []
    for j in range((n + 63) // 64):
        inner = " ".join(f"style(--{p}l: {i}): {leaf(j * 64 + i)};" for i in range(64) if j * 64 + i < n)
        outer.append(f"style(--{p}h: {j}): if({inner} else: {default});")
    return f"if({' '.join(outer)} else: {default})"
rom = image["rom"]

WNAMES = [f"wa{c}" for c in CH] + [f"wd{c}" for c in CH]
names = ", ".join(f"--{n}" for n, _, _ in regs)
inner_names = ", ".join(f"--{n}" for n, _, _ in regs if n not in WNAMES)
anims = ", ".join(f"r-{n}" for n, _, _ in regs)
# wall clock on #clk (around #cpu only), so its per-frame change doesn't restyle the memory
css = ["#clk { animation: wc 100s linear infinite; }\n@keyframes wc { from { --t: 0; } to { --t: 60000; } }",     # 600 ticks/s, wraps
       "#cpu {\n  timeline-scope: " + inner_names + ";\n  animation-name: " + anims + ";\n  animation-timeline: " + names +
       ";\n  animation-duration: auto;\n  animation-timing-function: linear;\n  animation-fill-mode: both;\n  " + "\n  ".join(dec) + "\n}"]
css += [f"@keyframes r-{n} {{ from {{ --{n}: {H - OFF}; }} to {{ --{n}: {-1 - OFF}; }} }}" for n, H, OFF in regs]
css.append(".r0 > .v0 {\n  " + "\n  ".join(v0) + "\n}")
css.append(".r1 > .v1 {\n  " + "\n  ".join(v1) + "\n}")
css.append(".r2 > .v2 {\n  " + "\n  ".join(v2 + ex + nx) + "\n}")
css.append(".r2 > .v2 { --rom: " + mux("pcf", len(rom), lambda k: rom[k], 0) + "; }")
css.append(".r0 { --s0: " + mux("a0", RAMN, lambda k: f"--c{k}", "--c0") + "; --s1: " + mux("a1", RAMN, lambda k: f"--c{k}", "--c0") + "; }")
css.append(".r1 { --s2: " + mux("a2", RAMN, lambda k: f"--c{k}", "--c0") + "; --s3: " + mux("a3", RAMN, lambda k: f"--c{k}", "--c0") + "; }")
css.append(".r2 { --s4: " + mux("a4", RAMN, lambda k: f"--c{k}", "--c0") + "; }")
# writes: decode tree (memtree.py)
_mp, _mc = memtree.css(CH, {n: (H, OFF) for n, H, OFF in regs if n in WNAMES}, RAMN, WOFF)
_sp, _sc = memtree.shared()
_mp += _sp; _mc = [memtree.scope(WNAMES)] + _sc + _mc
css += _mc
# console: one fixed reader per output cell
for i in range(OUT_SIZE):
    r, c = divmod(i, COLS)
    css.append(f".oc{i} {{ width: anchor-size(--c{OUT_BASE - ROM + i} width); left: calc(24px + {c} * 11px); top: calc(24px + {r} * 20px); }}")
css.append('@counter-style ascii { system: fixed 32; symbols: ' + " ".join('"\\""' if c == 34 else '"\\\\"' if c == 92 else f'"{chr(c)}"' for c in range(32, 127)) + '; fallback: blank; }')
css.append('@counter-style blank { system: cyclic; symbols: " "; }')

static = f"""
  body {{ font: 15px/1.5 system-ui, sans-serif; margin: 0; color: #222; background: #fff; }}
  h1 {{ font-size: 1.1rem; font-weight: 600; margin: 0 0 .3rem; }}
  .head {{ position: fixed; left: {COLS * 11 + 48}px; top: 16px; width: 34rem; }}
  .head p {{ margin: .3rem 0; color: #444; }}
  .head pre {{ font: 12px/1.35 ui-monospace, monospace; background: #f4f4f4; padding: .5rem .7rem; border-radius: 4px; margin: .4rem 0; }}
  .status {{ font-family: ui-monospace, monospace; color: #666; font-size: 13px; }} .status b {{ color: #222; margin-right: .8em; font-weight: 600; }}
  .num {{ counter-set: v var(--v); }} .num::after {{ content: counter(v); }}
  /* memory: a hidden leaf remembers its width; the fit-content wrapper is the anchor a port can read */
  .mem {{ height: 0; overflow: hidden; }}
  .w {{ width: fit-content; height: 1px; }}
  .cell {{ display: block; content-visibility: hidden; width: fit-content; height: 1px; contain-intrinsic-size: auto {WOFF}px; }}
  /* read ports */
  .rd {{ position: fixed; top: 0; left: 0; container-type: size; visibility: hidden; }}
  .r0 {{ width: anchor-size(var(--s0) width); height: anchor-size(var(--s1) width); }}
  .r1 {{ width: anchor-size(var(--s2) width); height: anchor-size(var(--s3) width); }}
  .r2 {{ width: anchor-size(var(--s4) width); height: 1px; }}
  .v2 {{ visibility: visible; }}
  /* console */
  .con {{ position: fixed; left: 16px; top: 16px; width: {COLS * 11 + 16}px; height: {ROWS * 20 + 16}px; background: #151515; border-radius: 6px; }}
  .oc {{ position: fixed; height: 20px; container-type: inline-size; visibility: hidden; font: 16px/20px ui-monospace, monospace; color: #eee; }}
  .oc > b {{ --code: calc(100cqi / 1px - {WOFF}); counter-set: ch var(--code); font-weight: 400; visibility: visible; display: inline-block; width: 11px; }}
  .oc > b::after {{ content: counter(ch, ascii); }}
  /* registers */
  .regs {{ height: 0; overflow: hidden; }}
  .reg {{ height: calc(var(--H) * 1px); overflow: hidden; }}
  .reg > div {{ display: block; }}
  .sp {{ height: calc((var(--in) + var(--OFF)) * 1px); }}
  .sub {{ height: 1px; }}
  .pad {{ height: calc(var(--H) * 1px); }}
"""

cells = memtree.html(image["ram"], list(range(RAMN)), WOFF)
regs_html = "\n".join(f'<div class="reg" style="--in: var(--next-{n}); --H: {H}; --OFF: {OFF}"><div class="sp"></div><div class="sub" style="view-timeline-name: --{n}"></div><div class="pad"></div></div>'
                      for n, H, OFF in regs)
console = "\n".join(f'<div class="oc oc{i}"><b></b></div>' for i in range(OUT_SIZE))
import html as _h
src_html = _h.escape(image.get("source", ""))
if image.get("direct"):
    blurb = (f"<p>The program below was compiled to {len(rom)} words of bytecode at build time and baked into the ROM; "
             f"the CSS machine executes it, two instructions per frame. Expected: {image.get('steps', '?')} steps.</p>")
else:
    blurb = (f"<p>The ROM ({len(rom)} words) is a JavaScript-subset compiler, written in that subset and compiled by itself. "
             f"At page load it tokenizes and parses the program below from RAM, compiles it into RAM, and jumps to it. "
             f"Two bytecode instructions per frame; the simulator says {image.get('steps', '?')} steps in total, so give it a few minutes.</p>")
blurb += f"<pre>{src_html}</pre>"

html = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>JavaScript on a CSS VM</title>
<style>
{static}
/* ---------- generated ---------- */
{chr(10).join(props + _mp)}
{chr(10).join(css)}
</style>
{cells}<div id="clk"><div id="cpu">
<div class="con"></div>
{console}
<div class="rd r0"><div class="v0"><div class="rd r1"><div class="v1"><div class="rd r2"><div class="v2">
<div class="head">
<h1>JavaScript, compiled and run by CSS</h1>
{blurb}
<div class="status">
 steps <b class="num" style="--v: var(--steps)"></b> pc <b class="num" style="--v: var(--pcx)"></b> op <b class="num" style="--v: var(--op)"></b>
 imm <b class="num" style="--v: var(--imm)"></b> sp <b class="num" style="--v: var(--sp)"></b> fp <b class="num" style="--v: var(--fp)"></b> top <b class="num" style="--v: var(--m1)"></b>
</div>
</div>
<div class="regs" aria-hidden="true">
{regs_html}
</div>
</div></div></div></div></div></div>
</div></div>
</html>
"""
open(sys.argv[2], "w").write(html)
print(len(html), "bytes,", len(css), "rules,", len(rom), "rom words,", K, "per frame")
