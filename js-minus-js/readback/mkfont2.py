# AsciiProbe font. At rest: monospace ASCII, 10px advance at 16px (upem 1024, adv 640).
# Axis SCAN = j+1 activates (via GSUB FeatureVariations) a lookup set that:
#   CAP_j  : marks the glyph at column j (exactly j ASCII glyphs before it) as carrier(c, v=c)
#   RPROP  : carries v rightward through every following glyph, into a sentinel U+E000 -> sent.v
#   LPROP  : carries v leftward (reverse chaining) into a leading sentinel
# sent.v has a static advance of (v-31) px. A GPOS pair kern cancels a leading sentinel's
# width on the next glyph, so visible text never moves.
# PAIR (a third argument 'pair'): SCAN = k reads two columns, 2k-2 and 2k-1, into a leading sentinel: CAP and LPROP the
# first (sent -> sent.a), RESET (carriers back to plain glyphs), CAP and LPROP2 the second (sent.a -> sent.a.b). sent.a.b
# is W = (a-31) + 96 (b-31) px wide, up to 9,215 px: an advance holds at most 32,767 units (511 px), so the rest comes from
# single-adjustment lookups (chunks of 511 px), and as many pair lookups take it off the next glyph. No RPROP (a trailing
# sentinel's: the page's sentinels lead their rows).
import sys
from fontTools.ttLib import TTFont, newTable
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.transformPen import TransformPen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

