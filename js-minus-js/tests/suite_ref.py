"""suite_ref.py [dir] — level 1: the reference compiler (cc_ref) + bytecode simulator against Node's output.
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
        c, r = R.compile_and_run(src, lib, strict=True, trace=trace if m else None)
        if r is None: return ('COMPILE-ERR', c.err)
        elif m and gcs != m.group(1).split(): return ('COLLECTIONS', f'{" ".join(gcs) or "none"}, want {m.group(1)}')
        elif r[1] == want: return ('ok', r[0])
        else: return ('WRONG', repr(r[1][:60]) + ' want ' + repr(want[:60]))
    except Exception as e: return ('CRASH', str(e)[:80])
from par import pmap                    # one program per worker process
fs = sorted(glob.glob(d + '/*.js'))
res = {os.path.basename(f)[:-3]: v for f, v in zip(fs, pmap(one, fs))}
ok = sum(1 for v in res.values() if v[0] == 'ok')
for k, v in res.items():
    if v[0] != 'ok': print(f'{k:18} {v[0]:12} {v[1]}')
print(f'{ok}/{len(res)} pass')
sys.exit(int(ok != len(res)))           # (make test stops on an L1 failure)
