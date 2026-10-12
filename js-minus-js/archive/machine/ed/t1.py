from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
import base64
names = ['.notdef', 'a', 'b', 'nl', 'sp', 'W', 'V', 'M']
fb = FontBuilder(1000, isTTF=True); fb.setupGlyphOrder(names)
fb.setupCharacterMap({0x61: 'a', 0x62: 'b', 0x0A: 'nl', 0x20: 'sp', 0xE000: 'M'})
box = TTGlyphPen(None); box.moveTo((0, 0)); box.lineTo((0, 500)); box.lineTo((400, 500)); box.lineTo((400, 0)); box.closePath()
fb.setupGlyf({g: box.glyph() for g in names})
adv = {'.notdef': 500, 'a': 500, 'b': 500, 'nl': 0, 'sp': 500, 'W': 30000, 'V': 20000, 'M': 0}
fb.setupHorizontalMetrics({g: (adv[g], 0) for g in names}); fb.setupHorizontalHeader(ascent=800, descent=-200)
fb.setupNameTable({'familyName': 'T1', 'styleName': 'Regular'}); fb.setupOS2(); fb.setupPost()
addOpenTypeFeaturesFromString(fb.font, """
lookup L1 { sub b a' by W; sub nl a' by V; sub M a' by V; } L1;
feature calt { lookup L1; } calt;
""")
fb.save('t1.ttf')
b64 = base64.b64encode(open('t1.ttf', 'rb').read()).decode()
css = f"@font-face {{ font-family: T1; src: url(data:font/ttf;base64,{b64}); }} .e {{ font: 1000px/1 T1; white-space: pre; width: max-content; }}"
tests = {
 'same_line': '<div class="e" id="x">ba</div>',
 'pre_newline': '<div class="e" id="x">b\na</div>',
 'ce_plain_newline': '<div class="e" id="x" contenteditable="plaintext-only">b\na</div>',
 'before_marker': '<style>#x::before { content: "\\E000"; }</style><div class="e" id="x" contenteditable="plaintext-only">a</div>',
 'before_marker_nl': '<style>#x::before { content: "\\E000"; }</style><div class="e" id="x" contenteditable="plaintext-only">\na</div>',
 'br': '<div class="e" id="x">b<br>a</div>',
}
for k, v in tests.items():
    open(f'{k}.html', 'w').write(f'<!doctype html><meta charset=utf-8><style>{css}</style>{v}')
print(' '.join(tests))
