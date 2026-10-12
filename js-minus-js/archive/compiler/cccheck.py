import json, sys, cc_ref as R
lib = json.load(open('/root/cc/lib.json'))
out = json.load(open(sys.argv[2]))
c = R.Compiler(4096, 4608, lib); words, data = c.compile(open(sys.argv[1]).read())
got = {int(k[3:]) + 4096: v for k, v in out['code'].items()}
gd = {int(k[3:]) + 4096: v for k, v in out['data'].items()}
from cc_ref import image_mem
im = image_mem(c, {}, data, lib['init']); data = {a: v for a, v in im.items()}
print('load', out['loadMs'], 'recalc', out['recalcMs'], 'layout', out['layoutMs'], out['err'])
bad = [(a, words.get(a), got.get(a)) for a in sorted(set(words) | set(got)) if words.get(a) != got.get(a)]
badd = [(a, data.get(a), gd.get(a)) for a in sorted(set(data) | set(gd)) if data.get(a) != gd.get(a)]
print('code words', len(words), 'got', len(got), 'mismatch', len(bad), bad[:6]); print('data', len(data), len(gd), 'mismatch', len(badd), badd[:6])
