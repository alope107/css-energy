"""fuzz.py MODE [-n N] [-s SEED] [--l2] [--c1] [-v] — differential tests of the compiler against Node, without a browser.

Modes (each program is checked against Node, which is the oracle, by the levels below):
  gen   random programs from progen.py (the whole language, typed so that only real bugs differ);
  fmt   every suite program rewritten in ways that must not change what it prints: semicolons dropped (semicolon
        insertion), comments between tokens, tabs, blank lines, CRLF line ends, one token per line where JavaScript
        allows it, all on one line;
  mut   suite programs with one random token edit. Properties: what Node rejects as a syntax error must be rejected;
        with --l2 the DSL must agree with cc_ref (rejected programs included). An output difference is listed for a
        look but fails only with --strict: a mutant can leave the language in ways no filter sees.
Levels:
  L1    cc_ref compiles and its 20-bit simulator runs; output compared with Node's. Also on the page's padded text
        (24 x 64, as ccpage5.padded_source) when the program fits the editor;
  L2    (--l2) the DSL, level by level, against cc_ref (state, tables, every code word, label and data word);
  C1    (--c1) the CSS CPU's model (machine/csssim.py) runs the image of the page's padded text; output compared
        with Node's.
A failure is written to build/fuzz/ as the program and Node's version, shrunk (lines removed while it still fails).
Exit status 1 if anything failed.
"""
import sys, os, json, re, random, subprocess, collections, argparse, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE] + [os.path.join(ROOT, d) for d in ('compiler', 'machine', 'readback')]
import cc_ref as R, progen
from ccpage5 import padded_source
sys.path.insert(0, os.path.join(ROOT, 'tests')); from par import pmap
LIB = json.load(open(os.path.join(ROOT, 'compiler', 'lib.json')))
LIMIT_ERRS = {20, 21, 22, 23, 24, 25, 26, 61, 62, 68}          # the compiler's documented limits
OUT = os.path.join(ROOT, 'build', 'fuzz')

def node(progs):
    """[(src, prelude)] -> [{out, error?, syntax?}] in one Node process"""
    with tempfile.TemporaryDirectory() as d:
        i, o = os.path.join(d, 'in.json'), os.path.join(d, 'out.json')
        json.dump([{'src': s, 'prelude': p} for s, p in progs], open(i, 'w'))
        subprocess.run(['node', os.path.join(HERE, 'oracle.js'), i, o], check=True)
        return json.load(open(o))

def ours(src, max_steps=2_000_000):
    """-> (err, output or None, 'steps' if the step limit was hit)"""
    c = R.Compiler(R.LAYOUT['data_base'], R.LAYOUT['code_base'], LIB)
    words, data = c.compile(src)
    if c.err: return c.err, None, None
    mem = R.image_mem(c, words, data, LIB.get('init', 5120))
    try: steps, out = R.run(LIB['rom'], mem, R.LAYOUT['sp0'], max_steps=max_steps, strict=True, ent=LIB.get('entries'))
    except RuntimeError as e:
        if 'step limit' in str(e): return 0, None, 'steps'
        return 0, None, f'crash: {e}'
    except Exception as e: return 0, None, f'crash: {type(e).__name__} {e}'
    if out.endswith('out of memory\n'): return 0, None, 'heap'          # (the heap is a limit, as the step count is)
    return 0, out, None

def fits(src):
    ls = src.rstrip('\n').split('\n')
    return len(ls) <= 24 and max(map(len, ls)) <= 64 and all(32 <= ord(ch) < 127 for ch in src.replace('\n', ''))

NUM = re.compile(r'-?\d+')
NUMTOK = re.compile(r'(\d+)(?:\.(\d+))?e([+-]\d+)')
def outside(out):
    """Node printed something our machine cannot (README Limits): a number whose shortest digits need a decimal scale past 22
    (a fraction below 1e-6 with many digits) or one from 1e39, which the machine prints with 17 digits, not always the shortest
    (digits joined to it by a string's + count as its own: that errs on the side of skipping)"""
    for m in NUMTOK.finditer(out):
        p, e = len(m.group(1)) + len(m.group(2) or ''), int(m.group(3))
        if p - 1 - e > 22 or e > 38: return True
    return False
# values that are strings, objects or arrays on our machine (cc_ref): numbers there print as those
TAGGED = [(R.STRV_LO, R.STRV_HI), (R.HEAP0 - R.OBJTAG, R.HEAP_HI - R.OBJTAG), (R.HEAP0 + R.ARRTAG, R.HEAP_HI + R.ARRTAG)]

# ---------------- checks of one program
class Res:
    def __init__(self): self.c = collections.Counter(); self.fails = []; self.explore = []

