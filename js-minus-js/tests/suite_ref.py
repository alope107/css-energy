"""suite_ref.py [dir] — level 1: the reference compiler (cc_ref) + bytecode simulator against Node's output."""
import sys, os, json, glob
import os, sys; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]  # repo root
import cc_ref as R
HERE = os.path.dirname(os.path.abspath(__file__))
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'suite')
res = {}
BIG = {'cmp_far'}                       # its long first line is a comment, which the page's truncation leaves harmless
for f in sorted(glob.glob(d + '/*.js')):
    name = os.path.basename(f)[:-3]; want = open(f[:-3] + '.out').read()
    lines = open(f).read().rstrip('\n').split('\n')
    if (len(lines) > 24 or max(map(len, lines)) > 64) and name not in BIG:       # the page would truncate it: L4 / L5 fail for the wrong reason
        res[name] = ('TOO-BIG', f'{len(lines)} lines, longest {max(map(len, lines))} (the editor is 24 x 64)'); continue
    try:
        c, r = R.compile_and_run(open(f).read(), lib, strict=True)
        if r is None: res[name] = ('COMPILE-ERR', c.err)
        elif r[1] == want: res[name] = ('ok', r[0])
        else: res[name] = ('WRONG', repr(r[1][:60]) + ' want ' + repr(want[:60]))
    except Exception as e: res[name] = ('CRASH', str(e)[:80])
ok = sum(1 for v in res.values() if v[0] == 'ok')
for k, v in res.items():
    if v[0] != 'ok': print(f'{k:18} {v[0]:12} {v[1]}')
print(f'{ok}/{len(res)} pass')
