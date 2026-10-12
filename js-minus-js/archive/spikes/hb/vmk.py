# Toy VM inside GSUB. State glyph S[p*256+a] (pc 0..63, acc 0..255). One shared step lookup,
# aliased K times in the LookupList (many indices -> same Lookup table), so one shaping = K VM steps.
import struct, sys, base64
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable

TARGET = 0x2D
PROG = [('JODD',3),('SHR1',0),('JMP',5),('SHR1',0),('XORI',0xB8),
        ('XORI',TARGET),('JZ',9),('XORI',TARGET),('JMP',0),('HALT',0)]
def step(p, a):
    if p >= len(PROG): return p, a
    op, k = PROG[p]
    if op == 'JODD': return (k if a & 1 else p+1), a
    if op == 'SHR1': return p+1, a >> 1
    if op == 'JMP':  return k, a
    if op == 'XORI': return p+1, a ^ k
    if op == 'JZ':   return (k if a == 0 else p+1), a
    if op == 'HALT': return p, a
KS = [1, 100, 1000, 10000, 16000]
K = max(KS)
ND, NS = 128, 64*256
gorder = ['.notdef'] + [f'D{i}' for i in range(ND)] + [f'S{i}' for i in range(NS)]
gid = {g: i for i, g in enumerate(gorder)}
D0, S0 = gid['D0'], gid['S0']

def coverage(glyphs):           # format 2 (ranges), glyphs sorted
    rs = []; 
    for g in glyphs:
        if rs and rs[-1][1] == g - 1: rs[-1][1] = g
        else: rs.append([g, g])
    out = struct.pack('>HH', 2, len(rs)); idx = 0
    for s, e in rs: out += struct.pack('>HHH', s, e, idx); idx += e - s + 1
    return out
def single2(mapping):          # SingleSubstFormat2
    gs = sorted(mapping); cov = coverage(gs)
    body = struct.pack('>HHH', 2, 0, len(gs)) + b''.join(struct.pack('>H', mapping[g]) for g in gs)
    return body[:2] + struct.pack('>H', len(body)) + body[4:] + cov
def ligature(first_to_ligs):   # LigatureSubstFormat1; first_to_ligs[g] = [(comps_after_first, lig)]
    firsts = sorted(first_to_ligs); n = len(firsts)
    hdr = 6 + 2*n; sets = b''; offs = []
    for g in firsts:
        ligs = first_to_ligs[g]; m = len(ligs); sb = struct.pack('>H', m); lb = b''; lo = []
        for comps, lg in ligs:
            lo.append(2 + 2*m + len(lb)); lb += struct.pack('>HH', lg, len(comps)+1) + b''.join(struct.pack('>H', c) for c in comps)
        sb += b''.join(struct.pack('>H', o) for o in lo) + lb
        offs.append(hdr + len(sets)); sets += sb
    cov_off = hdr + len(sets)
    return struct.pack('>HHH', 1, cov_off, n) + b''.join(struct.pack('>H', o) for o in offs) + sets + coverage(firsts)
def ext(lookup_type, sub):     # ExtensionSubstFormat1 followed directly by its subtable
    return struct.pack('>HHI', 1, lookup_type, 8) + sub

lig = {D0+h: [([D0+l], S0 + h*128 + l) for l in range(128)] for h in range(128)}
stepmap = {}
for s in range(NS):
    p, a = divmod(s, 256); q, b = step(p, a)
    if (q, b) != (p, a): stepmap[S0+s] = S0 + q*256 + b