def check(name, src, nres, opts, res, expect_reject=False, mutated=False):
    """compare one program (our text src) with Node's result; returns a failure description or None"""
    if opts.l2:                                       # the DSL agrees with cc_ref on every program, rejected ones too
        page = ''.join(ch if 32 <= ord(ch) < 127 or ch == '\n' else ' ' for ch in src)    # (the page has no tabs or CRs)
        ok, msg = dsl_check(page.rstrip('\n') + '\n')
        if not ok: return f'L2: {msg}'
    if nres.get('syntax'):
        err, _, _ = ours(src)
        if err == 0: return f'Node rejects it ({nres["syntax"]}) but we compile it'
        res.c['both reject'] += 1; return None
    if nres.get('error'):
        res.c['node error (skipped)'] += 1; return None
    if nres.get('bad') or outside(nres['out']): res.c['outside the language (skipped)'] += 1; return None
    err, out, lim = ours(src)
    if err in LIMIT_ERRS: res.c[f'limit error {err} (skipped)'] += 1; return None
    if err:
        if mutated: res.c['we reject, Node runs (subset)'] += 1; return None
        return f'compile error {err} on a valid program'
    if lim and lim.startswith('crash'): return f'the simulator crashed: {lim}'
    if lim: res.c['step limit (skipped)' if lim == 'steps' else 'out of memory (skipped)'] += 1; return None
    if out != nres['out']: return f'L1 output differs:\n--- ours\n{out}--- node\n{nres["out"]}'
    if fits(src):
        perr, pout, plim = ours(padded_source(src.rstrip('\n'), 24, 64))
        if (perr, pout) != (0, out) and plim not in ('steps', 'heap'): return f'L1 on the padded page text differs: err {perr} {plim or ""}\n{pout}'
        res.c['fits the page'] += 1
    if opts.c1 and fits(src):
        oc = c1(src)
        if oc != nres['out']: return f'C1 output differs:\n{oc}'
    res.c['ok'] += 1
    return None

def check_all(opts, res, jobs):
    """check() on each job (name, src, nres, kwargs) in worker processes (tests/par.py), adding their counts to res;
    yields each job's failure description or None, in order"""
    def one(j): r = Res(); return check(j[0], j[1], j[2], opts, r, **j[3]), r.c
    for why, c in pmap(one, jobs): res.c.update(c); yield why

dsl_check = None
def load_l2():
    global dsl_check
    os.environ['SPEC'] = '1'
    import cmp_dsl; dsl_check = cmp_dsl.check

def c1(src):
    import cssref, csssim
    c = R.Compiler(R.LAYOUT['data_base'], R.LAYOUT['code_base'], LIB); words, data = c.compile(padded_source(src.rstrip('\n'), 24, 64))
    mem = R.image_mem(c, words, data, LIB['init']); rom = R.LAYOUT['rom_size']
    s = csssim.Sim(cssref.from_image(dict(rom=LIB['rom'], romSize=rom, ram=[mem.get(rom + i, 0) for i in range(R.LAYOUT['ram_size'])], sp0=R.LAYOUT['sp0'], entries=LIB['entries'])))
    while not s.st['halt'] and s.passes < 200000: s.run_pass(32)
    return ''.join(map(chr, s.st['out']))

