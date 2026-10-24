"""ui_rb.py — the editor and its scan readback (from the CSS Text Readback page), adapted for the compiler page.

Changes from the original:
  - every custom property / anchor / container name is namespaced (rb*), so nothing meets the font CPU's names
    (--R, --t, --k, --v, --hit); the latch value is --lv; the visible read-back pane is hidden (the probes still lay out).
  - each latch cell carries the view-timeline register the compiler reads (ccpage5.cell_html).
  - the scan is frame-locked instead of time-driven: view-timeline registers keep last frame's clock (--rbtp) and a
    counter (--rbsc), so it advances exactly one column per frame at any frame rate (a time-driven scan skips
    columns when frames are slow). The range is fixed at P columns: a range derived from the editor's width
    flickers, because the trailing sentinel glyph's width is the code being read.
  - the scan runs only after Run (#run, the first element of body; its state is read with sibling selectors, not
    :has()), which makes the editor read-only: one full sweep (--rbsr counts frames since Run), then it stops and raises
    --rbrd, which shows the compiler. Edit lowers it again. While the user edits, the editor's font axis stays at 0
    (scanning reshapes the text every frame, which made a selection's highlight jump) and the registers are frozen.
  - several editors (.ed: #ed, the page's program, then the sample programs), one shown at a time by the picker's radio
    buttons (#pk<i>, each right before its editor in .frame): a hidden editor is display: none, so the line anchors are
    the shown one's, and the per-line checks (:has) look at the editor after the checked radio button.
  - the REPL's page (repl): no Run. The scan runs again from its start whenever the editor's row count (rows with a sentinel:
    --rbcnt, a register) differs from the one the sweep started with (nl, taken while the sweep counter is 0), and the
    sweep's start also takes the lines the compiler may skip, plus one (dn: the line count the last finished run read, the
    display's --rn, or 0 if the editor now has fewer or a run was going on, --rbz; machine/replui.py). dn is 0 from the moment
    the sweep stops until the next starts: the frame --ccgo drops in still had the last sweep's value, and a clear for it
    (dn 1: from line 0) blanked the console of a run that kept it. Its last row, the prompt, isn't read.
XHTML-safe output.
"""
import base64, html, subprocess, os, re
import sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'compiler'))
import ccpage5 as C
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'py'))
import csslabel as lbl     # section and group comments in the output (../../shared/README.md#labels-in-generated-css)

HERE = os.path.dirname(os.path.abspath(__file__))

def font_b64(P):
    bd = os.path.join(os.path.dirname(HERE), 'build'); os.makedirs(bd, exist_ok=True)
    out = os.path.join(bd, f'probe{P}.woff2')        # the readback font (built once, cached)
    if not os.path.exists(out):
        subprocess.run([sys.executable, os.path.join(HERE, 'mkfont2.py'), str(P), out], check=True, capture_output=True, cwd=bd)
    return base64.b64encode(open(out, 'rb').read()).decode()

def css_str(ch): return '"' + ch.replace('\\', '\\\\').replace('"', '\\"') + '"'

REGS = ['tp', 'sc', 'sr', 'rd']
RREGS = REGS + ['nl', 'dn']     # (the REPL's page)
BLOCKS = ('p, pre, li, h1, h2, h3, h4, h5, h6, blockquote, dt, dd, tr, ul, ol, dl, table, thead, tbody, tfoot, caption, '
          'section, article, header, footer, aside, nav, main, figure, figcaption, address, details, summary, fieldset, '
          'legend, center, form')     # pasted block elements: each shows as a row of its own

