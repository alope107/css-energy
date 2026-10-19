import sys, json
sys.path.insert(0, sys.argv[1])
import json5
V = [('153', 'v/g_ref_8010.json5'), ('155', 'v/g_ref_8059.json5'), ('157', 'v/g_ref_8103.json5'), ('main', 'v/g_ref_main.json5')]
data = {}
for v, p in V:
    for f in json5.load(p)['data']:
        data.setdefault(f['name'], {})[v] = f
def st(f):
    if f is None: return '—'
    s = f.get('status', '')
    if isinstance(s, dict):
        s = '{' + ','.join(f'{k}:{v or "off"}' for k, v in s.items()) + '}'
    return s or 'off'
rows = []
for name, d in data.items():
    sts = [st(d.get(v)) for v, _ in V]
    if len(set(sts)) > 1:
        last = d.get('main') or d.get('157') or d.get('155') or d.get('153')
        rows.append((name, sts, last.get('origin_trial_feature_name', ''), last.get('depends_on', ''), last.get('implied_by', '')))
kind = sys.argv[2] if len(sys.argv) > 2 else 'all'
for name, sts, ot, dep, imp in sorted(rows, key=lambda r: (r[1][0] != '—', r[1][3] != '—', r[0])):
    print(f"{name:55s} " + ' | '.join(f'{s:12s}' for s in sts) + (f' OT:{ot}' if ot else '') + (f' dep:{dep}' if dep else '') + (f' impl:{imp}' if imp else ''))
print(len(rows), file=sys.stderr)
