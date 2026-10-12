"""Strip families of gated @container blocks from a (usually frozen) PLAIN page, to measure what they cost.

  python3 tools/ablate.py out/FZ_x.html pairs=--(tcp|np|p\\d+_\\d+(uA|uB|ov)) ac=--ac\\d all=.
  -> out/FZ_x_pairs.html, out/FZ_x_ac.html, out/FZ_x_all.html  (then: node tools/tr.js a.html,b.html,...)

Each NAME=REGEX removes every top-level @container block whose condition matches REGEX (brace-matched).
Removing one gate family changes downstream gates, so deltas overlap; read them as rough attributions."""
import re, sys


def strip(s, pat):
    out, i, n = [], 0, 0
    for m in re.finditer(r'@container ([^{]*)\{', s):
        if m.start() < i:
            continue
        j, d = m.end(), 1
        while d:
            c = s[j]
            d += c == '{'
            d -= c == '}'
            j += 1
        if re.search(pat, m.group(1)):
            out.append(s[i:m.start()])
            i, n = j, n + 1
    out.append(s[i:])
    return ''.join(out), n


src = sys.argv[1]
s = open(src).read()
for arg in sys.argv[2:]:
    name, pat = arg.split('=', 1)
    t, n = strip(s, pat)
    dst = re.sub(r'\.html$', f'_{name}.html', src)
    open(dst, 'w').write(t)
    print(f'{dst}: removed {n} blocks, {len(s) - len(t)} bytes')