def css(L, P, GS, SWEEPS=1, DWELL=1, EDS=1, repl=False):
    NG = P // GS; GSW = GS * 10; REGS_ = RREGS if repl else REGS
    # The rows' names (--rbs<k>, rows 0 .. L-1), from the sentinels' view progress in the editor's frame. Rows are 24px
    # from the editor's 12px top padding, and a sentinel's box (16px: the probe font's content area) starts at its row's
    # top, 12 + 24r (measured), so a name changes halfway between two rows' boxes. RX cuts the scrollport to the rows
    # read: the progress of a box of height SH at top t is (RX - t) / (RX + SH).
    RX, SH = 24 * L + 36, 16
    edge = lambda r: (RX - 24 * r) / (RX + SH)     # the progress where row r begins
    segs = [(0, edge(L), 'none')] + [(edge(r + 1), edge(r), f'--rbs{r}') for r in range(L - 1, -1, -1)] + [(edge(0), 1, 'none')]
    rowkeys = '@keyframes rbrow {\n' + '\n'.join(f'  {max(0, a * 100 + .001):.4f}%, {min(100, b * 100 - .001):.4f}% {{ anchor-name: {n}; }}'
                                                  for a, b, n in segs) + '\n}'
    # per-frame driver state does NOT inherit: #app changes every frame, and inherited changes would restyle every cell
    regprops = '\n'.join(f'@property --rb{n} {{ syntax: "<integer>"; inherits: false; initial-value: 0; }} @property --rbn-{n} {{ syntax: "<integer>"; inherits: false; initial-value: 0; }}'
                          for n in REGS_) + '\n' + '\n'.join(f'@property --{n} {{ syntax: "<integer>"; inherits: {"true" if n in ("rbin", "rbdet") else "false"}; initial-value: 0; }}'
                                                           for n in ('rbclk', 'rbrun', 'rbfresh', 'rbready', 'rbin', 'rbdet', 'rbfrz') + (('rbcnt',) if repl else ()))
    regkeys = '\n'.join(f'@keyframes rbk{n} {{ from {{ --rb{n}: 4096; }} to {{ --rb{n}: -1; }} }}' for n in REGS_ + (['cnt'] if repl else []))
    ascii_symbols = ' '.join(css_str(chr(c)) for c in range(32, 127))
    g = [lbl.group('Probe font, scan clock and latches', 'the readback font, the scan\'s driver state and the per-row latches')]
    g.append(f"""
@font-face {{ font-family: "AsciiProbe"; src: url(data:font/woff2;base64,{font_b64(P)}) format("woff2"); font-display: block; }}
@counter-style rbblank {{ system: cyclic; symbols: ""; }}
@counter-style rbascii {{ system: fixed 32; symbols: {ascii_symbols}; fallback: rbblank; }}
@property --rbp     {{ syntax: "<number>";  inherits: false; initial-value: 0; }}
@property --rbng    {{ syntax: "<integer>"; inherits: false; initial-value: 1; }}
@property --rbR     {{ syntax: "<integer>"; inherits: false; initial-value: 1; }}
@property --rbscan  {{ syntax: "<integer>"; inherits: false; initial-value: 0; }}
@property --rbgj    {{ syntax: "<integer>"; inherits: true;  initial-value: 0; }}
@property --rbglive {{ syntax: "<integer>"; inherits: true;  initial-value: 0; }}
@property --rbhit   {{ syntax: "<integer>"; inherits: false; initial-value: 0; }}
@property --lv      {{ syntax: "<integer>"; inherits: false; initial-value: -1; }}
{regprops}
@keyframes rbclkk {{ from {{ --rbclk: 0; }} to {{ --rbclk: 4096; }} }}
@keyframes rbwidth {{ from {{ --rbp: 0; }} to {{ --rbp: 1; }} }}
{regkeys}
{rowkeys}
/* scan driver, frame-locked: a register holds last frame's clock, so --rbfresh is 1 on the first pass of each frame and
   the scan counter advances exactly one column per frame (columns 1..R, R = the columns the editor is wide).
   It runs only after Run: one full sweep (--rbsr counts frames since Run), then it stops and raises --rbrd, which
   lets the compiler see the text. The latches keep their values. */
#app {{
  container-name: rbscan;
  timeline-scope: --rbedw, --rbtpT, --rbscT, --rbsrT{', --rbnlT, --rbcntT' if repl else ''};
  animation: rbclkk .4096s linear infinite, rbwidth linear both, rbktp auto linear both, rbksc auto linear both, rbksr auto linear both{', rbknl auto linear both, rbkdn auto linear both, rbkcnt auto linear both, krn auto linear both, krbz auto linear both' if repl else ''};
  animation-timeline: auto, --rbedw, --rbtpT, --rbscT, --rbsrT{', --rbnlT, --rbdnT, --rbcntT, --rnT, --rbzT' if repl else ''};
  animation-range: normal, cover, normal, normal, normal{', normal' * 5 if repl else ''};
  --rbng: clamp(1, round(up, (10000 * var(--rbp) / (1 - var(--rbp)) - 30) / {GSW}, 1), {NG});
  --rbR: {P};   /* fixed: the editor's width includes the trailing sentinel, whose width is the code being read, so a
                    width-derived range flickers between frames and the scan would skip columns */
  --rbrun: 0;
  --rbfresh: min(1, abs(var(--rbclk) - var(--rbtp)));
  --rbready: clamp(0, var(--rbsr) - {SWEEPS * DWELL} * var(--rbR) - 1, 1);
  /* the counter register already shows next frame's value in the later passes of a frame (Chrome re-runs style and layout
     while view timelines are stale); --rbfresh is 0 exactly then, so sc - 1 + fresh keeps the column the same for every
     pass of a frame. A column that changed mid-frame would lose its latch (the hold transition starts from last frame). */
  --rbscan: calc(var(--rbrun) * (1 - var(--rbready)) * (mod(round(down, var(--rbsc) / {DWELL}), var(--rbR)) + 1));
  /* while editing, and once the compiler has the text (--rbdet), the registers stop changing: no layout or timeline
     work per frame */
  --rbfrz: calc(1 - var(--rbrun) * (1 - var(--rbdet)));
  --rbn-tp: calc(var(--rbclk) + var(--rbfrz) * (var(--rbtp) - var(--rbclk))); --rbn-sc: mod(var(--rbsc) + var(--rbfresh) * (1 - var(--rbfrz)), 4096);
  --rbn-sr: calc(var(--rbrun) * min(var(--rbsr) + var(--rbfresh) * (1 - var(--rbdet)), 4000)); --rbn-rd: calc(var(--rbrun) * var(--rbready));
  --rbdet: calc(var(--rbrun) * clamp(0, var(--rbsr) - {SWEEPS * DWELL} * var(--rbR) - 7, 1));    /* a few frames after the compiler took the text */
}}
#run:checked ~ #app {{ --rbrun: 1; }}
{repl_run() if repl else ''}#run:checked ~ #app .ed {{ -webkit-user-modify: read-only; opacity: .75; }}
.rbreg {{ position: absolute; left: 0; top: 0; width: 1px; height: 4096px; overflow: hidden; visibility: hidden; }}
.rbreg > div {{ display: block; width: 1px; }} .rbreg > .rbsp {{ height: calc(var(--rbin) * 1px); }} .rbreg > .rbsub {{ height: 1px; }} .rbreg > .rbpad {{ height: 4096px; }}
.width-reader {{ position: absolute; left: 0; bottom: 100%; width: 1px; height: anchor-size(--rbed width, 0px);
  view-timeline: --rbedw block; view-timeline-inset: -10000px 100%; visibility: hidden; pointer-events: none; }}
.ed {{
  anchor-name: --rbed; font: 16px/24px "AsciiProbe", monospace;
  font-kerning: normal; font-feature-settings: normal; letter-spacing: 0; word-spacing: 0;
  /* nowrap, not pre: where newlines are preserved, Chrome pastes plain text and inserts Shift+Enter as '\n' inside one
     line div, and only the last row of it is read. Spaces stay visible as &nbsp; (Chrome's editor writes them where a
     space would collapse; the font maps U+00A0 to the space glyph). */
  white-space: nowrap; width: max-content; min-width: 100%; box-sizing: border-box; min-height: {L * 24 + 24}px;
  padding: 12px 14px; outline: none; caret-color: var(--accent); color: var(--ink);
}}
/* No rule may match the line divs: Chrome copies the properties of matched rules into style="" on every copied line.
   Pasted rich text shows in the editor's font and style: !important beats the style attribute a paste brings (a font,
   white-space: pre: the line would show one way and read another), and `all` leaves unicode-bidi: a <pre> or a div
   isolates (UA style), which makes its text a shaping run of its own, unread (ENGINE_NOTES 75). Blocks stay blocks, each
   a row with its own sentinel: a div nested in a line (lines pasted in the wrapper VS Code copies them in, and Chrome's
   editing in an empty line) shows as the line it is and reads as one. Whitespace collapses as in typed lines: a newline
   kept in pasted text (a <pre> code block) would start a row with no sentinel, so a code block shows and reads as one
   line (.merged says so). Embedded content shows nothing. */
.ed :not(div, br) {{ all: unset !important; display: inline !important; unicode-bidi: normal !important; }}
.ed div div, .ed > div[style] {{ all: unset !important; display: block !important; unicode-bidi: normal !important; }}
.ed :is({BLOCKS}) {{ display: block !important; }}
.ed :is(img, svg, video, audio, iframe, object, embed, canvas, input, select, textarea, button, hr, math) {{ display: none !important; }}
/* The sentinels lead their rows: line 0's the text typed straight into the editor, and every block that holds no block
   its own (a wrapper's would show as a blank row of its own; Chrome leaves no text beside the lines it nests). Leading,
   because <br> shows: an empty line's placeholder <br> is where the caret goes (hidden, ArrowUp/Down skipped the line
   and Enter in it lost lines), and a trailing sentinel after it made the line two rows tall. A <br> inside a line
   (Shift+Enter, or pasted) starts a row with no sentinel, unread: .unread says so. Each sentinel is named by the row it
   shows in (--rbs<k>, read by probe k): a discrete animation of anchor-name on a view timeline, whose progress is where
   the sentinel is in the editor's frame (ENGINE_NOTES 77). The inset cuts the frame's scrollport to the rows read, so a
   frame that grows keeps every row's name; the rows below have none. (Positional selectors could only name the
   editor's children, and a paste or a deletion restyled every rule that named one.) A wrapper whose first element is a
   <br> has a row of its own before its lines: Enter at the end of line 0 wraps the lines below in a div, after the new
   line's text and a <br>. */
.ed::before, .ed :is(div, {BLOCKS}):is(:not(:has(> :is(div, {BLOCKS}))), :has(> br:first-child))::before {{ content: "\\2058"; animation: rbrow auto linear;
  animation-timeline: view(block 0px calc(100% - {RX}px)); }}
/* an empty block after the lines: line 0 then sits in a block of its own even when it is all the editor holds. Without
   one, line 0's sentinel had another box (its progress put it 12px higher) and read as no row at all. */
.ed::after {{ content: ""; display: block; }}
.rbout {{ anchor-name: --rbout; height: 0; visibility: hidden; }}
/* the probes' contents lay out only from Run on (#app's --rbrun, a style query): while the user edits nothing reads
   them. content-visibility, not display: none, keeps their boxes, so Run doesn't build ~6,000 of them (ENGINE_NOTES 76;
   BENCHMARKS §18). The probe of a row that isn't there is 0px wide (its width is its sentinel's height, which the scan
   doesn't change, times P * 10), and its cells aren't laid out: 64 cells per probe, every frame of the scan, made a
   compile of FizzBuzz (9 rows of 24) 1.37x as long (BENCHMARKS §18). */
.probe {{ position: absolute; top: calc(anchor(--rbout top) + var(--rbk) * 24px); left: anchor(--rbout left);
  container-type: size; visibility: hidden; content-visibility: hidden; }}
@container (width: 0px) {{ .row {{ display: none; }} }}
.row {{ position: absolute; left: 0; top: 0; max-width: 100cqw; overflow: hidden; visibility: hidden; font: 15px/24px monospace; white-space: pre; }}
.row > b {{ font-weight: inherit; --rbglive: calc(min(1, var(--rbgj)) * (100cqh / 1px + 31 * sign(100cqh))); }}
.row i {{
  font-style: normal;
  --rbhit: calc(1 - min(1, abs(var(--rbgj) - sibling-index())));
  --lv: calc(var(--rbhit) * (var(--rbglive) + 1) - 1);
  transition: --lv 0s calc((1 - var(--rbhit)) * 1000000s);
  counter-reset: rbch var(--lv);
}}
.row i::before {{ content: counter(rbch, rbascii); }}
""")
    g.append(lbl.group('Line probes: one per editor row', 'probe k is as tall as the sentinel of row k is wide'))
    # (the REPL's page: row k is read only if row k + 1 is there, so the last row, the prompt, isn't)
    for k in range(L):
        there = f'min(1px, anchor-size(--rbs{k + repl} height, 0px))' if k + repl < L else '0px'
        g.append(f'.probe:nth-child({k + 1}) {{ --rbk: {k}; height: anchor-size(--rbs{k} width, 0px); width: calc({there} * {P * 10}); }}')
    g.append('@container rbscan style(--rbrun: 1) { .probe { content-visibility: visible; } }')
    # (:has() on the editors' section with child combinators: on #app it searched ~10,000 elements, per rule and editor,
    # and the picker's eleven editors made a compile ~1.7 s slower. The editor that shows is the one after the checked
    # radio button, so one set of rules serves every editor: per editor they cost ~10% of a compile with twelve samples)
    ed = '> .frame > .pkr:checked + .ed'
    g.append(f'#app > .pane:has({ed} > div:nth-of-type({L})) .limit {{ display: block; }}')
    g.append(f'#app > .pane:has({ed} pre) .merged {{ display: block; }}')
    # a row with no sentinel above one with a sentinel: row k absent while row k + 1 is there (a sentinel is 16px tall,
    # an absent row's anchor-size is 0). .unread is that tall, times 1.5, so it shows only then.
    gaps = ', '.join(f'anchor-size(--rbs{k + 1} height, 0px) - anchor-size(--rbs{k} height, 0px)' for k in range(L - 1))
    g.append(f'.scanpos {{ anchor-name: --rbscanpos; }}\n'
             f'.unread {{ position: absolute; left: anchor(--rbscanpos left); top: calc(anchor(--rbscanpos top) - 4px); overflow: hidden; '
             f'white-space: nowrap; font: .8rem/24px system-ui, sans-serif; color: #b00; height: calc(1.5 * max(0px, {gaps})); }}\n'
             '#run:checked ~ #app .unread { display: none; }')
    g.append(lbl.group(f'Scan: one rule per column ({P})', 'the probe font\'s SCAN axis picks the column whose code each glyph\'s width carries'))
    for k in range(1, P + 1):
        G, j = (k - 1) // GS + 1, (k - 1) % GS + 1
        g.append(f'@container rbscan style(--rbscan: {k}) {{ .ed {{ font-variation-settings: "SCAN" {k}; }} .row > b:nth-child({G}) {{ --rbgj: {j}; }} .scanpos {{ --rbcol: {k}; }} }}')
    g.append('@property --rbcol { syntax: "<integer>"; inherits: false; initial-value: 0; }')
    g.append('.scanpos { counter-reset: rbcol var(--rbcol); } .scanpos::before { content: "reading column " counter(rbcol); }'
             ' @container rbscan style(--rbscan: 0) { .scanpos { visibility: hidden; } }')
    g.append(lbl.group('Character cells: the registers the compiler reads'))
    g.append(C.cell_css())
    return '\n'.join(g)

