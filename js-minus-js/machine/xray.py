"""xray.py — the X-ray page (`make xray`: XRAY=1 UI=1 machine/gen_css.py -> build/js_xray.xhtml): the editor page with its
work shown, as slowly as you like. Still no script: everything below is CSS reading the same state the machine runs on.

  scan     the editor's sentinel glyphs show (their width is the code of the column being read), and the latches the scan
           fills show as a grid, the column being read highlighted; the scan's clock is quantized (--xsd ms a column)
  lex      the character chain is gated a line at a time (ccpage5.xray_*): a line's band lights when its levels exist,
           and a mark under a character says the lexer finished token t there (colour: its kind)
  parse    the token chain is gated a level at a time: each level shows its row of the parse table (the token, the mode
           the parser is in after it, the instructions it emitted and where); the listing fills as the words land in RAM
  run      the CPU's pass is gated by a tick (--xr-t: the clock divided by --xdiv, or the Step checkbox), and each level of
           the chain shows the instruction it ran (or where it stalled), latched until the next pass; the registers, both
           caches, RAM (globals, stack) and the listing (pc highlighted) read the machine's own registers and anchors.

Readers of RAM anchors are absolutely positioned at a large negative offset (a reader is as wide as the word it reads,
up to 1.5 M px, and nothing left of or above the page extends its scroll area); their visible children are placed back on
the page. The page's other numbers are counters of registered integers.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, '..', 'compiler'), os.path.join(HERE, '..', '..', 'shared', 'py')]
import cc_ref as R, csslabel as lbl

WOFF = 1 << 20
FAR = 1600000          # a reader's offset off the page (its width is at most 1.5 * 2^20 px)
# speeds: (id, label, CPU tick: the clock (600 a second) divided by, scan ms a column, lexer gate a line, parser gate a level)
SPEEDS = [('full', 'full speed', 1, 1, '0s', '0s'), ('fast', 'fast', 30, 16, '150ms', '60ms'),
          ('slow', 'slow', 150, 60, '500ms', '220ms'), ('crawl', 'crawl', 600, 160, '1200ms', '600ms'),
          ('step', 'step', None, 60, '500ms', '220ms')]
DEFSPEED = 'slow'
KMAX = [1, 4, 32]
DEFK = 32

# ---------------- geometry (document px; #app, #cc and #tcr sit at the page's origin, checked by tools/xray_check.js)
BAR_H = 64
APP_X, APP_Y = 16, 76                      # #app: the editor pane, then the scan grid at RB inside it
RB_X, RB_Y = 736, 50
CW, LH = 8, 15                             # the scan grid's cell
CONS_X, CONS_Y = 1310, APP_Y + 62
GLOB_X, GLOB_Y, NGLOB = 1450, APP_Y + 62, 32
STK_X, STK_Y, NSTK = 1580, APP_Y + 62, 40
ROWB = 830
REG_X, REG_Y = 16, ROWB + 78
TRACE_X, TRACE_Y, TRH = 16, ROWB + 160, 15
LIST_X, LIST_Y, LIST_COLS, LIST_ROWS, LIST_W, LIST_H = 620, ROWB + 64, 3, 56, 236, 14
DC_X, DC_Y, CROW = 1340, ROWB + 64, 14
IC_X, IC_Y = 1340, ROWB + 64 + 32 * 14 + 44
ROWC = LIST_Y + LIST_ROWS * LIST_H + 30
TOK_X, TOK_Y, TOK_COLS, TOK_W, TOK_H = 16, ROWC + 56, 10, 168, 38
PAGE_W = 1716

def chain_args(P):
    """what ccpage5 needs to place the chain's own elements"""
    return {'grid': [APP_X + RB_X, APP_Y + RB_Y, CW, LH], 'tok': [TOK_X, TOK_Y, TOK_COLS, TOK_W, TOK_H], 'P': P}

def css_str(s): return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
def cstyle(name, first, syms, fallback='xblank'):
    return f'@counter-style {name} {{ system: fixed {first}; symbols: {" ".join(css_str(x) for x in syms)}; fallback: {fallback}; }}'
def eq(x, c): return f"(1 - min(1, abs(({x}) - ({c}))))"

def counter_styles(entries):
    ops = list(R.OPN)
    modes = {v: k for k, v in vars(R).items() if k.startswith('S_') and isinstance(v, int) and 0 <= v < R.NMODES}
    pun = {}
    for (a, b), c in R.TWO.items(): pun[c] = chr(a) + chr(b)
    pun.update({17: '>>>', 21: '<<=', 22: '>>=', 23: '>>>=', R.T_NL: '⏎', R.T_THIS: 'this', R.T_NEW: 'new', R.T_PROTO: '__proto__',
                R.T_PTYPE: 'prototype'})
    pun.update({c: chr(c) for c in range(33, 127)})
    rt = ['(none)'] + [n for n, _ in sorted(entries.items(), key=lambda e: e[1])]
    return [cstyle('xop', 0, ops), cstyle('xmode', 0, [modes.get(i, f'mode {i}')[2:] for i in range(R.NMODES)], 'decimal'),
            cstyle('xkw', 1, list(R.KW)), cstyle('xpun', 1, [pun.get(i, f'#{i}') for i in range(1, 127)], 'decimal'),
            cstyle('xspec', 0, ['Infinity', '-Infinity', 'true', 'false', 'null', 'undef', 'NaN', '-0']),
            cstyle('xrt', 0, rt), '@counter-style xblank { system: cyclic; symbols: ""; }']

