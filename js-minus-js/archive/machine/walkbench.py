# cost of context walks in HarfBuzz: rule "A := B-value" with B at distance d, skipping X glyphs (filtered) or not
import time, uharfbuzz as hb
from otl import *
from fontbase import make_font
names = ['.notdef', 'X'] + [f'A{i}' for i in range(16)] + [f'B{i}' for i in range(16)]
gid = {n: i for i, n in enumerate(names)}
A = [gid[f'A{i}'] for i in range(16)]; B = [gid[f'B{i}'] for i in range(16)]; X = gid['X']
sets = [Lookup(1, [single_subst({a: A[i] for a in A})]) for i in range(16)]
def font(d, filt, path):
    # filtered: context = [B] at view distance 1 (X skipped). unfiltered: context = B then d X's as class 0 positions
    bt_cd = {B[i]: 1 + i for i in range(16)}
    if filt: rules = [([1 + v], 1, [], [(0, v)]) for v in range(16)]
    else: rules = [([0] * d + [1 + v], 1, [], [(0, v)]) for v in range(16)]
    lk = Lookup(6, [chain_class(A, bt_cd, {a: 1 for a in A}, {}, rules)], mark_set=0 if filt else None)
    gsub = build_gsub(sets + [lk], list(range(17)), [('ss01', [16])])
    gdef = build_gdef({g: 3 for g in A + B + [X]}, [set(A + B)])
    make_font(path, names, {}, {0xE000 + i: n for i, n in enumerate(names[1:])}, gsub, gdef)
    return hb.Font(hb.Face(hb.Blob.from_file_path(path)))
cp = {n: chr(0xE000 + i) for i, n in enumerate(names[1:])}
for d in [0, 8, 32, 64]:
    for filt in (True, False):
        if not filt and d > 60: continue
        F = font(d, filt, 'wb.ttf')
        unit = cp['B15'] + cp['X'] * d + cp['A0']       # worst case: matching rule is the last tried
        text = unit * 200
        t = 0
        for _ in range(20):
            b = hb.Buffer(); b.add_str(text); b.guess_segment_properties()
            t0 = time.perf_counter(); hb.shape(F, b, {'ss01': True}); t += time.perf_counter() - t0
        ok = all(F.glyph_to_string(i.codepoint) == 'A15' for i in b.glyph_infos if F.glyph_to_string(i.codepoint).startswith('A'))
        per = t / 20 / 200 * 1e9
        print(f'd={d:3} filtered={filt!s:5}  {per:8.0f} ns per target (16 tries)  -> {per / 16 / max(1, d + 1):6.1f} ns per try-step  ok={ok}')
