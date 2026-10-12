"""ui_rb.py — the editor and its scan readback (from the CSS Text Readback page), adapted for the compiler page.

Changes from the original:
  - every custom property / anchor / container name is namespaced (rb*), so nothing meets the font CPU's names
    (--R, --t, --k, --v, --hit); the latch value is --lv; the visible read-back pane is hidden (the probes still lay out).
  - each latch cell carries the view-timeline register the compiler reads (ccpage5.cell_html).
  - the scan is frame-locked instead of time-driven: view-timeline registers keep last frame's clock (--rbtp) and a
    counter (--rbsc), so it advances exactly one column per frame at any frame rate (a time-driven scan skips
    columns when frames are slow). The range is fixed at P columns: a range derived from the editor's width
    flickers, because the trailing sentinel glyph's width is the code being read.
  - Run (#run, the first element of body; its state is read with sibling selectors, not :has()) makes the editor
    read-only; the scan does one more full sweep (--rbsr counts frames since Run), then stops and raises --rbrd,
    which shows the compiler. Edit lowers it again.
XHTML-safe output.
"""
import base64, html, subprocess, os
import sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'compiler'))
import ccpage5 as C

HERE = os.path.dirname(os.path.abspath(__file__))

def font_b64(P):
    bd = os.path.join(os.path.dirname(HERE), 'build'); os.makedirs(bd, exist_ok=True)
    out = os.path.join(bd, f'probe{P}.woff2')        # the readback font (built once, cached)
    if not os.path.exists(out):
        subprocess.run([sys.executable, os.path.join(HERE, 'mkfont2.py'), str(P), out], check=True, capture_output=True, cwd=bd)
    return base64.b64encode(open(out, 'rb').read()).decode()

def css_str(ch): return '"' + ch.replace('\\', '\\\\').replace('"', '\\"') + '"'

REGS = ['tp', 'sc', 'sr', 'rd']

def css(L, P, GS, SWEEPS=1, DWELL=1):
    NG = P // GS; GSW = GS * 10
    # per-frame driver state does NOT inherit: #app changes every frame, and inherited changes would restyle every cell
    regprops = '\n'.join(f'@property --rb{n} {{ syntax: "<integer>"; inherits: false; initial-value: 0; }} @property --rbn-{n} {{ syntax: "<integer>"; inherits: false; initial-value: 0; }}'
                          for n in REGS) + '\n' + '\n'.join(f'@property --{n} {{ syntax: "<integer>"; inherits: {"true" if n in ("rbin", "rbdet") else "false"}; initial-value: 0; }}'
                                                           for n in ('rbclk', 'rbrun', 'rbfresh', 'rbready', 'rbin', 'rbdet'))
    regkeys = '\n'.join(f'@keyframes rbk{n} {{ from {{ --rb{n}: 4096; }} to {{ --rb{n}: -1; }} }}' for n in REGS)
    ascii_symbols = ' '.join(css_str(chr(c)) for c in range(32, 127))
    g = []
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
/* scan driver, frame-locked: a register holds last frame's clock, so --rbfresh is 1 on the first pass of each frame and
   the scan counter advances exactly one column per frame (columns 1..R, R = the columns the editor is wide).
   Run: the scan finishes one more full sweep (--rbsr counts frames since Run), then stops and raises --rbrd, which
   lets the compiler see the text. The latches keep their values. */
#app {{
  container-name: rbscan;
  timeline-scope: --rbedw, --rbtpT, --rbscT, --rbsrT;
  animation: rbclkk .4096s linear infinite, rbwidth linear both, rbktp auto linear both, rbksc auto linear both, rbksr auto linear both;
  animation-timeline: auto, --rbedw, --rbtpT, --rbscT, --rbsrT;
  animation-range: normal, cover, normal, normal, normal;
  --rbng: clamp(1, round(up, (10000 * var(--rbp) / (1 - var(--rbp)) - 30) / {GSW}, 1), {NG});
  --rbR: {P};   /* fixed: the editor's width includes the trailing sentinel, whose width is the code being read, so a
                    width-derived range flickers between frames and the scan would skip columns */
  --rbrun: 0;
  --rbfresh: min(1, abs(var(--rbclk) - var(--rbtp)));
  --rbready: clamp(0, var(--rbsr) - {SWEEPS * DWELL} * var(--rbR) - 1, 1);
  /* the counter register already shows next frame's value in the later passes of a frame (Chrome re-runs style and layout
     while view timelines are stale); --rbfresh is 0 exactly then, so sc - 1 + fresh keeps the column the same for every
     pass of a frame. A column that changed mid-frame would lose its latch (the hold transition starts from last frame). */
  --rbscan: calc((1 - var(--rbrun) * var(--rbready)) * (mod(round(down, var(--rbsc) / {DWELL}), var(--rbR)) + 1));
  /* once the compiler has the text (--rbdet), the registers stop changing: no layout or timeline work per frame */
  --rbn-tp: calc(var(--rbclk) + var(--rbdet) * (var(--rbtp) - var(--rbclk))); --rbn-sc: mod(var(--rbsc) + var(--rbfresh) * (1 - var(--rbdet)), 4096);
  --rbn-sr: calc(var(--rbrun) * min(var(--rbsr) + var(--rbfresh) * (1 - var(--rbdet)), 4000)); --rbn-rd: calc(var(--rbrun) * var(--rbready));
  --rbdet: calc(var(--rbrun) * clamp(0, var(--rbsr) - {SWEEPS * DWELL} * var(--rbR) - 7, 1));    /* a few frames after the compiler took the text */
}}
#run:checked ~ #app {{ --rbrun: 1; }}
#run:checked ~ #app #ed {{ -webkit-user-modify: read-only; opacity: .75; }}
.rbreg {{ position: absolute; left: 0; top: 0; width: 1px; height: 4096px; overflow: hidden; visibility: hidden; }}
.rbreg > div {{ display: block; width: 1px; }} .rbreg > .rbsp {{ height: calc(var(--rbin) * 1px); }} .rbreg > .rbsub {{ height: 1px; }} .rbreg > .rbpad {{ height: 4096px; }}
.width-reader {{ position: absolute; left: 0; bottom: 100%; width: 1px; height: anchor-size(--rbed width, 0px);
  view-timeline: --rbedw block; view-timeline-inset: -10000px 100%; visibility: hidden; pointer-events: none; }}
