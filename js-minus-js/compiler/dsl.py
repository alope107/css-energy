"""dsl.py — integer expression DSL that evaluates in Python and compiles to CSS.

Semantics are those of registered <integer> custom properties: every value is an integer, |value| < 2^24
(Blink stores them as floats), division is floor division by a positive constant, mod takes the divisor's sign.
Booleans are 0/1. A Ctx runs a straight-line program under a guard (predicated execution): set() under a
guard becomes ite(guard, new, old), so branches compose without control flow. Every non-trivial value is
materialised as a temp (SSA), which becomes one CSS declaration.
"""

class N:
    __slots__ = ('op', 'a', 'v', 'h')
    def __init__(self, op, a=(), v=None):
        self.op, self.a, self.v = op, tuple(a), v
        self.h = hash((op, self.a, v))
    def __hash__(self): return self.h
    def __eq__(self, o): return isinstance(o, N) and self.op == o.op and self.a == o.a and self.v == o.v
    def __repr__(self): return f'{self.op}{self.v if self.v is not None else ""}{list(self.a) if self.a else ""}'
    # operator sugar
    def __add__(s, o): return add(s, o)
    def __radd__(s, o): return add(o, s)
    def __sub__(s, o): return sub(s, o)
    def __rsub__(s, o): return sub(o, s)
    def __mul__(s, o): return mul(s, o)
    def __rmul__(s, o): return mul(o, s)

def lift(x): return x if isinstance(x, N) else K(x)
def K(v): return N('K', v=int(v))
def S(n): return N('S', v=n)          # state var as inherited from the parent level
def I(n): return N('I', v=n)          # per-level input
def T(n): return N('T', v=n)          # temp on this level
isK = lambda x, v=None: x.op == 'K' and (v is None or x.v == v)

def add(*xs):
    xs = [lift(x) for x in xs]
    flat = []
    for x in xs: flat += list(x.a) if x.op == '+' else [x]
    k = sum(x.v for x in flat if x.op == 'K'); rest = [x for x in flat if x.op != 'K']
    if k: rest.append(K(k))
    if not rest: return K(0)
    if len(rest) == 1: return rest[0]
    return N('+', rest)
def sub(a, b):
    a, b = lift(a), lift(b)
    if isK(a) and isK(b): return K(a.v - b.v)
    if isK(b, 0): return a
    if a == b: return K(0)
    return N('-', (a, b))
def mul(a, b):
    a, b = lift(a), lift(b)
    if isK(a) and isK(b): return K(a.v * b.v)
    if isK(a, 0) or isK(b, 0): return K(0)
    if isK(a, 1): return b
    if isK(b, 1): return a
    return N('*', (a, b))