# ---------------- registered properties
# (inherited: what a pseudo-element or a child reads)
INH = ['xo', 'xa', 'xb', 'xc', 'xf', 'xak', 'xbk', 'xck', 'xav', 'xbv', 'xcv', 'xw1', 'xph', 'xgo', 'xt', 'xpc', 'xwk', 'xws', 'xT', 'xd',
       'xvic', 'xok', 'xrf', 'xon', 'xrt', 'xl', 'xtk', 'xtn', 'xpw', 'xlv', 'xpic']
LOC = ['xw', 'xwa', 'xrpc', 'xpres', 'xfill', 'xhere', 'xfp', 'xra', 'xrb', 'xrc', 'xrd', 'xre', 'xmf']
def props():
    return ([lbl.group('X-ray: registered properties')] +
            [f'@property --xr-{n[1:]} {{ syntax: "<integer>"; inherits: true; initial-value: 0; }}' for n in INH] +
            [f'@property --xr-{n[1:]} {{ syntax: "<integer>"; inherits: false; initial-value: 0; }}' for n in LOC])

# ---------------- an instruction's text: op, A, B, C on an element (inherited --xr-o --xr-a --xr-b --xr-c) and its spans
FORMS = {1: ('LOADK', 'PRINTK', 'CALL'), 2: ('JMP', 'HALT', 'TENTER'), 4: ('JZ', 'JNZ'), 5: ('MOV', 'NEG', 'NOT', 'PRINT', 'GETFP'),
         6: ('PUTC', 'RET'), 3: tuple(o for o in R.OPN if o.startswith('J') and o not in ('JMP', 'JZ', 'JNZ'))}
def insn_decls():
    """--xr-f (the operands' form, cc_ref.disasm's), the operands' kinds and shown values"""
    f = "calc(" + " + ".join(f"{k} * {eq('var(--xr-o)', R.OP[o])}" for k, os_ in FORMS.items() for o in os_) + ")"
    d = [f"--xr-f: {f};", "--xr-w1: calc((var(--xr-b) - 512) * 1024 + var(--xr-c));"]
    for n in 'abc':
        o = f"var(--xr-{n})"
        d += [f"--xr-{n}k: calc(clamp(0, {o} - 255, 1) + clamp(0, {o} - 767, 1) + clamp(0, {o} - 1015, 1));",
              f"--xr-{n}v: calc({o} - 256 * clamp(0, {o} - 255, 1) - 640 * clamp(0, {o} - 767, 1) - 120 * clamp(0, {o} - 1015, 1));"]
    return " ".join(d)
def opnd(n):
    return f'if(style(--xr-{n}k: 0): "G" counter(x{n}v); style(--xr-{n}k: 1): "F" counter(x{n}v); style(--xr-{n}k: 2): "#" counter(x{n}v); else: counter(x{n}v, xspec))'
def insn_css(sc, counters=''):
    """the spans .io .ia .ib .ic of an instruction under the selector sc (counters: the element's own, beside the instruction's)"""
    return [f"{sc} {{ {insn_decls()} counter-reset: xo var(--xr-o) xav var(--xr-av) xbv var(--xr-bv) xcv var(--xr-cv) xja calc(2 * var(--xr-a)) xw1 var(--xr-w1) xra var(--xr-a) {counters}; }}",
            f"{sc} .io::after {{ content: counter(xo, xop); }}",
            # A: a jump's target (an instruction pair: its address is 2 A), LOADK's operand, CALL's / PRINTK's number
            f"{sc} .ia::after {{ content: if(style(--xr-f: 2) or style(--xr-f: 3) or style(--xr-f: 4): \"@\" counter(xja);"
            f" style(--xr-f: 6): \"\"; style(--xr-f: 1) and style(--xr-o: {R.OP['LOADK']}): {opnd('a')}; style(--xr-f: 1): counter(xra);"
            f" style(--xr-o: {R.OP['PRINT']}): counter(xra); else: {opnd('a')}); }}",
            f"{sc} .ib::after {{ content: if(style(--xr-f: 1): \", \" counter(xw1); style(--xr-f: 2): \"\"; style(--xr-f: 6): {opnd('b')}; else: \", \" {opnd('b')}); }}",
            f"{sc} .ic::after {{ content: if(style(--xr-f: 0) or style(--xr-f: 3): \", \" {opnd('c')}; else: \"\"); }}"]
INSN = '<b class="io"></b> <b class="ia"></b><b class="ib"></b><b class="ic"></b>'

