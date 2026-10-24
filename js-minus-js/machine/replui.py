"""replui.py — the REPL's page (README REPL; gen_css.py UI=1 REPL=1): one editor, run by Enter instead of Run.

- Each time the editor's row count changes the scan starts again (readback/ui_rb.py, repl), which drops --ccgo and the CPU
  (its registers restart). The whole session (every row but the last, the prompt) is read and compiled in REPL mode (--repl:
  cc_ref Compiler repl), but only the entries after the lines the last run read are run: the compiler's rdone (the scan's
  rbdn register less 1: the line count the last finished run read, the display's latched --rn) sets where the run starts
  (--ccstart). RAM, the heap and the console are kept between runs (the CPU writes its cache back once halted, gen_css.py
  xk1), and the console's cursor starts where the last run left it (--optr0, from the latched end mark).
- A session with fewer lines than the last run read starts over: rdone is 0, the latched count is forced to 0 (so a session
  that then doesn't compile starts over too), and RAM, the globals (to undefined) and the console are cleared while the scan
  runs (--rclr, memtree.py), as on every run from line 0. So does one whose scan started while a run was going (Enter during
  a run, or while its cache was written back: --rbz, a latch), whose RAM holds part of an entry's writes.
- The program marks where each entry's output starts (PUTC marks: mark k for the entry that starts on line k, MARKEND at the
  end, which the library's halts write too).
- The console's box (.rcons: the whole console's RAM trees and the display) lies over the editor: its readers must share a
  containing block with the leaves they read. They latch: they take RAM's values only once the run has halted and the cache
  is written back (--rg: --ccgo and the hdone register), so Enter doesn't blank the transcript, and a session that doesn't compile keeps the last one.
- The latched marks and line count are registers (view timelines scoped on body), animated onto the display and onto the
  editor's frame: each line moves down by the output rows above it (a transform, which the rows' names ignore: they come
  from where each row is laid out, ENGINE_NOTES 77 and 81), and the readers put each row there.
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

def anim(names, extra=()):
    """the registers' animations (and others: (keyframes, timeline) pairs)"""
    pairs = [(f'k{n}', f'--{n}T') for n in names] + list(extra)
    return (f'animation-name: {", ".join(k for k, _ in pairs)}; animation-timeline: {", ".join(t for _, t in pairs)};'
            ' animation-duration: auto; animation-timing-function: linear; animation-fill-mode: both;')