def repl_run():
    """the REPL's page: the scan runs while the editor's row count (--rbcnt) is the one the sweep started with (the nl register),
    and a sweep's start takes it and the lines the compiler may skip + 1 (dn: the last finished run's line count, --rn, unless
    the editor now has fewer lines or a run was going on; 0 while the sweep is stopped)"""
    return ('#app { --rbrun: calc(1 - min(1, abs(var(--rbcnt) - var(--rbnl))));\n'
            '  --rbn-nl: calc(var(--rbnl) + (1 - min(1, var(--rbsr))) * (var(--rbcnt) - var(--rbnl)));\n'
            '  --rbn-dn: calc(var(--rbrun) * (var(--rbdn) + (1 - min(1, var(--rbsr))) * (1 + max(0, var(--rn)) * (1 - clamp(0, var(--rn) - var(--rbcnt) + 1, 1)) * (1 - var(--rbz)) - var(--rbdn)))); }\n')

def rcnt_html(L):
    """the REPL's page: the editor's row count as a register (inside #app): a box as wide as the rows with a sentinel are many
    (each 16px tall, an absent one 0), whose register reads its width"""
    w = ' + '.join(f'min(1px, anchor-size(--rbs{k} height, 0px))' for k in range(L))
    return (f'<div class="rcntw" style="position: absolute; left: 0; top: 0; height: 1px; visibility: hidden; container-type: inline-size; width: calc({w})">'
            '<div class="rbreg" style="--rbin: round(100cqi / 1px)"><div class="rbsp"></div><div class="rbsub" style="view-timeline-name: --rbcntT"></div><div class="rbpad"></div></div></div>')

