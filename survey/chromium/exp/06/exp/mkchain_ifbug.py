#!/usr/bin/env python3
"""mkchain.py K R P out.html — K dependent shapings inside ONE layout pass, js-minus-js style.

Level k: a line of text (#st<k>, position: fixed) with R spans; span i shows value v_i as three per-position digit glyphs
(counters through @counter-style), and the font's GSUB adds 1 (mod 16) to every span's low digit. R/2 nested readers
(position: fixed, container-type: size, width/height = anchor-size of two spans) turn the shaped widths back into
v_i on their child (100cqw / 1px); P registered props of "service logic" sit on the innermost reader's child, and the
next level's line and readers are nested inside it. So every level is: shape -> R/2 interleaved style recalcs -> next
line. After K levels each low digit has gone up by K (mod 16): the probe checks it against level 0 in one snapshot.

Level 0's values come from a wall clock (an animated registered integer), so every frame recomputes the whole chain.
"""
import sys, os, base64, io
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

K, R, P, OUT = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
WORK = int(os.environ.get('WORK', 0))     # extra GSUB work per shaping: WORK aliased-free copies of a no-op chain lookup over the line
assert R % 2 == 0

def font():
    order = ['.notdef'] + [f't{j}_{d}' for j in range(3) for d in range(16)]
    fb = FontBuilder(1024, isTTF=True); fb.setupGlyphOrder(order)
    fb.setupCharacterMap({0xE000 + 16 * j + d: f't{j}_{d}' for j in range(3) for d in range(16)})
    e = TTGlyphPen(None).glyph(); fb.setupGlyf({g: e for g in order})
    fb.setupHorizontalMetrics({'.notdef': (0, 0), **{f't{j}_{d}': (d * 16 ** j, 0) for j in range(3) for d in range(16)}})
    fb.setupHorizontalHeader(ascent=900, descent=-124); fb.setupNameTable({'familyName': 'ChainF', 'styleName': 'Regular'})
    fb.setupOS2(sTypoAscender=900, sTypoDescender=-124, usWinAscent=900, usWinDescent=124); fb.setupPost()
    t0 = ' '.join(f't0_{d}' for d in range(16)); t0n = ' '.join(f't0_{(d + 1) % 16}' for d in range(16))
    allg = ' '.join(order[1:])
    fea = [f'@T0 = [{t0}]; @T0N = [{t0n}]; @ALL = [{allg}];', 'lookup INC { sub @T0 by @T0N; } INC;']
    # optional dead weight: chain lookups whose context never matches (t2_15 followed by t2_15 never occurs in a value
    # < 4096 shown as 3 digits), so HarfBuzz walks the line WORK times
    for w in range(WORK): fea.append(f"lookup W{w} {{ sub t2_15' lookup INC t2_15; }} W{w};")
    fea.append('feature ss01 { lookup INC; ' + ' '.join(f'lookup W{w};' for w in range(WORK)) + ' } ss01;')
    addOpenTypeFeaturesFromString(fb.font, '\n'.join(fea))
    b = io.BytesIO(); fb.font.save(b); return base64.b64encode(b.getvalue()).decode()

css = [f'@font-face {{ font-family: ChainF; src: url(data:font/ttf;base64,{font()}); }}',
       "@property --t { syntax: '<integer>'; inherits: true; initial-value: 0; }",
       '@keyframes clk { from { --t: 0; } to { --t: 6000; } }',
       '#root { animation: clk 100s linear infinite; }' if not os.environ.get('STATIC') else '#root { --t: 5; }']
