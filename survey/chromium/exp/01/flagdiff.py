import re, sys
def load(p):
    t = open(p).read()
    out = {}
    for m in re.finditer(r'\{\s*(?://[^\n]*\n\s*)*name:\s*"([^"]+)"(.*?)\n\s*\}', t, re.S):
        name, body = m.group(1), m.group(2)
        st = re.search(r'status:\s*("[^"]+"|\{[^}]*\})', body)
        out[name] = st.group(1) if st else '-'
    return out
SP = sys.argv[1]
a = load(f'{SP}/src/versions/153/third_party/blink/renderer/platform/runtime_enabled_features.json5')
b = load(f'{SP}/src/versions/155/third_party/blink/renderer/platform/runtime_enabled_features.json5')
c = load(f'{SP}/src/chromium/third_party/blink/renderer/platform/runtime_enabled_features.json5')
pat = re.compile(sys.argv[2], re.I)
for n in sorted(set(a) | set(b) | set(c)):
    if not pat.search(n): continue
    va, vb, vc = a.get(n, 'absent'), b.get(n, 'absent'), c.get(n, 'absent')
    if va != vc or vb != vc:
        print(f'{n:60s} 153={va:14s} 155={vb:14s} main={vc}')
