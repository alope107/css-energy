"""suite_machine.py [dir] — level 4: the font CPU's reference model (uarch4.Machine4: 20-bit words, 4-word cache
lines, the page's trap service) runs each program from the RAM image the CSS compiler leaves (cc_ref on the padded
editor source, which level 3 shows the chain matches word for word); output compared with Node's."""
import sys, os, json, glob
HERE = os.path.dirname(os.path.abspath(__file__))
import os, sys; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]  # repo root
import cc_ref as R, ccpage5 as C
from uarch4 import Machine4
from uarch import ROM
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'suite')
N, S = 16, 32
ok = 0; tot = 0
for f in sorted(glob.glob(d + '/*.js')):
    name = os.path.basename(f)[:-3]; want = open(f[:-3] + '.out').read(); tot += 1
    c = R.Compiler(4096, 4608, lib); words, data = c.compile(C.padded_source(open(f).read().rstrip('\n'), 24, 64))
    if c.err: print(f'{name:22} COMPILE-ERR {c.err}'); continue
    mem = R.image_mem(c, words, data, lib['init'])
    image = dict(rom=lib['rom'], ram=[mem.get(ROM + i, 0) for i in range(3072)], sp0=R.LAYOUT['sp0'])
    m = Machine4(image, N)
    try: m.run(S)
    except Exception as e: print(f'{name:22} CRASH {e}'); continue
    got = ''.join(map(chr, m.out))
    if got == want: ok += 1
    else: print(f'{name:22} WRONG {got[:60]!r} want {want[:60]!r}')
    if os.environ.get('V'): print(f'{name:22} steps {m.steps} shapings {m.shapings}')
print(f'{ok}/{tot} pass')