# a word's text by its range (cc_ref's tags: a string, array, object, function, boxed double, closure env; the specials)
def word_css(sc):
    return [f"{sc} {{ --xr-wk: calc(round(down, var(--xr-w) / 32768) + 16); --xr-ws: clamp(0, var(--xr-w) - {R.SPV0 - 1}, 1); --xr-wa: mod(var(--xr-w), 32768);"
            f" counter-reset: xwv var(--xr-w) xwa var(--xr-wa) xws calc(var(--xr-w) - {R.SPV0}); }}",
            f"{sc}::after {{ content: if(style(--xr-ws: 1): counter(xws, xspec); style(--xr-wk: 8): \"s\" counter(xwa); style(--xr-wk: 24): \"a\" counter(xwa);"
            " style(--xr-wk: 1): \"o\" counter(xwa); style(--xr-wk: 2): \"f\" counter(xwa); style(--xr-wk: 3): \"d\" counter(xwa);"
            " style(--xr-wk: 4): \"e\" counter(xwa); style(--xr-wk: 0): \"p\" counter(xwa); else: counter(xwv));"
            " color: if(style(--xr-ws: 1): var(--col-spec); style(--xr-wk: 8): var(--col-str); style(--xr-wk: 24) or style(--xr-wk: 1) or style(--xr-wk: 2) or style(--xr-wk: 3) or style(--xr-wk: 4) or style(--xr-wk: 0): var(--col-ref);"
            " else: inherit); }"]

# ---------------- controls: inputs right after #run (siblings of #app, #ccw, #clkw, the bar, the phase reader)
def inputs_html():
    s = "".join(f'<input type="radio" name="xspd" id="xs-{i}" class="runcb"{" checked=\"checked\"" if i == DEFSPEED else ""}/>' for i, *_ in SPEEDS)
    s += "".join(f'<input type="radio" name="xk" id="xk{k}" class="runcb"{" checked=\"checked\"" if k == DEFK else ""}/>' for k in KMAX)
    return s + '<input type="checkbox" id="xstep" class="runcb"/>'

def controls_css(UIP):
    out = [lbl.group('X-ray: speed, instructions per pass, step', 'radio buttons after #run set the gates\' and the clock\'s lengths on #app, #ccw and #clkw')]
    for i, _, div, sd, lg, tg in SPEEDS:
        cpu = '--xspd: step; --xdiv: 1;' if div is None else f'--xspd: clock; --xdiv: {div};'
        if div == 1: cpu += ' --xiss: 2;'     # (full speed: two passes a frame, as the editor page)
        out.append(f'#xs-{i}:checked ~ #clkw {{ {cpu} }} #xs-{i}:checked ~ #app {{ --xsd: {sd}; }} #xs-{i}:checked ~ #ccw {{ --xlg: {lg}; --xtg: {tg}; }}'
                   f' #xs-{i}:checked ~ .xbar label[for="xs-{i}"] {{ background: var(--col-accent); color: #fff; border-color: var(--col-accent); }}')
    out += [f'#xk{k}:checked ~ #clkw {{ --xkmax: {k}; }} #xk{k}:checked ~ .xbar label[for="xk{k}"] {{ background: var(--col-accent); color: #fff; border-color: var(--col-accent); }}' for k in KMAX]
    out += ['#xstep:checked ~ #clkw { --xstep: 1; }',
            '.xbar .xstepb { display: none; } #xs-step:checked ~ .xbar .xstepb { display: inline-block; }',
            '#xstep:focus-visible ~ .xbar .xstepb { outline: 2px solid var(--col-ink); outline-offset: 2px; }',
            '#xs-step:not(:checked) ~ #clkw .xstepnote { display: none; }']
    return out

def bar_html():
    sp = "".join(f'<label for="xs-{i}">{lb}</label>' for i, lb, *_ in SPEEDS)
    kk = "".join(f'<label for="xk{k}">{k}</label>' for k in KMAX)
    return (f'<div class="xbar"><h1>JavaScript in CSS <span>X-ray</span></h1>'
            f'<label class="xrun" for="run"><span></span></label>'
            f'<div class="xseg" title="how fast the scan, the compiler\'s levels and the CPU\'s passes go">{sp}</div>'
            f'<label class="xstepb" for="xstep">Step &#9656; one pass</label>'
            f'<div class="xseg"><span class="xsegl">instructions per pass</span>{kk}</div></div>')

# ---------------- static cards behind the panels (titles and captions); early in the body, so everything paints over them
def card(x, y, w, h, title, cap):
    return f'<div class="xcard" style="left: {x}px; top: {y}px; width: {w}px; height: {h}px"><h2>{title}</h2><p>{cap}</p></div>'
