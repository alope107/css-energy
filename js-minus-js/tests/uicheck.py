"""uicheck.py source.js out.json L P — compare the chain's words with cc_ref on the padded source"""
import os, sys; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]  # repo root
import json, cc_ref as R, ccpage5 as C
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
src = open(sys.argv[1]).read().rstrip('\n'); out = json.load(open(sys.argv[2])); L, P = int(sys.argv[3]), int(sys.argv[4])
c = R.Compiler(4096, 4608, lib); words, data = c.compile(C.padded_source(src, L, P))
im = R.image_mem(c, {}, data, lib['init'])
got = {int(k[3:]) + 4096: v for k, v in out['code'].items()}; gd = {int(k[3:]) + 4096: v for k, v in out['data'].items()}
bad = [(a, words.get(a), got.get(a)) for a in sorted(set(words) | set(got)) if words.get(a) != got.get(a)]
badd = [(a, im.get(a), gd.get(a)) for a in sorted(set(im) | set(gd)) if im.get(a) != gd.get(a)]
print({k: out.get(k) for k in ('loadMs', 'doneMs', 'recalcMs', 'layoutMs', 'recalcs', 'done', 'err', 'words', 'ok')}, 'ref err', c.err, 'cp', c.cp)
print('code', len(words), len(got), 'mismatch', len(bad), bad[:6]); print('data', len(im), len(gd), 'mismatch', len(badd), badd[:6])
