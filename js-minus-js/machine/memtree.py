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

Sparse: below one tree level the leaves are wrapped in groups (GROUP leaves each) that are display: none until a write
reaches them. The group node latches --live with a transition (0 s to take a write, a 1,000,000 s delay to hold it), and
its wrapper child is shown by it. Blink restyles a whole subtree whenever an inherited property changes above it (every
write pass here), merges every rendered anchor into the containing block's anchor query on each layout pass, and walks
every child of a laid-out block; hidden groups cost none of that, so the page's per-pass cost follows the cells the
program has touched, not the RAM size. A hidden cell has no anchor, and the read ports fall back to 0: unwritten RAM.
Cells the page needs from the start (the console, and the static areas on a page without a compile chain) are in
groups that are live from the start.
"""
import os
GROUP = int(os.environ.get("MEMGROUP", 256))    # leaves per group (words of one bank: 4 x this of address space); 256 measured best

def group_level(R):
    """the tree level whose nodes become groups: the deepest level with at least GROUP leaves below it"""
    S = _strides(R)
    return max([l for l in range(len(R)) if S[l] >= GROUP] or [0])

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
    # groups: the node at level G sees a write to its subtree as one of its own channel enables; the latch holds it forever
    G = group_level(R); YG = "B" if G % 2 == 0 else "A"
    # (min: two channels may reach the group in one pass, and display: if(style(--live: 1)) must still match)
    out.append(f".g{p} {{ --wnow: min(1, calc(" + " + ".join(f"var(--e{p}{c}{YG})" for c in CH) + ")); --live: var(--wnow);"
               f" transition: --live 0s calc((1 - var(--wnow)) * 1000000s); }}")
    return props, out

def html(ram, cells, WOFF, prefix='', live=None):
    """cells: global RAM indices in this tree, in tree order (leaf i of the tree = cells[i]). live: cells whose groups are
    rendered from the start (None: all groups; a set: only the groups holding one of these)."""
    R = radix(len(cells)); D = len(R); S = _strides(R); p = prefix; G = group_level(R)
    leaf = lambda i, cls: (f'<div class="w{cls}" style="anchor-name: --c{cells[i]}"><i class="cell cell{p} c{cells[i]}" '
                           f'style="contain-intrinsic-size: auto {ram[cells[i]] + WOFF}px"></i></div>')
    def tree(l, base):
        if l == D - 1: return "".join(leaf(base + x, f" L{p}_{l} d{x}") for x in range(R[l]))
        if l == G:
            out = []
            for x in range(R[l]):
                b = base + x * S[l]; lv = live is None or any(cells[i] in live for i in range(b, min(b + S[l], len(cells))))
                out.append(f'<div class="tn gn L{p}_{l} d{x} g{p}{" glive" if lv else ""}"><div class="gc">' + tree(l + 1, b) + "</div></div>")
            return "".join(out)
        return "".join(f'<div class="tn L{p}_{l} d{x}">' + tree(l + 1, base + x * S[l]) + "</div>" for x in range(R[l]))
    return f'<div id="mem{p}" class="mem">\n' + tree(0, 0) + '\n</div>\n'

def shared():
    """Rules every tree uses (emit once)."""
    reg = lambda nm: f'@property --{nm} {{ syntax: "<integer>"; inherits: false; initial-value: 0; }}'
    return ([reg(nm) for nm in ("dg", "hit", "wv", "wnow")] + ['@property --live { syntax: "<integer>"; inherits: true; initial-value: 0; }'],
            [f".d{x} {{ --dg: {x}; }}" for x in range(16)] + [".tn { display: contents; }", ".tn.gn { display: block; height: 0; }",   # a group node has a box: its --live transition (the latch) must run
             ".tn.glive { --live: 1; transition: none; }",   # two classes: wins over the per-bank .g<p> rule; no latch delay on the initial 0 -> 1
                                                           ".gc { display: if(style(--live: 1): contents; else: none); }"])

def scope(names):
    return "body { timeline-scope: " + ", ".join("--" + n for n in names) + "; }"
