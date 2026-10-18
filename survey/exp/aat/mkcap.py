#!/usr/bin/env python3
"""mkcap.py M out.ttf — the binary counter with M increments as 2 aliased lookups (3 subtables) per increment, assembled
with js-minus-js's otl.py, to test GSUB subtable caps (3M subtables in all)."""
import sys, io
sys.path.insert(0, '/workspaces/css-energy/js-minus-js/machine')
import otl
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables.otBase import OTTableWriter
M, OUT = int(sys.argv[1]), sys.argv[2]
order = ['.notdef', 'zero', 'one', 'zeroC', 'oneC', 'endm']
fb = FontBuilder(1000, isTTF=True); fb.setupGlyphOrder(order)
fb.setupCharacterMap({ord('0'): 'zero', ord('1'): 'one', ord('|'): 'endm'})
e = TTGlyphPen(None).glyph(); fb.setupGlyf({g: e for g in order})
adv = {'.notdef': 100, 'zero': 100, 'one': 200, 'zeroC': 100, 'oneC': 200, 'endm': 0}
fb.setupHorizontalMetrics({g: (adv[g], 0) for g in order}); fb.setupHorizontalHeader(ascent=800, descent=-200)
fb.setupNameTable({'familyName': 'Cap', 'styleName': 'Regular'}); fb.setupOS2(); fb.setupPost()
f = fb.font
Z, O, ZC, OC, E = 1, 2, 3, 4, 5      # glyph ids
lks = [otl.Lookup(8, [otl.reverse_chain({Z: ZC, O: OC}, [], [[E]]), otl.reverse_chain({Z: ZC, O: OC}, [], [[OC]])], None, 'RIP'),
       otl.Lookup(1, [otl.single_subst({ZC: O, OC: Z})], None, 'FIX')]
print('subtables per increment', sum(len(l.subtables) for l in lks))
idx = [0, 1] * M
data = otl.build_gsub(lks, idx, [('calt', list(range(len(idx))))])
b = io.BytesIO(); f.save(b)
# keep the hand-assembled GSUB bytes exactly (fontTools would re-pack and dedupe): splice them in
f2 = TTFont(io.BytesIO(b.getvalue())); f2['GSUB'] = newTable('GSUB')
from fontTools.ttLib.tables.DefaultTable import DefaultTable
raw = DefaultTable('GSUB'); raw.data = data; f2.tables['GSUB'] = raw
f2.save(OUT); print(OUT, M, 'increments,', 3 * M, 'subtables')
