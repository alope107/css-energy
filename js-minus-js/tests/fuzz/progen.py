"""progen.py — random programs in the compiler's language, for differential testing against Node (tests/fuzz/fuzz.py).

A program is generated once as a tree and rendered twice from the same tree, with the same layout (line breaks,
optional semicolons, comments):
- for our compiler ('o'), as written;
- for Node ('n'), with the machine's integer semantics spelled out: + - * and unary - wrap to 20 bits (W), / truncates
  and gives 0 for a zero divisor (D), % gives 0 for a zero divisor (M). PRELUDE defines them.
So Node's output is what the program must print on our machine.

The generator stays inside the documented language (README "The language" and "Limits"), so any difference is a bug:
- values are typed: number, string, array of numbers or of strings (with a known minimum length: push only raises it),
  object (known keys); a variable keeps its type, and booleans never reach a variable, a parameter, a return value or an
  arithmetic operand (they are printed only as a comparison / ! / && / || / a method like includes of those, directly
  in console.log);
- strings are built with + anywhere (never two numbers: Node's + on numbers is spelled W(...)); string methods get
  arguments they can't fail on (charCodeAt on s + "z" at 0, indexes in range);
- indexes stay in bounds, missing properties are never read, objects are never printed (arrays are: the oracle skips
  what Node prints on several lines), number keys never meet the string spelling of the same number;
- loops terminate: counters are reserved names that only their loop changes, continue is used only where the counter
  still advances, calls form a DAG except self-recursion on a decreasing depth parameter;
- every typed function ends with a return; a function's value is used only if it has a type.
Limits the compiler enforces with an error (labels, code size, nesting, strings) are not avoided: fuzz.py skips such
programs and counts them.
"""
import random, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'compiler'))
import cc_ref as _R
TAGGED = [(_R.STRV_LO, _R.STRV_HI), (_R.HEAP0 - _R.OBJTAG, _R.HEAP_HI - _R.OBJTAG), (_R.HEAP0 + _R.ARRTAG, _R.HEAP_HI + _R.ARRTAG)]

PRELUDE = ('function W(x){x=((x%1048576)+1048576)%1048576;return x>=524288?x-1048576:x}'
           'function D(a,b){return b===0?0:W(Math.trunc(a/b))}function M(a,b){return b===0?0:a%b}')

STRS = ['"a"', '"hi"', "'x y'", '""', '"Fizz"', '"it\'s"', "'q\\\"t'", '"t\\tx"', '"n\\\\m"', "'ok!'", '"A\\nB"']
NAMES = ['a', 'b', 'c', 'd', 'e', 'g', 'h', 'x', 'y', 'z', 'u', 'v', 'w', 'p', 'q', 'r', 's', 't', 'k', 'm', 'n2', 'val',
         'sum', 'tmp', 'acc', 'lo', 'hi2', 'abc', 'x_1', '$v', '_q']
KEYS = ['a', 'b', 'k', 'len', 'next', 'v2']
URLS = ['"hello.txt"', '"n.txt"', '"nope.txt"', '"/data/lines.txt"', '"http://x/"']     # fetch's (tests/net/)
SKEYS = ['"c d"', '"x"', "'k'"]          # string keys ('k' is the same property as the identifier key k)
PREC = {'||': 2, '&&': 3, '==': 4, '!=': 4, '===': 4, '!==': 4, '<': 5, '>': 5, '<=': 5, '>=': 5, '+': 6, '-': 6,
        '*': 7, '/': 7, '%': 7}

# ---------------- expressions: (kind, ...) tuples; render(e, t) -> (text, precedence)
def lit(v): return ('lit', v)

def rend(e, t):
    k = e[0]
    if k == 'lit': return str(e[1]), 9
    if k == 'raw': return e[1], 9                     # a name, a string literal, a call already rendered
    if k == 'neg':
        s, p = rend(e[1], t)
        if t == 'n': return f'W(-{paren(s, p < 9)})', 9
        return '-' + (f'({s})' if p < 9 or s.startswith('-') else s), 8
    if k == 'not':
        s, p = rend(e[1], t)
        return '!' + (f'({s})' if p < 8 else s), 8
    if k == 'bin':
        op, a, b = e[1], e[2], e[3]
        sa, pa = rend(a, t); sb, pb = rend(b, t)
        if t == 'n' and op in '+-*': return f'W({paren(sa, pa < 9)} {op} {paren(sb, pb < 9)})', 9
        if t == 'n' and op == '/': return f'D({sa}, {sb})', 9
        if t == 'n' and op == '%': return f'M({sa}, {sb})', 9
        p = PREC[op]
        return f'{paren(sa, pa < p)} {op} {paren(sb, pb <= p)}', p
    if k == 'tern':
        sc, pc = rend(e[1], t); sa, pa = rend(e[2], t); sb, pb = rend(e[3], t)
        return f'{paren(sc, pc <= 1)} ? {paren(sa, pa < 1)} : {sb}', 1
    if k == 'par':                                    # explicit parentheses (exercise the parser)
        s, _ = rend(e[1], t); return f'({s})', 9
    if k == 'call':
        return e[1] + '(' + ', '.join(rend(a, t)[0] for a in e[2]) + ')', 9
    if k == 'idx':                                    # x[i]
        s, p = rend(e[1], t); return f'{paren(s, p < 9)}[{rend(e[2], t)[0]}]', 9
    if k == 'dot':
        s, p = rend(e[1], t); return f'{paren(s, p < 9)}.{e[2]}', 9
    if k == 'inc':                                    # x++ ++x x-- --x on a number variable (not wrapped in Node: small values)
        return (e[2] + e[1]) if e[3] else (e[1] + e[2]), 8
    if k == 'arr': return '[' + ', '.join(rend(x, t)[0] for x in e[1]) + ']', 9
    if k == 'scat':                                   # a + b with a string on one side: the same text for Node (no W)
        sa, pa = rend(e[1], t); sb, pb = rend(e[2], t)
        return f'{paren(sa, pa < 6)} + {paren(sb, pb <= 6)}', 6
    if k == 'meth':                                   # x.name(args)
        s_, p_ = rend(e[1], t); return f'{paren(s_, p_ < 9)}.{e[2]}(' + ', '.join(rend(a, t)[0] for a in e[3]) + ')', 9
    if k == 'obj': return '{' + ', '.join(f'{kk}: {rend(v, t)[0]}' for kk, v in e[1]) + '}', 9
    raise ValueError(k)

