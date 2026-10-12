#!/usr/bin/env python3
"""gen_fvm.py image.json fcpu out.html [--issue=K] — the CSS VM with HarfBuzz as the CPU. No script in the page.

Memory, write channels, console and clock are gen_vm.py's. The CPU is a font (fcpu.woff2 from fvm_build.py):
each layout pass renders the machine state as one line of text (a counter per state digit), Blink shapes it
with feature cv01 (S micro-cycles of a cached CPU in GSUB), and the widths of ~60 spans are the next state.
Between shapings CSS services the trap the font stopped on: cache miss (one RAM read port), dirty write-back
(one write channel), MUL/DIV/MOD/SHL13, PUTC.
"""
import json, sys, base64, html as _h
import zoomfix, memtree

image = json.load(open(sys.argv[1])); pre = sys.argv[2]; outp = sys.argv[3]
meta = json.load(open(pre + '.json')); font64 = base64.b64encode(open(pre + '.woff2', 'rb').read()).decode()
K = int(next((a.split('=')[1] for a in sys.argv if a.startswith('--issue=')), 2))
RAMMODE = next((a.split('=')[1] for a in sys.argv if a.startswith('--ram=')), 'tree')
N, S = meta['N'], meta['S']
ROM, RAMN, WOFF = 4096, image['ramSize'], 1 << 20
OUT_BASE, ROWS, COLS = image['outBase'], image['rows'], image['cols']
OUT_SIZE = ROWS * COLS
CH = 'ABCD'[:2 * K]
CV = [tuple(v) for v in meta['cvals']]
ci = lambda *v: CV.index(tuple(v))
I_START, I_MISS, I_WFAIL, I_PUTC, I_HALT = ci('S'), ci('T', 'MISS'), ci('T', 'WFAIL'), ci('T', 'PUTC'), ci('T', 'HALT')
I_EXT = {op: ci('T', 'EXT_' + op) for op in ['MUL', 'DIV', 'MOD', 'SHL13']}

def eq(x, c): return f"calc(1 - min(1, max({x} - {c}, {c} - {x})))"
def prop(name, init=0): return f'@property --{name} {{ syntax: "<integer>"; inherits: true; initial-value: {init}; }}'
def sgn20(x): return f"calc({x} - {1 << 20} * min(1, max(0, {x} - {(1 << 19) - 1})))"
M20 = 1 << 20