#ed {{
  anchor-name: --rbed; font: 16px/24px "AsciiProbe", monospace;
  font-kerning: normal; font-feature-settings: normal; letter-spacing: 0; word-spacing: 0;
  white-space: pre; tab-size: 4; width: max-content; min-width: 100%; box-sizing: border-box; min-height: {L * 24 + 24}px;
  padding: 12px 14px; outline: none; caret-color: var(--accent); color: var(--ink);
}}
#ed * {{ all: unset; display: inline; }}
#ed > div {{ display: block; }}
#ed br {{ all: revert; }}
#ed::before, #ed > div::after {{ content: "\\2058"; }}
.rbout {{ anchor-name: --rbout; height: 0; visibility: hidden; }}
.probe {{ position: absolute; top: calc(anchor(--rbout top) + var(--rbk) * 24px); left: anchor(--rbout left);
  width: calc({P} * 10px); container-type: size; visibility: hidden; }}
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
    g.append('#ed::before { anchor-name: --rbs0; }')
    for k in range(1, L):
        g.append(f'#ed > div:nth-of-type({k})::after {{ anchor-name: --rbs{k}; }}')
    for k in range(L):
        g.append(f'.probe:nth-child({k + 1}) {{ --rbk: {k}; height: anchor-size(--rbs{k} width, 0px); }}')
    for k in range(1, L):
        g.append(f'#app:not(:has(#ed > div:nth-of-type({k}))) .probe:nth-child({k + 1}) {{ display: none; }}')
    g.append(f'#app:has(#ed > div:nth-of-type({L})) .limit {{ display: block; }}')
    for k in range(1, P + 1):
        G, j = (k - 1) // GS + 1, (k - 1) % GS + 1
        g.append(f'@container rbscan style(--rbscan: {k}) {{ #ed {{ font-variation-settings: "SCAN" {k}; }} .row > b:nth-child({G}) {{ --rbgj: {j}; }} .scanpos {{ --rbcol: {k}; }} }}')
    g.append('@property --rbcol { syntax: "<integer>"; inherits: false; initial-value: 0; }')
    g.append('.scanpos { counter-reset: rbcol var(--rbcol); } .scanpos::before { content: "scan column " counter(rbcol); }')
    g.append(C.cell_css())
    return '\n'.join(g)

def regs_html():
    """the scan registers (inside #app). --rbrdT is read outside #app (by the compiler's wrapper), so it is scoped on body."""
    return ''.join(f'<div class="rbreg" style="--rbn-{n}: inherit; --rbin: var(--rbn-{n})"><div class="rbsp"></div><div class="rbsub" style="view-timeline-name: --rb{n}T"></div><div class="rbpad"></div></div>'
                   for n in REGS)

def editor_html(text):
    lines = text.rstrip('\n').split('\n')
    first = html.escape(lines[0]) if lines[0] else ''
    return first + ''.join(f'<div>{html.escape(s) if s else "<br/>"}</div>' for s in lines[1:])

def probes_html(L, P, GS):
    NG = P // GS
    out = []
    for k in range(L):
        groups = ''.join('<b>' + ''.join(f'<i>{C.cell_html(k, g * GS + j)}</i>' for j in range(GS)) + '</b>' for g in range(NG))
        out.append(f'<div class="probe"><div class="row">{groups}</div></div>')
    return '<div class="probes" style="display: contents">' + ''.join(out) + '</div>'
