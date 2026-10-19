import json, collections, sys
W = sys.argv[1]; info = json.load(open(f'{W}/lkinfo.json')); L = info['lookups']; idx = info['index_list']
def load(p):
    lk = {}
    for line in open(p):
        f = line.split()
        if f[0] == 'tsc_ghz': ghz = float(f[1]); sh = int(f[3])
        if f[0] == 'lk': lk[int(f[1])] = list(map(int, f[2:]))
    return ghz, sh, lk
g, sh, lt = load(sys.argv[2]); g2, sh2, lc = load(sys.argv[3])
agg = collections.defaultdict(lambda: [0.0] * 8)
for li, v in lt.items(): agg[idx[li]][0] += v[0] / g / sh  # ns per shaping
for li, v in lc.items():
    a = agg[idx[li]]
    for k in range(1, 7): a[k] += v[k] / sh2
rows = list(agg.items())
names = ['app', 'fwd_apply', 'rapply', 'step', 'classdef']
X = [[a[1], a[2], a[4], a[5], a[6]] for d, a in rows]; y = [a[0] for d, a in rows]
n = len(names)
A = [[sum(x[i] * x[j] for x in X) for j in range(n)] + [sum(x[i] * yy for x, yy in zip(X, y))] for i in range(n)]
for i in range(n):
    p = max(range(i, n), key=lambda r: abs(A[r][i])); A[i], A[p] = A[p], A[i]
    for r in range(n):
        if r != i:
            f = A[r][i] / A[i][i]; A[r] = [a - f * b for a, b in zip(A[r], A[i])]
coef = [A[i][n] / A[i][i] for i in range(n)]
pred = [sum(c * xx for c, xx in zip(coef, x)) for x in X]; ym = sum(y) / len(y)
r2 = 1 - sum((a - b) ** 2 for a, b in zip(y, pred)) / sum((a - ym) ** 2 for a in y)
print('ns per ' + '  '.join(f'{nm} {c:.2f}' for nm, c in zip(names, coef)), f' R^2 {r2:.3f}')
tot = sum(y); print('share: ' + ' '.join(f'{nm}={sum(c * x[i] for x in X) / tot:.0%}' for i, (nm, c) in enumerate(zip(names, coef))))
