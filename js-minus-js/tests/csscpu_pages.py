"""csscpu_pages.py dir [maxsteps] — CSS CPU pages for level C2: for each suite program of at most maxsteps steps
(default 1500), the image of its padded editor source and the page machine/gen_css.py builds from it, with Node's
output as the expected console. Writes dir/<name>.html and .json."""
import sys, os, json, glob, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback', 'tests')]
import cc_ref as R, ccpage5 as C
from par import pmap
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
out = sys.argv[1]; maxsteps = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
os.makedirs(out, exist_ok=True)
def one(f):
    name = os.path.basename(f)[:-3]
    im = R.image(C.padded_source(open(f).read().rstrip('\n'), 24, 64), lib, ram=True)
    if im['steps'] > maxsteps: return None
    im['expected'] = open(f[:-3] + '.out').read()
    js = os.path.join(out, name + '.json'); json.dump(im, open(js, 'w'))
    subprocess.run([sys.executable, os.path.join(ROOT, 'machine', 'gen_css.py'), js, os.path.join(out, name + '.html')], check=True, capture_output=True)
    return name
names = [n for n in pmap(one, sorted(glob.glob(os.path.join(ROOT, 'tests', 'suite', '*.js')))) if n]
open(os.path.join(out, 'list.txt'), 'w').write('\n'.join(names) + '\n')
print(len(names), 'pages')