def paren(s, need): return f'({s})' if need else s
def R(e, t='o'): return rend(e, t)[0]

class Var:
    def __init__(self, name, ty, const=False, ln=0, keys=None, counter=False):
        self.name, self.ty, self.const, self.ln, self.keys, self.counter = name, ty, const, ln, keys, counter

class Fn:
    def __init__(self, name, params, ret, depth):
        self.name, self.params, self.ret, self.depth = name, params, ret, depth     # params: [(name, ty)]
        self.prints = False                           # its body (or a function it calls) prints

# ---------------- statements render to lines; layout decisions are made at generation time and stored
class Gen:
    def __init__(self, seed, size=1.0):
        self.r = random.Random(seed); self.size = size
        self.scopes = [{}]; self.fns = []; self.cur = None; self.loops = 0; self.inswitch = 0; self.nctr = 0
        self.budget = int(self.r.randint(8, 40) * size); self.strs = self.r.sample(STRS, self.r.randint(2, 6))
        self.hide = None; self.selfcalls = 0; self.contok = False; self.inlog = False; self.nst = {}      # nst: statements so far per scope (by id)

    # ---- scope
    def vars(self, pred=lambda v: True):
        seen = {}
        for sc in self.scopes:
            for n, v in sc.items(): seen[n] = v
        return [v for v in seen.values() if pred(v) and v.name != self.hide]
    def fresh(self):
        used = {n for sc in self.scopes for n in sc} | {f.name for f in self.fns}
        cand = [n for n in NAMES if n not in self.scopes[-1] and n not in {f.name for f in self.fns}]
        if self.r.random() < 0.15 and not self.nst.get(id(self.scopes[-1])):      # shadow an outer name, as a block's first statement (TDZ)
            outer = [n for n in used if n not in self.scopes[-1] and n in NAMES]
            if outer and len(self.scopes) > 1: return self.r.choice(outer)
        cand = [n for n in cand if n not in used] or cand
        return self.r.choice(cand) if cand else None

    # ---- expressions
    def num(self, d=0):
        r = self.r
        opts = ['lit', 'lit', 'var', 'var', 'bin', 'bin', 'bin', 'neg', 'tern', 'call', 'idx', 'len', 'prop', 'inc', 'par', 'logic', 'smeth', 'ameth']
        if d >= 3: opts = ['lit', 'var', 'var', 'idx', 'len', 'prop']
        k = r.choice(opts)
        if k == 'lit':
            x = r.random()
            v = r.randint(0, 9) if x < .5 else r.randint(10, 999) if x < .8 else r.randint(1000, 9000) if x < .95 else r.randint(8192, 300000)
            return lit(v if not any(lo <= v < hi for lo, hi in TAGGED) else 8192)       # (numbers there are arrays to our machine)
        if k == 'var':
            vs = self.vars(lambda v: v.ty == 'num')
            return ('raw', r.choice(vs).name) if vs else lit(r.randint(0, 20))
        if k == 'bin':
            op = r.choice('+-*+-*/%')
            a, b = self.num(d + 1), self.num(d + 1)
            return ('bin', op, a, b)
        if k == 'neg': return ('neg', self.num(d + 1))
        if k == 'tern': return ('tern', self.cond(d + 1), self.num(d + 1), self.num(d + 1))
        if k == 'par': return ('par', self.num(d + 1))
        if k == 'logic': return ('bin', r.choice(['&&', '||']), self.num(d + 1), self.num(d + 1))
        if k == 'call':
            c = self.call('num', d)
            return c if c else lit(1)
        if k == 'idx':
            a = self.arrexpr(need=1)
            return ('idx', a[0], self.index(a[1], d)) if a else lit(2)
        if k == 'len':
            a = self.arrexpr(need=0)
            return ('dot', a[0], 'length') if a else lit(3)
        if k == 'prop':
            p = self.propread('num')
            return p if p else lit(4)
        if k == 'inc':
            vs = self.vars(lambda v: v.ty == 'num' and not v.const and not v.counter)
            if not vs: return lit(5)
            return ('inc', r.choice(vs).name, r.choice(['++', '--']), r.random() < 0.5)
        if k == 'smeth':                              # a number from a string
            x = r.random(); s_ = self.strx(d + 1)
            if x < 0.3: return ('dot', s_, 'length')
            if x < 0.55: return ('meth', s_, 'indexOf', [self.strx(d + 1)])
            if x < 0.8: return ('meth', ('par', ('scat', s_, ('raw', '"z"'))), 'charCodeAt', [lit(0)])
            return ('call', 'parseInt', [('call', 'String', [self.num(d + 1)])])
        if k == 'ameth':                              # a number from an array
            a = self.arrexpr(need=0); x = r.random()
            if not a: return lit(6)
            if x < 0.4: return ('meth', a[0], 'indexOf', [self.num(d + 1)])
            if x < 0.7: return ('meth', ('arr', [self.num(d + 1), self.num(d + 1)]), 'pop', [])
            vs = self.vars(lambda v: v.ty == 'arr' and not v.counter)
            if vs and not self.inlog: return ('meth', ('raw', r.choice(vs).name), 'push', [self.num(d + 1)])
            return ('dot', a[0], 'length')
    def index(self, ln, d):
        """an index expression in 0 .. ln - 1 (ln known) or, for an array of unknown length, 0"""
        r = self.r
        if ln is None: return lit(0)
        ctrs = self.vars(lambda v: v.counter)
        x = r.random()
        if x < 0.4 or (not ctrs and x < 0.8): return lit(r.randint(0, ln - 1))
        if ctrs: return ('bin', '%', ('raw', r.choice(ctrs).name), lit(ln))          # counters are >= 0
        return lit(0)
    def arrexpr(self, need):
        """an array-valued expression -> (expr, length or None); need: minimum length"""
        r = self.r
        c = [(('raw', v.name), v.ln) for v in self.vars(lambda v: v.ty == 'arr' and (v.ln is None or v.ln >= need))]   # (a parameter's array has >= 1)
        for v in self.vars(lambda v: v.ty == 'obj'):
            for kk, (ty, ln) in v.keys.items():
                if ty == 'arr' and ln >= need: c.append((self.keyread(v.name, kk), ln))
        if r.random() < 0.1:
            n = r.randint(max(need, 1), 4); return (('arr', [self.elem() for _ in range(n)]), n)
        return r.choice(c) if c else None
    def elem(self):
        """an element of an array literal: a number literal, or (sometimes) any number expression"""
        r = self.r
        if r.random() < 0.3 and not self.inlog: return self.num(2)
        return lit(r.randint(-9, 99)) if r.random() < .8 else ('neg', lit(r.randint(1, 9)))
    def sarr(self):
        """an array of strings -> (expr, minimum length)"""
        r = self.r
        vs = self.vars(lambda v: v.ty == 'sarr')
        if vs and r.random() < 0.6: v = r.choice(vs); return ('raw', v.name), v.ln
        n = r.randint(1, 3); return ('arr', [('raw', r.choice(self.strs)) for _ in range(n)]), n
    def keyread(self, oname, kk):
        if kk.startswith('#'): return ('idx', ('raw', oname), lit(int(kk[1:])))
        if kk.startswith('"') or kk.startswith("'"): return ('idx', ('raw', oname), ('raw', kk))
        if self.r.random() < 0.2: return ('idx', ('raw', oname), ('raw', f'"{kk}"'))
        return ('dot', ('raw', oname), kk)
    def propread(self, ty):
        c = []
        for v in self.vars(lambda v: v.ty == 'obj'):
            for kk, (kty, _) in v.keys.items():
                if kty == ty: c.append(self.keyread(v.name, kk))
                if kty == 'obj' and ty == 'num': c.append(('dot', self.keyread(v.name, kk), 'e'))   # nested objects have key e
        return self.r.choice(c) if c else None
    def strx(self, d=0):
        r = self.r; k = r.random()
        vs = self.vars(lambda v: v.ty == 'str')
        if k < 0.35 and vs: return ('raw', r.choice(vs).name)
        if k < 0.45 and d < 2: return ('tern', self.cond(d + 1), self.strx(d + 1), self.strx(d + 1))
        if k < 0.55:
            c = self.call('str', d)
            if c: return c
        if k < 0.6:
            p = self.propread('str')
            if p: return p
        if k < 0.75 and d < 3:                        # + with a string on one side
            x = r.random()
            if x < 0.4: return ('scat', self.strx(d + 1), self.strx(d + 1))
            if x < 0.7: return ('scat', self.strx(d + 1), self.num(d + 1))
            return ('scat', self.num(d + 1), self.strx(d + 1))
        if k < 0.85 and d < 3:                        # string methods
            x = r.random(); s_ = self.strx(d + 1)
            if x < 0.2: return ('meth', s_, 'toUpperCase', [])
            if x < 0.4: return ('meth', s_, 'slice', [lit(r.randint(0, 3))] + ([lit(r.randint(-2, 5))] if r.random() < .5 else []))
            if x < 0.55: return ('meth', s_, 'charAt', [lit(r.randint(0, 4))])
            if x < 0.7: return ('call', 'String', [self.num(d + 1)])
            if x < 0.85:
                a, ln = self.sarr(); return ('meth', a, 'join', [('raw', r.choice(self.strs))] if r.random() < .7 else [])
            a = self.arrexpr(need=0)
            if a: return ('meth', a[0], 'join', [('raw', r.choice(self.strs))])
        if k < 0.9:
            a, ln = self.sarr(); return ('idx', a, lit(r.randint(0, ln - 1)))
        if k < 0.93 and d < 3: return ('bin', r.choice(['||', '&&']), self.strx(d + 1), self.strx(d + 1))
        return ('raw', r.choice(self.strs))
    def cond(self, d=0):
        r = self.r; k = r.random()
        bv = self.vars(lambda v: v.ty == 'bool')
        if k < 0.08 and bv: return ('raw', r.choice(bv).name)
        if k < 0.1: return ('raw', r.choice(['true', 'false']))
        if d >= 3 or k < 0.45: return ('bin', r.choice(['<', '>', '<=', '>=', '==', '!=', '===', '!==']), self.num(d + 1), self.num(d + 1))
        if k < 0.5: return ('bin', r.choice(['===', '!==', '==', '!=']), self.strx(d + 1), self.strx(d + 1))
        if k < 0.55:
            x = r.random()
            if x < 0.4: return ('bin', r.choice(['<', '>', '<=', '>=']), self.strx(d + 1), self.strx(d + 1))
            if x < 0.6: return ('meth', self.strx(d + 1), r.choice(['includes', 'startsWith']), [self.strx(d + 1)])
            a = self.arrexpr(need=0)
            if a: return ('meth', a[0], 'includes', [self.num(d + 1)])
            return ('meth', self.sarr()[0], 'includes', [self.strx(d + 1)])
        if k < 0.6: return ('not', self.cond(d + 1))
        if k < 0.65: return ('not', self.strx(d + 1)) if r.random() < .6 else ('not', ('not', self.strx(d + 1)))     # a string's truth ("" is false)
        if k < 0.85: return ('bin', r.choice(['&&', '||']), self.cond(d + 1), self.cond(d + 1))
        return ('par', self.cond(d + 1))
    def call(self, ret, d):
        selfok = self.cur is not None and self.cur.depth and self.selfcalls < 2
        cands = [f for f in self.fns if f.ret == ret and (self.cur is None or (f is self.cur and selfok) or self.fns.index(f) < self.fns.index(self.cur))]
        if selfok and self.cur.ret == ret and self.r.random() < 0.5: cands = [self.cur]
        if self.inlog: cands = [f for f in cands if not f.prints and f is not self.cur]   # README: console.log prints as it goes
        if not cands or d > 2: return None
        f = self.r.choice(cands)
        args = []
        for i, (pn, ty) in enumerate(f.params):
            if i == 0 and f.depth:
                args.append(('bin', '-', ('raw', 'dep'), lit(1)) if f is self.cur else lit(self.r.randint(0, 3)))
            else: args.append(self.val(ty, d + 1))
        if f is self.cur: self.selfcalls += 1
        if self.cur is not None and f.prints: self.cur.prints = True
        return ('call', f.name, args)
    def val(self, ty, d=1):
        if ty == 'num': return self.num(d)
        if ty == 'str': return self.strx(d)
        if ty == 'objp':                              # an object with a number at key a: shared with the callee
            os_ = [v for v in self.vars(lambda v: v.ty == 'obj' and v.keys.get('a', (None,))[0] == 'num')]
            if os_ and self.r.random() < 0.7: return ('raw', self.r.choice(os_).name)
            return ('obj', [('a', self.num(d + 1))] + ([('b', self.num(d + 1))] if self.r.random() < 0.5 else []))
        a = self.arrexpr(need=1)
        return a[0] if a else ('arr', [lit(1), lit(2)])

    # ---- statements: each returns a list of lines (without the trailing newline)
    def semi(self):
        """a simple statement's end: ';' or nothing (the newline or '}' ends it: semicolon insertion)"""
        return ';' if self.r.random() < 0.6 else ''
    def cmt(self):
        x = self.r.random()
        return ' // note' if x < 0.04 else ' /* c */' if x < 0.07 else ''
    def simple(self, text): return [text + self.semi() + self.cmt()]
    def block(self, n=None, scope=True):
        if scope: self.scopes.append({})
        out = []
        for _ in range(n if n is not None else self.r.randint(0, 3)):
            if self.budget <= 0: break
            out += self.stmt()
        if scope: self.scopes.pop()
        return out
    def body(self, lead=None):
        """a body: { ... } or a single statement (lead: statements that must come first, e.g. a counter step)"""
        r = self.r
        if lead is None and r.random() < 0.3 and self.budget > 0:
            self.scopes.append({})
            s = self.stmt(braceless=True)
            self.scopes.pop()
            if len(s) == 1 and (isinstance(s[0], str) or s[0][0] not in ('DECL', 'RAWL', 'FN')): return ('one', s)
            return ('blk', s)
        self.scopes.append({})
        inner = (lead or []) + self.block(scope=False)
        self.scopes.pop()
        return ('blk', inner)
    def stmt(self, braceless=False):
        sc = id(self.scopes[-1]); out = self.stmt1(braceless)
        self.nst[sc] = self.nst.get(sc, 0) + 1
        return out
    def stmt1(self, braceless=False):
        r = self.r; self.budget -= 1
        opts = ['decl', 'decl', 'asg', 'asg', 'log', 'log', 'log', 'if', 'if', 'loop', 'inc', 'aset', 'pset', 'switch', 'callst', 'blk', 'putc', 'alloc', 'push', 'net']
        if self.loops: opts += ['break', 'cont']
        if self.cur is not None: opts += ['ret']
        if len(self.scopes) > 6 or self.budget < 0: opts = ['log', 'asg', 'inc']
        k = r.choice(opts)
        if braceless and k in ('decl', 'blk'): k = 'log'
        f = getattr(self, 's_' + k)
        out = f()
        return out if out is not None else self.s_log()
    def s_decl(self):
        r = self.r
        if self.inswitch: return None                 # (a case's let is scoped to the whole switch: TDZ across cases)
        n = self.fresh()
        if n is None: return None
        kw = r.choice(['var', 'let', 'const', 'let'])
        if kw == 'var' and len(self.scopes) != (2 if self.cur is not None else 1): kw = 'let'     # var only at function / program level
        self.hide = n                                 # the initialiser must not read an outer n (it would be in its TDZ)
        ty = r.choice(['num', 'num', 'num', 'str', 'arr', 'obj', 'bool', 'sarr'])
        if ty == 'num': e = self.num()
        elif ty == 'bool': e = self.cond()
        elif ty == 'str': e = self.strx()
        elif ty == 'arr':
            ln = r.randint(0, 5); e = ('arr', [self.elem() for _ in range(ln)])
        elif ty == 'sarr':
            e, ln = self.sarr()
            if e[0] == 'raw': e = ('meth', e, 'slice', [])        # (a copy: the variable's length is its own)
        else:
            keys, items = {}, []
            for kk in r.sample(KEYS, r.randint(0, 3)) + (r.sample(SKEYS, 1) if r.random() < .3 else []) + ([f'#{r.randint(0, 99)}'] if r.random() < .2 else []):
                if kk in ("'k'",) and 'k' in keys: continue
                kty = r.choice(['num', 'num', 'str', 'arr', 'obj'])
                if kty == 'num': v = self.num(1)
                elif kty == 'str': v = self.strx(1)
                elif kty == 'arr':
                    ln = r.randint(1, 4); v = ('arr', [lit(r.randint(0, 30)) for _ in range(ln)])
                else: v = ('obj', [('e', self.num(2))])
                keys[kk] = (kty, ln if kty == 'arr' else 0)
                items.append((kk[1:] if kk.startswith('#') else kk, v))
            e = ('obj', items)
        # a second declarator sometimes (var a = 1, b = 2)
        self.hide = None
        decls = [(n, e)]
        v = Var(n, ty, const=(kw == 'const'), ln=(len(e[1]) if ty == 'arr' else ln if ty == 'sarr' else 0), keys=(keys if ty == 'obj' else None))
        self.scopes[-1][n] = v
        if ty == 'num' and r.random() < 0.15:          # var a = 1, b = 2
            n2 = self.fresh()
            if n2 and n2 != n:
                self.hide = n2; decls.append((n2, self.num(1))); self.hide = None
                self.scopes[-1][n2] = Var(n2, 'num', const=(kw == 'const'))
        return [('DECL', kw, decls)]
    def s_asg(self):
        r = self.r
        vs = self.vars(lambda v: not v.const and not v.counter and v.ty in ('num', 'str', 'bool'))
        if not vs: return None
        v = r.choice(vs)
        if v.ty == 'str': return [('ASG', v.name, '=', self.strx())]
        if v.ty == 'bool': return [('ASG', v.name, '=', self.cond())]
        op = r.choice(['=', '=', '+=', '-=', '*=', '/=', '%='])
        return [('ASG', v.name, op, self.num())]
    def s_inc(self):
        vs = self.vars(lambda v: v.ty == 'num' and not v.const and not v.counter)
        if not vs: return None
        n = self.r.choice(vs).name; op = self.r.choice(['++', '--'])
        return self.simple(self.r.choice([n + op, op + n]))
    def s_aset(self):
        r = self.r
        cs = [v for v in self.vars(lambda v: v.ty == 'arr' and v.ln)]
        if not cs: return None
        v = r.choice(cs); i = self.index(v.ln, 1)
        k = r.random()
        if k < 0.2: return self.simple(f'{v.name}[{R(i)}]' + r.choice(['++', '--']))
        op = r.choice(['=', '=', '+=', '-=', '*='])
        return [('ASET', v.name, i, op, self.num())]
    def s_push(self):
        """an array grows: push, or a store at its length (its known minimum length stays valid)"""
        r = self.r
        cs = self.vars(lambda v: v.ty in ('arr', 'sarr') and not v.counter)
        if not cs: return None
        v = r.choice(cs); e = self.num() if v.ty == 'arr' else self.strx()
        if r.random() < 0.7: return [('EXPR', ('meth', ('raw', v.name), 'push', [e]), self.semi())]
        return [('ASET', v.name, ('dot', ('raw', v.name), 'length'), '=', e)]
    def s_pset(self):
        r = self.r
        cs = self.vars(lambda v: v.ty == 'obj')
        if not cs: return None
        v = r.choice(cs)
        nk = [kk for kk, (ty, _) in v.keys.items() if ty == 'num']
        if not nk or r.random() < 0.2:                # a new key (remembered only if it is surely added)
            kk = r.choice(KEYS)
            if kk in v.keys or ("'k'" in v.keys and kk == 'k'): return None
            e = self.num()                            # (before the key exists: the value must not read it)
            if len(self.scopes) == 1 and self.cur is None: v.keys[kk] = ('num', 0)
            return [('PSET', self.keyread(v.name, kk), '=', e)]
        kk = r.choice(nk); tgt = self.keyread(v.name, kk)
        if r.random() < 0.2: return self.simple(R(tgt) + r.choice(['++', '--']))
        return [('PSET', tgt, r.choice(['=', '+=', '-=', '*=', '%=']), self.num())]
    def s_log(self):
        if self.cur is not None: self.cur.prints = True
        self.inlog = True; out = self.s_log1(); self.inlog = False
        return out
    def s_log1(self):
        r = self.r; args = []
        for _ in range(r.choice([0, 1, 1, 1, 2, 2, 3])):
            k = r.random()
            if k < 0.4: args.append(('num', self.num()))
            elif k < 0.6: args.append(('str', self.strx()))
            elif k < 0.7: args.append(('cond', self.cond()))
            elif k < 0.75:                              # an array itself
                a = self.arrexpr(need=0) if r.random() < 0.6 else self.sarr()
                args.append(('arr', a[0] if a else ('arr', [])))
            else:                                       # "..." + n + ...: pieces joined by + (a string first, or after numbers)
                pieces = []
                if r.random() < 0.3: pieces += [('num', self.num(2)), ('num', self.num(2))]
                for _ in range(r.randint(1, 3)): pieces += [('str', self.strx(2)), ('num', self.num(1))]
                args.append(('cat', pieces))
        return [('LOG', args)]
    def s_net(self):
        """fetch / read: the tests' gateway (net/device.py) and the oracle's (net/shim.js) serve tests/net/ alike"""
        if self.cur is not None: self.cur.prints = True
        r = self.r
        if r.random() < 0.4: return self.simple(f'console.log(fetch({r.choice(URLS)}))')
        return self.simple('console.log(read())')
    def s_putc(self):
        if self.cur is not None: self.cur.prints = True
        return self.simple(f'putc({self.r.randint(33, 126)})')
    def s_callst(self):
        fs = [f for f in self.fns if self.cur is None or self.fns.index(f) < self.fns.index(self.cur)]
        if not fs: return None
        f = self.r.choice(fs)
        if self.cur is not None and f.prints: self.cur.prints = True
        args = [lit(self.r.randint(0, 3)) if i == 0 and f.depth else self.val(ty) for i, (_, ty) in enumerate(f.params)]
        return [('EXPR', ('call', f.name, args), self.semi())]
    def s_blk(self): return [('BLK', self.block())]
    def s_ret(self):
        e = self.num() if self.cur.ret == 'num' else self.strx()
        return [('RET', e)]
    def s_break(self): return [('IFJ', self.cond(), 'break')] if self.r.random() < 0.8 else self.simple('break')
    def s_cont(self):
        if not self.contok: return None
        return [('IFJ', self.cond(), 'continue')]
    def s_if(self):
        x = self.r.random(); c = self.cond() if x < 0.8 else self.num() if x < 0.9 else self.strx()      # (a string: its truth)
        th = self.body(); els = []
        k = self.r.random()
        if k < 0.25: els = [('else', self.body())]
        elif k < 0.4:
            els = [('elif', self.cond(), self.body())]
            if self.r.random() < 0.5: els.append(('else', self.body()))
        return [('IF', c, th, els)]
    def s_loop(self):
        r = self.r
        if self.nctr >= 8: return None
        ctr = f'i{self.nctr}'; self.nctr += 1; K = r.randint(0, 5)
        kind = r.choice(['for', 'for', 'forv', 'fordown', 'while', 'do'])
        self.loops += 1; savec = getattr(self, 'contok', False)
        if kind in ('for', 'forv', 'fordown'):
            self.contok = True
            if kind == 'forv' and (self.cur is not None or len(self.scopes) > 1): kind = 'for'
            sc = {ctr: Var(ctr, 'num', counter=True)}
            self.scopes.append(sc); b = self.body(); self.scopes.pop()
            if kind == 'fordown': hdr = f'for (let {ctr} = {K}; {ctr} > 0; {ctr}--)'
            else: hdr = f'for ({"var" if kind == "forv" else "let"} {ctr} = 0; {ctr} < {K}; {r.choice([ctr + "++", "++" + ctr, ctr + " += 1"])})'
            out = [('LOOP', hdr, b, None)]
        else:
            self.contok = True
            decl = [f'var {ctr} = 0;' if self.cur is None and len(self.scopes) == 1 else f'let {ctr} = 0;']
            self.scopes[-1][ctr] = Var(ctr, 'num', counter=True)
            b = self.body(lead=[f'{ctr}++;'])
            if kind == 'while': out = [('RAWL', decl), ('LOOP', f'while ({ctr} < {K})', b, None)]
            else: out = [('RAWL', decl), ('LOOP', 'do', b, f'while ({ctr} < {K})')]
        self.loops -= 1; self.contok = savec
        return out
    def s_alloc(self):
        """a loop that allocates an object per iteration and keeps a few: enough to run the garbage collector"""
        r = self.r
        if self.nctr >= 8 or self.loops or self.cur is not None: return None
        ctr = f'i{self.nctr}'; self.nctr += 1; n = r.choice([50, 200, 500])
        acc = self.fresh()
        if acc is None: return None
        keep = r.random() < 0.5
        lines = [f'let {acc} = {{a: 0, nx: null}}' if keep else f'let {acc} = 0',
                 f'for (let {ctr} = 0; {ctr} < {n}; {ctr}++) {{',
                 f'  let t = {{a: {ctr}, b: [5, 2], c: {{d: {ctr} % 7}}}}',
                 (f'  if ({ctr} % 50 == 0) {acc} = {{a: {acc}.a + t.c.d, nx: {acc}}}' if keep else f'  {acc} = {acc} + t.b[0] % 3 + t.c.d'),
                 '}',
                 f'console.log({acc}.a)' if keep else f'console.log({acc})']
        self.scopes[-1][acc] = Var(acc, 'obj', keys={'a': ('num', 0)}) if keep else Var(acc, 'num')
        return [('RAWL', lines)]
    def s_switch(self):
        r = self.r; k = r.random()
        if k < 0.6: disc, mk = self.num(), lambda: lit(r.randint(-2, 6)) if r.random() < .8 else self.num(2)
        elif k < 0.8: disc, mk = self.strx(), lambda: ('raw', r.choice(self.strs))
        else: disc, mk = ('raw', 'true'), lambda: self.cond(2)
        clauses = []; hasdef = False
        for _ in range(r.randint(0, 4)):
            if not hasdef and r.random() < 0.25: hasdef = True; lab = None
            else: lab = mk()
            self.inswitch += 1; self.loops += 1                    # break is allowed in a switch
            savec = getattr(self, 'contok', False); self.contok = savec and self.loops > 1
            self.scopes.append({}); st = self.block(r.randint(0, 2), scope=False); self.scopes.pop()
            self.loops -= 1; self.inswitch -= 1; self.contok = savec
            if r.random() < 0.5: st = st + ['break;']
            clauses.append((lab, st))
        return [('SWITCH', disc, clauses)]

    # ---- whole program
    def program(self):
        r = self.r
        # globals first (functions may use them, so they exist before any call), then function definitions and
        # statements, interleaved
        top = []
        for _ in range(r.randint(1, 4)):
            top += self.s_decl() or []
        nf = r.randint(0, 4)
        for i in range(nf):
            ps = [('dep', 'num')] if r.random() < 0.4 else []
            ps += [(pn, r.choice(['num', 'num', 'str', 'arr', 'objp'])) for pn in r.sample(['p1', 'p2', 'p3', 'pa'], r.randint(0, 3))]
            self.fns.append(Fn(f'f{i}', ps, r.choice(['num', 'num', 'str', None]), bool(ps and ps[0][0] == 'dep')))
        defs = []
        for f in self.fns:
            self.cur = f; self.selfcalls = 0
            self.scopes.append({pn: (Var(pn, 'obj', keys={'a': ('num', 0)}) if ty == 'objp' else Var(pn, ty, ln=None, counter=(pn == 'dep')))
                                for pn, ty in f.params})
            saveb = self.budget; self.budget = int(r.randint(2, 8) * self.size)
            body = []
            if f.depth:                               # the recursion's base case (no self-call in it)
                self.selfcalls = 2
                body.append(('IFJ', ('bin', '<=', ('raw', 'dep'), lit(0)), ('RET', self.num(2) if f.ret == 'num' else self.strx(2)) if f.ret else 'return'))
                self.selfcalls = 0
            body += self.block(scope=False)
            if f.ret: body.append(('RET', self.num() if f.ret == 'num' else self.strx()))
            self.scopes.pop(); self.budget = saveb; self.cur = None
            defs.append(('FN', f, body))
        rest = []
        while self.budget > 0: rest += self.stmt()
        for d in defs: rest.insert(r.randint(0, len(rest)), d)
        return top + rest

