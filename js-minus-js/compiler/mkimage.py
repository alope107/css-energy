"""mkimage.py source.js out.json — f4 image for the CSS-compiled page: ROM = lib (with startup copy), RAM all zero
(the compile chain's overlays supply code and data); expected output/steps from cc_ref's simulation of what the
chain produces."""
import sys, json
import cc_ref as R
import os
lib = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib.json')))
src = open(sys.argv[1]).read()
c, r = R.compile_and_run(src, lib)
assert not c.err and r, c.err
im = dict(rom=lib['rom'], ram=[0] * 3072, ramSize=3072, sp0=R.LAYOUT['sp0'], outBase=7040, rows=16, cols=8, source=src,
          codeBase=R.LAYOUT['code_base'], steps=r[0], expected=r[1], direct=False, romWords=len(lib['rom']), cssCompiled=True)
json.dump(im, open(sys.argv[2], 'w'))
print('steps', r[0], 'rom', len(lib['rom']))
