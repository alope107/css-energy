"""python3 shared/test/test_checks.py — unit tests of shared/make (checks as make targets; no browser). Exits 1 on a failure.

A scratch Makefile includes checks.mk with one check, b/t.log, that prints in.txt and appends to runs.log each time it
really runs, so a test can tell a run from a skip."""
import os, subprocess, sys, tempfile
SHARED = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

MAKEFILE = f'''include {SHARED}/make/checks.mk
T := b/t.$(call id,b/t,-,t.js).log
$(T): in.txt $(RERUN_IF)
	@$(LOGGED) $@ -p '^([0-9]+)/\\1 pass$$' -f FAIL -- node t.js
t: $(T)
	$(call report,$<,1)
'''
T_JS = 'const fs = require("fs"); fs.appendFileSync("runs.log", "r\\n"); if (process.env.T_EXIT) process.exit(1);\nconsole.log(fs.readFileSync("in.txt", "utf8").trim());\n'

n = bad = 0
def t(name, f):
    global n, bad
    n += 1
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, 'Makefile'), 'w').write(MAKEFILE); open(os.path.join(d, 't.js'), 'w').write(T_JS)
        try:
            f(Dir(d))
        except AssertionError as e:
            bad += 1; print(f'FAIL {name}: {e}')

def eq(a, b):
    assert a == b, f'{a!r} != {b!r}'

class Dir:
    def __init__(self, d): self.d = d
    def write(self, rel, s):
        open(os.path.join(self.d, rel), 'w').write(s)            # newer than any log written before (ns mtimes)
    def make(self, *args, env=None):
        """-> (exit status, output, ran?)"""
        log = os.path.join(self.d, 'runs.log')
        before = open(log).read().count('\n') if os.path.exists(log) else 0
        e = {k: v for k, v in os.environ.items() if k not in ('RERUN', 'T_EXIT', 'T_VAR')}
        r = subprocess.run(['make', '-s', 't', *args], cwd=self.d, env={**e, **(env or {})}, capture_output=True, text=True)
        after = open(log).read().count('\n') if os.path.exists(log) else 0
        return r.returncode, r.stdout + r.stderr, after > before

def skip(d):
    d.write('in.txt', '3/3 pass')
    eq(d.make()[::2], (0, True))
    rc, out, ran = d.make(); eq((rc, ran), (0, False)); assert 'up to date: b/t.' in out and '3/3 pass' in out, out
t('a pass is skipped while its prerequisites are older, and says so', skip)

def changed(d):
    d.write('in.txt', '3/3 pass'); d.make()
    d.write('in.txt', '4/4 pass'); rc, out, ran = d.make(); eq((rc, ran), (0, True)); assert 'up to date' not in out, out
    eq(d.make()[2], False)
t('a newer prerequisite re-runs it', changed)

def env(d):
    open(os.path.join(d.d, 't.js'), 'a').write('process.env.T_VAR;\n')    # a variable the script reads by name
    d.write('in.txt', '3/3 pass'); d.make()
    eq(d.make(env={'T_VAR': '1'})[2], True); eq(d.make(env={'T_VAR': '1'})[2], False)
    eq(d.make(env={'OTHER': '1', 'T_VAR': '1'})[2], False)              # one it doesn't read: no re-run
    eq(d.make('T_VAR=1')[2], False); eq(d.make('T_VAR=2')[2], True)    # set on make's command line
    eq(d.make()[2], False); eq(d.make('T_VAR=2')[2], False)             # switching back finds each pass
t('a variable the script reads re-runs it; others don\'t; each value keeps its pass', env)

def rerun(d):
    d.write('in.txt', '3/3 pass'); d.make()
    eq(d.make('RERUN=1')[2], True); eq(d.make(env={'RERUN': '1'})[2], True); eq(d.make()[2], False)
t('RERUN=1 runs it anyway', rerun)

def fails(d):
    d.write('in.txt', '2/3 pass')
    rc, out, ran = d.make(); assert rc != 0 and ran and 'FAILED' in out, out           # exit 0, but no "n/n pass"
    eq(d.make()[2], True)                                                              # a failure is never kept
    logs = os.listdir(os.path.join(d.d, 'b')); assert not [f for f in logs if f.endswith('.log')] and [f for f in logs if f.endswith('.log.failed')], logs
    d.write('in.txt', '3/3 FAIL 3/3 pass'); eq(d.make()[0] != 0, True)                 # -f
    d.write('in.txt', '3/3 pass'); eq(d.make(env={'T_EXIT': '1'})[0] != 0, True)        # exit status
    eq(d.make()[::2], (0, True)); eq(d.make()[2], False)
t('failures (exit status, -p, -f) are re-run until they pass', fails)

print(f'{n - bad}/{n} pass')
sys.exit(1 if bad else 0)
