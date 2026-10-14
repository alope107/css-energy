"""python3 shared/test/test_py.py — unit tests of shared/py (no browser). Exits 1 on a failure."""
import os, sys, runpy, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'py'))
import ablate as A

n = bad = 0
def t(name, f):
    global n, bad
    n += 1
    try:
        f()
    except AssertionError as e:
        bad += 1; print(f'FAIL {name}: {e}')

def eq(a, b):
    assert a == b, f'{a!r} != {b!r}'

CSS = ('a{x:1}@container b1 style(--np0_1: 1){#L1{--q:1}}'
       '@container pres{#L2{--r:1}@container b2 style(--tcp0_2: 1){#L2{--s:1}}}'
       '@container b3 style(--ac3: 1){#L3{content:"}{";--t:1/* } */}}z{y:2}')
t('removes matching blocks, keeps the rest', lambda: eq(A.strip(CSS, r'--np'), (CSS.replace('@container b1 style(--np0_1: 1){#L1{--q:1}}', ''), 1)))
t('a matching block nested in a kept one is removed on its own',
  lambda: eq(A.strip(CSS, r'--tcp')[0], CSS.replace('@container b2 style(--tcp0_2: 1){#L2{--s:1}}', '')))
t('braces in strings and comments do not end a block',
  lambda: eq(A.strip(CSS, r'--ac\d')[0], 'a{x:1}@container b1 style(--np0_1: 1){#L1{--q:1}}@container pres{#L2{--r:1}@container b2 style(--tcp0_2: 1){#L2{--s:1}}}z{y:2}'))
t('removing an outer block takes its inner ones', lambda: eq(A.strip(CSS, r'^pres'), (CSS.replace('@container pres{#L2{--r:1}@container b2 style(--tcp0_2: 1){#L2{--s:1}}}', ''), 1)))
t('all = every block', lambda: eq(A.strip(CSS, '.')[1], 3))
t('escaped quote inside a string', lambda: eq(A.strip('@container a{x{content:"\\"}"}}k{}', 'a'), ('k{}', 1)))
t('output names keep the extension and never overwrite the source', lambda: (
    eq(A.out_name('out/FZ_p48.html', 'pairs'), 'out/FZ_p48_pairs.html'),
    eq(A.out_name('build/js_in_css.xhtml', 'mem'), 'build/js_in_css_mem.xhtml'),
    eq(A.out_name('page', 'x'), 'page_x')))

def cli():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, 'p.xhtml'); open(src, 'w').write(CSS)
        sys.argv = ['ablate.py', src, 'np=--np']
        runpy.run_path(os.path.join(HERE, '..', 'py', 'ablate.py'), run_name='__main__')
        eq(open(src).read(), CSS)
        eq(open(os.path.join(d, 'p_np.xhtml')).read(), A.strip(CSS, '--np')[0])
t('the command line writes page_NAME.xhtml and leaves the source alone', cli)

print(f'{n - bad}/{n} pass')
sys.exit(1 if bad else 0)
