# upem-1000 font: glyphs with advances N (no outlines) to probe the scale path
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
advs = {'A': 1, 'B': 7, 'C': 1000, 'D': 4096, 'E': 12288, 'F': 30000, 'G': 32767}
names = ['.notdef'] + list(advs)
fb = FontBuilder(1000, isTTF=True)
fb.setupGlyphOrder(names); fb.setupCharacterMap({ord(k): k for k in advs})
e = TTGlyphPen(None).glyph(); fb.setupGlyf({g: e for g in names})
fb.setupHorizontalMetrics({g: (advs.get(g, 500), 0) for g in names})
fb.setupHorizontalHeader(ascent=900, descent=-100)
fb.setupNameTable({'familyName': 'Adv1000', 'styleName': 'Regular'}); fb.setupOS2(); fb.setupPost()
fb.save('adv1000.ttf')
