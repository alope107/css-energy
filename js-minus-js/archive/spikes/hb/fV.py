# Variable-font LUT: axis XVAL 0..4095, HVAR advance(g) = f(x) via one tent region per integer x.
# Also axes AAAA, BBBB 0..127 with one corner region: advance(m) = 16 * a * b  (bilinear product).
import base64
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib import newTable
from fontTools.varLib import builder as vb
from mk import build
M=4095
f = lambda x: (x*x*7 + 3) % 32768
def extra(fb):
    fb.setupFvar([('XVAL',0,0,16384,'X'), ('AAAA',0,0,127,'A'), ('BBBB',0,0,127,'B')], [])
def n14(v): return round(v*16384)/16384
font = build('v.ttf', ['g','m'], {'g':0,'m':0}, {0xE000:'g', 0xE001:'m'}, "", upem=1024, box=True, extra=extra)
from fontTools.ttLib import TTFont
font = TTFont('v.ttf')
axes = ['XVAL','AAAA','BBBB']
regions = []
for k in range(1, M+1):
    p = 4*k/16384; lo = 4*(k-1)/16384; hi = 4*(k+1)/16384 if k < M else 1.0
    regions.append({'XVAL': (lo, p, hi)})
regions.append({'AAAA': (0, 1.0, 1.0), 'BBBB': (0, 1.0, 1.0)})
rl = vb.buildVarRegionList(regions, axes)
rows_g = [f(k) - f(0) for k in range(1, M+1)] + [0]
rows_m = [0]*M + [16*127*127 if 16*127*127 < 32768 else 0]
# product delta must fit int16: use 2*127*127 = 32258
rows_m[-1] = 2*127*127
vd = vb.buildVarData(list(range(len(regions))), [[0]*len(regions), rows_g, rows_m], optimize=False)
store = vb.buildVarStore(rl, [vd])
hvar = newTable('HVAR'); hvar.table = ot.HVAR(); hvar.table.Version = 0x00010000; hvar.table.VarStore = store
hvar.table.AdvWidthMap = None; hvar.table.LsbMap = None; hvar.table.RsbMap = None
font['HVAR'] = hvar
font['hmtx']['g'] = (f(0), 0)
font.save('v.ttf')
import uharfbuzz as hb
F = hb.Font(hb.Face(hb.Blob.from_file_path('v.ttf')))
bad = 0
for x in range(0, M+1):
    F.set_variations({'XVAL': 4*x}); b = hb.Buffer(); b.add_str(''); b.guess_segment_properties(); hb.shape(F, b, {})
    bad += b.glyph_positions[0].x_advance != f(x)
print('HVAR LUT harfbuzz mismatches', bad)
F.set_variations({'AAAA': 100, 'BBBB': 77}); b = hb.Buffer(); b.add_str(''); b.guess_segment_properties(); hb.shape(F, b, {})
print('product 100*77*2 =', 100*77*2, 'got', b.glyph_positions[0].x_advance)
