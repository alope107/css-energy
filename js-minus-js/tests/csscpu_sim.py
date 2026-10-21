"""csscpu_sim.py [K] — level C1: the CSS CPU's design (machine/csssim.py: cache, prefetch, stalls, PRINT chunks) runs
each suite program from the RAM image the CSS compiler leaves (the padded editor source, as the page); output compared
with Node's, steps with cc_ref's. A program the compiler doesn't take yet (error 90) is skipped."""
import sys, os, json, glob
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]
import cc_ref as R, ccpage5 as C, cssref as ref, csssim as sim
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
K = int(sys.argv[1]) if __name__ == '__main__' and len(sys.argv) > 1 else 32
L = R.LAYOUT
def uses_objects(im):
    """(C2's page list once skipped programs with instructions the page lacked; the page has every instruction)"""
    return False
def one(f):
    """-> (verdict: pass / fail / skip, lines to print)"""
    name = os.path.basename(f)[:-3]; want = open(f[:-3] + '.out').read()
    try: im = R.image(C.padded_source(open(f).read().rstrip('\n'), 24, 64), lib, ram=True)
    except ValueError as e: return ('skip', []) if str(e) == f'compile error {R.NOTSUB}' else ('fail', [f'{name:22} COMPILE-ERR {e}'])
    s = sim.Sim(ref.from_image(im))
    try:
        while not s.st['halt'] and s.passes < 200000: s.run_pass(K)
    except (Exception, SystemExit) as e: return 'fail', [f'{name:22} CRASH {e}']
    got = ''.join(map(chr, s.st['out']))
    bad = [] if got == want else [f'WRONG {got[:60]!r} want {want[:60]!r}']
    if s.st['steps'] != im['steps']: bad.append(f"steps {s.st['steps']} want {im['steps']}")
    out = [f'{name:22} ' + '; '.join(bad)] if bad else []
    if os.environ.get('V'): out.append(f"{name:22} steps {s.st['steps']} passes {s.passes}")
    return 'fail' if bad else 'pass', out
if __name__ == '__main__':
    from par import pmap
    fs = sorted(glob.glob(os.path.join(ROOT, 'tests', 'suite', '*.js'))); n = {'pass': 0, 'fail': 0, 'skip': 0}
    for v, out in pmap(one, fs):
        n[v] += 1
        for ln in out: print(ln)
    print(f"{n['pass']}/{n['pass'] + n['fail']} pass" + (f" ({n['skip']} outside the compiler's language so far)" if n['skip'] else ''))
