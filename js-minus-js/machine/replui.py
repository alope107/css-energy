"""replui.py — the REPL on the editor page (README REPL): one more editor in the picker, run by Enter instead of Run.

- Each time its line count changes the scan starts again (readback/ui_rb.py repl_run), which drops --ccgo: RAM, the
  globals and the console are cleared (here: a property, not Edit's selector) and the CPU's registers restart. Then the
  whole session (every line but the last, the prompt) is read, compiled in REPL mode (--repl: cc_ref Compiler repl) and run
  again: the machine keeps no state between entries, and a session's replay prints what it printed before.
- The console's grid is the REPL's (repl_cols x repl_rows), and the program marks where each entry's output starts (PUTC
  marks: mark k for the entry that starts on line k, MARKEND at the end, which the library's halts write too).
- The console box (.cons) lies over the editor: its readers must share a containing block with the console's leaves, so
  the REPL's readers live in it (.rdisp). They latch: they take RAM's values only once the run has ended (--rg: --ccgo and
  the end mark), so Enter doesn't blank the transcript, and a session that doesn't compile keeps the last one.
- The latched marks and line count are registers (view timelines scoped on body), animated onto the display and onto the
  editor's frame: each line's ::before opens room for the output above it, and the readers put each row there.
Row r shows above line L(r) = #{lines L < n : t_L <= r}, at y = 12 + 24 (r + L(r)), where n is the latched line count and
t_L the output rows before line L's entry (the marks' rows, a running maximum: a line without a mark continues an entry)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'py'))
import csslabel as lbl

LH, PADT, PADL, CW = 24, 12, 14, 10      # the editor's line height, padding, a character's advance (the probe font: 10px at 16px)
GUT = 4 * CW                             # the prompts' gutter: "> " or "... " left of each line
DEMO = '3 + 4\n"hello, " + "world".toUpperCase()\nvar xs = [1, 2, 3]\nxs.concat(4).reverse()\n'

def nreg(n, H):
    """a register of height H: its keyframes map the view timeline --{n}T onto --{n} (value = the subject's top)"""
    return f'@keyframes k{n} {{ from {{ --{n}: {H}; }} to {{ --{n}: -1; }} }}'

def css(R, L, cells, WOFF, RCOLS, RROWS, NMARK, MARKEND, OUTMAX, ginit, UNDEF):
    """R: the REPL editor's index; L: lines; cells(k): the RAM index (--c<k>) of console cell k (marks from OUTMAX)"""
    pk = f'#pk{R}:checked'
    M = list(range(L)) + ['E']                      # the marks the display reads: one per line, and the end
    mcell = lambda k: cells(OUTMAX + (MARKEND if k == 'E' else k))
    regs = [f'mk{k}' for k in M] + ['rn']           # (onto the display and the frame) and rg, rcl (onto the display only)
    out = [lbl.section('REPL', 'machine/replui.py: Enter replays the session; the console lies over the editor and shows each entry\'s output under it')]
    out.append(lbl.group('Properties and register keyframes'))
    out += [f'@property --{n} {{ syntax: "<integer>"; inherits: true; initial-value: 0; }}'
            for n in regs + ['rg', 'rcl', 'rml', 'rnl', 'rqrE'] + [f'rqr{k}' for k in range(L)] + [f'rqt{k}' for k in range(L)]]
    out += ['@property --rcd { syntax: "<integer>"; inherits: false; initial-value: -1; }']
    out += [nreg(f'mk{k}', 2048) for k in M] + [nreg('rn', 32), nreg('rg', 2), nreg('rcl', 4096)]
    # ---- running it: the CPU on, the REPL's grid, RAM cleared while the scan runs (--ccgo 0)
    out.append(lbl.group('Running', 'the CPU on while the REPL shows; RAM, globals and console cleared while the scan runs (Edit\'s rules are for the programs)'))
    out.append(f'{pk} ~ #clkw {{ --run: 1; --ocols: {RCOLS}; --osize: {RCOLS * RROWS}; }}')
    out.append(f'{pk} ~ #memw {{ animation: kccgo auto linear both; animation-timeline: --rbrdT; }}')
    keep = f'style(--hit: 1): calc((var(--wv) + {WOFF}) * 1px); else: fit-content'
    out.append(f'{pk} ~ #memw .cell, {pk} ~ #clkw .cons .cell {{ content-visibility: if(style(--hit: 1) or style(--ccgo: 0): visible; else: hidden);'
               f' width: if(style(--ccgo: 0): {WOFF}px; {keep}); }}')
    out.append(f'{pk} ~ #memw :is({", ".join(f".c{a}" for a in ginit)}) {{ width: if(style(--ccgo: 0): {UNDEF + WOFF}px; {keep}); }}')
    # ---- the page around it
    out.append(lbl.group('Page', 'no Run button; the editor\'s frame grows with the output; the prompts\' gutter'))
    out.append(f'{pk} ~ #app {{ height: {(L + RROWS) * LH + 640}px; }}')
    out.append(f'{pk} ~ #app .runbtn, #pk{R}:not(:checked) ~ #app .replhint, {pk} ~ #app .notes > :not(.replnote), #pk{R}:not(:checked) ~ #app .notes > .replnote {{ display: none; }}')
    out.append(f'.replhint {{ font: .8rem ui-monospace, monospace; color: var(--muted); }} {pk} ~ #app #in-label {{ display: none; }}')
    # the compile status beside the hint (the console's column is the editor now): reading, compiling, compiled, or the error
    out.append(f'{pk} ~ .cst {{ position: absolute; left: calc(anchor(--rbed right) - 240px); top: calc(anchor(--rbed top) - 98px); }}'
               f' {pk} ~ .cst .cstv {{ width: 240px; text-align: right; }} {pk} ~ .cst .cstv::before {{ color: if(style(--cse: 0): var(--muted); else: #b00); }}')
    out.append(f'#app .ed{R} {{ padding-left: {PADL + GUT}px; background: none; }}')
    out.append(f'{pk} ~ #clkw .cons {{ position: absolute; left: anchor(--rbed left); top: anchor(--rbed top); width: anchor-size(--rbed width);'
               f' height: anchor-size(--rbed height); pointer-events: none; }}')
    out.append(f'{pk} ~ #clkw .cons :is(.con, .oc) {{ display: none; }} #pk{R}:not(:checked) ~ #clkw .rdisp {{ display: none; }}')
    # ---- the display's values: latched marks -> rows; the frame (::before) and the display (.rdisp) compute them alike
    rows = [f'--rqr{k}: round(up, max(0, var(--mk{k}) - 1) / {RCOLS});' for k in range(L)] + [f'--rqrE: round(up, max(0, var(--mkE) - 1) / {RCOLS});']
    rows += [f'--rqt{k}: max({", ".join(f"var(--rqr{j})" for j in range(k + 1))});' for k in range(L)]
    anim = lambda names: (f'animation-name: {", ".join(f"k{n}" for n in names)}; animation-timeline: {", ".join(f"--{n}T" for n in names)};'
                          ' animation-duration: auto; animation-timing-function: linear; animation-fill-mode: both;')
    out.append(lbl.group('Output room', 'each line\'s ::before opens the rows shown above it (the latched marks: n lines, t_L rows before line L)'))
    out.append(f'{pk} ~ #app .frame {{ overflow: visible; {anim(regs)} ' + ' '.join(rows) + ' }')
    for k in range(1, L):
        above = f'clamp(0, var(--rn) - {k}, 1) * (var(--rqt{k}) - var(--rqt{k - 1})) + (1 - min(1, abs(var(--rn) - {k}))) * (var(--rqrE) - var(--rqt{k - 1}))'
        out.append(f'.ed{R} > div:nth-of-type({k})::before {{ content: ""; display: block; height: calc(({above}) * {LH}px); }}')
    out.append(lbl.group('Display', 'the latch gate (rg), the marks\' and line count\'s latches, each row\'s place, the prompts'))
    ry = []
    for r in range(RROWS):
        L_r = ' + '.join(f'clamp(0, var(--rn) - {k}, 1) * clamp(0, {r + 1} - var(--rqt{k}), 1)' for k in range(L))
        ry += [f'--rqy{r}: calc({PADT}px + {LH}px * ({r} + {L_r}));', f'--rqv{r}: clamp(0, var(--rqrE) - {r}, 1);']
    # a prompt per line: ">" where an entry starts (a mark), "..." where one goes on; from the latched prompt on, ">"
    pm = []
    for k in range(1, L):
        pm += [f'--rqpy{k}: calc({PADT}px + {LH}px * ({k} + clamp(0, var(--rn) - {k}, 1) * var(--rqt{k}) + (1 - clamp(0, var(--rn) - {k}, 1)) * var(--rqrE)));',
               f'--rqpg{k}: max(clamp(0, var(--mk{k}), 1), 1 - clamp(0, var(--rn) - {k}, 1));', f'--rqps{k}: clamp(0, var(--rcl) - {k} + 1, 1);']
    out.append(f'.rdisp {{ display: contents; {anim(regs + ["rg", "rcl"])} ' + ' '.join(rows + ry + pm) + ' }')
    out += [f'@property --{n}{i} {{ syntax: "<{"length" if n in ("rqy", "rqpy") else "integer"}>"; inherits: true; initial-value: 0{"px" if n in ("rqy", "rqpy") else ""}; }}'
            for n, rng in (('rqy', range(RROWS)), ('rqv', range(RROWS)), ('rqpy', range(1, L)), ('rqpg', range(1, L)), ('rqps', range(1, L))) for i in rng]
    # the gate: the run ended (the end mark is set) and the compile chain is on; the latches take RAM's values only then
    out.append(f'.rgate {{ width: anchor-size(--c{mcell("E")} width, {WOFF}px); }}'
               f' .rgate .sub {{ top: calc(var(--ccgo) * min(1, max(0, round(100cqi / 1px) - {WOFF})) * 1px); }}')
    # a latch: -1 while the gate is shut, which a transition held for 1,000,000 s keeps showing the last value for; the value
    # itself once it opens (no delay). The gate must come through a rule, as the scan's latches do (@container style()): a
    # change an animation makes doesn't start a transition, and --rg is animated. It opens a frame after the end mark (rg, a
    # register) and shuts with --ccgo itself, in the frame the scan starts and RAM is cleared
    latch = lambda sel, n, v: (f'{sel} {{ --{n}: -1; transition: --{n} 0s 1000000s; }}'
                               f' @container style(--rg: 1) and style(--ccgo: 1) {{ {sel} {{ --{n}: {v}; transition-delay: 0s; }} }}')
    out.append(latch('.rmk > .rml', 'rml', f'calc(round(100cqi / 1px) - {WOFF})') + ' .rml .sub { top: calc(max(0, var(--rml)) * 1px); }')
    out += [f'.rmk{k} {{ width: anchor-size(--c{mcell(k)} width, {WOFF}px); }}' for k in M]
    out.append(latch('.rnl', 'rnl', 'var(--rcl)') + ' .rnl .sub { top: calc(max(0, var(--rnl)) * 1px); }')
    out.append(f'.rrow {{ display: none; }}' + ''.join(f' .rrow{r} {{ display: if(style(--rqv{r}: 1): contents; else: none); --rqyy: var(--rqy{r}); }}' for r in range(RROWS)))
    out.append(f'.rc {{ position: absolute; top: var(--rqyy); height: {LH}px; container-type: inline-size; visibility: hidden; font: 16px/{LH}px "AsciiProbe", monospace; color: var(--muted); }}'
               f' .rc > b {{ counter-set: ch var(--rcd); font-weight: 400; visibility: visible; display: inline-block; width: {CW}px; }}'
               f' .rc > b::after {{ content: counter(ch, ascii); }} ' + latch('.rc > b', 'rcd', f'calc(round(100cqi / 1px) - {WOFF})'))
    out.append(f'.rpm {{ position: absolute; left: {PADL}px; display: none; font: 16px/{LH}px "AsciiProbe", monospace; color: var(--accent); }}'
               + ''.join(f' .rpm{k} {{ top: var(--rqpy{k}); display: if(style(--rqps{k}: 1): block; else: none); }}'
                         f' .rpm{k}::before {{ content: if(style(--rqpg{k}: 1): ">"; else: "..."); }}' for k in range(1, L)))
    return out

def html_cons(L, RCOLS, RROWS, MARKEND, cells, OUTMAX, WOFF):
    """the REPL's display, inside .cons: the gate, the marks' and the line count's latches (registers), the rows' readers, the prompts"""
    reg = lambda n, H: f'<div class="reg" style="height: {H}px"><div class="sub" style="view-timeline-name: --{n}T"></div></div>'
    h = ['<div class="rdisp">', f'<div class="rp rgate">{reg("rg", 2)}</div>']
    h += [f'<div class="rp rmk rmk{k}"><div class="rml">{reg(f"mk{k}", 2048)}</div></div>' for k in list(range(L)) + ['E']]
    h.append(f'<div class="rnl">{reg("rn", 32)}</div>')
    for r in range(RROWS):
        h.append(f'<div class="rrow rrow{r}">' + ''.join(f'<i class="rc" style="width: anchor-size(--c{cells(r * RCOLS + c)} width, {WOFF}px); left: {PADL + GUT + c * CW}px"><b></b></i>'
                                                        for c in range(RCOLS)) + '</div>')
    h += [f'<i class="rpm rpm{k}"></i>' for k in range(1, L)]
    return ''.join(h) + '</div>'

def html_app():
    """the line count the scan's sweep started with (--rbnl, on #app: it changes a frame after --ccgo drops) as a register the
    display reads (inside #app, like the scan's)"""
    return ('<div class="rbreg" style="--rbnl: inherit; --rbin: var(--rbnl)"><div class="rbsp"></div><div class="rbsub" style="view-timeline-name: --rclT"></div>'
            '<div class="rbpad"></div></div>')

def timelines(L):
    return [f'--mk{k}T' for k in list(range(L)) + ['E']] + ['--rnT', '--rgT', '--rclT']
