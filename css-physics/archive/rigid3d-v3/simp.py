"""Tiny algebraic simplifier for the generator's calc() expressions.

Chrome re-parses every substituted calc() token on every style pass (~0.3-0.5us per token), so
emitting fewer tokens is directly faster. This parses an expression into a small tree, flattens
sums and products, folds constants, cancels negations, and prints with minimal parentheses.

Grammar handled: numbers, var(--x) and var(--x, fallback) (kept as opaque atoms), function calls
(sign, max, min, clamp, abs, hypot, pow, sqrt, sin, cos, mod, round, ...), + - * / and parentheses.
Anything it does not understand is returned unchanged.
"""
import math
import re

_num = re.compile(r'-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?')
_ident = re.compile(r'[a-z][a-z0-9-]*\(')


class Num:
    __slots__ = ('v',)
    def __init__(self, v): self.v = float(v)


class Atom:
    __slots__ = ('t',)
    def __init__(self, t): self.t = t


class Fn:
    __slots__ = ('name', 'args')
    def __init__(self, name, args): self.name, self.args = name, args


class Sum:     # terms: list of (sign, node)
    __slots__ = ('terms',)
    def __init__(self, terms): self.terms = terms


class Prod:    # coef * f1 * f2 / d1 / d2
    __slots__ = ('coef', 'num', 'den')
    def __init__(self, coef, num, den): self.coef, self.num, self.den = coef, num, den


class _P:
    def __init__(self, s):
        self.s, self.i = s, 0

    def ws(self):
        while self.i < len(self.s) and self.s[self.i] == ' ':
            self.i += 1

    def peek(self):
        self.ws()
        return self.s[self.i] if self.i < len(self.s) else ''

    def balanced(self, start):
        depth, j = 0, start
        while j < len(self.s):
            c = self.s[j]
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        raise ValueError('unbalanced')

    def expr(self):
        terms = [(1, self.term())]
        while True:
            self.ws()
            if self.s.startswith('+ ', self.i) or self.s.startswith('+', self.i) and self.i + 1 < len(self.s) and self.s[self.i + 1] == ' ':
                self.i += 1
                terms.append((1, self.term()))
            elif self.s.startswith('- ', self.i):
                self.i += 1
                terms.append((-1, self.term()))
            else:
                break
        return terms[0][1] if len(terms) == 1 and terms[0][0] == 1 else Sum(terms)

    def term(self):
        num, den, coef = [self.factor()], [], 1.0
        while True:
            self.ws()
            if self.s.startswith('*', self.i):
                self.i += 1
                num.append(self.factor())
            elif self.s.startswith('/', self.i):
                self.i += 1
                den.append(self.factor())
            else:
                break
        if len(num) == 1 and not den:
            return num[0]
        return Prod(coef, num, den)

    def factor(self):
        self.ws()
        s, i = self.s, self.i
        if s.startswith('var(', i):
            j = self.balanced(i + 3)
            self.i = j
            return Atom(s[i:j])
        m = _ident.match(s, i)
        if m:
            name = m.group(0)[:-1]
            j = self.balanced(i + len(name))
            inner = s[i + len(name) + 1:j - 1]
            self.i = j
            args = _split_args(inner)
            if name == 'calc' and len(args) == 1:
                return parse(args[0])
            return Fn(name, [parse(a) for a in args])
        if s.startswith('(', i):
            j = self.balanced(i)
            self.i = j
            return parse(s[i + 1:j - 1])
        m = _num.match(s, i)
        if m:
            self.i = m.end()
            return Num(m.group(0))
        raise ValueError(f'cannot parse at {s[i:i + 20]!r}')


def _split_args(s):
    out, depth, cur = [], 0, []
    for c in s:
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        if c == ',' and depth == 0:
            out.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(c)
    out.append(''.join(cur).strip())
    return out


def parse(s):
    p = _P(s)
    node = p.expr()
    p.ws()
    if p.i != len(s):
        raise ValueError('trailing input')
    return node


# ---- simplification -------------------------------------------------------------------
_FOLD = {
    'abs': lambda a: abs(a[0]), 'sign': lambda a: (a[0] > 0) - (a[0] < 0), 'max': max, 'min': min,
    'sqrt': lambda a: math.sqrt(a[0]), 'sin': lambda a: math.sin(a[0]), 'cos': lambda a: math.cos(a[0]),
    'hypot': lambda a: math.sqrt(sum(x * x for x in a)), 'pow': lambda a: a[0] ** a[1],
    'clamp': lambda a: max(a[0], min(a[1], a[2])),
}


def _as_prod(n):
    """view any node as (coef, num, den)"""
    if isinstance(n, Num):
        return n.v, [], []
    if isinstance(n, Prod):
        return n.coef, n.num, n.den
    return 1.0, [n], []


