# Adder font: U+E000+k has advance 2**k units (k = 0..14); U+E0FF has advance 0. unitsPerEm 1000.
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
UPEM = 1024
names = ['.notdef', 'zero'] + [f'b{k}' for k in range(15)]
fb = FontBuilder(UPEM, isTTF=True)
fb.setupGlyphOrder(names)
cmap = {0xE0FF: 'zero'}
cmap.update({0xE000 + k: f'b{k}' for k in range(15)})
fb.setupCharacterMap(cmap)
def box(w):
    p = TTGlyphPen(None)
    if w > 0:
        p.moveTo((0, 0)); p.lineTo((0, 100)); p.lineTo((min(w, 100), 100)); p.lineTo((min(w, 100), 0)); p.closePath()
    return p.glyph()
glyphs = {'.notdef': box(500), 'zero': box(0)}
glyphs.update({f'b{k}': box(2 ** k) for k in range(15)})
fb.setupGlyf(glyphs)
metrics = {'.notdef': (500, 0), 'zero': (0, 0)}
metrics.update({f'b{k}': (2 ** k, 0) for k in range(15)})
fb.setupHorizontalMetrics(metrics)
fb.setupHorizontalHeader(ascent=800, descent=-200)
fb.setupNameTable({'familyName': 'Adder', 'styleName': 'Regular'})
fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
fb.setupPost()
fb.save('adder.ttf')
print('ok')
