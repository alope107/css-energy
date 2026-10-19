import re, sys
def parse(p):
    s = open(p).read()
    out = {}
    for m in re.finditer(r'BASE_FEATURE\((k\w+)\s*,(.*?)\);', s, re.S):
        body = m.group(2)
        en = 'ENABLED' in body; dis = 'DISABLED' in body
        st = 'cond' if (en and dis) else 'on' if en else 'off'
        if '#if' in body: st = 'cond:' + ','.join(re.findall(r'#if (.*)', body))[:60] + (' on' if en else '') + (' off' if dis else '')
        out[m.group(1)] = st
    return out
V = [('153', 'v/g_feat_8010.cc'), ('155', 'v/g_feat_8059.cc'), ('157', 'v/g_feat_8103.cc'), ('main', 'v/g_feat_main.cc')]
d = {v: parse(p) for v, p in V}
names = set().union(*[x.keys() for x in d.values()])
for n in sorted(names, key=lambda n: (n in d['153'], n in d['main'], n)):
    sts = [d[v].get(n, '—') for v, _ in V]
    if len(set(sts)) > 1:
        print(f"{n:60s} " + ' | '.join(f'{x:6s}' for x in sts))
