# a font with glyphs of chosen advances (upem 1024); A..: big advances; a..: fractional-at-small-size advances
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
advs = {'A': 32767, 'B': 32768, 'C': 40000, 'D': 65535, 'E': 1000, 'F': 1001, 'G': 1003, 'H': 7, 'I': 13}
names = ['.notdef'] + list(advs)
fb = FontBuilder(1024, isTTF=True)
fb.setupGlyphOrder(names); fb.setupCharacterMap({ord(k): k for k in advs})
gl = {}
for g in names:
    p = TTGlyphPen(None)
    if g != '.notdef':
        p.moveTo((10, 0)); p.lineTo((10, 500)); p.lineTo((300, 500)); p.lineTo((300, 0)); p.closePath()
    gl[g] = p.glyph()
fb.setupGlyf(gl)
fb.setupHorizontalMetrics({g: (advs.get(g, 500), 0) for g in names})
fb.setupHorizontalHeader(ascent=900, descent=-124)
fb.setupNameTable({'familyName': 'Adv', 'styleName': 'Regular'}); fb.setupOS2(); fb.setupPost()
fb.save('adv.ttf')