# ---------------- layout: statements -> text (t: 'o' ours, 'n' Node)
class Layout:
    def __init__(self, seed, t):
        self.r = random.Random(seed); self.t = t
    def e(self, x): return R(x, self.t)
    def lines(self, sts, ind):
        out = []
        for s in sts: out += self.st(s, ind)
        return out
    def end(self):
        return ';' if self.r.random() < 0.6 else ''
    def st(self, s, ind):
        p = '  ' * ind; r = self.r
        if isinstance(s, str): return [p + s]
        k = s[0]
        if k == 'DECL':
            _, kw, ds = s
            return [f'{p}{kw} ' + ', '.join(f'{n} = {self.e(e)}' for n, e in ds) + self.end()]
        if k == 'EXPR': return [p + self.e(s[1]) + s[2]]
        if k in ('ASG', 'ASET', 'PSET'):              # Node: x op= e as x = x op e with the machine's arithmetic
            if k == 'ASG': _, n, op, e = s; tgt = n
            elif k == 'ASET': _, n, i, op, e = s; tgt = f'{n}[{self.e(i)}]'
            else: _, t_, op, e = s; tgt = self.e(t_)
            end = self.end()
            if self.t == 'n' and op != '=': return [f'{p}{tgt} = {self.e(("bin", op[0], ("raw", tgt), e))}{end}']
            return [f'{p}{tgt} {op} {self.e(e)}{end}']
        if k == 'LOG':
            parts = []
            for kind, a in s[1]:
                if kind == 'cat':
                    ps = []
                    for pk, pe in a:
                        txt, pr = rend(pe, self.t)
                        ps.append(txt if pr >= 7 or (pk == 'str' and pr >= 9) else f'({txt})')
                    parts.append(' + '.join(ps))
                else: parts.append(self.e(a))
            return [f'{p}console.log({", ".join(parts)}){self.end()}']
        if k == 'RET': return [f'{p}return {self.e(s[1])}{self.end()}']
        if k == 'IFJ':
            j = s[2]
            js = (f'return {self.e(j[1])}' if isinstance(j, tuple) else j) + ';'
            return [f'{p}if ({self.e(s[1])}) {js}'] if r.random() < 0.6 else [f'{p}if ({self.e(s[1])}) {{ {js} }}']
        if k == 'BLK': return [p + '{'] + self.lines(s[1], ind + 1) + [p + '}']
        if k == 'RAWL': return [p + x for x in s[1]]
        if k == 'IF':
            _, c, th, els = s
            out = self.body(f'{p}if ({self.e(c)})', th, ind)
            for el in els:
                if el[0] == 'elif': out = self.join_else(out, self.body(f'else if ({self.e(el[1])})', el[2], ind), p)
                else: out = self.join_else(out, self.body('else', el[1], ind), p)
            return out
        if k == 'LOOP':
            _, hdr, b, tail = s
            out = self.body(p + hdr, b, ind)
            if tail: out[-1] += ' ' + tail + self.end()
            return out
        if k == 'SWITCH':
            _, disc, cl = s
            out = [f'{p}switch ({self.e(disc)}) {{']
            for lab, st in cl:
                head = f'{p}  ' + ('default:' if lab is None else f'case {self.e(lab)}:')
                body = self.lines(st, ind + 2)
                if body and r.random() < 0.4 and len(body) == 1: out.append(head + ' ' + body[0].strip())
                else: out += [head] + body
            return out + [p + '}']
        if k == 'FN':
            _, f, body = s
            return [f'{p}function {f.name}({", ".join(pn for pn, _ in f.params)}) {{'] + self.lines(body, ind + 1) + [p + '}']
        raise ValueError(k)
    def body(self, head, b, ind):
        p = '  ' * ind
        if b[0] == 'one':
            inner = self.lines(b[1], 0)
            if len(inner) == 1 and self.r.random() < 0.5: return [f'{head} {inner[0]}']
            return [head] + ['  ' * (ind + 1) + x for x in inner]
        return [head + ' {'] + self.lines(b[1], ind + 1) + [p + '}']
    def join_else(self, out, el, p):
        if out[-1].strip() == '}' or out[-1].rstrip().endswith('}'):
            if self.r.random() < 0.5: out[-1] += ' ' + el[0].strip(); return out + el[1:]
        el[0] = p + el[0].strip(); return out + el

def generate(seed, size=1.0):
    """-> (ours, node): the program for our compiler and for Node (run after PRELUDE)"""
    g = Gen(seed, size); prog = g.program()
    return Layout(seed, 'o').lines(prog, 0), Layout(seed, 'n').lines(prog, 0)

if __name__ == '__main__':
    import sys
    o, n = generate(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
    print('\n'.join(o)); print('// ---- node'); print('\n'.join(n))
