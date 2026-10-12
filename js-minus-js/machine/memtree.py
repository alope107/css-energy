"""memtree.py — RAM for the CSS VMs: remembered-size leaves written through a decode tree.

Each leaf is a content-visibility: hidden element whose remembered width is the word (+ WOFF); a write makes it
visible with width = data until the next write on that channel, so its remembered size updates at the frame end.

The tree keeps per-pass style work off the leaves. Its root sits outside #cpu (so the registers and the wall
clock don't inherit into it) and gets the write channels from its own non-inherited copies of the wa/wd
registers (same view timelines, declared in a timeline-scope on body). Level l turns parity-X properties into
parity-Y ones for its digit of the cell index; a node off the write path computes constants, so restyling stops
one level below it. Measured on the font CPU: style+layout per pass 70 ms -> ~20 ms.

Banks: css()/html() take a prefix; each bank is its own tree over its own cells with its own channels
(register names wa{prefix}{c}/wd{prefix}{c}); leaves keep their global anchor names --c{index}.
"""

def radix(n):
    r = []
    while n % 4 == 0 and n > 4: r.append(4); n //= 4
    return [n] + r

def _strides(R):
    S = [1] * len(R)
    for l in range(len(R) - 2, -1, -1): S[l] = S[l + 1] * R[l + 1]
    return S

def css(CH, wregs, n, WOFF, prefix=''):
    """CH: channel letters; wregs: {name: (H, OFF)} for wa{prefix}*/wd{prefix}*; n: cells in this tree. Returns (props, rules)."""
    R = radix(n); D = len(R); S = _strides(R); p = prefix
    reg = lambda nm, inh: f'@property --{nm} {{ syntax: "<integer>"; inherits: {inh}; initial-value: 0; }}'
    props = [reg(f"m{nm}", "false") for nm in wregs]
    props += [reg(f"{x}{p}{c}{P}", "true") for c in CH for P in "AB" for x in "ead"]
    out = [f"@keyframes m-{nm} {{ from {{ --m{nm}: {H - OFF}; }} to {{ --m{nm}: {-1 - OFF}; }} }}" for nm, (H, OFF) in wregs.items()]
    out.append(f"#mem{p} {{ animation-name: " + ", ".join(f"m-{nm}" for nm in wregs) + "; animation-timeline: " + ", ".join("--" + nm for nm in wregs) +
               "; animation-duration: auto; animation-timing-function: linear; animation-fill-mode: both;\n  " +
               " ".join(f"--e{p}{c}A: min(1, var(--mwa{p}{c})); --a{p}{c}A: max(0, calc(var(--mwa{p}{c}) - 1)); --d{p}{c}A: var(--mwd{p}{c});" for c in CH) + " }")
    for l in range(D):
        X, Y = ("A", "B") if l % 2 == 0 else ("B", "A")
        decl = []
        for c in CH:
            dig = f"mod(round(down, var(--a{p}{c}{X}) / {S[l]}), {R[l]})"
            decl.append(f"--e{p}{c}{Y}: calc(var(--e{p}{c}{X}) * (1 - min(1, max({dig} - var(--dg), var(--dg) - {dig}))));"
                        f" --a{p}{c}{Y}: calc(var(--e{p}{c}{Y}) * var(--a{p}{c}{X})); --d{p}{c}{Y}: calc(var(--e{p}{c}{Y}) * var(--d{p}{c}{X}));")
        out.append(f".L{p}_{l} {{ {' '.join(decl)} }}")
    Z = "B" if D % 2 == 1 else "A"
    out.append(f".cell{p} {{ --hit: calc(" + " + ".join(f"var(--e{p}{c}{Z})" for c in CH) + "); --wv: calc(" + " + ".join(f"var(--e{p}{c}{Z}) * var(--d{p}{c}{Z})" for c in CH) + ");\n"
               f"  content-visibility: if(style(--hit: 1): visible; else: hidden); width: if(style(--hit: 1): calc((var(--wv) + {WOFF}) * 1px); else: fit-content); }}")
    return props, out

def html(ram, cells, WOFF, prefix=''):
    """cells: global RAM indices in this tree, in tree order (leaf i of the tree = cells[i])."""
    R = radix(len(cells)); D = len(R); S = _strides(R); p = prefix
    leaf = lambda i, cls: (f'<div class="w{cls}" style="anchor-name: --c{cells[i]}"><i class="cell cell{p} c{cells[i]}" '
                           f'style="contain-intrinsic-size: auto {ram[cells[i]] + WOFF}px"></i></div>')
    def tree(l, base):
        if l == D - 1: return "".join(leaf(base + x, f" L{p}_{l} d{x}") for x in range(R[l]))
        return "".join(f'<div class="tn L{p}_{l} d{x}">' + tree(l + 1, base + x * S[l]) + "</div>" for x in range(R[l]))
    return f'<div id="mem{p}" class="mem">\n' + tree(0, 0) + '\n</div>\n'

def shared():
    """Rules every tree uses (emit once)."""
    reg = lambda nm: f'@property --{nm} {{ syntax: "<integer>"; inherits: false; initial-value: 0; }}'
    return [reg(nm) for nm in ("dg", "hit", "wv")], [f".d{x} {{ --dg: {x}; }}" for x in range(16)] + [".tn { display: contents; }"]

def scope(names):
    return "body { timeline-scope: " + ", ".join("--" + n for n in names) + "; }"
