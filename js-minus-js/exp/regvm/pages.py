"""pages.py dir [maxsteps] — the register CPU's C2 pages: for each suite program inside the subset with at most maxsteps steps
(default 1500), the image of its padded editor source and the page gen_rcss.py builds from it, Node's output as the expected
console (as tests/csscpu_pages.py). Run them with node tests/csscpu_pages.js dir."""
import sys, os, json, glob, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE] + [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback', 'tests')]
import rc_ref as RC, ccpage5 as C
from par import pmap
out = sys.argv[1]; maxsteps = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
os.makedirs(out, exist_ok=True)
def one(f):
    name = os.path.basename(f)[:-3]
    try: im = RC.image(C.padded_source(open(f).read().rstrip('\n'), 24, 64))
    except ValueError: return None                       # outside the subset
    if im['steps'] > maxsteps: return None
    im['expected'] = open(f[:-3] + '.out').read()
    js = os.path.join(out, name + '.json'); json.dump(im, open(js, 'w'))
    subprocess.run([sys.executable, os.path.join(HERE, 'gen_rcss.py'), js, os.path.join(out, name + '.html')], check=True, capture_output=True)
    return name
names = [n for n in pmap(one, sorted(glob.glob(os.path.join(ROOT, 'tests', 'suite', '*.js')))) if n]
open(os.path.join(out, 'list.txt'), 'w').write('\n'.join(names) + '\n')
print(len(names), 'pages')