# ---------------- shrinking: drop lines (the same lines from both versions) while the failure stays
def shrink(ol, nl, fails_with):
    ol, nl = list(ol), list(nl)
    chunk = max(1, len(ol) // 2)
    while chunk >= 1:
        i, changed = 0, False
        while i < len(ol):
            o2, n2 = ol[:i] + ol[i + chunk:], nl[:i] + nl[i + chunk:]
            if o2 and fails_with(o2, n2): ol, nl, changed = o2, n2, True
            else: i += chunk
        if not changed: chunk //= 2
    return ol, nl

def kind(why): return why.split(':')[0].split('\n')[0]
def report(res, name, src, nsrc, why, opts, failfn=None):
    os.makedirs(OUT, exist_ok=True)
    if failfn and not opts.noshrink:
        k = kind(why)
        same = lambda ol, nl: (lambda w: w is not None and kind(w) == k)(failfn(ol, nl))
        ol, nl = shrink(src.rstrip('\n').split('\n'), nsrc.rstrip('\n').split('\n'), same)
        src, nsrc = '\n'.join(ol) + '\n', '\n'.join(nl) + '\n'
    base = os.path.join(OUT, name)
    open(base + '.js', 'w').write(src); open(base + '.node.js', 'w').write(nsrc)
    res.fails.append((name, why.split('\n')[0]))
    print(f'FAIL {name}: {why}\n{src}' if opts.v or len(res.fails) <= 5 else f'FAIL {name}: {why.splitlines()[0]}')

# ---------------- modes
def mode_gen(opts, res):
    progs = []
    for k in (opts.k or range(opts.n)):
        seed = opts.seed * 100003 + k
        o, n = progen.generate(seed, opts.size * random.Random(seed).uniform(0.3, 1.2))     # small ones fit the page (padded text, C1)
        progs.append((seed, '\n'.join(o) + '\n', '\n'.join(n) + '\n'))
    nres = node([(n, progen.PRELUDE) for _, _, n in progs])
    whys = check_all(opts, res, [(f'gen{seed}', o, nr, {}) for (seed, o, _), nr in zip(progs, nres)])
    for (seed, o, n), why in zip(progs, whys):
        if why:
            def fails_with(ol, nl):
                r2 = node([('\n'.join(nl) + '\n', progen.PRELUDE)])[0]
                if r2.get('syntax') or r2.get('error'): return None
                return check('shrink', '\n'.join(ol) + '\n', r2, opts, Res())
            report(res, f'gen{seed}', o, n, why, opts, fails_with)

# tokens of the language (for fmt / mut): strings, comments, words, numbers, operators
TOK = re.compile(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|//[^\n]*|/\*.*?\*/|[A-Za-z_$][\w$]*|\d+|===|!==|==|!=|<=|>=|&&|\|\||\+\+|--|[-+*/%]=|\S', re.S)
def toks(src): return TOK.findall(src)

def variants(src):
    """formatting variants that must print the same as src (Node checks each one too)"""
    out = {}
    lines = src.rstrip('\n').split('\n')
    out['nosemi'] = '\n'.join(re.sub(r';(\s*(//.*)?)$', r'\1', l) for l in lines) + '\n'
    out['crlf'] = src.replace('\n', '\r\n')
    out['tabs'] = '\n'.join('\t' + l.replace('  ', '\t') for l in lines) + '\n'
    out['blank'] = '\n\n'.join(lines) + '\n\n'
    out['comments'] = ' '.join(t if t.startswith('//') else t + ' /*c*/' for t in toks(src)).replace('/*c*/ //', '//')
    out['comments'] = re.sub(r'(//[^\n]*)', r'\1\n', out['comments']) + '\n'
    out['eol-comments'] = '\n'.join(l + ' // x' if not l.rstrip().endswith('*/') and '//' not in l else l for l in lines) + '\n'
    ts = [t for t in toks(src) if not t.startswith('//') and not t.startswith('/*')]
    out['oneline'] = ' '.join(ts) + '\n'
    out['tight'] = ''.join(t + (' ' if re.match(r'[\w$]', t) else '') for t in ts) + '\n'
    out['spaces'] = '  '.join(ts) + '\n'
    out['tokenlines'] = '\n'.join(ts) + '\n'      # semicolon insertion may change the meaning: Node is the oracle
    return out

def suite_programs():
    d = os.path.join(ROOT, 'tests', 'suite')
    return [(f[:-3], open(os.path.join(d, f)).read()) for f in sorted(os.listdir(d)) if f.endswith('.js')]

def mode_fmt(opts, res):
    items = [(f'{name}.{v}', s) for name, src in suite_programs() for v, s in variants(src).items()]
    nres = node([(s, '') for _, s in items])
    whys = check_all(opts, res, [(name, s, nr, dict(mutated=name.endswith('.tokenlines'))) for (name, s), nr in zip(items, nres)])
    for (name, s), why in zip(items, whys):
        if why:
            def fails_with(ol, nl):
                t = '\n'.join(ol) + '\n'; r2 = node([(t, '')])[0]
                if r2.get('syntax') or r2.get('error'): return None
                return check('shrink', t, r2, opts, Res())
            report(res, name, s, s, why, opts, fails_with if '\n' in s.strip() else None)

EDITS = ['del', 'dup', 'swap', 'ins', 'rep']
INS = [';', '{', '}', '(', ')', '[', ']', ',', ':', '?', '.', '=', '+', '-', '!', '++', '--', '+=', 'x', '1', '"s"', 'if', 'else',
       'var', 'let', 'const', 'while', 'do', 'for', 'return', 'break', 'continue', 'function', 'switch', 'case', 'default',
       'null', 'true', '\n', 'length', '===', '&&', '||', '<', '%', '/', '*', '0', 'console', 'log', 'putc']
def mode_mut(opts, res):
    r = random.Random(opts.seed); progs = suite_programs(); items = []
    for k in range(opts.n):
        name, src = r.choice(progs)
        ts = re.split(r'(' + TOK.pattern + r')', src, flags=re.S)        # tokens at odd positions, the text between at even
        idx = [i for i in range(1, len(ts), 2) if ts[i]]
        for _ in range(r.choice([1, 1, 1, 2])):
            i = r.choice(idx); e = r.choice(EDITS)
            if e == 'del': ts[i] = ''
            elif e == 'dup': ts[i] = ts[i] + ' ' + ts[i]
            elif e == 'swap':
                j = r.choice(idx); ts[i], ts[j] = ts[j], ts[i]
            elif e == 'ins': ts[i] = ts[i] + ' ' + r.choice(INS) + ' '
            else: ts[i] = r.choice(INS)
        items.append((f'mut{opts.seed}_{k}_{name}', ''.join(ts)))
    nres = node([(s, '') for _, s in items])
    whys = check_all(opts, res, [(name, s, nr, dict(mutated=True)) for (name, s), nr in zip(items, nres)])
    for (name, s), why in zip(items, whys):
        if why and kind(why).startswith('L1 output differs') and not opts.strict:
            # a mutant can leave the language in ways no filter sees (a string compared with a number, + on a string in
            # a parameter): saved and listed for a look, not a failure (--strict makes it one)
            os.makedirs(OUT, exist_ok=True); open(os.path.join(OUT, name + '.js'), 'w').write(s); open(os.path.join(OUT, name + '.node.js'), 'w').write(s)
            res.c['output differs (exploratory)'] += 1; res.explore.append(name); continue
        if why:
            def fails_with(ol, nl):
                t = '\n'.join(ol) + '\n'; r2 = node([(t, '')])[0]
                return check('shrink', t, r2, opts, Res(), mutated=True)
            report(res, name, s, s, why, opts, fails_with)

def mode_dump(opts, res):
    """write programs that fit the editor to opts.dir, for L3 in Chrome (make fuzz-l3: tests/suite_css.py + .js): -n
    generated ones (valid) and as many one-token mutants (mostly rejected; the chain must agree on those too)"""
    os.makedirs(opts.dir, exist_ok=True)
    for f in os.listdir(opts.dir):
        if f.endswith('.js'): os.remove(os.path.join(opts.dir, f))
    k = n = 0
    while n < opts.n and k < 50 * opts.n:
        seed = opts.seed * 100003 + k; k += 1
        o, _ = progen.generate(seed, 0.4 * opts.size)
        src = '\n'.join(o) + '\n'
        if fits(src) and ours(src)[0] not in LIMIT_ERRS:
            open(os.path.join(opts.dir, f'g{seed}.js'), 'w').write(src); n += 1
    r = random.Random(opts.seed); progs = [(nm, s) for nm, s in suite_programs() if fits(s)]
    for i in range(opts.n):
        name, src = r.choice(progs); ts = re.split(r'(' + TOK.pattern + r')', src, flags=re.S)
        idx = [j for j in range(1, len(ts), 2) if ts[j]]; j = r.choice(idx)
        ts[j] = r.choice(['', ts[j] + ' ' + r.choice(INS) + ' ', r.choice(INS)])
        m = ''.join(ts)
        if fits(m): open(os.path.join(opts.dir, f'm{opts.seed}_{i}_{name}.js'), 'w').write(m)
    res.c['written'] = len([f for f in os.listdir(opts.dir) if f.endswith('.js')])

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('mode', choices=['gen', 'fmt', 'mut', 'dump'])
    ap.add_argument('--dir', default=os.path.join(OUT, 'l3'))
    ap.add_argument('-n', type=int, default=200); ap.add_argument('-s', '--seed', type=int, default=1)
    ap.add_argument('--size', type=float, default=1.0); ap.add_argument('--l2', action='store_true'); ap.add_argument('--c1', action='store_true')
    ap.add_argument('--k', type=int, nargs='*', help='gen: only these program numbers'); ap.add_argument('--strict', action='store_true', help='mut: an output difference fails'); ap.add_argument('-v', action='store_true'); ap.add_argument('--noshrink', action='store_true')
    opts = ap.parse_args()
    if opts.l2: load_l2()
    res = Res()
    {'gen': mode_gen, 'fmt': mode_fmt, 'mut': mode_mut, 'dump': mode_dump}[opts.mode](opts, res)
    print(f'{opts.mode}: ' + ', '.join(f'{k} {v}' for k, v in sorted(res.c.items())) + f'; FAILED {len(res.fails)}')
    for n, w in res.fails[:40]: print(f'  {n}: {w}')
    if res.explore: print('  to look at (exploratory, in build/fuzz/; tests/fuzz/show.py replays): ' + ' '.join(res.explore[:20]))
    sys.exit(1 if res.fails else 0)
