"""traps.py prog.js... — what each program costs the font CPU, from its reference model (no browser): code words,
steps, shapings and traps by kind under uarch4 at the shipped configuration (N=16 lines, S=32 cycles/shaping).
Shapings track wall time on the page (each one is a layout pass), and traps end shapings early: MISS / WFAIL are
cache misses and write-backs, EXT is MUL/DIV/MOD/SHL13, PUTC is console output. MISS=1 prints misses by line."""
import os, sys; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]  # repo root
import json, collections
import cc_ref as R
import uarch4
from uarch import ROM
lib = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
N, S = int(os.environ.get('N', 16)), int(os.environ.get('S', 32))
for f in sys.argv[1:]:
    c = R.Compiler(4096, 4608, lib); words, data = c.compile(open(f).read())
    if c.err: print(f'{os.path.basename(f):24} compile error {c.err}'); continue
    mem = R.image_mem(c, words, data, lib['init'])
    m = uarch4.Machine4(dict(rom=lib['rom'], ram=[mem.get(ROM + i, 0) for i in range(3072)], sp0=R.LAYOUT['sp0']), N)
    miss = collections.Counter(); svc = m.service
    def service(t, svc=svc):
        if t and t[0] == 'MISS': miss[t[1] // 4 * 4] += 1
        return svc(t)
    m.service = service; m.run(S)
    print(f'{os.path.basename(f):24} code {len(words):4} steps {m.steps:6} shapings {m.shapings:5} traps {dict(m.trapkinds)}')
    if os.environ.get('MISS'): print('   misses by line:', sorted(miss.items()))
