#!/usr/bin/env python3
"""gen_fvm4.py image.json fcpu4 out.html [--issue=K] — the HarfBuzz-CPU page for the 4-word-line font (cpu4.py).

RAM is four banks (address mod 4), each its own decode tree with its own write channels, so a whole cache line
(one aligned block) is written back or filled in one service: four bank read ports (768-way muxes) and up to four
writes per issue. Per cache line the page reads back 8 spans (tag + victim flag, 7 x three value nibbles; the
last also carries the four word states).

(gen_fvm.py notes follow.)
gen_fvm.py image.json fcpu out.html [--issue=K] — the CSS VM with HarfBuzz as the CPU. No script in the page.

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

def eq(x, c): return f"calc(1 - min(1, max({x} - {c}, {c} - {x})))"
def prop(name, init=0): return f'@property --{name} {{ syntax: "<integer>"; inherits: true; initial-value: {init}; }}'
def sgn20(x): return f"calc({x} - {1 << 20} * min(1, max(0, {x} - {(1 << 19) - 1})))"
M20 = 1 << 20

# ---------------- registers: (name, H, OFF). Value range [-OFF, H-OFF)
# 20-bit machine words are kept SIGNED (|v| < 2^19) in every property that crosses a var(): Chrome substitutes a
# registered <integer> by its serialization, which has 6 significant digits, so 1048575 (= -1) became 1048580.
regs = [("CR", 512, 0), ("PC", 8192, 0), ("SP", 8192, 0), ("FP", 8192, 0), ("MAR", 8192, 0), ("T1", M20, M20 // 2), ("T2", M20, M20 // 2),
        ("RES", M20, M20 // 2), ("init", 2, 0), ("optr", 256, 0), ("k", 16, 0), ("par", 2, 0), ("tprev", 65536, 0), ("steps", 1 << 21, 0), ("fok", 2, 0), ("nsh", 1 << 21, 0)]
regs += [(f"A{k}", 4096, 0) for k in range(N)] + [(f"V{k}_{s}", 4096 if s < 6 else 32768, 0) for k in range(N) for s in range(7)]
regs += [(f"wa{w}{c}", BANKN + 1, 0) for w in range(WB) for c in CH] + [(f"wd{w}{c}", 1 << 21, 1 << 20) for w in range(WB) for c in CH]
readback = {"CR": ["CR"], "PC": ["HPC"], "SP": ["HSP"], "FP": ["HFP"], "MAR": ["HMAR"], "T1": ["HT1lo", "HT1hi"], "T2": ["HT2lo", "HT2hi"]}
for k in range(N):
    readback[f"A{k}"] = [f"L{k}A"]
    for s in range(7): readback[f"V{k}_{s}"] = [f"L{k}V{s}"]

scalar = ["t", "fresh", "go", "chan", "kind", "resvin", "isMISS", "isWFAIL", "isPUTC", "isHALT", "isEXT", "isMUL", "isDIV", "isMOD", "isSHL",
          "v0", "v1", "vtag", "ch", "nl", "doPUT", "a2", "b1", "bs", "q", "ext", "mblk", "thany", "victim", "missv", "putaddr", "putbank",
          "resT", "resvT", "rb", "rbh", "rbl", "ni", "first", "PCe", "SPe", "FPe", "RESe", "rbv", "rblo", "rbhi"]
scalar += [f"{x}{w}" for w in range(WB) for x in ["vval", "vdirty", "doWB", "doWrite", "waddr", "wval", "Wb", "mval"]]
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
        "--mblk: round(down, var(--MAR) / 4);"]
for k in range(N): svc.append(f"--th{k}: calc(var(--present{k}) * {eq(f'var(--tag{k})', 'var(--mblk)')});")
svc += ["--thany: calc(" + " + ".join(f"var(--th{k})" for k in range(N)) + ");",
        "--missv: calc(var(--isMISS) * (1 - var(--thany)));",          # miss on an absent block: the victim takes it
        "--victim: calc(var(--missv) + var(--isWFAIL));",
        "--ch: mod(var(--T1), 256);", f"--nl: {eq('var(--ch)', 10)};",
        "--doPUT: calc(var(--isPUTC) * (1 - var(--nl)));",
        f"--putaddr: calc({OUT_BASE} + var(--optr));", "--putbank: mod(var(--putaddr), 4);"]
for w in range(WB):
    svc += [f"--vval{w}: calc(" + " + ".join(f"var(--isv{k}) * var(--val{k}_{w})" for k in range(N)) + ");",
            f"--vdirty{w}: calc(" + " + ".join(f"var(--isv{k}) * var(--dirty{k}_{w})" for k in range(N)) + ");",
            f"--doWB{w}: calc(var(--victim) * var(--vdirty{w}));",
            f"--doWrite{w}: calc(var(--doWB{w}) + var(--doPUT) * {eq('var(--putbank)', w)});",
            f"--waddr{w}: calc(var(--doWB{w}) * (4 * var(--vtag) + {w}) + var(--doPUT) * {eq('var(--putbank)', w)} * var(--putaddr));",
            f"--wval{w}: calc(var(--doWB{w}) * {sgn20(f'var(--vval{w})')} + var(--doPUT) * {eq('var(--putbank)', w)} * var(--ch));",
            f"--Wb{w}: calc(var(--go) * var(--doWrite{w}) * (round(down, (var(--waddr{w}) - {ROM}) / 4) + 1));"]
svc += [# EXT: a = T2, b = T1 (signed); SHL13 uses T1
        f"--a2: {sgn20('var(--T2)')};", f"--b1: {sgn20('var(--T1)')};",
        f"--bs: calc(var(--b1) + {eq('var(--b1)', 0)});", "--q: round(to-zero, var(--a2) / var(--bs));",
        f"--ext: calc(var(--isMUL) * var(--a2) * var(--b1) + (1 - {eq('var(--b1)', 0)}) * (var(--isDIV) * var(--q) + var(--isMOD) * (var(--a2) - var(--b1) * var(--q))) + var(--isSHL) * var(--b1) * 8192);",
        f"--resT: calc(var(--isEXT) * var(--ext) + (1 - var(--isEXT)) * var(--RESe));",
        "--resvT: min(1, calc(var(--resvin) + var(--isEXT) + var(--isPUTC)));",
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
def hold(name, expr): return f"--next-{name}: calc({g} * ({expr}) + (1 - {g}) * var(--{name}));"
nx = ["--next-tprev: var(--t);", "--next-nsh: calc(var(--nsh) + var(--go));",
      f"--next-k: calc(var(--fresh) + (1 - var(--fresh)) * min({K}, var(--k) + 1));",  # saturates: once the K issues are done nothing changes, so Blink stops re-running layout this frame,
      "--next-par: calc(var(--fresh) * (1 - var(--par)) + (1 - var(--fresh)) * var(--par));",
      hold("init", "1"), hold("RES", "var(--resT)"),
      hold("optr", f"var(--isPUTC) * mod(var(--nl) * (round(down, var(--optr) / {COLS}) + 1) * {COLS} + (1 - var(--nl)) * (var(--optr) + 1), {OUT_SIZE}) + (1 - var(--isPUTC)) * var(--optr)")]
for w in range(WB):
    for i, c in enumerate(CH):
        sel = f"var(--go) * {eq('var(--chan)', i)}"
        rel = f"min(1, var(--Wb{w})) * {eq(f'var(--Wb{w})', f'var(--wa{w}{c})')}"
        nx.append(f"--next-wa{w}{c}: calc({sel} * var(--Wb{w}) + (1 - {sel}) * (1 - {rel}) * var(--wa{w}{c}));")
        nx.append(f"--next-wd{w}{c}: calc({sel} * var(--doWrite{w}) * var(--wval{w}) + (1 - {sel}) * var(--wd{w}{c}));")

def mux(p, n, leaf, default):
    outer = []
    for j in range((n + 63) // 64):
        inner = " ".join(f"style(--{p}l: {i}): {leaf(j * 64 + i)};" for i in range(64) if j * 64 + i < n)
        outer.append(f"style(--{p}h: {j}): if({inner} else: {default});")
    return f"if({' '.join(outer)} else: {default})"

import os
ABL = os.environ.get('ABL', '')
isline = lambda n: n[0] in 'AV' and n[1:2].isdigit()
aregs = [r for r in regs if not (ABL in ('noregs', 'noread') and isline(r[0]))]
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

# ---------------- readback readers: width = anchor-size(span); value = 100cqi / 1px; registers live inside
def reg_html(n, H, OFF):
    return (f'<div class="reg" style="--in: var(--next-{n}); --H: {H}; --OFF: {OFF}"><div class="sp"></div>'
            f'<div class="sub" style="view-timeline-name: --{n}"></div><div class="pad"></div></div>')
rb_html = []
for n, H, OFF in regs:
    if n not in readback: continue
    if ABL == 'noread' and isline(n): continue
    if ABL == 'noregs' and isline(n):
        rb_html.append(f'<div class="rb" style="width: anchor-size(--a-{readback[n][0]} width)"><div class="rv" style="--next-{n}: calc(var(--go) * round(100cqi / 1px * var(--R)) + (1 - var(--go)) * var(--{n}))"></div></div>')
        continue
    sp = readback[n]
    if isline(n) and os.environ.get('PAIRS', '1') == '1':
        # line spans are read two per reader: width = one span, height = the next (container-type: size)
        k_, rest = n[1:].split('_')[0] if '_' in n else n[1:], None
        names_k = [f"A{k_}"] + [f"V{k_}_{s}" for s in range(7)]
        i_ = names_k.index(n)
        if i_ % 2: continue
        n2 = names_k[i_ + 1]; H2 = dict((r[0], r[1]) for r in regs)[n2]
        inner = (f'<div class="rv" style="--next-{n}: calc(var(--go) * round(100cqw / 1px * var(--R)) + (1 - var(--go)) * var(--{n})); '
                 f'--next-{n2}: calc(var(--go) * round(100cqh / 1px * var(--R)) + (1 - var(--go)) * var(--{n2}))">{reg_html(n, H, OFF)}{reg_html(n2, H2, 0)}</div>')
        rb_html.append(f'<div class="rb rb2" style="width: anchor-size(--a-{sp[0]} width); height: anchor-size(--a-{readback[n2][0]} width)">{inner}</div>')
    elif len(sp) == 1:
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
  .rp {{ height: 1px; container-type: inline-size; }}
  .rb {{ height: 1px; container-type: inline-size; }}
  .rb.rb2 {{ container-type: size; }}
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
         f"{S} micro-cycles of a bytecode CPU implemented in GSUB (a {N}-line cache of RAM inside the glyph string, four words per line); the widths of the "
         f"state's spans are read back as the next state. CSS handles what the font traps on: cache misses, write-backs, MUL/DIV/MOD, output. "
         f"The ROM is the self-hosted JavaScript-subset compiler; it compiles the program below and runs it.</p><pre>{src_html}</pre>")
local_html = "\n".join(reg_html(n, H, OFF) for n, H, OFF in local_regs)
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
open(outp, 'w').write(page)
print(len(page), 'bytes', len(css), 'rules', K, 'shapings/frame max')
