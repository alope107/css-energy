"""show.py build/fuzz/NAME — run one saved failure: our output against Node's, line by line (first differences)."""
import sys, os, difflib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.argv += []; import fuzz, progen
base = sys.argv[1].removesuffix('.js')
o, n = open(base + '.js').read(), open(base + '.node.js').read()
nr = fuzz.node([(n, progen.PRELUDE if n != o else '')])[0]
err, out, lim = fuzz.ours(o)
print('ours err', err, lim or '')
for l in list(difflib.unified_diff((nr.get('out') or '').split('\n'), (out or '').split('\n'), 'node', 'ours', lineterm='', n=1))[:int(os.environ.get('N', 12))]: print(l)
