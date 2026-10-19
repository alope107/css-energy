import re, sys
def parse(p):
    s = open(p).read()
    out = {}
    for m in re.finditer(r'BASE_FEATURE\((k\w+)\s*,(.*?)\);', s, re.S):
        body = m.group(2); en = 'ENABLED' in body; dis = 'DISABLED' in body
        st = ('cond' if en and dis else 'on' if en else 'off')
        out[m.group(1)] = st
    return out
a, b = parse(sys.argv[1]), parse(sys.argv[2])
pat = re.compile(sys.argv[3], re.I) if len(sys.argv) > 3 else None
for n in sorted(set(a) | set(b)):
    if a.get(n) != b.get(n) and (not pat or pat.search(n)):
        print(f"  {n:60s} 153={a.get(n, '—'):5s} main={b.get(n, '—')}")
