"""regfuzz.py MODE [tests/fuzz/fuzz.py's options] — tests/fuzz/fuzz.py against the register machine: rc_ref compiles and runs
(L1), and with --c1 rsim.py runs the padded page text's image (C1); Node is the oracle, as there. Programs outside the
subset (error 90) are skipped and counted, and so are outputs that differ from Node's exactly as main's does (cc_ref). gen draws numbers and booleans only (progen's string, array and object
types and statements are filtered out of its choices), and its string expressions are literals, so many of its programs stay inside the subset."""
import sys, os, random
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, os.path.join(ROOT, 'tests', 'fuzz'), os.path.join(ROOT, 'compiler')]
import rc_ref as RC

class NumRandom(random.Random):
    """progen's choices without the types and statements outside the subset"""
    OUT = {'str', 'arr', 'obj', 'sarr', 'objp', 'aset', 'pset', 'switch', 'alloc', 'push', 'idx', 'len', 'prop', 'smeth', 'ameth'}
    def choice(self, seq):
        if isinstance(seq, list) and any(isinstance(x, str) and x in self.OUT for x in seq):
            seq = [x for x in seq if not (isinstance(x, str) and x in self.OUT)] or seq
        return super().choice(seq)
if 'gen' in sys.argv:
    random.Random = NumRandom
    import progen
    progen.Gen.strx = lambda self, d=0: ('raw', self.r.choice(self.strs))     # string expressions: literals only
import fuzz as F
from ccpage5 import padded_source

def ours(src, max_steps=2_000_000):
    c, words, data = RC.compile_src(src)
    if c.err: return c.err, None, None
    try: steps, out = RC.run(RC.image_mem(c, words, data), max_steps)
    except RuntimeError as e:
        if 'step limit' in str(e): return 0, None, 'steps'
        return 0, None, f'crash: {e}'
    except Exception as e: return 0, None, f'crash: {type(e).__name__} {e}'
    return 0, out, None
def c1(src):
    import rsim
    s = rsim.Sim(rsim.load(padded_source(src.rstrip('\n'), 24, 64)))
    while not s.st['halt'] and s.passes < 200000: s.run_pass(32)
    return ''.join(map(chr, s.st['out']))
main_ours, main_check = F.ours, F.check
def check(name, src, nres, opts, res, expect_reject=False, mutated=False):
    """fuzz.check; an output that differs from Node's as main's does (cc_ref: a value wrapped into a tag range, README
    Limits) is the language's limit, counted, not a failure"""
    why = main_check(name, src, nres, opts, res, expect_reject, mutated)
    if why and why.startswith('L1 output differs') and main_ours(src)[1] == ours(src)[1]:
        res.c['differs from Node as main does (skipped)'] += 1; return None
    return why
F.ours, F.c1, F.check = ours, c1, check
F.LIMIT_ERRS = F.LIMIT_ERRS | {RC.NOTSUB}
F.OUT = os.path.join(ROOT, 'build', 'fuzz-reg')

if __name__ == '__main__':
    sys.argv[0] = F.__file__
    exec(compile(open(F.__file__).read().split("if __name__ == '__main__':")[1].replace('\n    ', '\n'), F.__file__, 'exec'), vars(F))