# ---------------- registers: (name, H, OFF). Value range [-OFF, H-OFF)
# 20-bit machine words are kept SIGNED (|v| < 2^19) in every property that crosses a var(): Chrome substitutes a
# registered <integer> by its serialization, which has 6 significant digits, so 1048575 (= -1) became 1048580.
regs = [("CR", 512, 0), ("PC", 8192, 0), ("SP", 8192, 0), ("FP", 8192, 0), ("MAR", 8192, 0), ("T1", M20, M20 // 2), ("T2", M20, M20 // 2),
        ("RES", M20, M20 // 2), ("init", 2, 0), ("optr", 256, 0), ("k", 16, 0), ("par", 2, 0), ("tprev", 65536, 0), ("steps", 1 << 21, 0), ("fok", 2, 0), ("nsh", 1 << 21, 0)]
regs += [(f"A{k}", 65536, 0) for k in range(N)] + [(f"V{k}", M20, M20 // 2) for k in range(N)]
regs += [(f"wa{c}", RAMN + 1, 0) for c in CH] + [(f"wd{c}", 1 << 21, 1 << 20) for c in CH]
readback = {"CR": ["CR"], "PC": ["HPC"], "SP": ["HSP"], "FP": ["HFP"], "MAR": ["HMAR"], "T1": ["HT1lo", "HT1hi"], "T2": ["HT2lo", "HT2hi"]}
for k in range(N): readback[f"A{k}"] = [f"L{k}A"]; readback[f"V{k}"] = [f"L{k}B", f"L{k}C"]

scalar = ["t", "fresh", "go", "chan", "kind", "resvin", "isMISS", "isWFAIL", "isPUTC", "isHALT", "isEXT", "isMUL", "isDIV", "isMOD", "isSHL",
          "v0", "v1", "vtag", "vval", "vdirty", "doWB", "ch", "nl", "doPUT", "doWrite", "waddr", "wval", "W", "a2", "b1", "bs", "q", "ext",
          "resT", "resvT", "mval", "maddr", "maddrh", "maddrl", "ni", "first", "PCe", "SPe", "FPe", "RESe", "rbv", "rblo", "rbhi"]
scalar += [f"{x}{k}" for k in range(N) for x in ["Ae", "Ve", "vf", "vd", "tag", "isv", "fill", "tagT", "valT", "vdT", "vfT"]]
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
for k in range(N):
    eff += [f"--Ae{k}: calc(var(--init) * var(--A{k}) + var(--first) * {24576 if k == 0 else 0});", f"--Ve{k}: calc(var(--init) * var(--V{k}));",
            f"--vf{k}: round(down, var(--Ae{k}) / 24576);", f"--vd{k}: round(down, mod(var(--Ae{k}), 24576) / 8192);",
            f"--tag{k}: mod(var(--Ae{k}), 8192);"]
# ---------------- frame gate (gen_vm)
gate = ["--fresh: calc(min(1, max(var(--t) - var(--tprev), var(--tprev) - var(--t))));",
        f"--go: calc(var(--fok) * min(1, var(--fresh) + min(1, max(0, {K} - var(--k)))));",
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
svc += ["--vtag: calc(" + " + ".join(f"var(--isv{k}) * var(--tag{k})" for k in range(N)) + ");",
        "--vval: calc(" + " + ".join(f"var(--isv{k}) * var(--Ve{k})" for k in range(N)) + ");",
        "--vdirty: calc(" + " + ".join(f"var(--isv{k}) * {eq(f'var(--vd{k})', 2)}" for k in range(N)) + ");",
        "--doWB: calc((var(--isMISS) + var(--isWFAIL)) * var(--vdirty));",
        "--ch: mod(var(--T1), 256);", f"--nl: {eq('var(--ch)', 10)};",
        "--doPUT: calc(var(--isPUTC) * (1 - var(--nl)));",
        "--doWrite: calc(var(--doWB) + var(--doPUT));",
        f"--waddr: calc(var(--doWB) * var(--vtag) + var(--doPUT) * ({OUT_BASE} + var(--optr)));",
        f"--wval: calc(var(--doWB) * {sgn20('var(--vval)')} + var(--doPUT) * var(--ch));",
        f"--W: calc(var(--go) * var(--doWrite) * (var(--waddr) - {ROM} + 1));",
        # EXT: a = T2, b = T1 (signed); SHL13 uses T1
        f"--a2: {sgn20('var(--T2)')};", f"--b1: {sgn20('var(--T1)')};",
        f"--bs: calc(var(--b1) + {eq('var(--b1)', 0)});", "--q: round(to-zero, var(--a2) / var(--bs));",
        f"--ext: calc(var(--isMUL) * var(--a2) * var(--b1) + (1 - {eq('var(--b1)', 0)}) * (var(--isDIV) * var(--q) + var(--isMOD) * (var(--a2) - var(--b1) * var(--q))) + var(--isSHL) * var(--b1) * 8192);",
        f"--resT: calc(var(--isEXT) * var(--ext) + (1 - var(--isEXT)) * var(--RESe));",
        "--resvT: min(1, calc(var(--resvin) + var(--isEXT) + var(--isPUTC)));",
        # read port value (cache fill on MISS): RAM[MAR]
        f"--maddr: calc(min({RAMN - 1}, max(0, var(--MAR) - {ROM})));",
        "--maddrh: round(down, var(--maddr) / 64);", "--maddrl: calc(var(--maddr) - 64 * var(--maddrh));"]
for k in range(N):
    svc += [f"--fill{k}: calc(var(--isMISS) * var(--isv{k}));",
            f"--tagT{k}: calc(var(--fill{k}) * var(--MAR) + (1 - var(--fill{k})) * var(--tag{k}));",
            f"--valT{k}: calc(var(--fill{k}) * var(--mval) + (1 - var(--fill{k})) * var(--Ve{k}));",
            f"--vdT{k}: calc(var(--fill{k}) * 1 + var(--isWFAIL) * var(--isv{k}) * var(--vdirty) * (1 - var(--vd{k})) + (1 - var(--fill{k})) * var(--vd{k}));",
            f"--vfT{k}: calc(var(--isMISS) * {eq('var(--v1)', k)} + (1 - var(--isMISS)) * var(--isv{k}));"]
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
        e = {'vf': f"var(--vfT{k})", 'vd': f"var(--vdT{k})", 'tag': f"mod(round(down, var(--tagT{k}) / {16 ** j}), 16)",
             'val': f"mod(round(down, mod(var(--valT{k}), {M20}) / {16 ** j}), 16)"}[kind_]
    inp.append(f"--i{c['pos']}: {e};")

# ---------------- next-state (inside readback readers for the font outputs)
g = "var(--go)"
def hold(name, expr): return f"--next-{name}: calc({g} * ({expr}) + (1 - {g}) * var(--{name}));"
nx = ["--next-tprev: var(--t);", "--next-nsh: calc(var(--nsh) + var(--go));",
      f"--next-k: calc(var(--fresh) + (1 - var(--fresh)) * min({K}, var(--k) + 1));",  # saturates: once the K issues are done nothing changes, so Blink stops re-running layout this frame,
      "--next-par: calc(var(--fresh) * (1 - var(--par)) + (1 - var(--fresh)) * var(--par));",
      hold("init", "1"), hold("RES", "var(--resT)"),
      hold("optr", f"var(--isPUTC) * mod(var(--nl) * (round(down, var(--optr) / {COLS}) + 1) * {COLS} + (1 - var(--nl)) * (var(--optr) + 1), {OUT_SIZE}) + (1 - var(--isPUTC)) * var(--optr)")]
for i, c in enumerate(CH):
    sel = f"var(--go) * {eq('var(--chan)', i)}"
    rel = f"min(1, var(--W)) * {eq('var(--W)', f'var(--wa{c})')}"
    nx.append(f"--next-wa{c}: calc({sel} * var(--W) + (1 - {sel}) * (1 - {rel}) * var(--wa{c}));")
    nx.append(f"--next-wd{c}: calc({sel} * var(--doWrite) * var(--wval) + (1 - {sel}) * var(--wd{c}));")

def mux(p, n, leaf, default):
    outer = []
    for j in range((n + 63) // 64):
        inner = " ".join(f"style(--{p}l: {i}): {leaf(j * 64 + i)};" for i in range(64) if j * 64 + i < n)
        outer.append(f"style(--{p}h: {j}): if({inner} else: {default});")
    return f"if({' '.join(outer)} else: {default})"

names = ", ".join(f"--{n}" for n, _, _ in regs)
anims = ", ".join(f"r-{n}" for n, _, _ in regs)
WNAMES = [f"wa{c}" for c in CH] + [f"wd{c}" for c in CH]
inner_names = names if RAMMODE == 'flat' else ", ".join(f"--{n}" for n, _, _ in regs if n not in WNAMES)
css = ["#clk { animation: wc 100s linear infinite; }\n@keyframes wc { from { --t: 0; } to { --t: 60000; } }",
       "#cpu {\n  timeline-scope: " + inner_names + ";\n  animation-name: " + anims + ";\n  animation-timeline: " + names +
       ";\n  animation-duration: auto;\n  animation-timing-function: linear;\n  animation-fill-mode: both;\n  " + "\n  ".join(gate + eff + svc[:len(svc) - 5 * N]) + "\n}"]
css += [f"@keyframes r-{n} {{ from {{ --{n}: {H - OFF}; }} to {{ --{n}: {-1 - OFF}; }} }}" for n, H, OFF in regs]
css.append(".rp { --sR: " + mux("maddr", RAMN, lambda k: f"--c{k}", "--c0") + "; }")
css.append(".vp { " + f"--mval: calc(100cqi / 1px - {WOFF});\n  " + "\n  ".join(svc[len(svc) - 5 * N:] + inp + nx) + " }")
# writes
if RAMMODE == 'flat':   # one rule per cell per channel
    for k in range(RAMN):
        for c in CH:
            css.append(f"@container style(--wa{c}: {k + 1}) {{ .cell.c{k} {{ content-visibility: visible; width: calc((var(--wd{c}) + {WOFF}) * 1px); }} }}")
else:
    _mp, _mc = memtree.css(CH, {n: (H, OFF) for n, H, OFF in regs if n in WNAMES}, RAMN, WOFF)
    _sp, _sc = memtree.shared()
    _mp += _sp; _mc = [memtree.scope(WNAMES)] + _sc + _mc
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

# ---------------- readback readers: width = anchor-size(span); value = 100cqi / 1px; registers live inside
def reg_html(n, H, OFF):
    return (f'<div class="reg" style="--in: var(--next-{n}); --H: {H}; --OFF: {OFF}"><div class="sp"></div>'
            f'<div class="sub" style="view-timeline-name: --{n}"></div><div class="pad"></div></div>')
rb_html = []
for n, H, OFF in regs:
    if n not in readback: continue
    sp = readback[n]
    if len(sp) == 1:
        inner = f'<div class="rv" style="--next-{n}: calc(var(--go) * round(100cqi / 1px * var(--R)) + (1 - var(--go)) * var(--{n}))">{reg_html(n, H, OFF)}</div>'
        rb_html.append(f'<div class="rb" style="width: anchor-size(--a-{sp[0]} width)">{inner}</div>')
    else:
        inner = (f'<div class="rv" style="--rblo: round(100cqi / 1px * var(--R))"><div class="rb" style="width: anchor-size(--a-{sp[1]} width)">'
                 f'<div class="rv" style="--next-{n}: calc(var(--go) * {sgn20("(var(--rblo) + 4096 * round(100cqi / 1px * var(--R)))")} + (1 - var(--go)) * var(--{n}))">'
                 f'{reg_html(n, H, OFF)}</div></div></div>')
        rb_html.append(f'<div class="rb" style="width: anchor-size(--a-{sp[0]} width)">{inner}</div>')
# steps: += instructions completed (NI span)
rb_html.append('<div class="rb" style="width: anchor-size(--a-NI width)"><div class="rv" style="--next-steps: calc(var(--steps) + var(--go) * round(100cqi / 1px * var(--R)))">'
               + reg_html('steps', 1 << 21, 0) + '</div></div>')
# font-ready sentinel: SP digits of the initial state shaped with cv02 (export only) must measure sp0 units
rb_html.append(f'<div class="rb" style="width: anchor-size(--a-SENT width)"><div class="rv" style="--next-fok: {eq("round(100cqi / 1px * var(--R))", sp0)}">'
               + reg_html('fok', 2, 0) + '</div></div>')
sent = ''.join('&#x%X;' % c['symbols'][(sp0 >> (4 * c['input'][2])) & 15] for c in meta['cells'] if c['span'] == 'HSP')
local_regs = [r for r in regs if r[0] not in readback and r[0] not in ('steps', 'fok')]

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
  .rp {{ width: anchor-size(var(--sR) width); height: 1px; container-type: inline-size; }}
  .rb {{ height: 1px; container-type: inline-size; }}
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
  .reg {{ height: calc(var(--H) * 1px); overflow: hidden; }}
  .reg > div {{ display: block; }}
  .sp {{ height: calc((var(--in) + var(--OFF)) * 1px); }}
  .sub {{ height: 1px; }}
  .pad {{ height: calc(var(--H) * 1px); }}
"""
cells_html = "\n".join(f'<div class="w" style="anchor-name: --c{k}"><i class="cell c{k}" style="contain-intrinsic-size: auto {image["ram"][k] + WOFF}px"></i></div>' for k in range(RAMN))
console = "\n".join(f'<div class="oc oc{i}"><b></b></div>' for i in range(OUT_SIZE))
src_html = _h.escape(image.get("source", ""))
blurb = (f"<p>The CPU is a font. Each layout pass, the machine state is rendered as a line of text and Blink's HarfBuzz runs "
         f"{S} micro-cycles of a bytecode CPU implemented in GSUB (a {N}-line cache of RAM inside the glyph string); the widths of the "
         f"state's spans are read back as the next state. CSS handles what the font traps on: cache misses, write-backs, MUL/DIV/MOD, output. "
         f"The ROM is the self-hosted JavaScript-subset compiler; it compiles the program below and runs it.</p><pre>{src_html}</pre>")
local_html = "\n".join(reg_html(n, H, OFF) for n, H, OFF in local_regs)
mem_outer, mem_inner = ("", f'<div class="mem">\n{cells_html}\n</div>\n') if RAMMODE == 'flat' else (memtree.html(image["ram"], list(range(RAMN)), WOFF), "")
page = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>JavaScript on a HarfBuzz CPU</title>
<style>
{static}
/* ---------- generated ---------- */
{chr(10).join(props)}
{chr(10).join(css)}
</style>
{mem_outer}<div id="clk"><div id="cpu">
{mem_inner}<div class="con"></div>
{console}
<div class="rp"><div class="vp">
<div id="sent"><span style="anchor-name: --a-SENT">{sent}</span></div>
<div id="state">{''.join(spans_html)}</div>
{''.join(rb_html)}
<div class="head">
<h1>JavaScript, compiled and run by a font</h1>
<p class="zw">This screen scale / zoom level isn't one the page recognises, so the machine won't start. Reset the zoom (Cmd/Ctrl + 0).</p>
{blurb}
<div class="status">steps <b class="num" style="--v: var(--steps)"></b> pc <b class="num" style="--v: var(--PC)"></b> sp <b class="num" style="--v: var(--SP)"></b>
 trap <b class="num" style="--v: var(--kind)"></b></div>
</div>
<div class="regs" aria-hidden="true">
{local_html}
</div>
</div></div>
</div></div>
</html>
"""
open(outp, 'w').write(page)
print(len(page), 'bytes', len(css), 'rules', K, 'shapings/frame max')