def simp(n):
    if isinstance(n, (Num, Atom)):
        return n
    if isinstance(n, Fn):
        args = [simp(a) for a in n.args]
        f = _FOLD.get(n.name)
        if f and all(isinstance(a, Num) for a in args):
            vals = [a.v for a in args]
            try:
                return Num(f(vals) if n.name not in ('max', 'min') else f(vals))
            except Exception:
                pass
        return Fn(n.name, args)
    if isinstance(n, Prod):
        coef, num, den = n.coef, [], []
        for f in n.num:
            sf = simp(f)
            if isinstance(sf, Sum) and len(sf.terms) == 1:      # -(x) as a factor: absorb the sign
                coef *= sf.terms[0][0]
                sf = sf.terms[0][1]
            c, nn, dd = _as_prod(sf)
            coef *= c
            num += nn
            den += dd
        for f in n.den:
            c, nn, dd = _as_prod(simp(f))
            if c == 0:
                return Prod(coef, num, den + [Num(0)])   # keep a literal division by zero as is
            coef /= c
            den += nn
            num += dd
        if coef == 0:
            return Num(0)
        num.sort(key=lambda x: show(x, 'prod'))
        den.sort(key=lambda x: show(x, 'prod'))
        if not num and not den:
            return Num(coef)
        if coef == 1 and len(num) == 1 and not den:
            return num[0]
        return Prod(coef, num, den)
    if isinstance(n, Sum):
        const, terms = 0.0, []
        def push(sign, node):
            nonlocal const
            node = simp(node)
            if isinstance(node, Num):
                const += sign * node.v
            elif isinstance(node, Sum):
                for s2, t2 in node.terms:
                    push(sign * s2, t2)
            elif isinstance(node, Prod) and node.coef < 0:
                terms.append((-sign, Prod(-node.coef, node.num, node.den) if not (-node.coef == 1 and len(node.num) == 1 and not node.den) else node.num[0]))
            else:
                terms.append((sign, node))
        for sgn, t in n.terms:
            push(sgn, t)
        # combine like terms: c1 * X + c2 * X -> (c1 + c2) * X (X compared by its printed form)
        acc, order = {}, []
        for sgn, t in terms:
            c, nn, dd = _as_prod(t)
            key = show(Prod(1.0, nn, dd)) if (nn or dd) else None
            if key is None:
                const += sgn * c
                continue
            if key not in acc:
                acc[key] = [0.0, nn, dd]
                order.append(key)
            acc[key][0] += sgn * c
        terms = []
        for key in order:
            c, nn, dd = acc[key]
            if c == 0:
                continue
            node = nn[0] if (abs(c) == 1 and len(nn) == 1 and not dd) else Prod(abs(c), nn, dd)
            terms.append((1 if c > 0 else -1, node))
        if const != 0:
            terms.append((1 if const > 0 else -1, Num(abs(const))))
        if not terms:
            return Num(0)
        # print a positive term first when there is one (avoids a leading '-1 * ')
        terms.sort(key=lambda t: 0 if t[0] > 0 else 1)
        if len(terms) == 1 and terms[0][0] == 1:
            return terms[0][1]
        if len(terms) == 1 and terms[0][0] == -1:
            t = terms[0][1]
            c, nn, dd = _as_prod(t)
            return Prod(-c, nn, dd) if nn or dd else Num(-c)
        return Sum(terms)
    return n


# ---- printing ----------------------------------------------------------------------------
def fmt(v):
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    s = repr(round(v, 9))
    if 'e' in s:
        s = f'{v:.12f}'.rstrip('0').rstrip('.')
    return s


def show(n, ctx='top'):
    """ctx: 'top' (no parens needed), 'sum' (inside a sum), 'prod' (factor of a product)"""
    if isinstance(n, Num):
        return fmt(n.v) if n.v >= 0 or ctx == 'top' else f'({fmt(n.v)})' if False else fmt(n.v)
    if isinstance(n, Atom):
        return n.t
    if isinstance(n, Fn):
        return f"{n.name}({', '.join(show(a) for a in n.args)})"
    if isinstance(n, Prod):
        parts = []
        if n.coef != 1 or not n.num:
            parts.append(fmt(n.coef) if n.coef != -1 or not n.num else '-1')
        parts += [show(f, 'prod') for f in n.num]
        s = ' * '.join(parts)
        for d in n.den:
            ds = show(d, 'prod')
            if isinstance(d, Prod):
                ds = f'({ds})'
            s += f' / {ds}'
        return f'({s})' if ctx == 'prod' and False else s
    if isinstance(n, Sum):
        out = []
        for k, (sgn, t) in enumerate(n.terms):
            ts = show(t, 'sum')
            if k == 0:
                out.append(ts if sgn > 0 else (f'-1 * {ts}' if not isinstance(t, Sum) else f'-1 * ({ts})'))
            else:
                out.append(f"{'+' if sgn > 0 else '-'} {ts if not isinstance(t, Sum) else f'({ts})'}")
        s = ' '.join(out)
        return f'({s})' if ctx == 'prod' else s
    raise TypeError(n)


def simplify(expr):
    try:
        return show(simp(parse(expr)))
    except Exception:
        return expr


if __name__ == '__main__':
    tests = ['(28 + ((-1 * (-1 * var(--p4y))))) - ((-1 * var(--mA)))', 'var(--a) * 1 + 0 * var(--b) - (-1 * 3)',
             '(1 - 0.5 * max(0, -1 * (0 * var(--gx) + -1 * var(--gy))))', 'a']
    for t in tests:
        print(t, ' => ', simplify(t))