css += [f"@property --v{i} {{ syntax: '<integer>'; inherits: true; initial-value: 0; }}" for i in range(R)]
css += [f"@property --w{p} {{ syntax: '<integer>'; inherits: false; initial-value: 0; }}" for p in range(P)]
css += [f'@counter-style p{j} {{ system: fixed 0; symbols: ' + ' '.join(f'"\\{0xE000 + 16 * j + d:X}"' for d in range(16)) + '; }' for j in range(3)]
css.append('#root { ' + ' '.join(f'--v{i}: mod(var(--t) * {i + 1} + {37 * i}, 4096);' for i in range(R)) + ' }')
CB = os.environ.get('CB', 'fixed')   # fixed: every element fixed (js-minus-js); rel: a position: relative wrapper per level, readers absolute
POS = 'absolute' if CB == 'rel' else 'fixed'   # contain: wrappers with layout containment (the CB of their fixed readers)
css.append('.lv { position: relative; width: 0; height: 0; ' + ('contain: layout; ' if CB == 'contain' else '') + '}')
css.append('.st { position: ' + ('fixed' if CB == 'fixed' else 'static') + '; left: 0; top: 0; font: 1024px/1 ChainF; font-feature-settings: "ss01" 1; white-space: pre; visibility: hidden; }')
if os.environ.get('IFC'):
    css += [f"@property --d{j} {{ syntax: '<integer>'; inherits: false; initial-value: 0; }}" for j in range(3)]
    def dig(j): return 'if(' + ' '.join(f'style(--d{j}: {d}): "\\{0xE000 + 16 * j + d:X}";' for d in range(16)) + ')'
    css.append('.st > span::before { content: ' + dig(2) + ' ' + dig(1) + ' ' + dig(0) + '; }')
else:
    css.append('.st > span::before { content: counter(x2, p2) counter(x1, p1) counter(x0, p0); }')
for i in range(R):
    if os.environ.get('IFC'):
        css.append(f'.st > .s{i} {{ --d2: mod(round(down, var(--v{i}) / 256), 16); --d1: mod(round(down, var(--v{i}) / 16), 16); --d0: mod(var(--v{i}), 16); }}')
    else:
        css.append(f'.st > .s{i} {{ counter-set: x2 mod(round(down, var(--v{i}) / 256), 16) x1 mod(round(down, var(--v{i}) / 16), 16) x0 mod(var(--v{i}), 16); }}')
css.append(f'.rd {{ position: {POS}; left: 0; top: 0; container-type: size; visibility: hidden; }}')
for k in range(K):
    for a in range(0, R, 2):
        css.append(f'.L{k}.r{a} {{ width: anchor-size(--k{k}s{a} width, 0px); height: anchor-size(--k{k}s{a + 1} width, 0px); }}')
css.append('.rv { ' + '' + ' }')
for a in range(0, R, 2):
    css.append(f'.rv{a} {{ --v{a}: round(100cqw / 1px); --v{a + 1}: round(100cqh / 1px); }}')
# service logic: P props on the innermost reader child of every level (inherits: false: they cost only there)
css.append('.svc { ' + ' '.join(f'--w{p}: calc(var(--v{p % R}) * {p % 7 + 1} + mod(var(--v{(p * 5) % R}), {p % 13 + 2}));' for p in range(P)) + ' }')
css.append('#probe { ' + ' '.join(f'--f{i}: var(--v{i});' for i in range(R)) + ' }')

def level(k):
    if k == K:
        return '<div id="probe"></div>'
    line = f'<div class="st" id="st{k}">' + ''.join(f'<span class="s{i}" style="anchor-name: --k{k}s{i}"></span>' for i in range(R)) + '</div>'
    opens = ''.join(f'<div class="rd L{k} r{a}"><div class="rv rv{a}{" svc" if a == R - 2 else ""}">' for a in range(0, R, 2))
    body = line + opens + level(k + 1) + '</div></div>' * (R // 2)
    return body if CB == 'fixed' else f'<div class="lv">{body}</div>'

html = (f'<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/><style><![CDATA[{chr(10).join(css)}]]></style></head>'
        f'<body><div id="root">{level(0)}</div></body></html>')   # XHTML: the reader nests pass HTML's 512-element limit
open(OUT, 'w').write(html)
print(OUT, len(html), 'bytes')
