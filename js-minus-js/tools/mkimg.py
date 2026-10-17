"""mkimg.py prog.js out.json — the RAM image the CSS compiler leaves for a program (cc_ref on the source), as the machine
harnesses take it: machine/hbtest.py (the font in uharfbuzz against the model), gen_fvm4.py's CPU-only pages."""
import os, sys, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine')]
import cc_ref as R
from uarch import ROM
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
c = R.Compiler(R.LAYOUT['data_base'], R.LAYOUT['code_base'], lib); words, data = c.compile(open(sys.argv[1]).read())
if c.err: sys.exit(f'compile error {c.err}')
mem = R.image_mem(c, words, data, lib['init'])
_, r = R.compile_and_run(open(sys.argv[1]).read(), lib)
json.dump(dict(rom=lib['rom'], ram=[mem.get(ROM + i, 0) for i in range(R.LAYOUT['ram_size'])], sp0=R.LAYOUT['sp0'], expected=r[1]),
          open(sys.argv[2], 'w'))
