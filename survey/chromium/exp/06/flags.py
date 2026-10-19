import re, sys
def parse(p):
    t = open(p).read()
    out = {}
    # split on entries: each starts with '{' and has name:
    for m in re.finditer(r'\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}', t):
        body = m.group(1)
        n = re.search(r'name:\s*"([^"]+)"', body)
        if not n: continue
        s = re.search(r'status:\s*("[^"]*"|\{[^}]*\})', body)
        out[n.group(1)] = re.sub(r'\s+', ' ', s.group(1)) if s else '-'
    return out
paths = sys.argv[1:]
ds = [parse(p) for p in paths]
names = sorted(set().union(*ds))
pat = re.compile(r'Font|Shap|Harf|Glyph|Text(?!Area)|Emoji|Palette|Kern|Ligat|Counter|Math|Ift|Incremental|Fontation|Avar|Variab|LineBreak|Ruby|Hyphen|Letter|WordSpac')
for n in names:
    if not pat.search(n): continue
    vals = [d.get(n, 'ABSENT') for d in ds]
    if len(set(vals)) > 1:
        print(n.ljust(48), ' | '.join(v.ljust(14) for v in vals))
