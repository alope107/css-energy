"""suite_ui.py [maxsteps [limit]] — level 5 setup: for every suite test the machine can finish quickly, write the expected
console (Node's output laid out on the page's console grid, layout.json's cols x rows, as the output instructions do) to build/ui_exp, and
print the ui_seq.js argument list. The user's program from the bug report is first.
The net_* programs need the network gateway: NET=1 lists only them (make l5-net), otherwise they are left out."""
import sys, os, json, glob
import os, sys; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]  # repo root
import cc_ref as R
HERE = os.path.dirname(os.path.abspath(__file__))
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
EXP = os.path.join(ROOT, 'build', 'ui_exp')
COLS, ROWS = R.LAYOUT['cols'], R.LAYOUT['rows']
def grid(out):
    g = [' '] * (COLS * ROWS); p = 0
    for ch in out:
        if ch == '\n': p = (p // COLS + 1) * COLS % (COLS * ROWS)
        else: g[p] = ch if ' ' <= ch <= '~' else ' '; p = (p + 1) % (COLS * ROWS)     # the console shows other codes as blanks
    return '\n'.join(''.join(g[r * COLS:(r + 1) * COLS]).rstrip() for r in range(ROWS)).rstrip()
maxsteps = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10 ** 6     # at most this many valid programs (smoke runs)
os.makedirs(EXP, exist_ok=True)
open(f'{EXP}/user_report.js', 'w').write('var a = "hi"; console.log(a);\n'); open(f'{EXP}/user_report.out', 'w').write('hi\n')
args = []
# the page's initial program is tests/fizz.js (= suite/fizzbuzz.js): its grid is always written, for ui_seq's EXP1
open(f'{EXP}/fizzbuzz.grid', 'w').write(grid(open(os.path.join(HERE, 'suite', 'fizzbuzz.out')).read()) + '\n')
NET = os.environ.get('NET') == '1'
progs = sorted(glob.glob(os.path.join(HERE, 'suite', '*.js')))
progs = [f for f in progs if os.path.basename(f).startswith('net_') == NET]
for f in ([] if NET else [f'{EXP}/user_report.js']) + progs:
    if len(args) >= 2 * limit: break
    c, r = R.compile_and_run(open(f).read(), lib)
    if r is None or (r[0] > maxsteps and not NET): continue      # (r None: the compiler rejects it; a network program's time is its round trips)
    name = os.path.basename(f)[:-3]
    open(f'{EXP}/{name}.grid', 'w').write(grid(open(f[:-3] + '.out').read()) + '\n')
    args += [f, f'{EXP}/{name}.grid']
errs = [f for f in sorted(glob.glob(os.path.join(HERE, 'suite_err', '*.js'))) if os.path.basename(f).startswith('net_') == NET]
for f in errs[:2 if limit < 10 ** 6 else None]: args += [f, 'ERR:error']
print(' '.join(args))
