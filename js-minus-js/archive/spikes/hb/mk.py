# Helpers: build a tiny TTF with glyphs named in GN, advances in ADV, cmap, and FEA code.
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
def build(path, names, adv, cmap, fea, upem=1000, box=True, extra=None):
    fb = FontBuilder(upem, isTTF=True)
    gn = ['.notdef'] + [n for n in names if n != '.notdef']
    fb.setupGlyphOrder(gn)
    fb.setupCharacterMap(cmap)
    glyphs = {}
    for n in gn:
        p = TTGlyphPen(None)
        if box and n != '.notdef':
            p.moveTo((10,0)); p.lineTo((10,100)); p.lineTo((60,100)); p.lineTo((60,0)); p.closePath()
        glyphs[n] = p.glyph()
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({n: (adv.get(n, 0), 0) for n in gn})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({'familyName': 'T', 'styleName': 'Regular'})
    fb.setupOS2(xAvgCharWidth=500); fb.setupPost()
    if extra: extra(fb)
    if fea: addOpenTypeFeaturesFromString(fb.font, fea)
    fb.save(path)
    return fb.font
