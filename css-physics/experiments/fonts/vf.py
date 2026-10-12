"""Minimal variable fonts for compute experiments.
Axes run -16384..0..16384 user units, so the CSS value is the F2DOT14 coordinate.
HVAR terms: glyph -> [(support{tag:(s,p,e) in F2DOT14 ints}, delta)]; MVAR terms: tag -> same."""
import base64, io
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables import otTables as ot
from fontTools.varLib import builder as vb
from fontTools.ttLib import newTable

UPEM = 16384

def _store(tags, rows):
    sups = []; key = {}
    for terms in rows:
        for s, _ in terms:
            k = tuple(sorted(s.items()))
            if k not in key: key[k] = len(sups); sups.append(k)
    if not sups:
        sups = [((tags[0], (0, 16384, 16384)),)]; key[sups[0]] = 0
    reg = vb.buildVarRegionList([{t: tuple(v / 16384 for v in ss) for t, ss in k} for k in sups], tags)
    items = []
    for terms in rows:
        d = [0] * len(sups)
        for s, v in terms: d[key[tuple(sorted(s.items()))]] += v
        items.append(d)
    vd = vb.buildVarData(list(range(len(sups))), items, optimize=False)
    return vb.buildVarStore(reg, [vd])

def build(tags, glyphs, mvar=None, os2=dict(xh=8000, cap=11000), family='Calc'):
    """glyphs: list of (codepoint, name, advance, terms)"""
    names = ['.notdef'] + [g[1] for g in glyphs]
    fb = FontBuilder(UPEM, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({g[0]: g[1] for g in glyphs})
    pen = TTGlyphPen(None); pen.moveTo((0, 0)); pen.lineTo((0, 1)); pen.lineTo((1, 1)); pen.closePath()
    box = pen.glyph()
    fb.setupGlyf({n: box for n in names})
    fb.setupHorizontalMetrics({'.notdef': (UPEM, 0), **{g[1]: (g[2], 0) for g in glyphs}})
    fb.setupHorizontalHeader(ascent=UPEM, descent=0)
    fb.setupNameTable({'familyName': family, 'styleName': 'Regular'})
    fb.setupOS2(sTypoAscender=UPEM, sTypoDescender=0, usWinAscent=UPEM, usWinDescent=0, sxHeight=os2['xh'], sCapHeight=os2['cap'], version=4)
    fb.setupPost()
    fb.setupFvar([(t, -16384, 0, 16384, t) for t in tags], [])
    font = fb.font
    # HVAR, direct mapping: varIdx = glyph order (outer 0)
    rows = [[]] + [g[3] for g in glyphs]
    store = _store(tags, rows)
    hv = ot.HVAR(); hv.Version = 0x00010000; hv.VarStore = store
    hv.AdvWidthMap = None; hv.LsbMap = None; hv.RsbMap = None
    t = newTable('HVAR'); t.table = hv; font['HVAR'] = t
    if mvar:
        tg = list(mvar)
        st = _store(tags, [mvar[k] for k in tg])
        mv = ot.MVAR(); mv.Version = 0x00010000; mv.Reserved = 0; mv.VarStore = st
        recs = []
        for i, k in enumerate(tg):
            r = ot.MetricsValueRecord(); r.ValueTag = k; r.VarIdx = i; recs.append(r)
        mv.ValueRecord = sorted(recs, key=lambda r: r.ValueTag); mv.ValueRecordSize = 8; mv.ValueRecordCount = len(recs)
        t = newTable('MVAR'); t.table = mv; font['MVAR'] = t
    b = io.BytesIO(); font.save(b); return b.getvalue()

def b64(data): return base64.b64encode(data).decode()
POS = (0, 16384, 16384)
NEG = (-16384, -16384, 0)