P = int(sys.argv[1]); out = sys.argv[2]; PAIR = len(sys.argv) > 3 and sys.argv[3] == 'pair'
UPEM, ADV, PX = 1024, 640, 64           # 64 units = 1px at 16px
src = TTFont('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf')
sgs = src.getGlyphSet(); scmap = src.getBestCmap()
codes = list(range(32, 127))
base = {c: f'c{c}' for c in codes}
car = {(c, v): f'c{c}.v{v}' for c in codes for v in codes}
sent = {v: f'sent.v{v}' for v in codes}
sentp = {(a, b): f'sent.v{a}.{b}' for a in codes for b in codes} if PAIR else {}
CH = 32704                              # a chunk of a pair sentinel's width: 511 px, at most one advance
def wunits(a, b): return ((a - 31) + 96 * (b - 31)) * PX
NCH = max((wunits(a, b) + CH - 1) // CH for a, b in sentp) if PAIR else 0
def chunk(a, b, i): return max(0, min(CH, wunits(a, b) - i * CH))
order = ['.notdef', 'sent'] + list(base.values()) + list(sent.values()) + list(car.values()) + list(sentp.values())
glyphs, adv = {}, {}
glyphs['.notdef'] = TTGlyphPen(None).glyph(); adv['.notdef'] = ADV
glyphs['sent'] = TTGlyphPen(None).glyph(); adv['sent'] = 0
for c in codes:
    g = sgs[scmap[c]]; dx = (ADV - g.width * 0.5) / 2
    pen = TTGlyphPen(sgs); g.draw(TransformPen(pen, (0.5, 0, 0, 0.5, dx, 0)))
    glyphs[base[c]] = pen.glyph(); adv[base[c]] = ADV
for v in codes:
    glyphs[sent[v]] = TTGlyphPen(None).glyph(); adv[sent[v]] = (v - 31) * PX
for (a, b), n in sentp.items():
    glyphs[n] = TTGlyphPen(None).glyph(); adv[n] = chunk(a, b, 0)
for (c, v), n in car.items():
    if c == 32: glyphs[n] = TTGlyphPen(None).glyph()
    else:
        pen = TTGlyphPen(glyphs); pen.addComponent(base[c], (1, 0, 0, 1, 0, 0)); glyphs[n] = pen.glyph()
    adv[n] = ADV
fb = FontBuilder(UPEM, isTTF=True)
fb.setupGlyphOrder(order)
cm = {c: base[c] for c in codes}; cm[0xA0] = base[32]; cm[0x2058] = 'sent'
fb.setupCharacterMap(cm)
fb.setupGlyf(glyphs)
gl = fb.font['glyf']
for n in order: gl[n].recalcBounds(gl)
fb.setupHorizontalMetrics({n: (adv[n], getattr(gl[n], 'xMin', 0)) for n in order})
fb.setupHorizontalHeader(ascent=760, descent=-240)
fb.setupNameTable({'familyName': 'AsciiProbe', 'styleName': 'Regular'})
fb.setupOS2(sTypoAscender=760, sTypoDescender=-240, sTypoLineGap=0, usWinAscent=760, usWinDescent=240, xAvgCharWidth=ADV)
fb.setupPost(isFixedPitch=0)
fb.setupFvar(axes=[('SCAN', 0, 0, P, 'Scan')], instances=[])
f = fb.font
gv = newTable('gvar'); gv.version = 1; gv.reserved = 0; gv.variations = {n: [] for n in order}; f['gvar'] = gv

B = '[' + ' '.join(base.values()) + ']'
fea = [f'@BASE = {B};', f'@BS = [{" ".join(base.values())} sent];']
for v in codes:
    fea.append(f'@CV{v} = [{" ".join(car[(c, v)] for c in codes)}];')
fea.append(f'@TXT = [{" ".join(base.values())} {" ".join(car.values())}];')
fea.append(f'@CAR = [{" ".join(car.values())}];')
fea.append('lookup SETCAP { ' + ' '.join(f'sub {base[c]} by {car[(c, c)]};' for c in codes) + ' } SETCAP;')
for j in range(P):
    fea.append(f'lookup CAP{j} {{ sub c32 by c32.v32; }} CAP{j};')   # placeholder, replaced below
for v in codes:   # base -> carrier(., v); sentinel -> sent.v
    fea.append(f'lookup TO{v} {{ ' + ' '.join(f'sub {base[c]} by {car[(c, v)]};' for c in codes) + f' sub sent by {sent[v]}; }} TO{v};')
if not PAIR:
    fea.append('lookup RPROP {')
    for v in codes: fea.append(f"  sub @CV{v} @BS' lookup TO{v};")
    fea.append('} RPROP;')
fea.append('lookup LPROP {')
for v in codes:
    fea.append(f"  rsub @BS' @CV{v} by [{' '.join(car[(c, v)] for c in codes)} {sent[v]}];")
fea.append('} LPROP;')
if PAIR:     # (a feature applies its lookups in LookupList order: the second capture's CAPB come after RESET)
    fea.append('lookup RESET { ' + ' '.join(f'sub {n} by {base[c]};' for (c, v), n in car.items()) + ' } RESET;')
    for j in range(P): fea.append(f'lookup CAPB{j} {{ sub c32 by c32.v32; }} CAPB{j};')   # placeholder, replaced below
    fea.append('lookup LPROP2 {')
    for v in codes:
        fea.append(f"  rsub [{' '.join(base.values())} {' '.join(sent.values())}]' @CV{v} by [{' '.join(car[(c, v)] for c in codes)} {' '.join(sentp[(a, v)] for a in codes)}];")
    fea.append('} LPROP2;')
fea.append('feature rclt { } rclt;')
for j in range(P // 2 if PAIR else P):
    fea.append(f'conditionset scan{j} {{ SCAN {j + 0.5} {j + 1.5}; }} scan{j};')
    if PAIR: fea.append(f'variation rclt scan{j} {{ lookup CAP{2 * j}; lookup LPROP; lookup RESET; lookup CAPB{2 * j + 1}; lookup LPROP2; }} rclt;')
    else: fea.append(f'variation rclt scan{j} {{ lookup CAP{j}; lookup RPROP; lookup LPROP; }} rclt;')
# Leading sentinel: cancel its width on the next glyph (shift ink back, shorten advance).
fea.append('feature kern {')
for v in codes:
    w = (v - 31) * PX
    fea.append(f'  pos {sent[v]} <0 0 0 0> {"@TXT" if PAIR else "@CAR"} <{-w} 0 {-w} 0>;')
fea.append('} kern;')
open('probe.fea', 'w').write('\n'.join(fea))
addOpenTypeFeaturesFromString(f, '\n'.join(fea))
from fontTools.ttLib.tables import otTables as ot
LL = f['GSUB'].table.LookupList.Lookup
assert LL[0].SubTable[0].mapping['c72'] == 'c72.v72'
def cov(names):
    c = ot.Coverage(); c.glyphs = sorted(names, key=f.getGlyphID); return c
TXT = cov(list(base.values()) + list(car.values())); BASE = cov(list(base.values()))
def rule(nback, lookups):
    st = ot.ChainContextSubst(); st.Format = 3
    st.BacktrackGlyphCount = nback; st.BacktrackCoverage = [TXT] * nback
    st.InputGlyphCount = 1; st.InputCoverage = [BASE]
    st.LookAheadGlyphCount = 0; st.LookAheadCoverage = []
    recs = []
    for li in lookups:
        r = ot.SubstLookupRecord(); r.SequenceIndex = 0; r.LookupListIndex = li; recs.append(r)
    st.SubstCount = len(recs); st.SubstLookupRecord = recs
    return st
ph = [i for i, L in enumerate(LL) if L.LookupType == 1 and L.SubTable[0].mapping == {'c32': 'c32.v32'}]   # the placeholders
assert len(ph) == P * (2 if PAIR else 1) and ph[:P] == list(range(1, P + 1))
for j, li in enumerate(ph):
    j %= P; L = LL[li]; L.LookupType = 6; L.LookupFlag = 0
    L.SubTable = [rule(j + 1, []), rule(j, [0])]     # column > j: stop; column == j: capture
    L.SubTableCount = 2
if PAIR:     # sent.a.b: the rest of its width (chunk i > 0, single adjustments), all of it off the next glyph (pairs)
    from fontTools.otlLib import builder as ob
    GP = f['GPOS'].table; txt = list(base.values()) + list(car.values())
    new = []
    for i in range(NCH):
        if i:
            vals = {n: ob.buildValue({'XAdvance': chunk(a, b, i)}) for (a, b), n in sentp.items() if chunk(a, b, i)}
            new.append(ob.buildLookup([ob.buildSinglePosSubtable(vals, f.getReverseGlyphMap())]))
        pairs = {}
        for (a, b), n in sentp.items():
            c = chunk(a, b, i)
            if c: pairs.setdefault(c, []).append(n)
        sub = ob.buildPairPosClassesSubtable({(tuple(g), tuple(txt)): (None, ob.buildValue({'XPlacement': -c, 'XAdvance': -c})) for c, g in pairs.items()}, f.getReverseGlyphMap())
        new.append(ob.buildLookup([sub]))
    k0 = len(GP.LookupList.Lookup); GP.LookupList.Lookup += new; GP.LookupList.LookupCount = len(GP.LookupList.Lookup)
    for fr in GP.FeatureList.FeatureRecord:
        if fr.FeatureTag == 'kern':
            fr.Feature.LookupListIndex += list(range(k0, k0 + len(new))); fr.Feature.LookupCount = len(fr.Feature.LookupListIndex)
f.save(out.replace('.woff2', '.ttf')); f.flavor = 'woff2'; f.save(out)
print(out, len(order), 'glyphs', len(open(out, 'rb').read()), 'bytes')
