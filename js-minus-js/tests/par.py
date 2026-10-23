"""par.py — fn over many items in worker processes, results in order (harness only). The test levels check each program
independently, so they spread over every CPU and still print what the serial run prints, in the same order.
JOBS=N sets the number of workers (default: every CPU); JOBS=1 runs in this process (for pdb or a profile).
Workers are forked: they inherit everything loaded so far, and fn may be a closure. Items and results are pickled.
A cache a worker fills in memory is filled once per worker (cmp_dsl's parser variants are on disk: cc_dsl.compiled)."""
import os, multiprocessing as mp
_fn = None
def _call(x): return _fn(x)

def jobs(): return int(os.environ.get('JOBS') or os.cpu_count() or 1)

def pmap(fn, items):
    global _fn
    items = list(items); n = min(jobs(), len(items))
    if n <= 1: yield from map(fn, items); return
    _fn = fn
    with mp.get_context('fork').Pool(n) as pool:
        yield from pool.imap(_call, items, chunksize=max(1, len(items) // (n * 8)))
