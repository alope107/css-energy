"""suite_ref.py [dir] — level 1: the reference compiler (cc_ref) + bytecode simulator against Node's output. A directory named
repl holds REPL sessions (tests/repl_expect.js): compiled and run as the page's REPL does, twice: replayed whole, and as it is
typed (session(): each line runs only the entries it adds, on the memory the last run left), which must leave the same output,
console and marks.
A program may declare the garbage collections it is written to cause, in order, by the routine that called the collector
(`// collections: galloc gcnew`: an ALLOC, a NEW, gccat for a string's +). A GC test's loops are sized for the heap, so
a change that moves where (or whether) it collects fails here instead of leaving the test quietly weaker."""
import sys, os, json, glob, re, bisect
import os, sys; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]  # repo root
import cc_ref as R
HERE = os.path.dirname(os.path.abspath(__file__))
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'suite')
ENT = lib['entries']; STARTS = sorted((a, n) for n, a in ENT.items()); ADDRS = [a for a, _ in STARTS]
def routine(pc): return STARTS[bisect.bisect_right(ADDRS, pc) - 1][1] if pc < R.LAYOUT['rom_size'] else 'user'
BIG = {'cmp_far'}                       # its long first line is a comment, which the page's truncation leaves harmless
def one(f):
    want = open(f[:-3] + '.out').read()
    lines = open(f).read().rstrip('\n').split('\n')
    if (len(lines) > 24 or max(map(len, lines)) > 64) and os.path.basename(f)[:-3] not in BIG:       # the page would truncate it: C1 / L5 fail for the wrong reason
        return ('TOO-BIG', f'{len(lines)} lines, longest {max(map(len, lines))} (the editor is 24 x 64)')
    src = open(f).read(); m = re.search(r'^// collections: (.*)$', src, re.M); gcs, prev = [], [0]
    def trace(pc, *a):
        if pc == ENT['gc']: gcs.append(routine(prev[0]))
        prev[0] = pc
    try:
        c, r = R.compile_and_run(src, lib, strict=True, trace=trace if m else None, repl=REPL)
        if r is None: return ('COMPILE-ERR', c.err)
        elif m and gcs != m.group(1).split(): return ('COLLECTIONS', f'{" ".join(gcs) or "none"}, want {m.group(1)}')
        elif r[1] == want: return check_session(src, want) or ('ok', r[0]) if REPL else ('ok', r[0])
        else: return ('WRONG', repr(r[1][:60]) + ' want ' + repr(want[:60]))
    except Exception as e: return ('CRASH', str(e)[:80])
LA = R.LAYOUT; MARKS = LA['out_base'] + R.OUTMAX
def runs(src, rdone, mem=None):
    """the REPL's page's run of the session src: compiled with rdone (the lines the last run read) and started at the first entry
    after them, on mem (the memory the last run left; None: a fresh one), with the console's cursor where that run's end mark
    left it -> (compile error, steps, output, final memory)"""
    c = R.Compiler(LA['data_base'], LA['code_base'], lib, repl=True, rdone=rdone); words, data = c.compile(src)
    if c.err: return c.err, 0, '', mem
    im = R.image_mem(c, words, data, lib.get('init', LA['init']))
    if mem is None: m, optr0 = im, 0
    else: m = dict(enumerate(mem)); m.update({a: v for a, v in im.items() if a not in R.GINIT}); optr0 = max(0, mem[MARKS + R.MARKEND] - 1)     # (the overlays: code, strings, .fin's)
    fin = {}
    steps, out = R.run(lib['rom'], m, LA['sp0'], strict=True, ent=ENT, cols=LA['repl_cols'], rows=LA['repl_rows'], pc0=2 * c.rst, optr0=optr0, final=fin)
    return 0, steps, out, fin['mem']
def session(src):
    """src typed a line at a time, as on the page: after each line every line so far compiled, the new entries run (none while
    an entry is still open: a compile error) -> (output, the console and marks at the end)"""
    lines = src.rstrip('\n').split('\n'); mem, done, out = None, 0, ''
    for n in range(1, len(lines) + 1):
        err, _, o, m = runs('\n'.join(lines[:n]) + '\n', done, mem)
        if not err: mem, done, out = m, n, out + o
    return out, mem[LA['out_base']:MARKS + R.NMARK]
def check_session(src, want):
    _, _, full, m = runs(src, 0)
    got, con = session(src)
    if got != want: return ('SESSION', repr(got[:60]) + ' want ' + repr(want[:60]))
    if con != m[LA['out_base']:MARKS + R.NMARK]: return ('SESSION', 'the console or marks differ from the replay\'s')
from par import pmap                    # one program per worker process
REPL = os.path.basename(os.path.normpath(d)) == 'repl'
fs = sorted(glob.glob(d + '/*.js'))
res = {os.path.basename(f)[:-3]: v for f, v in zip(fs, pmap(one, fs))}
ok = sum(1 for v in res.values() if v[0] == 'ok')
for k, v in res.items():
    if v[0] != 'ok': print(f'{k:18} {v[0]:12} {v[1]}')
print(f'{ok}/{len(res)} pass')
sys.exit(int(ok != len(res)))           # (make test stops on an L1 failure)