def css(L, cells, WOFF, RCOLS, RROWS, NMARK, MARKEND, OUTMAX):
    """L: lines; cells(k): the RAM index (--c<k>) of console cell k (marks from OUTMAX)"""
    M = list(range(L)) + ['E']                      # the marks the display reads: one per line, and the end
    regs = [f'mk{k}' for k in M] + ['rn']           # (onto the display and the frame) and rg, rcl, rbz (onto the display only)
    out = [lbl.section('REPL', 'machine/replui.py: Enter runs the new entries; the console lies over the editor and shows each entry\'s output under it')]
    out.append(lbl.group('Properties and register keyframes'))
    out += [f'@property --{n} {{ syntax: "<integer>"; inherits: true; initial-value: 0; }}'
            for n in regs + ['rg', 'rcl', 'rbz', 'rml', 'rnl', 'rbzl', 'rqrE', 'rres', 'rfr'] + [f'rqt{k}' for k in range(L)]]
    out += ['@property --rcd { syntax: "<integer>"; inherits: false; initial-value: -1; }']
    out += [nreg(f'mk{k}', 2048) for k in M] + [nreg('rn', 32), nreg('rg', 2), nreg('rcl', 4096), nreg('rbz', 2)]
    # ---- running it: the CPU on, the REPL's grid; RAM cleared while the scan runs, if the run starts from line 0 (rbdn 0)
    out.append(lbl.group('Running', 'the CPU on; where it starts; RAM, globals and console cleared while the scan of a run from line 0 runs (rbdn 1; 0: not known yet)'))
    out.append(f'#clkw {{ --run: 1; --ocols: {RCOLS}; --osize: {RCOLS * RROWS}; animation-name: kccgo, rbkdn, kmkE; animation-timeline: --rbrdT, --rbdnT, --mkET;'
               ' animation-duration: auto; animation-timing-function: linear; animation-fill-mode: both;'
               ' --rfr: calc(1 - min(1, abs(var(--rbdn) - 1))); --optr0: calc((1 - var(--rfr)) * max(0, var(--mkE) - 1)); }')
    # (the cells' own rule clears them while --rclr is 1, memtree.py: a rule of its own here was one more each cell tests)
    out.append('#memw { animation-name: kccgo, rbkdn; animation-timeline: --rbrdT, --rbdnT; animation-duration: auto; animation-timing-function: linear;'
               ' animation-fill-mode: both; --rclr: calc((1 - var(--ccgo)) * (1 - min(1, abs(var(--rbdn) - 1)))); }')
    out.append('body #ccw { animation-name: kccgo, rbkdn; animation-timeline: --rbrdT, --rbdnT; --repl: 1; --rdone: max(0, var(--rbdn) - 1); }')
    # ---- the page around it
    out.append(lbl.group('Page', 'the editor\'s frame holds the output too; the prompts\' gutter'))
    out.append(f'#app {{ height: {(L + RROWS) * LH + 640}px; }} .replhint {{ font: .8rem ui-monospace, monospace; color: var(--muted); }}')
    # the compile status beside the hint (no console column: the console is the editor)
    out.append('.cst { position: absolute; left: calc(anchor(--rbed right) - 240px); top: calc(anchor(--rbed top) - 72px); }'
               ' .cst .cstv { width: 240px; text-align: right; } .cst .cstv::before { color: if(style(--cse: 0): var(--muted); else: #b00); }')
    out.append(f'#app .ed {{ padding-left: {PADL + GUT}px; background: none; min-height: {(L + RROWS) * LH + 2 * PADT}px; }}')
    # (a fixed size: anchor-size() of the editor changed every frame of the scan, whose font axis moves the lines' sentinels,
    # and laid the box and its readers out again each time)
    out.append(f'.rcons {{ --rclr: calc((1 - var(--ccgo)) * var(--rfr)); display: block; position: absolute; left: anchor(--rbed left); top: anchor(--rbed top);'
               f' width: {PADL + GUT + RCOLS * CW + 8}px; height: {(L + RROWS) * LH + 2 * PADT}px; pointer-events: none; }}')
    # ---- the display's values: latched marks -> rows; the frame and the display (.rdisp) compute them alike
    rows = [f'--rqt{k}: max({"var(--rqt%d), " % (k - 1) if k else ""}round(up, max(0, var(--mk{k}) - 1) / {RCOLS}));' for k in range(L)]
    rows += [f'--rqrE: round(up, max(0, var(--mkE) - 1) / {RCOLS});']
    # the output rows above line k: the rows before its entry, or (from the latched prompt on) all of them
    above = lambda k: f'clamp(0, var(--rn) - {k}, 1) * var(--rqt{k}) + (1 - clamp(0, var(--rn) - {k}, 1)) * var(--rqrE)'
    out.append(lbl.group('Output room', 'each line moves down by the rows shown above it (the latched marks: n lines, t_L rows before line L)'))
    out.append(f'.frame {{ {anim(regs)} ' + ' '.join(rows) + ' }')
    # (line 0 is the editor's own text, which never has output above it; lines 1 ... are its divs. A transform moves where a
    # line shows, not its sentinel's view progress, which names its row (ui_rb.py); position: relative moved both)
    for k in range(1, L):
        out.append(f'.ed > div:nth-of-type({k}) {{ transform: translateY(calc(({above(k)}) * {LH}px)); }}')
    out.append(lbl.group('Display', 'the latch gate (rg), the marks\' and line count\'s latches, each row\'s place, the prompts'))
    ry = []
    for r in range(RROWS):
        L_r = ' + '.join(f'clamp(0, var(--rn) - {k}, 1) * clamp(0, {r + 1} - var(--rqt{k}), 1)' for k in range(L))
        ry += [f'--rqy{r}: calc({PADT}px + {LH}px * ({r} + {L_r}));', f'--rqv{r}: clamp(0, var(--rqrE) - {r}, 1);']
    # a prompt per line: ">" where an entry starts (a mark; line 0 always), "..." where one goes on; from the latched prompt on, ">"
    pm = []
    for k in range(L):
        pm += [f'--rqpy{k}: calc({PADT}px + {LH}px * ({k} + {above(k)}));',
               f'--rqpg{k}: ' + ('1;' if k == 0 else f'max(clamp(0, var(--mk{k}), 1), 1 - clamp(0, var(--rn) - {k}, 1));'),
               f'--rqps{k}: clamp(0, var(--rcl) - {k} + 1, 1);']
    # a session with fewer lines than the last run read, or whose scan started while a run went on (--rres), starts over: its
    # latched count goes to 0 (below)
    out.append(f'.rdisp {{ display: contents; {anim(regs + ["rg", "rcl", "rbz"], [("r-ccok", "--ccok")])}'
               ' --rres: calc((1 - var(--ccgo)) * max(clamp(0, var(--rn) - var(--rcl), 1), var(--rbz))); '
               + ' '.join(rows + ry + pm) + ' }')
    out += [f'@property --{n}{i} {{ syntax: "<{"length" if n in ("rqy", "rqpy") else "integer"}>"; inherits: true; initial-value: 0{"px" if n in ("rqy", "rqpy") else ""}; }}'
            for n, rng in (('rqy', range(RROWS)), ('rqv', range(RROWS)), ('rqpy', range(L)), ('rqpg', range(L)), ('rqps', range(L))) for i in rng]
    # the gate: the run has halted and the compile chain is on; the latches take RAM's values only then (the end mark can't say
    # so: the last run's stays in RAM)
    out.append('.rgate { animation: r-hdone auto linear both; animation-timeline: --hdone; } .rgate .sub { top: calc(var(--ccgo) * var(--hdone) * 1px); }')
    # a latch: -1 while the gate is shut, which a transition held for 1,000,000 s keeps showing the last value for; the value
    # itself once it opens (no delay). The gate must come through a rule, as the scan's latches do (@container style()): a
    # change an animation makes doesn't start a transition, and --rg is animated (ENGINE_NOTES 79). It opens a frame after the
    # halt (rg, a register) and shuts with --ccgo itself, in the frame the scan starts
    latch = lambda sel, n, v: (f'{sel} {{ --{n}: -1; transition: --{n} 0s 1000000s; }}'
                               f' @container style(--rg: 1) and style(--ccgo: 1) {{ {sel} {{ --{n}: {v}; transition-delay: 0s; }} }}')
    out.append(latch('.rmk > .rml', 'rml', f'calc(round(100cqi / 1px) - {WOFF})') + ' .rml .sub { top: calc(max(0, var(--rml)) * 1px); }')
    out += [f'.rmk{k} {{ width: anchor-size(--c{cells(OUTMAX + (MARKEND if k == "E" else k))} width, {WOFF}px); }}' for k in M]
    out.append(latch('.rnl', 'rnl', 'var(--rcl)') + ' .rnl .sub { top: calc(max(0, var(--rnl)) * 1px); }'
               ' @container style(--rres: 1) { .rnl { --rnl: 0; transition-delay: 0s; } }')
    # busy: from the run's start (the CPU on: ccok) until it is done (rg), held while the scan runs
    out.append('.rbzl { --rbzl: -1; transition: --rbzl 0s 1000000s; } .rbzl .sub { top: calc(max(0, var(--rbzl)) * 1px); }'
               ' @container style(--ccgo: 1) and style(--ccok: 1) and style(--rg: 0) { .rbzl { --rbzl: 1; transition-delay: 0s; } }'
               ' @container style(--ccgo: 1) and style(--rg: 1) { .rbzl { --rbzl: 0; transition-delay: 0s; } }')
    out.append(f'.rrow {{ display: none; }}' + ''.join(f' .rrow{r} {{ display: if(style(--rqv{r}: 1): contents; else: none); --rqyy: var(--rqy{r}); }}' for r in range(RROWS)))
    out.append(f'.rc {{ position: absolute; top: var(--rqyy); height: {LH}px; container-type: inline-size; visibility: hidden; font: 16px/{LH}px "AsciiProbe", monospace; color: var(--muted); }}'
               f' .rc > b {{ counter-set: ch var(--rcd); font-weight: 400; visibility: visible; display: inline-block; width: {CW}px; }}'
               f' .rc > b::after {{ content: counter(ch, ascii); }} ' + latch('.rc > b', 'rcd', f'calc(round(100cqi / 1px) - {WOFF})'))
    out.append(f'.rpm {{ position: absolute; left: {PADL}px; display: none; font: 16px/{LH}px "AsciiProbe", monospace; color: var(--accent); }}'
               + ''.join(f' .rpm{k} {{ top: var(--rqpy{k}); display: if(style(--rqps{k}: 1): block; else: none); }}'
                         f' .rpm{k}::before {{ content: if(style(--rqpg{k}: 1): ">"; else: "..."); }}' for k in range(L)))
    return out

