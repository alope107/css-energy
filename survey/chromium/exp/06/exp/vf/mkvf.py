# mkvf.py NAXES out.ttf : variable font, glyf outlines (no hinting instructions), 2+ axes "AX00".."AXnn", HVAR via varLib
import sys
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.designspaceLib import DesignSpaceDocument, AxisDescriptor, SourceDescriptor
from fontTools import varLib
n, out = int(sys.argv[1]), sys.argv[2]
names = ['.notdef', 'zero', 'x', 'H', 'space', 'water']
cmap = {0x30: 'zero', 0x78: 'x', 0x48: 'H', 0x20: 'space', 0x6C34: 'water'}
def master(adv0, xh, extra):
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(names); fb.setupCharacterMap(cmap)
    glyphs = {}
    for g in names:
        p = TTGlyphPen(None)
        if g not in ('space', '.notdef'):
            w = adv0 if g == 'zero' else 500
            p.moveTo((50, 0)); p.lineTo((50, xh)); p.lineTo((w - 50, xh)); p.lineTo((w - 50, 0)); p.closePath()
            p.moveTo((100, 100)); p.lineTo((w - 100, 100)); p.lineTo((w - 100, xh - 100)); p.lineTo((100, xh - 100)); p.closePath()
        glyphs[g] = p.glyph()
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({g: ((adv0 if g == 'zero' else 500) + extra, 0) for g in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({'familyName': 'VF', 'styleName': 'Regular'})
    fb.setupOS2(sxHeight=xh, sCapHeight=700); fb.setupPost()
    return fb.font
ds = DesignSpaceDocument()
for i in range(n):
    a = AxisDescriptor(); a.tag = 'A%03d' % i; a.name = a.tag; a.minimum = 0; a.default = 0; a.maximum = 1000; ds.addAxis(a)
srcs = [master(500, 500, 0)] + [master(500 + 37 * (i + 1), 500 + 3 * (i + 1), 0) for i in range(n)]
for i, f in enumerate(srcs):
    s = SourceDescriptor(); s.font = f; s.location = {('A%03d' % j): (1000 if j == i - 1 else 0) for j in range(n)}; ds.addSource(s)
vf, _, _ = varLib.build(ds, exclude=['MVAR'] if False else [])
vf.save(out)
print('tables', sorted(vf.keys()))