def cards_html(UIL, UIP):
    gw = (UIP + 1) * CW + 16
    c = [card(APP_X + RB_X - 10, APP_Y, gw + 8, RB_Y + UIL * LH + 150, '1&#8202;&#183;&#8202;Scan, 2&#8202;&#183;&#8202;Lex',
              'What CSS read back from the editor, and where the lexer ended each token.'),
         card(CONS_X - 10, APP_Y, 136, CONS_Y - APP_Y + 16 * 20 + 26, 'Console', '144 RAM cells'),
         card(GLOB_X - 10, APP_Y, 124, GLOB_Y - APP_Y + NGLOB * 13 + 16, 'Globals', 'RAM, from G25'),
         card(STK_X - 10, APP_Y, 130, STK_Y - APP_Y + NSTK * 13 + 16, 'Stack', 'RAM from sp0; yellow: fp'),
         card(REG_X - 10, ROWB, 594, TRACE_Y - ROWB + 32 * TRH + 14, '4&#8202;&#183;&#8202;Run: the CPU',
              'Registers are view timelines read back each pass. A pass is one style recalc: the chain below runs up to the chosen '
              'number of instructions, one nested element each (fetch &#8250; execute &#8250; commit); the first cache miss stops it.'),
         card(LIST_X - 10, ROWB, LIST_COLS * LIST_W + 18, LIST_ROWS * LIST_H + 48, '3&#8202;&#183;&#8202;Code: what the compiler emitted',
              'Each instruction is two overlay elements named after their RAM cells (anchor-name --c&lt;cell&gt;); these rows read them back. A forward jump reads @0 until its label is defined (the label is an anchor whose width the word adds). pc is highlighted.'),
         card(DC_X - 10, ROWB, PAGE_W - DC_X + 10, IC_Y - ROWB + 16 * CROW + 14, 'Caches',
              'Data: 16 sets &#215; 2 ways of 4 words, all custom properties. Code: 16 lines. Blue: filled this pass.'),
         card(TOK_X - 10, ROWC, TOK_COLS * TOK_W + 18, 60, '3&#8202;&#183;&#8202;Parse: one element per token',
              'Each token level picks its parser variant with @container style(--mode) and style(--token), and shows: the token, the mode after it, the instructions it emitted (+n @address).')]
    c.append(f'<div class="xnote" style="left: {APP_X + RB_X}px; top: {APP_Y + RB_Y + UIL * LH + 8}px; width: {gw - 8}px">'
             '<b>Scan.</b> The editor\'s font has a variable axis, SCAN. At SCAN = N its substitution rules copy column N\'s character '
             'code into the width of the sentinel glyph at each line\'s end (the orange boxes). anchor-size() measures each one, and a '
             'transition of 0 s with a delay of 1,000,000 s latches it into this grid; the yellow column is the one being read. '
             '<b>Lex.</b> The lexer is one element per character, nested 1,561 deep; a line lights up when its elements exist, and a '
             'coloured mark under a character means a token ended there (number: its index; blue a number, green a name, orange a string, grey punctuation).</div>')
    return '<div class="xcards">' + "".join(c) + '</div>'

