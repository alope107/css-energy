"""fuzz dsl.css2 against dsl.ev (CSS math evaluated as Python)"""
import random, re, math
from dsl import *
def topy(t):
    t = t.replace('calc(', '(').replace('round(down,', 'fl(').replace('clamp(', 'cl(').replace('mod(', 'md(')
    return re.sub(r'var\(--(\w+)\)', r'env["\1"]', t)
random.seed(1)
leaves = [S('a'), S('b'), I('c'), K(3), K(-2), K(0), K(1)]
def rnd(d):
    if d == 0: return random.choice(leaves)
    o = random.choice(['+', '-', '*', '//', '%', 'min', 'max', '==', '<', '!', '&', '|', '?'])
    r = lambda: rnd(d - 1)
    return {'+': lambda: add(r(), r(), r()), '-': lambda: sub(r(), r()), '*': lambda: mul(r(), r()), '//': lambda: fdiv(r(), random.choice([2, 3, 64])),
            '%': lambda: mod(r(), random.choice([2, 7])), 'min': lambda: mn(r(), r()), 'max': lambda: mx(r(), r()), '==': lambda: eq(r(), r()),
            '<': lambda: lt(r(), r()), '!': lambda: not_(eq(r(), r())), '&': lambda: and_(eq(r(), r()), lt(r(), r())),
            '|': lambda: or_(eq(r(), r()), lt(r(), r())), '?': lambda: ite(eq(r(), r()), r(), r())}[o]()
bad = 0
for i in range(5000):
    n = rnd(4); env = {k: random.randint(-5, 5) for k in 'abc'}
    t = css2(n, lambda k, v: f'var(--{v})')
    v = eval(topy(t), {'env': env, 'fl': math.floor, 'cl': lambda lo, x, hi: max(lo, min(x, hi)), 'md': lambda a, k: a - k * math.floor(a / k), 'abs': abs, 'min': min, 'max': max})
    if v != ev(n, {('S', 'a'): env['a'], ('S', 'b'): env['b'], ('I', 'c'): env['c']}):
        bad += 1
        if bad < 3: print(t)
print('bad', bad)