def html_cons(L, RCOLS, RROWS, cells, WOFF):
    """the REPL's display, inside .rcons: the gate, the marks' and the line count's latches (registers), the rows' readers, the prompts"""
    reg = lambda n, H: f'<div class="reg" style="height: {H}px"><div class="sub" style="view-timeline-name: --{n}T"></div></div>'
    h = ['<div class="rdisp">', f'<div class="rp rgate">{reg("rg", 2)}</div>']
    h += [f'<div class="rp rmk rmk{k}"><div class="rml">{reg(f"mk{k}", 2048)}</div></div>' for k in list(range(L)) + ['E']]
    h.append(f'<div class="rnl">{reg("rn", 32)}</div><div class="rbzl">{reg("rbz", 2)}</div>')
    for r in range(RROWS):
        h.append(f'<div class="rrow rrow{r}">' + ''.join(f'<i class="rc" style="width: anchor-size(--c{cells(r * RCOLS + c)} width, {WOFF}px); left: {PADL + GUT + c * CW}px"><b></b></i>'
                                                        for c in range(RCOLS)) + '</div>')
    h += [f'<i class="rpm rpm{k}"></i>' for k in range(L)]
    return ''.join(h) + '</div>'

def html_app():
    """the lines the scan's sweep read (--rbnl, the rows it started with, less the prompt; on #app: it changes a frame after
    --ccgo drops) as a register the display reads (inside #app, like the scan's)"""
    return ('<div class="rbreg" style="--rbnl: inherit; --rbin: max(0, var(--rbnl) - 1)"><div class="rbsp"></div><div class="rbsub" style="view-timeline-name: --rclT"></div>'
            '<div class="rbpad"></div></div>')

def timelines(L):
    return [f'--mk{k}T' for k in list(range(L)) + ['E']] + ['--rnT', '--rgT', '--rclT', '--rbzT']
