"""Glyph-type renumbering so that heavily walked lookups' mark-filtering sets fit one 512-gid bit-page.
usage: renum.py image.json prof_t.txt order.json   (writes a type order; variant builds use it via ORDER=order.json)"""
import sys, os, json, collections, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../repo/js-minus-js/machine'); os.environ['CPUMOD'] = 'cpu4'
import cpu4
image = json.load(open(sys.argv[1])); cpu = cpu4.CPU(image, 16); P = cpu.P
P.build(32, top13=cpu.top13, ptype='P', export_stage=cpu.export, debug_features=0)
L = P.all_lookups; lc = P.lookup_counts; nL, nP, nC, nT = lc['lib'], lc['pre'], lc['cycle'], lc['tail']
idx = list(range(nL)) + [nL + i for i in range(nP)] + [nL + nP + i for _ in range(32) for i in range(nC)] + [nL + nP + nC + i for i in range(nT)]
ms = collections.Counter()
for line in open(sys.argv[2]):
    f = line.split()
    if f[0] == 'tsc_ghz': g = float(f[1]); sh = int(f[3])
    if f[0] == 'lk': ms[idx[int(f[1])]] += int(f[2]) / g / 1e6 / sh
types = list(P.types.values()); size = {t.name: len(t.values) for t in types}
gid2type = {}
for t in types:
    for k in range(len(t.values)): gid2type[t.gid0 + k] = t.name
lk_types = []
for d, lk in enumerate(L):
    if lk.mark_set is None: continue
    ts = sorted({gid2type[gg] for gg in P.mark_sets[lk.mark_set]})
    if sum(size[t] for t in ts) < 512: lk_types.append((ms[d], ts, lk.name))
def score(order):
    pos = {}; p = 1
    for t in order: pos[t] = p; p += size[t]
    s = 0
    for w, ts, _ in lk_types:
        lo = min(pos[t] for t in ts); hi = max(pos[t] + size[t] for t in ts)
        if hi - lo <= 512: s += w
    return s
orig = [t.name for t in types]
print('score original', round(score(orig), 2), 'max', round(sum(w for w, _, _ in lk_types), 2))
# greedy: heaviest lookup first, append its unplaced types
order = []; placed = set()
for w, ts, n in sorted(lk_types, key=lambda x: -x[0]):
    for t in ts:
        if t not in placed: order.append(t); placed.add(t)
order += [t for t in orig if t not in placed]
print('score greedy', round(score(order), 2))
seed = [f'L.BD{j}' for j in range(5)] + [x for j in range(5) for x in [f'L.GS{j}'] + [f'L.VAL{w}_{j}' for w in range(4)]] + [f'L.G{b}' for b in range(20)] + [f'MDRB{b}' for b in range(20)] + ['MOP']
order = seed + [t for t in order if t not in seed]
print('score seeded', round(score(order), 2))
# local search: move a random type block to a random position
random.seed(1); best = score(order); cur = order[:]
for it in range(int(os.environ.get('ITERS', 3000))):
    i = random.randrange(len(cur)); j = random.randrange(len(cur))
    cand = cur[:]; t = cand.pop(i); cand.insert(j, t)
    s = score(cand)
    if s >= best: best, cur = s, cand
print('score local', round(best, 2))
json.dump(cur, open(sys.argv[3], 'w'))
if os.environ.get('SHOW'):
    pos = {}; p = 1
    for t in cur: pos[t] = p; p += size[t]
    for w, ts, n in sorted(lk_types, key=lambda x: -x[0])[:40]:
        lo = min(pos[t] for t in ts); hi = max(pos[t] + size[t] for t in ts)
        print(f'{n[:24]:24s} {w:.3f} n={sum(size[t] for t in ts):4d} span={hi-lo:5d} {"OK" if hi-lo<=512 else "  "} ', ' '.join(f'{t}:{size[t]}' for t in ts)[:150])