def regs_html(repl=False):
    """the scan registers (inside #app). --rbrdT is read outside #app (by the compiler's wrapper), so it is scoped on body
    (and the REPL's --rbdnT: by the compiler's, RAM's and the CPU's wrappers)."""
    return ''.join(f'<div class="rbreg" style="--rbn-{n}: inherit; --rbin: var(--rbn-{n})"><div class="rbsp"></div><div class="rbsub" style="view-timeline-name: --rb{n}T"></div><div class="rbpad"></div></div>'
                   for n in (RREGS if repl else REGS))

def editor_html(text):
    """the first line straight in the editor (line 0, after #ed::before), every other line in its own div. (Enter in
    line 0, with lines below, makes Chrome nest all of them in one new div; nested lines read as they show.)"""
    first, *rest = [nbsp(html.escape(s)) if s else '<br/>' for s in text.rstrip('\n').split('\n')]
    return first + ''.join(f'<div>{s}</div>' for s in rest)

def nbsp(s):
    """the spaces of a line as Chrome's editor writes them under white-space: nowrap: a run at either end of the line,
    and all but the last space of a run inside it, become U+00A0, so none collapses"""
    return re.sub(' +', lambda m: '\u00a0' * len(m.group()) if m.start() == 0 or m.end() == len(s) else '\u00a0' * (len(m.group()) - 1) + ' ', s)

def probes_html(L, P, GS):
    NG = P // GS
    out = []
    for k in range(L):
        groups = ''.join('<b>' + ''.join(f'<i>{C.cell_html(k, g * GS + j)}</i>' for j in range(GS)) + '</b>' for g in range(NG))
        out.append(f'<div class="probe"><div class="row">{groups}</div></div>')
    return '<div class="probes" style="display: contents">' + ''.join(out) + '</div>'
