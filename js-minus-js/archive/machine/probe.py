import uharfbuzz as hb
from otl import *
from fontbase import make_font
names = ['.notdef', 'X'] + [f'A{i}' for i in range(4)] + [f'B{i}' for i in range(4)] + [f'a{i}' for i in range(4)]
gid = {n: i for i, n in enumerate(names)}
A = [gid[f'A{i}'] for i in range(4)]; B = [gid[f'B{i}'] for i in range(4)]; X = gid['X']
# SET lookups 0..3: map A*/B* -> value i
sets = [Lookup(1, [single_subst({**{a: A[i] for a in A}, **{b: B[i] for b in B}})], name=f'SET{i}') for i in range(4)]
# T1: filter {A,B}; B := value of previous A (view offset -1); A := previous B + 1
cdA = {A[i]: 1 + i for i in range(4)}; cdB = {B[i]: 5 + i for i in range(4)}
bt_cd = {**cdA, **cdB}; in_cd = {**{a: 1 for a in A}, **{b: 2 for b in B}}
rules = [([1 + v], 2, [], [(0, v)]) for v in range(4)] + [([5 + v], 1, [], [(0, (v + 1) % 4)]) for v in range(4)]
t1 = Lookup(6, [chain_class(A + B, bt_cd, in_cd, {}, rules)], mark_set=0)
# T2: reverse: A := 3 if next A (view) is 3
t2 = Lookup(8, [reverse_chain({a: A[3] for a in A}, [], [[A[3]]])], mark_set=1)
# export: A_i -> a_i (base)
ex = Lookup(1, [single_subst({A[i]: gid[f'a{i}'] for i in range(4)})])
lks = sets + [t1, t2, ex]
gsub = build_gsub(lks, list(range(len(lks))), [('ss01', [4]), ('ss02', [5]), ('ss03', [6]), ('ss04', [])])
gc = {g: 3 for g in A + B + [X]}; gc.update({gid[f'a{i}']: 1 for i in range(4)})
gdef = build_gdef(gc, [set(A + B), set(A)])
cmap = {0xE000 + i: n for i, n in enumerate(names[1:])}
make_font('probe.ttf', names, {n: 100 for n in names}, cmap, gsub, gdef)
F = hb.Font(hb.Face(hb.Blob.from_file_path('probe.ttf')))
cp = {n: chr(0xE000 + i) for i, n in enumerate(names[1:])}
def run(seq, feats):
    b = hb.Buffer(); b.add_str(''.join(cp[n] for n in seq)); b.guess_segment_properties(); hb.shape(F, b, feats)
    return [names[i.codepoint] for i in b.glyph_infos], [p.x_advance for p in b.glyph_positions]
print('T1 filter+backtrack:', run(['A1', 'X', 'B0', 'X', 'A0', 'X', 'B0'], {'ss01': True})[0], '(want A1 X B1 X A2 X B2)')
print('T2 reverse+filter: ', run(['A0', 'X', 'A0', 'X', 'B2', 'A3'], {'ss02': True})[0], '(want A3 X A3 X B2 A3)')
print('marks advance:     ', run(['A1', 'X', 'B0'], {})[1], ' exported:', run(['A1', 'X', 'B0'], {'ss03': True}))
