"""mkimage.py [--ram] source.js out.json — a machine image (cc_ref.image). Without --ram, the page's image: ROM = the lib,
RAM all zero, since the compile chain supplies code and data (make page). With --ram, the program sits in RAM as the
CSS compiler leaves it: for CPU-only pages (machine/gen_css.py without UI=1) and the CSS CPU's model."""
import sys, json, os
import cc_ref as R
args = [a for a in sys.argv[1:] if a != '--ram']
lib = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib.json')))
im = R.image(open(args[0]).read(), lib, ram='--ram' in sys.argv)
json.dump(im, open(args[1], 'w'))
print('steps', im['steps'], 'rom', len(lib['rom']))
