import json, sys
d = json.load(open(sys.argv[1]))
def get(path):
    x = d
    for p in path.split('.'):
        x = x.get(p) if isinstance(x, dict) else None
        if x is None: return None
    return x
def fmt(st):
    if st is None: return '?'
    if isinstance(st, list): st = st[0]
    v = st.get('version_added')
    flags = ' (flag)' if st.get('flags') else ''
    pref = ' partial' if st.get('partial_implementation') else ''
    return f"{v}{flags}{pref}"
keys = sys.argv[2:]
for k in keys:
    c = get(k)
    if not c or '__compat' not in c:
        # list children
        print(f"{k:70s} MISSING"); continue
    s = c['__compat']['support']
    print(f"{k:70s} chrome {fmt(s.get('chrome')):12s} firefox {fmt(s.get('firefox')):16s} safari {fmt(s.get('safari'))}")
