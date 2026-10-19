import json, sys, collections
W = sys.argv[1]; info = json.load(open(f'{W}/lkinfo.json')); L = info['lookups']; idx = info['index_list']
def load(p):
    ghz = sh = None; lk = {}; cnt = {}
    for line in open(p):
        f = line.split()
        if f[0] == 'tsc_ghz': ghz = float(f[1]); sh = int(f[3])
        elif f[0] == 'cnt': cnt[int(f[1])] = int(f[2])
        elif f[0] == 'lk': lk[int(f[1])] = list(map(int, f[2:]))
    return ghz, sh, lk, cnt
ghz, sh, lkt, cnt = load(sys.argv[2]); ghz2, sh2, lkc, cnt2 = load(sys.argv[3])
agg = collections.defaultdict(lambda: [0.0] * 8)
for li, v in lkt.items():
    d = idx[li]; a = agg[d]; a[0] += v[0] / ghz / 1e6 / sh; a[1] += v[1] / sh
for li, v in lkc.items():
    d = idx[li]; a = agg[d]
    for k in range(2, 7): a[k] += v[k] / sh2
tot = sum(a[0] for a in agg.values())
print(f'total GSUB ms/shaping (sum of lookups) {tot:.2f}; GSUB apply total {cnt[40]/ghz/1e6/cnt[41]:.2f}')
rows = sorted(agg.items(), key=lambda kv: -kv[1][0])
print(f'{"lookup":28s} {"type":>4s} {"sub":>4s} {"rules":>6s} {"ms_n":>5s} {"span":>5s} {"ms":>6s} {"%":>5s} {"apps":>5s} {"fwdap":>7s} {"rules":>7s} {"rapply":>7s} {"steps":>8s} {"cls":>7s}')
cum = 0
for d, a in rows[:45]:
    l = L[d]; cum += a[0]
    print(f'{l["name"][:28]:28s} {l["type"]:4d} {l["nsub"]:4d} {l.get("rules",0):6d} {l.get("ms_n",0):5d} {l.get("ms_span",0):5d} {a[0]:6.3f} {100*a[0]/tot:5.1f} {a[1]:5.0f} {a[2]:7.0f} {a[3]:7.0f} {a[4]:7.0f} {a[5]:8.0f} {a[6]:7.0f}')
print('cum top45 %', 100 * cum / tot)
# by type
bt = collections.defaultdict(float)
for d, a in agg.items(): bt[L[d]['type']] += a[0]
print('by type', {k: round(v, 2) for k, v in bt.items()})
# lib vs cycle
nL = info['counts']['lib']
print('nested lib lookups top-level time', sum(a[0] for d, a in agg.items() if d < nL))
print('--- cheapest 15')
for d, a in sorted(agg.items(), key=lambda kv: kv[1][0])[:15]:
    l = L[d]; print(f'{l["name"][:28]:28s} {l["type"]:4d} {l["nsub"]:4d} ms {a[0]:.4f} us/app {a[0]*1e3/max(a[1],1):.2f} fwdap {a[2]:.0f} steps {a[5]:.0f}')
# groups
import re
grp = collections.defaultdict(float)
for d, a in agg.items():
    n = L[d]['name']; g = re.sub(r'[:.].*', '', n) if not n.startswith('K3 gather') else 'K3 gather'
    grp[g] += a[0]
print('--- by stage group (ms)')
for g, v in sorted(grp.items(), key=lambda kv: -kv[1]): print(f'  {g:20s} {v:6.2f} {100*v/tot:5.1f}%')
steps = sum(a[5] for a in agg.values()); fa = sum(a[2] for a in agg.values()); ra = sum(a[4] for a in agg.values())
print(f'per shaping: steps {steps:.0f} fwd_apply {fa:.0f} rapply {ra:.0f} lookup apps {sum(a[1] for a in agg.values()):.0f}')
