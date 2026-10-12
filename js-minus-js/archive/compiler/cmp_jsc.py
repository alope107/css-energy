"""cmp_jsc.py files... — compile each with jsc (build.js --direct) and with cc_ref; compare output and steps."""
import sys, json, subprocess, os
from cc_ref import compile_and_run
lib = json.load(open('lib.json'))
ok = True
for f in sys.argv[1:]:
    subprocess.run(['node', 'build.js', f, '/tmp/cmp.json', '--direct'], capture_output=True, check=True)
    im = json.load(open('/tmp/cmp.json'))
    c, r = compile_and_run(open(f).read(), lib)
    if c.err or r is None: print(f, 'ERROR', c.err); ok = False; continue
    same = r[1] == im['expected']
    print(f'{f}: output {"same" if same else "DIFFERENT"}; steps jsc {im["steps"]} cc {r[0]} (diff {r[0] - im["steps"]})')
    if not same: print('  jsc:', repr(im['expected'])); print('  cc :', repr(r[1])); ok = False
print('ALL OK' if ok else 'FAILURES')
