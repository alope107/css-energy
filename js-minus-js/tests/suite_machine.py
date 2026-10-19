"""suite_machine.py [dir] — level 4: the font CPU's reference model (uarch4.Machine4: 20-bit words, 4-word cache
lines, the page's trap service) runs each program from the RAM image the CSS compiler leaves (cc_ref on the padded
editor source, which level 3 shows the chain matches word for word); output compared with Node's."""
import sys, os, json, glob
HERE = os.path.dirname(os.path.abspath(__file__))
import os, sys; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]  # repo root
import cc_ref as R, ccpage5 as C
from uarch4 import Machine4
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'suite')
N, S = 16, 32
def one(f):
    """-> (passed, lines to print)"""
    name = os.path.basename(f)[:-3]; want = open(f[:-3] + '.out').read()
    try: image = R.image(C.padded_source(open(f).read().rstrip('\n'), 24, 64), lib, ram=True)
    except ValueError as e: return False, [f'{name:22} COMPILE-ERR {e}']
    m = Machine4(image, N)
    try: m.run(S)
    except Exception as e: return False, [f'{name:22} CRASH {e}']
    got = ''.join(map(chr, m.out))
    out = [] if got == want else [f'{name:22} WRONG {got[:60]!r} want {want[:60]!r}']
    if os.environ.get('V'): out.append(f'{name:22} steps {m.steps} shapings {m.shapings}')
    return got == want, out
from par import pmap                    # one program per worker process
fs = sorted(glob.glob(d + '/*.js')); ok = 0
for passed, out in pmap(one, fs):
    ok += passed
    for ln in out: print(ln)
print(f'{ok}/{len(fs)} pass')