CH = 32
lig_payloads = [ligature({g: lig[g] for g in sorted(lig)[c:c+CH]}) for c in range(0, 128, CH)]
step_payload = single2(stepmap)
n0 = len(lig_payloads)
# Layout (absolute offsets from GSUB start):
#   header(10) | ScriptList | LookupList head (count, offsets, Lookup tables, ext headers) | FeatureList | payloads
feats = [(f'ss{i+1:02d}', [0] + list(range(1, k+1))) for i, k in enumerate(KS)]
nf = len(feats)
langsys = struct.pack('>HHH', 0, 0xFFFF, nf) + b''.join(struct.pack('>H', i) for i in range(nf))
scriptlist = struct.pack('>H', 1) + b'DFLT' + struct.pack('>H', 8) + struct.pack('>HH', 4, 0) + langsys
SL = 10; LL = SL + len(scriptlist)
nl = K + 1
lk1 = 2 + 2*nl; lk0 = lk1 + 8; xh = lk0 + 6 + 2*n0          # relative to LL
x_ligs = [xh + 8*i for i in range(n0)]
x_step = xh + 8*n0
ll_head_len = x_step + len(step_payload)
FL = LL + ll_head_len
assert FL < 65536, FL
recs = b''; ftabs = b''; fbase = 2 + 6*nf
for tag, idxs in feats:
    assert fbase + len(ftabs) < 65536
    recs += tag.encode() + struct.pack('>H', fbase + len(ftabs))
    ftabs += struct.pack('>HH', 0, len(idxs)) + b''.join(struct.pack('>H', i) for i in idxs)
featurelist = struct.pack('>H', nf) + recs + ftabs
PAY = FL + len(featurelist)
p = PAY; p_ligs = []
for pl in lig_payloads: p_ligs.append(p); p += len(pl)
L1 = struct.pack('>HHHH', 1, 0, 1, x_step - lk1)
assert x_step - lk1 < 65536
L0 = struct.pack('>HHH', 7, 0, n0) + b''.join(struct.pack('>H', x - lk0) for x in x_ligs)
X = b''.join(struct.pack('>HHI', 1, 4, pl - (LL + x)) for pl, x in zip(p_ligs, x_ligs))
ll_head = struct.pack('>H', nl) + struct.pack('>H', lk0) + struct.pack('>H', lk1) * K + L1 + L0 + X + step_payload
assert len(ll_head) == ll_head_len
gsub = struct.pack('>IHHH', 0x00010000, SL, FL, LL) + scriptlist + ll_head + featurelist + b''.join(lig_payloads)
PAD = int(__import__("os").environ.get("PAD", "0")); gsub += bytes(PAD)

fb = FontBuilder(1024, isTTF=True); fb.setupGlyphOrder(gorder)
fb.setupCharacterMap({0xE000+i: f'D{i}' for i in range(ND)})
empty = TTGlyphPen(None).glyph()
box = TTGlyphPen(None); box.moveTo((0,0)); box.lineTo((0,10)); box.lineTo((10,10)); box.lineTo((10,0)); box.closePath()
fb.setupGlyf({g: (box.glyph() if g == '.notdef' else empty) for g in gorder})
fb.setupHorizontalMetrics({g: ((int(g[1:]) if g.startswith('S') else 0), 0) for g in gorder})
fb.setupHorizontalHeader(ascent=800, descent=-200); fb.setupNameTable({'familyName':'VM','styleName':'Regular'})
fb.setupOS2(xAvgCharWidth=500); fb.setupPost()
t = newTable('GSUB'); t.decompile = None
from fontTools.ttLib.tables.DefaultTable import DefaultTable
raw = DefaultTable('GSUB'); raw.data = gsub; fb.font['GSUB'] = raw
fb.save('vm.ttf'); print('GSUB bytes', len(gsub), 'font', len(open('vm.ttf','rb').read()))

def ref(s, n):
    p, a = divmod(s, 256)
    for _ in range(n): p, a = step(p, a)
    return p*256 + a
if __name__ == '__main__':
    import uharfbuzz as hb, random, time
    F = hb.Font(hb.Face(hb.Blob.from_file_path('vm.ttf')))
    random.seed(1); bad = 0
    for i, k in enumerate(KS):
        tt = 0
        for _ in range(20):
            s = random.randrange(0, 256) if random.random() < .5 else random.randrange(NS)
            b = hb.Buffer(); b.add_str(chr(0xE000 + s//128) + chr(0xE000 + s%128)); b.guess_segment_properties()
            t0 = time.perf_counter(); hb.shape(F, b, {f'ss{i+1:02d}': True}); tt += time.perf_counter() - t0
            w = sum(q.x_advance for q in b.glyph_positions)
            if w != ref(s, k): bad += 1; print('BAD', k, s, w, ref(s, k)) if bad < 5 else None
        print(f'K={k:6d}  avg {tt/20*1e3:.3f} ms  ({tt/20/k*1e9:.1f} ns/step)')
    print('mismatches', bad)