def fdiv(a, k):
    a = lift(a)
    if isK(a): return K(a.v // k)
    if k == 1: return a
    return N('//', (a,), k)
def mod(a, k):
    a = lift(a)
    if isK(a): return K(a.v % k)
    return N('%', (a,), k)
def mn(*xs):
    xs = [lift(x) for x in xs]
    if all(isK(x) for x in xs): return K(min(x.v for x in xs))
    return N('min', xs)
def mx(*xs):
    xs = [lift(x) for x in xs]
    if all(isK(x) for x in xs): return K(max(x.v for x in xs))
    return N('max', xs)
def eq(a, b):
    a, b = lift(a), lift(b)
    if isK(a) and isK(b): return K(int(a.v == b.v))
    if a == b: return K(1)
    return N('==', (a, b))
def ne(a, b): return not_(eq(a, b))
def lt(a, b):
    a, b = lift(a), lift(b)
    if isK(a) and isK(b): return K(int(a.v < b.v))
    return N('<', (a, b))
def le(a, b): return lt(a, add(b, 1))
def gt(a, b): return lt(b, a)
def ge(a, b): return lt(b, add(a, 1))
def not_(a):
    a = lift(a)
    if isK(a): return K(1 - a.v)
    if a.op == '!': return a.a[0]
    return N('!', (a,))
def and_(*xs):
    xs = [lift(x) for x in xs]
    if any(isK(x, 0) for x in xs): return K(0)
    xs = [x for x in xs if not isK(x, 1)]
    if not xs: return K(1)
    if len(xs) == 1: return xs[0]
    return N('&', xs)
def or_(*xs):
    xs = [lift(x) for x in xs]
    if any(isK(x, 1) for x in xs): return K(1)
    xs = [x for x in xs if not isK(x, 0)]
    if not xs: return K(0)
    if len(xs) == 1: return xs[0]
    return N('|', xs)
def ite(c, a, b):
    c, a, b = lift(c), lift(a), lift(b)
    if isK(c): return a if c.v else b
    if a == b: return a
    if isK(a, 1) and isK(b, 0): return c
    if isK(a, 0) and isK(b, 1): return not_(c)
    return N('?', (c, a, b))
def inrange(x, lo, hi): return and_(ge(x, lo), le(x, hi))
def anyeq(x, vals): return or_(*[eq(x, v) for v in vals])

# ---------------- evaluation
def ev(n, env):
    op = n.op
    if op == 'K': return n.v
    if op in ('S', 'I', 'T'): return env[(op, n.v)]
    a = [ev(x, env) for x in n.a] if op != '?' else None
    if op == '+': return sum(a)
    if op == '-': return a[0] - a[1]
    if op == '*': return a[0] * a[1]
    if op == '//': return a[0] // n.v
    if op == '%': return a[0] % n.v
    if op == 'min': return min(a)
    if op == 'max': return max(a)
    if op == '==': return int(a[0] == a[1])
    if op == '<': return int(a[0] < a[1])
    if op == '!': return 1 - a[0]
    if op == '&': return int(all(a))
    if op == '|': return int(any(a))
    if op == '?': return ev(n.a[1], env) if ev(n.a[0], env) else ev(n.a[2], env)
    raise ValueError(op)

# ---------------- CSS
def css(n, ref):
    """ref(kind, name) -> 'var(--...)' for S/I/T leaves."""
    op = n.op
    if op == 'K': return str(n.v) if n.v >= 0 else f'calc({n.v})'
    if op in ('S', 'I', 'T'): return ref(op, n.v)
    c = lambda x: css(x, ref)
    if op == '+': return 'calc(' + ' + '.join(c(x) for x in n.a) + ')'
    if op == '-': return f'calc({c(n.a[0])} - {c(n.a[1])})'
    if op == '*': return f'calc({c(n.a[0])} * {c(n.a[1])})'
    if op == '//': return f'round(down, calc({c(n.a[0])} / {n.v}))'
    if op == '%': return f'mod({c(n.a[0])}, {n.v})'
    if op == 'min': return f'min({", ".join(c(x) for x in n.a)})'
    if op == 'max': return f'max({", ".join(c(x) for x in n.a)})'
    if op == '==':
        d = f'calc({c(n.a[0])} - {c(n.a[1])})'
        return f'calc(1 - min(1, max({d}, calc(0 - {d}))))'
    if op == '<': return f'min(1, max(0, calc({c(n.a[1])} - {c(n.a[0])})))'
    if op == '!': return f'calc(1 - {c(n.a[0])})'
    if op == '&': return 'calc(' + ' * '.join(c(x) for x in n.a) + ')'
    if op == '|': return 'min(1, calc(' + ' + '.join(c(x) for x in n.a) + '))'
    if op == '?':
        cc, a, b = n.a
        return f'calc({c(b)} + {c(cc)} * calc({c(a)} - {c(b)}))'
    raise ValueError(op)

def css2(n, ref):
    """compact CSS: one calc() at the top, parentheses inside, abs()/clamp() for comparisons"""
    if n.op == 'K': return str(n.v)
    e, kind = _c2(n, ref)
    return f'calc({e})' if kind != 'atom' else e
def _c2(n, ref):
    """-> (text, kind): kind 'atom' (number, var(), function call), 'prod', 'sum'"""
    op = n.op
    if op == 'K': return (str(n.v), 'atom') if n.v >= 0 else (f'({n.v})', 'atom')
    if op in ('S', 'I', 'T'): return ref(op, n.v), 'atom'
    def term(x):                      # operand of * : sums need parentheses
        t, k = _c2(x, ref); return f'({t})' if k == 'sum' else t
    def arg(x): return _c2(x, ref)[0]
    if op == '+':
        parts = []
        for x in n.a:
            t, k = _c2(x, ref)
            if x.op == 'K' and x.v < 0: parts.append(f'- {-x.v}')
            else: parts.append(f'+ {t}')
        txt = ' '.join(parts); txt = txt[2:] if txt.startswith('+ ') else '0 ' + txt
        return txt, 'sum'
    if op == '-': 
        t, k = _c2(n.a[1], ref)
        return f'{arg(n.a[0])} - {t if k != "sum" else "(" + t + ")"}', 'sum'
    if op == '*': return f'{term(n.a[0])} * {term(n.a[1])}', 'prod'
    if op == '//': return f'round(down, {term(n.a[0])} / {n.v})', 'atom'
    if op == '%': return f'mod({arg(n.a[0])}, {n.v})', 'atom'
    if op == 'min': return f'min({", ".join(arg(x) for x in n.a)})', 'atom'
    if op == 'max': return f'max({", ".join(arg(x) for x in n.a)})', 'atom'
    if op == '==':
        b, k = _c2(n.a[1], ref)
        return f'1 - min(1, abs({arg(n.a[0])} - {b if k != "sum" else "(" + b + ")"}))', 'sum'
    if op == '<':
        a, k = _c2(n.a[0], ref)
        return f'clamp(0, {arg(n.a[1])} - {a if k != "sum" else "(" + a + ")"}, 1)', 'atom'
    if op == '!':
        t, k = _c2(n.a[0], ref)
        return f'1 - {t if k != "sum" else "(" + t + ")"}', 'sum'
    if op == '&': return ' * '.join(term(x) for x in n.a), 'prod'
    if op == '|': return 'min(1, ' + ' + '.join(arg(x) for x in n.a) + ')', 'atom'
    if op == '?':
        c, a, b = n.a
        bt, bk = _c2(b, ref)
        at, ak = _c2(a, ref)
        diff = f'{at} - {bt if bk != "sum" else "(" + bt + ")"}'
        return f'{bt} + {term(c)} * ({diff})', 'sum'
    raise ValueError(op)

def size(n, memo=None):
    if n.op in ('K', 'S', 'I', 'T'): return 1
    return 1 + sum(size(x) for x in n.a)

# ---------------- predicated program context
class Ctx:
    def __init__(self, state, inputs):
        self.state = list(state); self.inputs = list(inputs)
        self.cur = {n: S(n) for n in self.state}
        self.g = K(1)
        self.temps = []          # (name, node) in order
        self.memo = {}
        self.nt = 0
    def mat(self, node, hint='t'):
        node = lift(node)
        if node.op in ('K', 'S', 'I', 'T'): return node
        if node in self.memo: return self.memo[node]
        name = f'{hint}{self.nt}'; self.nt += 1
        self.temps.append((name, node)); t = T(name); self.memo[node] = t
        return t
    def v(self, n): return self.cur[n]
    def set(self, n, val, hint=None):
        new = ite(self.g, lift(val), self.cur[n])
        self.cur[n] = self.mat(new, hint or n.replace('[', '_').replace(']', '') + '_')
    def when(self, cond):
        ctx = self
        class W:
            def __enter__(s):
                s.old = ctx.g; ctx.g = ctx.mat(and_(ctx.g, cond), 'g'); return ctx
            def __exit__(s, *a): ctx.g = s.old
        return W()
    def dce(self, keep):
        """drop temps not reachable from the final state or from the temps named in keep"""
        live = set(keep); byname = dict(self.temps)
        stack = [x for x in self.cur.values()] + [byname[n] for n in keep]
        while stack:
            x = stack.pop()
            if x.op == 'T':
                if x.v not in live: live.add(x.v); stack.append(byname[x.v])
            else: stack.extend(x.a)
        self.temps = [(n, x) for n, x in self.temps if n in live]
    def run_python(self, env):
        """env: {('S', n): v, ('I', n): v} -> evaluates temps; returns new state dict."""
        e = dict(env)
        for name, node in self.temps: e[('T', name)] = ev(node, e)
        return {n: ev(self.cur[n], e) for n in self.state}, e
