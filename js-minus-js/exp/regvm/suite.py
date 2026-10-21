"""suite.py [-v] — the register machine's L1: rc_ref compiles and runs every tests/suite program inside the subset, against
Node's output; tests/suite_err must be rejected. Prints the steps beside main's (cc_ref) for each."""
import sys, os, glob, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, os.path.join(ROOT, 'compiler')]
import rc_ref as RC, cc_ref as R
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
res, tot = {}, [0, 0]
for f in sorted(glob.glob(os.path.join(ROOT, 'tests', 'suite', '*.js'))):
    n = os.path.basename(f)[:-3]; src = open(f).read(); want = open(f[:-3] + '.out').read()
    try:
        c, r = RC.compile_and_run(src)
        if r is None: res[n] = ('outside' if c.err == RC.NOTSUB else 'COMPILE-ERR', c.err); continue
        if r[1] != want: res[n] = ('WRONG', repr(r[1][:50]) + ' want ' + repr(want[:50])); continue
        s0 = R.compile_and_run(src, lib)[1][0]; res[n] = ('ok', f'{r[0]:6} steps, main {s0:6}  ({s0 / r[0]:.2f}x)'); tot[0] += r[0]; tot[1] += s0
    except Exception as e: res[n] = ('CRASH', str(e)[:80])
rej = 0; errs = sorted(glob.glob(os.path.join(ROOT, 'tests', 'suite_err', '*.js')))
for f in errs:
    c, words, data = RC.compile_src(open(f).read())
    if c.err: rej += 1
    else: res['err/' + os.path.basename(f)] = ('ACCEPTED', 'should be rejected')
for k, v in res.items():
    if v[0] != 'outside' and (v[0] != 'ok' or '-v' in sys.argv): print(f'{k:22} {v[0]:12} {v[1]}')
ok = sum(1 for v in res.values() if v[0] == 'ok'); out = sum(1 for v in res.values() if v[0] == 'outside')
print(f'{ok} ok, {out} outside the subset, {len(res) - ok - out} failing; suite_err {rej}/{len(errs)} rejected;'
      f' steps {tot[0]} vs main {tot[1]} ({tot[1] / max(1, tot[0]):.2f}x fewer)')
