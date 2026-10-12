"""fontbase.py — wrap raw GSUB/GDEF bytes into a minimal TrueType font (fontTools for the boilerplate)."""
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables.DefaultTable import DefaultTable

def make_font(path, glyph_names, advances, cmap, gsub, gdef, upem=1024, family='CPU', woff2=False):
    fb = FontBuilder(upem, isTTF=True)
    fb.setupGlyphOrder(glyph_names)
    fb.setupCharacterMap(cmap)
    empty = TTGlyphPen(None).glyph()
    box = TTGlyphPen(None); box.moveTo((0, 0)); box.lineTo((0, 10)); box.lineTo((10, 10)); box.lineTo((10, 0)); box.closePath()
    fb.setupGlyf({g: (box.glyph() if i == 0 else empty) for i, g in enumerate(glyph_names)})
    fb.setupHorizontalMetrics({g: (advances.get(g, 0), 0) for g in glyph_names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({'familyName': family, 'styleName': 'Regular'})
    fb.setupOS2(xAvgCharWidth=500); fb.setupPost()
    for tag, data in (('GSUB', gsub), ('GDEF', gdef)):
        t = DefaultTable(tag); t.data = data; fb.font[tag] = t
    if woff2: fb.font.flavor = 'woff2'
    fb.save(path)