# ---------------- inside #cpu: registers, the trace's frame, the caches, the listing, RAM; all from the registers / anchors
def far(x, y): return f'left: {x + FAR}px; top: {y + FAR}px'
XNO = set(os.environ.get('XNO', '').split(','))     # (measurement: panels left out)
def cpu_html(K, NL, ISET, entries, code_cells, sp0, data_base, rom):
    h = []
    # registers
    rows = [('pc', 'var(--pc)'), ('fp', 'var(--fp)'), ('pst', 'var(--pst)'), ('steps', 'var(--steps)'),
            ('halt', 'var(--halt)'), ('pending', 'var(--pend)'), ('console', 'var(--optr)')]
    h.append('<div class="xregs">' + "".join(f'<span><i>{n}</i><b class="xn" style="--xr-w: {e}"></b></span>' for n, e in rows) + '</div>')
    h.append('<div class="xwhere"></div><div class="xmiss"></div><div class="xstepnote">Step mode: each click on Step runs one pass.</div>')
    h.append('<b class="xha"></b>' + ('' if 'trace' in XNO else trace_rows(K)))
    # data cache
    for k in ([] if 'cache' in XNO else range(NL)):
        h.append(f'<b class="xdc" style="top: {DC_Y + k * CROW}px; --xr-T: var(--T{k}); --xr-fill: calc({eq("var(--fk1)", k + 1)} + {eq("var(--gk1)", k + 1)});'
                 f' --xr-vic: calc{eq(f"var(--F{k // 2})", k % 2)}"><i>{k // 2:2}.{k % 2}</i><b class="xtag"></b>' +
                 "".join(f'<b class="xwd" style="--xr-w: var(--W{k}_{j})"></b>' for j in range(4)) + '</b>')
    for i in ([] if 'cache' in XNO else range(ISET)):
        h.append(f'<b class="xic" style="top: {IC_Y + i * CROW}px; --xr-T: var(--IT{i}); --xr-fill: calc({eq("var(--ik1)", i + 1)} + {eq("var(--ig1)", i + 1)})">'
                 f'<i>{i:2}</i><b class="xtag"></b>' + "".join(f'<b class="xwd" style="--xr-w: var(--IW{i}_{j})"></b>' for j in range(4)) + '</b>')
    # listing: a reader per instruction pair, width word0, height word1 (+2^20 each: 0 when absent)
    cb = R.LAYOUT['code_base']
    for i in ([] if 'list' in XNO else range(min(LIST_COLS * LIST_ROWS, code_cells // 2))):
        c, r = divmod(i, LIST_ROWS); a = cb + 2 * i; cell = a - rom
        h.append(f'<b class="xlr" style="width: anchor-size(--c{cell} width, 0px); height: anchor-size(--c{cell + 1} width, 0px)">'
                 f'<b class="xli" style="{far(LIST_X + c * LIST_W, LIST_Y + r * LIST_H)}; --xr-here: calc{eq("var(--pc)", a)}"><i>{a}</i> {INSN}</b></b>')
    # RAM: globals, stack
    for i in ([] if 'ram' in XNO else range(NGLOB)):
        g = 25 + i
        h.append(f'<b class="xram" style="width: anchor-size(--c{data_base + g - rom} width, {WOFF}px)"><b style="{far(GLOB_X, GLOB_Y + i * 13)}"><i>G{g}</i><b class="xwd"></b></b></b>')
    for i in ([] if 'ram' in XNO else range(NSTK)):
        a = sp0 + i
        h.append(f'<b class="xram" style="width: anchor-size(--c{a - rom} width, {WOFF}px)"><b style="{far(STK_X, STK_Y + i * 13)}; --xr-fp: calc{eq("var(--fp)", a)}">'
                 f'<i>{a}</i><b class="xwd"></b></b></b>')
    return "".join(h)

# the trace: each level's registers (a: 4 pc + ok + 1, 0 before its first pass; b, c: the instruction's words; d, e: the
# values of B and C; f: the missing block on a stall, else pst)
TRF = [('a', 1 << 17, 0), ('b', 1 << 20, 0), ('c', 1 << 20, 1 << 19), ('d', WOFF, WOFF // 2), ('e', WOFF, WOFF // 2), ('f', 32768, 0)]
def trace_regs(K): return [] if 'tregs' in XNO else [(f"xr-t{L}{f}", H, O, f"var(--xr-t{L}{f})") for L in range(1, K + 1) for f, H, O in TRF]
def trace_rows(K):
    return "".join(f'<b class="xr" style="top: {TRACE_Y + (L - 1) * TRH}px; ' + "; ".join(f"--xr-r{f}: var(--xr-t{L}{f})" for f, _, _ in TRF) +
                   f'"><i>{L:2}</i><b class="xpc"></b> {INSN}<b class="xst"></b></b>' for L in range(1, K + 1))

def tail_html(UIL, TMAX):
    """end of the body: the phase bar's readers (they read anchors from #cc, #tcr and #cpu, which come earlier)"""
    return ('<b class="xph"><b class="xpills" style="' + far(330, 12) + '">' +
            "".join(f'<b class="xp{i}">{n}</b>' for i, n in enumerate(['edit', 'scan', 'lex', 'parse', 'run', 'halt'])) + '</b></b>'
            f'<b class="xpg"><b class="xpgt" style="{far(334, 42)}"></b></b>')

# ---------------- the CSS
def css(UIL, UIP, COLS, ROWS, K, NL, entries, opn_count):
    gw = (UIP + 1) * CW
    rtn = sorted(entries.values())
    rti = "calc(" + " + ".join(f"clamp(0, var(--pc) - {a - 1}, 1)" for a in rtn) + ")"
    o = [lbl.section('X-ray', 'machine/xray.py: the page shows its work (layout, panels, the chain\'s trace)')]
    o += counter_styles(entries)
    o += [lbl.group('Colours and layout'),
          ':root { --col-ink: #17212b; --col-muted: #5b6875; --col-rule: #d5dbe1; --col-card: #fff; --col-paper: #eef1f4; --col-accent: #2456c9;'
          ' --col-bad: #fde2e1; --col-num: #2f7ed8; --col-id: #2e9d57; --col-str: #d0761b; --col-punct: #8d99a6; --col-lexed: #dfeafc; --col-hit: #fff3b0;'
          ' --col-ok: #2e9d57; --col-miss: #c93a2e; --col-idle: #b8c1ca; --col-spec: #8a4fd0; --col-ref: #b0476f; --col-fill: #d8e6ff; }',
          f'body {{ background: var(--col-paper); min-width: {PAGE_W + 16}px; min-height: {TOK_Y + 400}px; }}',
          f'.xbar {{ position: fixed; z-index: 10; left: 0; top: 0; width: {PAGE_W + 16}px; height: {BAR_H}px; box-sizing: border-box; padding: 0 16px;'
          ' display: flex; align-items: flex-start; padding-top: 12px; gap: 14px; background: #17212b; color: #fff; font: 13px system-ui, sans-serif; }',
          '.xbar h1 { font-size: 16px; font-weight: 650; margin: 0 6px 0 0; white-space: nowrap; } .xbar h1 span { color: #8fb4ff; font-weight: 500; }',
          '.xbar .xseg { display: flex; gap: 0; align-items: center; } .xbar .xseg:first-of-type { margin-left: 390px; } .xbar h1 { margin-top: 4px; }',
          '.xbar .xseg label { cursor: pointer; padding: 5px 9px; border: 1px solid #3b4a5a; color: #c9d4df; margin-left: -1px; user-select: none; }',
          '.xbar .xseg label:first-of-type { border-radius: 5px 0 0 5px; } .xbar .xseg label:last-child { border-radius: 0 5px 5px 0; }',
          '.xsegl { color: #8d99a6; margin-right: 8px; }',
          '.xstepb { cursor: pointer; padding: 5px 12px; border-radius: 5px; background: #f0b429; color: #17212b; font-weight: 600; user-select: none; }',
          '.xrun { cursor: pointer; font-weight: 600; padding: 6px 14px; border-radius: 6px; background: var(--col-accent); color: #fff; user-select: none; white-space: nowrap; }',
          '.xrun span::before { content: "\\25B6  Run"; } #run:checked ~ .xbar .xrun { background: #5b6875; } #run:checked ~ .xbar .xrun span::before { content: "\\270E  Edit"; }',
          '.xcards { position: absolute; left: 0; top: 0; }',
          '.xcard { position: absolute; box-sizing: border-box; padding: 6px 10px; background: var(--col-card); border: 1px solid var(--col-rule); border-radius: 8px;'
          ' font: 12px/1.35 system-ui, sans-serif; color: var(--col-muted); overflow: hidden; }',
          '.xcard h2 { font-size: 13px; color: var(--col-ink); margin: 0 0 1px; } .xcard p { margin: 0; max-width: 100%; white-space: normal; }',
          '.xnote { position: absolute; font: 12px/1.4 system-ui, sans-serif; color: var(--col-muted); } .xnote b { color: var(--col-ink); }',
          # the editor page's parts moved into this layout
          f'#app {{ position: absolute; left: {APP_X}px; top: {APP_Y}px; margin: 0; padding: 0; width: {RB_X + gw + 20}px; height: {RB_Y + UIL * LH + 520}px; display: block; }}',
          '#app > header, #app > .notes { display: none; } #app .pane { width: 700px; } #app .bar { margin-bottom: 4px; }',
          f'#app .rbout {{ position: absolute; left: {RB_X}px; top: {RB_Y}px; height: 0; }}',
          f'#app .probe {{ top: calc(anchor(--rbout top) + var(--rbk) * {LH}px); }}',
          f'#app .row {{ visibility: visible; font: 12px/{LH}px ui-monospace, monospace; color: var(--col-ink); max-width: none; }}',
          f'#app .row i {{ display: inline-block; width: {CW}px; text-align: center; }}',
          '@container style(--rbhit: 1) { #app .row i::before { background: var(--col-hit); outline: 1px solid #e0b400; } }',
          '#run:checked ~ #app .ed::before, #run:checked ~ #app .ed > div::after { background: #ffd7a8; outline: 1px solid #d0761b; }',
          f'.cons {{ position: absolute; left: {CONS_X - 8}px; top: {CONS_Y - 8}px; }}',
          '.cst { z-index: 11; left: 716px; top: 43px; } .cstv { color: #c9d4df; width: 420px; font-size: 12px; } .cst2 { z-index: 11; left: 1000px; top: 43px; }',
          '#run:checked ~ .cst .cstv::before { color: #fff; }',
          '#cpu .head { display: none; }',
          '#cc, #tcr { contain: size layout style; }']
    o += controls_css(UIP)
    # phase bar: lexd + 2 ccdone + 4 halt; with run and ccgo: 0 edit, 1 scan, 2 lex, 3 parse, 4 run, 5 halt
    o += [lbl.group('X-ray: the phase bar', 'a reader of the compiler\'s and the CPU\'s anchors'),
          f'.xph {{ position: fixed; z-index: 11; left: {-FAR}px; top: {-FAR}px; container-type: size; animation: kccgo auto linear both; animation-timeline: --rbrdT;'
          ' width: calc(anchor-size(--xlexd width, 0px) + 2 * anchor-size(--ccdone width, 0px) + 4 * anchor-size(--xhalt width, 0px)); height: 1px; }',
          '#run:checked ~ .xph { --run: 1; }',
          '.xpills { position: absolute; display: flex; gap: 4px; --xr-w: round(100cqi / 1px);'
          ' --xr-ph: calc(var(--run) * (1 + var(--ccgo) * (1 + mod(var(--xr-w), 2) + mod(round(down, var(--xr-w) / 2), 2) + round(down, var(--xr-w) / 4)))); }',
          '.xpills > b { font: 600 11px/1 system-ui, sans-serif; padding: 5px 8px; border-radius: 99px; background: #2b3947; color: #8d99a6; text-transform: uppercase; letter-spacing: .05em; }']
    o += [f'.xpills > .xp{i} {{ background: if(style(--xr-ph: {i}): {c}; else: #2b3947); color: if(style(--xr-ph: {i}): #fff; else: #8d99a6); }}'
          for i, c in enumerate(['#5b6875', '#e0b400', '#2f7ed8', '#2e9d57', '#d0761b', '#c93a2e'])]
    o += [f'.xpg {{ position: fixed; z-index: 11; left: {-FAR}px; top: {-FAR}px; container-type: size; width: anchor-size(--xlprog width, 0px);'
          ' height: calc(anchor-size(--xtprog width, 0px) * 1000 + anchor-size(--xntf width, 0px)); animation: kccgo auto linear both; animation-timeline: --rbrdT; }',
          '.xpgt { position: absolute; font: 12px ui-monospace, monospace; color: #c9d4df; white-space: nowrap; --xr-l: round(100cqi / 1px); --xr-pw: round(100cqb / 1px);'
          ' --xr-tk: round(down, var(--xr-pw) / 1000); --xr-tn: mod(var(--xr-pw), 1000); counter-reset: xl var(--xr-l) xt var(--xr-tk) xn var(--xr-tn); }',
          f'.xpgt::after {{ content: if(style(--ccgo: 0): ""; style(--xr-l: 0): ""; else: "lexed " counter(xl) "/{UIL} lines \\B7  parsed " counter(xt) "/" counter(xn) " tokens"); }}']
    # registers panel
    o += [lbl.group('X-ray: registers'),
          f'.xregs {{ position: absolute; left: {REG_X}px; top: {REG_Y}px; display: grid; grid-template-columns: repeat(4, 140px); gap: 2px 8px; font: 13px ui-monospace, monospace; }}',
          '.xregs i { font-style: normal; color: var(--col-muted); display: inline-block; width: 62px; }',
          '.xn { counter-reset: xn var(--xr-w); } .xn::after { content: counter(xn); }',
          f'.xwhere {{ position: absolute; left: {REG_X}px; top: {REG_Y + 44}px; font: 13px ui-monospace, monospace; color: var(--col-ink); counter-reset: xrt var(--xr-rt); }}',
          f'.xwhere::after {{ content: "running: " if(style(--xr-rt: {len(rtn)}): "your code"; else: "ROM routine " counter(xrt, xrt)); }}',
          f'.xwhere {{ --xr-rt: if(style(--xr-pc: 1): {len(rtn)}; else: {rti}); --xr-pc: clamp(0, var(--pc) - {R.LAYOUT["code_base"] - 1}, 1); }}',
          f'.xmiss {{ position: absolute; left: {REG_X + 290}px; top: {REG_Y + 44}px; font: 13px ui-monospace, monospace; color: var(--col-miss);'
          ' counter-reset: xmb calc(var(--pend) - 1) xma calc(4 * var(--pend) - 4); }',
          '.xmiss::after { content: if(style(--pend: 0): ""; else: "fill: block " counter(xmb) " (@" counter(xma) ")" if(style(--pic: 1): " into the code cache"; else: "")); }',
          f'.xstepnote {{ position: absolute; left: {REG_X}px; top: {REG_Y + 62}px; font: 12px system-ui, sans-serif; color: #9a6b00; }}',
          '.xha { position: absolute; left: 0; top: 0; height: 0; anchor-name: --xhalt; width: calc(var(--halt) * 1px); }']
    # the trace: a row per chain level, from its registers (trace_regs)
    o += [lbl.group(f'X-ray: the chain\'s trace ({K} rows)', 'each level writes its instruction into registers of its own on passes that run (--xr-go): they keep the last pass'),
          *[f'@container style(--xr-go: 1) {{ .xl{L} {{ --xr-t{L}a: calc(4 * var(--pc) + var(--ok) + 1); --xr-t{L}b: var(--vf); --xr-t{L}c: var(--vg);'
            f' --xr-t{L}d: var(--xB); --xr-t{L}e: var(--yC); --xr-t{L}f: if(style(--ok: 0): var(--mb); else: var(--pst)); }} }}' for L in range(1, K + 1)],
          '.xr { position: absolute; left: %dpx; width: 568px; height: %dpx; font: 12px/%dpx ui-monospace, monospace; white-space: pre; border-radius: 3px; padding-left: 4px;'
          % (TRACE_X, TRH - 1, TRH - 1) +
          ' --xr-ok: calc(mod(var(--xr-ra), 4) - 1); --xr-rpc: round(down, var(--xr-ra) / 4);'
          ' --xr-o: round(down, var(--xr-rb) / 8192); --xr-a: mod(var(--xr-rb), 8192); --xr-b: calc(round(down, var(--xr-rc) / 1024) + 512); --xr-c: mod(var(--xr-rc), 1024);'
          ' color: if(style(--xr-ok: 2): var(--col-idle); else: var(--col-ink)); background: if(style(--xr-ok: 1): #e9f6ee; style(--xr-ok: 0): var(--col-bad); else: transparent); }',
          '.xr > i { font-style: normal; color: var(--col-muted); }',
          '.xr .xpc::before { content: "  "; } .xr .xpc::after { content: if(style(--xr-ok: 0) or style(--xr-ok: 1): counter(xpc); else: ""); display: inline-block; width: 6ch; }',
          '.xr .io::before { content: "  "; } .xr .io { display: inline-block; width: 9ch; }',
          '.xr .xst { position: absolute; left: 330px; }',
          '.xr .xst::after { content: if(style(--xr-ok: 1): "\\2713  B=" counter(xvb) " C=" counter(xvc) if(style(--xr-rf: 0): ""; else: "  pst " counter(xps));'
          ' style(--xr-ok: 0): "\\2717  cache miss: block " counter(xps) " (@" counter(xma) ")"; style(--xr-ok: 2): "\\B7  not reached"; else: ""); }',
          '@container style(--xr-ok: 2) or style(--xr-on: 0) or style(--xr-mf: 1) { .xr .io, .xr .ia, .xr .ib, .xr .ic { visibility: hidden; } }',
          '.xr { --xr-on: min(1, var(--xr-ra)); --xr-mf: calc((1 - min(1, abs(var(--xr-ok)))) * (1 - min(1, abs(var(--xr-o) - 255)))); }']
    o += insn_css('.xr', 'xpc var(--xr-rpc) xvb var(--xr-rd) xvc var(--xr-re) xps var(--xr-rf) xma calc(4 * var(--xr-rf))')
    # caches
    o += [lbl.group('X-ray: the caches', 'tags, dirty bits and words, from the registers'),
          f'.xdc, .xic {{ position: absolute; left: {DC_X}px; height: {CROW}px; font: 11px/{CROW}px ui-monospace, monospace; white-space: pre; width: 360px;'
          ' background: if(style(--xr-fill: 1): var(--col-fill); else: transparent); counter-reset: xtg calc(4 * round(down, var(--xr-T) / 2) - 4) xit calc(4 * var(--xr-T) - 4); }',
          '.xdc > i, .xic > i { font-style: normal; color: var(--col-muted); display: inline-block; width: 5ch; }',
          '.xdc > i::after { content: if(style(--xr-vic: 1): "\\25B8"; else: " "); color: var(--col-muted); }',
          '.xtag { display: inline-block; width: 9ch; } .xdc .xtag::after { content: if(style(--xr-T: 0): "\\2014"; else: "@" counter(xtg) if(style(--xr-d: 1): "*"; else: "")); }',
          '.xdc { --xr-d: mod(var(--xr-T), 2); } .xic .xtag::after { content: if(style(--xr-T: 0): "\\2014"; else: "@" counter(xit)); }',
          '.xdc .xwd, .xic .xwd { display: inline-block; width: 8ch; text-align: right; }',
          '@container style(--xr-T: 0) { .xdc .xwd, .xic .xwd { visibility: hidden; } }']
    o += word_css('.xwd')
    # listing
    o += [lbl.group('X-ray: the listing', 'a reader per instruction: width word0, height word1 (each + 2^20)'),
          f'.xlr {{ position: absolute; left: {-FAR}px; top: {-FAR}px; container-type: size; visibility: hidden; }}',
          f'.xli {{ position: absolute; visibility: visible; width: {LIST_W - 6}px; height: {LIST_H}px; font: 12px/{LIST_H}px ui-monospace, monospace; white-space: pre;'
          f' --xr-pres: min(1, round(100cqi / 1px)); --xr-o: round(down, (round(100cqi / 1px) - {WOFF}) / 8192); --xr-a: mod(round(100cqi / 1px) - {WOFF}, 8192);'
          f' --xr-b: calc(round(down, (round(100cqb / 1px) - {WOFF}) / 1024) + 512); --xr-c: mod(round(100cqb / 1px) - {WOFF}, 1024);'
          ' display: if(style(--xr-pres: 0): none; else: block); background: if(style(--xr-here: 1): #ffe08a; else: transparent); border-radius: 3px; }',
          '.xli > i { font-style: normal; color: var(--col-muted); } .xli .io { display: inline-block; width: 7ch; }']
    o += insn_css('.xli')
    # RAM
    o += [lbl.group('X-ray: RAM', 'readers of the RAM leaves\' anchors (a hidden group has none: 0)'),
          f'.xram {{ position: absolute; left: {-FAR}px; top: {-FAR}px; height: 1px; container-type: inline-size; visibility: hidden; }}',
          f'.xram > b {{ position: absolute; visibility: visible; width: 116px; height: 13px; font: 11px/13px ui-monospace, monospace; white-space: pre;'
          f' --xr-w: calc(round(100cqi / 1px) - {WOFF}); background: if(style(--xr-fp: 1): #ffe08a; else: transparent); }}',
          '.xram > b > i { font-style: normal; color: var(--col-muted); display: inline-block; width: 6ch; }',
          '.xram .xwd { display: inline-block; width: 8ch; text-align: right; --xr-w: inherit; }']
    return o
