#!/usr/bin/env python3
"""cpu4.py — font CPU v4: cpu2 with 4-word cache lines (semantics = uarch4.py).

Line = one aligned block of B=4 words: TAG = address // 4 (TAG0 holds address bits 2-3), per word state
WS (0 invalid, 1 clean, 2 dirty) and value nibbles VAL{w}_{j}. The word is selected by the low two bits of
the address digit on the bus (BA0). WE = 1 + word on the line being written. GS_j = 2 + word on the line
that hits a read. Readback: span A (tag + victim flag) and 7 spans of three value nibbles each (in cell
order: digit-major, word-minor); the last one also carries the four word states.

(cpu2 notes follow.)
font CPU v2, laid out for HarfBuzz's cost model (rules tried x context walk distance).

Core is digit-major: block j holds digit j of every register next to a local copy of the control glyph,
so contexts are a few glyphs long. Arithmetic is dispatched: a rule starts at the source digit (one rule
per value class) and applies a nested SET/ADD to the target; then a carry ripple; NORM at cycle end.
Cache: N lines, ring with a victim flag (no data ever moves between lines).
Semantics = uarch.py (victim-pointer ring, no evict buffer).
"""
import re
from cpugen import Program, A, RA, MAP, DA, Op
from uarch import OPN, UCODE, ROM, MASK, s20, PRINTOPS, SEL
# the 4-digit registers' top digit is masked: addresses (PC, SP, FP, MAR) to 3 bits (15-bit addresses: ROM + RAM up to 32K words),
# the immediate to 1 bit (an instruction word is op * 8192 + a 13-bit immediate)
TOPMASK = {'IMM3': 1}
def topmask(reg3): return TOPMASK.get(reg3, 7)
assert ROM % 256 == 0 and ROM <= 4096

D16 = [(d, 0) for d in range(16)]
D48 = [(d, c) for c in range(3) for d in range(16)]
BAV = [(d, e) for e in (0, 1) for d in range(16)]
BIT = [0, 1]
EXTOPS = ['MUL', 'DIV', 'MOD', 'SHL13'] + PRINTOPS + ['NET']
CVALS = [('S',), ('F', 0)] + [(n, u) for n in OPN for u in range(len(UCODE[n]))] + \
        [('T', k) for k in ['MISS', 'WFAIL', 'PUTC', 'HALT'] + ['EXT_' + e for e in EXTOPS]]
OKV = ['ok', 'miss', 'wfail', 'wait']
REG13 = ['IMM', 'PC', 'FP', 'SP', 'MAR']
REG20 = ['MDR', 'RES', 'T1', 'T2', 'T3', 'D', 'MDW']
BLOCK = ['MDR', 'RES', 'IMM', 'PC', 'FP', 'SP', 'T1', 'T2', 'T3', 'D', 'MAR', 'MDW']   # dispatch sources before targets
def width(r): return 4 if r in REG13 or r == 'SIM' else 5
# SIM: the 13-bit immediate read as signed (>= 4096 means negative). The address registers are 15-bit now, so adding it to FP
# must sign-extend: when the immediate's top digit is 1 (its only possible nonzero value), the sum's top digit gets 7 = 1 + 6
# (0x6000 = 32768 - 8192), and the carry stage's ADDM masks the result to 3 bits.
def regcell(r): return 'IMM' if r == 'SIM' else r
def srcdigit(r, j, v): return (7 if v & 1 else 0) if r == 'SIM' and j == 3 else v     # (the rules are enumerated for every digit value; only 0 / 1 occur)
WB = 4
LINEF = (['BOP', 'MB', 'VF', 'VD', 'WE'] + [x for j in range(4) for x in (f'BA{j}', f'TAG{j}')] + ['WH'] +
         [x for j in range(5) for x in [f'GS{j}', f'BD{j}'] + [f'VAL{w}_{j}' for w in range(WB)] + [f'G{4*j+i}' for i in range(4)]] +
         ['GH', 'VS', 'GF'] + [f'WS{w}' for w in range(WB)])
LINEV = {'BOP': ['N', 'R', 'W'], 'VF': [0, 1, 2, 3], 'VD': [0, 1, 2], 'MB': [0, 1], 'GH': [0, 1], 'GF': [0, 1], 'VS': [0, 1], 'WE': list(range(WB + 1)),
         'WH': [0, 1], **{f'GS{j}': list(range(14)) for j in range(5)}, **{f'WS{w}': [0, 1, 2] for w in range(WB)}}
NIB = [f'VAL{w}_{j}' for j in range(5) for w in range(WB)]          # nibble order along the line (readback)

def digits(v, n): v &= (1 << (4 * n)) - 1; return [(v >> (4 * j)) & 15 for j in range(n)]
def terms_of(gk): return list(gk)
def choices_of(cv, e, z=None):
    """{(cv, z): expr} for an expression that may be a selector dict ({ZSEL value: expr})"""
    if isinstance(e, dict): return {(cv, zz): x for zz, x in e.items()}
    return {(cv, z): e}

def parse(e):
    """-> (terms [(sign, reg)], K) or ('BOOL', name)."""
    m = re.fullmatch(r'(ADD|SUB|LT|GT|LE|GE|EQ|NE|AND|OR)\(T2,T1\)', e)
    if m:
        f = m.group(1)
        if f == 'ADD': return [(1, 'T2'), (1, 'T1')], 0
        if f == 'SUB': return [(1, 'T2'), (-1, 'T1')], 0
        return 'BOOL', f
    if e == 'Z(T1)': return 'BOOL', 'Z'
    terms, K = [], 0
    for sign, tok in re.findall(r'([+-]?)([A-Z0-9]+)', e):
        sg = -1 if sign == '-' else 1
        if tok.isdigit(): K += sg * int(tok)
        else: terms.append((sg, tok))
    return terms, K

class CPU:
    def __init__(self, image, N=16):
        self.image, self.N = image, N
        P = self.P = Program(); t = P.T
        t('P', list(range(ROM)) + ['RAM']); t('C', CVALS); t('RESV', BIT); t('NI', list(range(64)))
        self.HDR = [('HPC', 4), ('HSP', 4), ('HFP', 4), ('HRES', 5), ('HMAR', 4), ('HT1', 5), ('HT2', 5)]
        for h, w in self.HDR:
            for j in range(w): t(f'{h}{j}', D16)
        for j in range(5):
            t(f'CJ{j}', CVALS); t(f'ZJ{j}', [0, 1, 2]); t(f'OKJ{j}', OKV)
            for b in range(4): t(f'MDRB{4*j+b}', BIT)
            for r in BLOCK:
                if j < width(r): t(f'{r}{j}', D48)
        t('BF', list(range(16)))
        for f in ['ZT1', 'ZT2', 'ZD', 'SD', 'ST2', 'HIT', 'FAIL', 'VANY', 'MBC', 'FAIL0']: t(f, BIT)
        t('ZSEL', [0, 1, 2])
        t('MOP', ['N', 'R', 'W']); t('OK1', OKV[:3]); t('OK', OKV)
        for f in LINEF:
            t(f'L.{f}', LINEV.get(f, BAV if f.startswith('BA') else BIT if f[0] in 'GM' else D16))
        # layout
        self.core = {}
        def put(n): self.core[n] = P.cell(P.types[n], 'core', None, n)
        for n in ['P', 'C', 'RESV', 'NI'] + [f'{h}{j}' for h, w in self.HDR for j in range(w)]: put(n)
        for j in range(5):
            for n in [f'CJ{j}', f'ZJ{j}', f'OKJ{j}'] + [f'MDRB{4*j+b}' for b in range(4)]: put(n)
            for r in BLOCK:
                if j < width(r):
                    if r == 'MAR' and j == 0: put('BF')
                    put(f'{r}{j}')
        for n in ['ZT1', 'ZT2', 'ZD', 'SD', 'ST2', 'ZSEL', 'OK1', 'OK', 'FAIL', 'MBC', 'FAIL0', 'HIT', 'VANY', 'MOP']: put(n)
        self.lines = [{f: P.cell(P.types[f'L.{f}'], 'L', k, f) for f in LINEF} for k in range(N)]
        # ---- readback: export twins (base glyphs) whose advances encode values; spans are contiguous cell ranges
        self.weights = {'C': lambda v: CVALS.index(v), 'RESV': lambda v: 256 * v, 'NI': lambda v: v, 'L.VF': lambda v: 8192 * (v == 1)}   # tag < 8192
        for h, w in self.HDR:
            if h == 'HRES': continue
            for j in range(w):
                self.weights[f'{h}{j}'] = (lambda e: lambda v: v[0] << (4 * e))(j if not (h in ('HT1', 'HT2') and j >= 3) else j - 3)
        for j, wt in enumerate([1, 4, 64, 1024]): self.weights[f'L.TAG{j}'] = (lambda wt: lambda v: v[0] * wt)(wt)
        for i, f in enumerate(NIB): self.weights[f'L.{f}'] = (lambda e: lambda v: v[0] << (4 * e))(i % 3)
        for w, wt in enumerate([256, 768, 2304, 6912]): self.weights[f'L.WS{w}'] = (lambda wt: lambda v: v * wt)(wt)
        self.twin = {}
        for tn in self.weights:
            tt = P.types[tn]; self.twin[tn] = P.T('X.' + tn, tt.values)
        cells = P.cells
        def rng(a, b): return [x for x in cells[a.pos:b.pos + 1]]
        cc = self.core
        self.spans = [('CR', rng(cc['C'], cc['RESV'])), ('NI', [cc['NI']])]
        for h, w in self.HDR:
            if h in ('HT1', 'HT2'):
                self.spans += [(h + 'lo', rng(cc[f'{h}0'], cc[f'{h}2'])), (h + 'hi', rng(cc[f'{h}3'], cc[f'{h}4']))]
            else:
                self.spans.append((h, rng(cc[f'{h}0'], cc[f'{h}{w-1}'])))
        for k, ln in enumerate(self.lines):
            self.spans.append((f'L{k}A', rng(ln['BOP'], ln['TAG3'])))
            for s_ in range(7):
                a, b = ln[NIB[3 * s_]], (ln[NIB[min(3 * s_ + 2, 19)]] if s_ < 6 else ln[f'WS{WB - 1}'])
                self.spans.append((f'L{k}V{s_}', rng(a, b)))
        self.top13 = [f'{r}3' for r in REG13]; P.topmask = topmask
        import os
        if os.environ.get('SPLITALL'):
            orig = P.stage
            def st(name, specs):
                if len(specs) > 1 and not name.startswith(tuple(os.environ.get('KEEP', '#').split(','))):
                    for s_ in specs: orig(f'{name}/{s_.name}', [s_])
                else: orig(name, specs)
            P.stage = st
        self.stages()
        self.io_stages()

    def c(self, n): return self.core[n]
    def reg(self, r): return [self.core[f'{r}{j}'] for j in range(width(r))]
    def before(self, a, b): return self.core[a].pos < self.core[b].pos

    # ------------------------------------------------------------ arithmetic: target := expr chosen by C
    def lin(self, target, choices, commit=False, merge=False):
        """choices: {(cv, zreq): expr}; zreq None/0/1. Returns (R1, R2, R3) spec lists."""
        tw = width(target)
        groups = {}
        zcv = {cv for (cv, z) in choices if z is not None}
        for (cv, z), e in choices.items():
            p = parse(e)
            gk = ('BOOL',) if p[0] == 'BOOL' else tuple(sorted(p[0]))
            # control values gated by ZJ get rules of their own: in a shared group every member would enumerate ZJ's values
            groups.setdefault((gk, cv in zcv), {})[(cv, z)] = p
        R1, R2, R3 = [], [], []
        ungated = list(choices) == [('*', None)]
        any_carry = False
        marks = []                                    # where each group's specs start (merge_digits merges within a group)
        for (gk, _), mem in groups.items():
            marks.append((len(R1), len(R2)))
            sems = {}
            for (cv, z), p in mem.items(): sems.setdefault(cv, []).append((z, p))
            def dkey(f, sems=sems):
                """the control-copy key for rules that depend on a member's expression only through f(p): members alike in f share
                a class (per digit: SP-1 and SP-2 differ only in digit 0, so digits 1-3 share their rules)"""
                canon, ck = {}, {}
                for cv, lst in sems.items():
                    sig = repr(sorted(((z, f(p)) for z, p in lst), key=repr))
                    ck[cv] = canon.setdefault(sig, cv)
                return lambda v, ck=ck: ck.get(v)
            usez = any(z is not None for (_, z) in mem)
            def semof(k, sems=sems, ungated=ungated):
                if ungated: return sems['*'][0][1]
                cv = k.get('cj')
                if cv is None: return None
                if commit and k.get('okj') != 'ok': return None
                for z, p in sems[cv]:
                    if z is None or z == k.get('zj'): return p
                return None
            def gates(j):
                if ungated: return {}
                g = {'cj': self.c(f'CJ{j}')}
                if usez: g['zj'] = self.c(f'ZJ{j}')
                if commit: g['okj'] = self.c(f'OKJ{j}')
                return g
            gkeys = {'cj': dkey(lambda p: repr(p)), 'zj': lambda v: v, 'okj': lambda v: v}
            def gk_(f): return {**gkeys, 'cj': dkey(f)}
            if gk == ('BOOL',):
                # digit 0 from BF, other digits 0; BF sits right before MAR0 in block 0
                def fn0(it, k, semof=semof):
                    p = semof(k)
                    if p is None: return None
                    bf = k['src']; sd, zd, z1, z2 = bf >> 3 & 1, bf >> 2 & 1, bf >> 1 & 1, bf & 1
                    b = {'LT': sd, 'GT': (not sd) and (not zd), 'LE': sd or zd, 'GE': not sd, 'EQ': zd, 'NE': not zd,
                         'AND': (not z2) and (not z1), 'OR': not (z2 and z1), 'Z': z1}[p[1]]
                    return [(0, ('SET', (int(bool(b)), 0)))]
                R1.append(DA(f'{target}0<-BOOL', [dict(src=self.c('BF'), targets=[self.c(f'{target}0')], gates=gates(0))],
                             {'src': lambda v: v, **gk_(lambda p: p[1])}, fn0))
                items = [dict(src=self.c(f'CJ{j}'), targets=[self.c(f'{target}{j}')], gates={k_: v_ for k_, v_ in gates(j).items() if k_ != 'cj'})
                         for j in range(1, tw)]
                R1.append(DA(f'{target}<-BOOL0', items, {'src': dkey(lambda p: 0), 'zj': gkeys['zj'], 'okj': gkeys['okj']},
                             lambda it, k, semof=semof: [(0, ('SET', (0, 0)))] if semof({**k, 'cj': k['src']}) else None))
                continue
            if not terms_of(gk):
                # a constant: every digit from the control copy (gated like the narrower-operand digits below)
                any_carry = True
                for j in range(tw):
                    tgt = self.c(f'{target}{j}')
                    mask = tw == 4 and j == 3
                    def fnk(it, k, semof=semof, j=j, mask=mask, tm=topmask(f'{target}3')):
                        p = semof({**k, 'cj': k['src']})
                        if p is None: return None
                        d = digits(p[1] & MASK, 5)[j]
                        return [(0, ('SET', ((d & tm) if mask else d, 0)))]
                    R1.append(DA(f'{target}{j}<-C', [dict(src=self.c(f'CJ{j}'), targets=[tgt], gates={x: y for x, y in gates(j).items() if x != 'cj'})],
                                 {'src': dkey(lambda p, j=j: digits(p[1] & MASK, 5)[j]), 'zj': gkeys['zj'], 'okj': gkeys['okj']}, fnk))
                continue
            terms = sorted(gk, key=lambda t: t[1] != target)     # a self-term must be read before it is overwritten
            neg = sum(1 for sg, _ in terms if sg < 0)
            carry = len(terms) > 1 or neg > 0 or any(p[1] for p in mem.values())
            any_carry |= carry
            def kd(p, j, neg=neg): return digits((p[1] + neg) & MASK, 5)[j]
            (sa, ra) = terms[0]
            for j in range(tw):
                tgt = self.c(f'{target}{j}')
                mask = tw == 4 and j == 3 and not carry
                def setop(raw, mask=mask, tm=topmask(f'{target}3')): return ('SET', ((raw % 16) & tm, 0) if mask else (raw % 16, raw // 16))
                if j < width(ra) and self.before(f'{regcell(ra)}{j}', f'{target}{j}') or ra == target:
                    def fn(it, k, semof=semof, j=j, sa=sa, setop=setop, kd=kd, ra=ra):
                        p = semof(k)
                        if p is None: return None
                        a = srcdigit(ra, j, k['src']) if sa > 0 else 15 - k['src']
                        return [(0, setop(a + kd(p, j)))]
                    R1.append(DA(f'{target}{j}<-{ra}', [dict(src=self.c(f'{regcell(ra)}{j}'), targets=[tgt], gates=gates(j))],
                                 {'src': lambda v: v[0], **gk_(lambda p, j=j, kd=kd: kd(p, j))}, fn))
                elif j < width(ra):
                    # source sits after the target: backtrack-style copy (16 rules, gated by the local control copy)
                    assert len(terms) == 1 and sa > 0 and ra != 'SIM', (target, gk)
                    def fna(cell, k, semof=semof, j=j, setop=setop, kd=kd):
                        p = semof(k)
                        if p is None: return None
                        return setop(k['src'] + kd(p, j))[1]
                    R1.append(A(f'{target}{j}<-{ra}(la)', [tgt], (lambda g, s_: lambda c: {**g, 'src': s_})(gates(j), self.c(f'{ra}{j}')),
                                {'src': lambda v: v[0], **gk_(lambda p, j=j, kd=kd: kd(p, j))}, fna))
                else:
                    # narrower operand: the digit is a constant (complemented if negated)
                    if ungated: continue
                    def fnc(it, k, semof=semof, j=j, sa=sa, setop=setop, kd=kd):
                        p = semof({**k, 'cj': k['src']})
                        if p is None: return None
                        return [(0, setop((15 if sa < 0 else 0) + kd(p, j)))]
                    R1.append(DA(f'{target}{j}<-K', [dict(src=self.c(f'CJ{j}'), targets=[tgt], gates={x: y for x, y in gates(j).items() if x != 'cj'})],
                                 {'src': dkey(lambda p, j=j, kd=kd: kd(p, j)), 'zj': gkeys['zj'], 'okj': gkeys['okj']}, fnc))
                if len(terms) > 1:
                    (sb, rb) = terms[1]
                    if j < width(rb):
                        assert self.before(f'{regcell(rb)}{j}', f'{target}{j}'), (target, rb)
                        def fnb(it, k, semof=semof, sb=sb, rb=rb, j=j):
                            if semof(k) is None: return None
                            b = srcdigit(rb, j, k['src']) if sb > 0 else 15 - k['src']
                            return [(0, ('ADD', b))] if b else None
                        R2.append(DA(f'{target}{j}+={rb}', [dict(src=self.c(f'{regcell(rb)}{j}'), targets=[tgt], gates=gates(j))],
                                     {'src': lambda v: v[0], **gk_(lambda p: 0)}, fnb))
                    elif sb < 0 and not ungated:
                        R2.append(DA(f'{target}{j}+=15', [dict(src=self.c(f'CJ{j}'), targets=[tgt], gates={x: y for x, y in gates(j).items() if x != 'cj'})],
                                     {'src': dkey(lambda p: 0), 'zj': gkeys['zj'], 'okj': gkeys['okj']},
                                     lambda it, k, semof=semof: [(0, ('ADD', 15))] if semof({**k, 'cj': k['src']}) else None))
        marks.append((len(R1), len(R2)))
        if merge:
            R1 = [x for i in range(len(marks) - 1) for x in self.merge_digits(target, R1[marks[i][0]:marks[i + 1][0]])]
            R2 = [x for i in range(len(marks) - 1) for x in self.merge_digits(target, R2[marks[i][1]:marks[i + 1][1]])]
        if any_carry:
            for j in range(1, tw):
                top = tw == 4 and j == 3
                R3.append(A(f'{target}{j}.carry', [self.c(f'{target}{j}')], (lambda pc: lambda c: {'cy': pc})(self.c(f'{target}{j-1}')),
                            {'cy': lambda v: v[1]},
                            (lambda top: lambda cell, k: Op('ADDM', k['cy']) if top else (Op('ADD', k['cy']) if k['cy'] else None))(top)))
        return R1, R2, R3

    def merge_digits(self, target, specs):
        """One dispatch spec per expression group instead of one per digit: the digits' rules start at different glyph types,
        so they share a subtable (the subtable count per cycle is capped: S x subtables <= 16,384)."""
        out, by = [], {}
        for s_ in specs:
            m = re.fullmatch(re.escape(target) + r'(\d)(<-.*|\+=.*)', s_.name)
            if not isinstance(s_, DA) or not m: out.append(s_); continue
            key = m.group(2)
            if key not in by:
                by[key] = DA(target + key, [], {r: {} for r in s_.keys}, lambda it, k: it['fn'](it, k)); out.append(by[key])
            for it in s_.items:
                cells = {'src': [it['src']], 'tgt': it['targets'], **{r: [c] for r, c in it['gates'].items()}}
                for r, f in s_.keys.items():
                    for c in cells.get(r, []): by[key].keys[r][c.type.name] = f
            by[key].items += [dict(it, fn=s_.fn) for it in s_.items]
        return out

    def split_stage(self, name, specs, group=None):
        """One lookup per group of specs (group(spec) -> key; default: one per spec). A lookup with many
        heterogeneous subtables costs more than the sum of narrow ones: every glyph in its coverage scans every
        subtable digest, and the wider mark-filter view lengthens context walks."""
        import os
        if os.environ.get('PROFSPLIT'): group = None
        if os.environ.get('NOSPLIT'): group = lambda s_: 'all'
        gs = {}
        for s_ in specs: gs.setdefault(group(s_) if group else s_.name, []).append(s_)
        for k, v in gs.items(): self.P.stage(f'{name}:{k}', v)

    def stage3(self, name, parts):
        for i, p in enumerate(parts):
            if p: self.P.stage(f'{name}.{i+1}', p)

    # ------------------------------------------------------------ the cycle
    def stages(self):
        P, C, N, core, L = self.P, self.c('C'), self.N, self.core, self.lines
        uc = {(n, u): cyc for n in OPN for u, cyc in enumerate(UCODE[n])}
        last = {cv: cv[1] == len(UCODE[cv[0]]) - 1 for cv in uc}
        rom = self.image['rom']
        pcd = self.reg('PC')
        start = lambda v: v == ('S',)
        # ---- K0: composite PC glyph, then one dispatch sets op and imm from the ROM
        # P2: a PC digit 2 at or past the ROM's size (ROM // 256 pages) is RAM, like any nonzero digit 3
        for name, role, f in [('P0', 0, lambda k: Op('PSET', k['pc'])), ('P1', 1, lambda k: Op('P16', k['pc']) if k['pc'] else None),
                              ('P2', 2, lambda k: (Op('P256', k['pc']) if k['pc'] < ROM // 256 else Op('PRAM')) if k['pc'] else None)]:
            P.stage(f'K0 {name}', [A(name, [core['P']], (lambda r: lambda c: {'c': C, 'pc': pcd[r]})(role),
                                     {'c': start, 'pc': lambda v: v[0]}, (lambda f: lambda cell, k: f(k) if k['c'] else None)(f))])
        P.stage('K0 P3', [A('P3', [core['P']], lambda c: {'c': C, 'pc': pcd[3]}, {'c': start, 'pc': lambda v: v[0] != 0},
                            lambda cell, k: Op('PRAM') if k['c'] and k['pc'] else None)])
        def pkey(v):
            if v == 'RAM': return 'RAM'
            return rom[v] if v < len(rom) else None
        def lut(it, k):
            if k['tgts'][0] is not True: return None
            w = k['src']
            if w is None: return None
            if w == 'RAM': return [(0, ('SET', ('F', 0)))]
            imm = w % 8192
            return [(0, ('SET', (OPN[w // 8192], 0)))] + [(1 + j, ('SET', (d, 0))) for j, d in enumerate(digits(imm, 4))]
        P.stage('K0 lut', [DA('LUT', [dict(src=core['P'], targets=[C] + self.reg('IMM'), gates={})],
                               {'src': pkey, 'tgt': lambda v: v == ('S',) if isinstance(v, tuple) and isinstance(v[0], str) else None}, lut)])
        # ---- K1: D = T2-T1, zero/sign flags, BF, local control copies, MOP
        P.stage('K1 init', [MAP('finit', [P.types[n] for n in ['ZT1', 'ZT2', 'ZD', 'SD', 'ST2', 'ZSEL']], lambda t, v: 0 if t.name in ('SD', 'ST2', 'ZSEL') else 1)])
        self.stage3('K1 D', self.lin('D', {('*', None): 'T2-T1'}))
        for flag, r in [('ZT1', 'T1'), ('ZT2', 'T2'), ('ZD', 'D')]:
            P.stage(f'K1 {flag}', [DA(flag, [dict(src=core[f'{r}{j}'], targets=[core[flag]], gates={}) for j in range(5)],
                                      {'src': lambda v: v[0] != 0}, lambda it, k: [(0, ('SET', 0))] if k['src'] else None)])
        # SD: T2 < T1, exactly. The sign of the 20-bit difference D = T2 - T1 overflows when the operands' signs differ, and
        # then T2 < T1 just when T2 is the negative one (LT GT LE GE and the 'sd' selector compare exactly, as uarch.py does)
        P.stage('K1 SD', [A('SD', [core['SD']], lambda c: {'d': core['D4'], 'a': core['T14'], 'b': core['T24']},
                            {'d': lambda v: v[0] >= 8, 'a': lambda v: v[0] >= 8, 'b': lambda v: v[0] >= 8},
                            lambda cell, k: (1 if (k['b'] if k['a'] != k['b'] else k['d']) else None))])
        P.stage('K1 ST2', [DA('ST2', [dict(src=core['T24'], targets=[core['ST2']], gates={})], {'src': lambda v: v[0] >= 8},
                              lambda it, k: [(0, ('SET', 1))] if k['src'] else None)])
        # ZSEL: the gate the cycle's choices use (uarch.SEL): Z(T1) by default (JZ / JNZ), else the cycle's selector. One small
        # rule set per selector, each with only the flags it reads (ZSEL is 0 from K1 init)
        selof = {cv: cyc.get('sel', 'z1') for cv, cyc in uc.items()}
        def zrule(name, flags, f):
            ctx = {'c': C, **{x: core[x] for x in flags}}
            return A(f'ZSEL.{name}', [core['ZSEL']], lambda cell, ctx=ctx: ctx,
                     {'c': lambda v, name=name: name if selof.get(v) == name else None, **{x: (lambda v: v) for x in flags}},
                     lambda cell, k, name=name, f=f: (f(k) or None) if k['c'] == name else None)
        P.stage('K1 zsel', [zrule('z1', ['ZT1'], lambda k: k['ZT1']),
                            zrule('scan', ['ZD', 'ZT2', 'ST2'], lambda k: 1 if (k['ZD'] or k['ZT2']) else 2 if k['ST2'] else 0),
                            zrule('nst2', ['ST2'], lambda k: 1 - k['ST2']), zrule('nzt2', ['ZT2'], lambda k: 1 - k['ZT2']),
                            zrule('sd', ['SD'], lambda k: k['SD'])])
        assert set(selof.values()) <= {'z1', 'scan', 'nst2', 'nzt2', 'sd'} and set(SEL) == {'scan', 'nst2', 'nzt2', 'sd'}
        ctlmop = {}
        for cv, cyc in uc.items():
            m = cyc.get('mem'); ctlmop[cv] = ('R' if m[0] == 'R' else 'W' + ('?' if cyc.get('ext') else '')) if m else 'N'
        ctlmop[('F', 0)] = 'R'
        def mopf(cell, k):
            m = k['c']
            if m == 'W?': return 'W' if k['resv'] else 'N'
            return m
        P.stage('K1 small', [
            A('BF', [core['BF']], lambda c: {'sd': core['SD'], 'zd': core['ZD'], 'z1': core['ZT1'], 'z2': core['ZT2']},
              {'sd': lambda v: v, 'zd': lambda v: v, 'z1': lambda v: v, 'z2': lambda v: v},
              lambda cell, k: 8 * k['sd'] + 4 * k['zd'] + 2 * k['z1'] + k['z2']),
            *[A(f'ZJ{j}', [core[f'ZJ{j}']], lambda c: {'z': core['ZSEL']}, {'z': lambda v: v}, lambda cell, k: k['z']) for j in range(5)],
            A('MOP', [core['MOP']], lambda c: {'c': C, 'resv': core['RESV']}, {'c': lambda v: ctlmop.get(v, 'N'), 'resv': lambda v: v}, mopf)])
        P.stage('K1 cj', [DA('CJ', [dict(src=C, targets=[core[f'CJ{j}'] for j in range(5)], gates={})], {'src': lambda v: v},
                             lambda it, k: [(j, ('SET', k['src'])) for j in range(5)])])
        # ---- K2: address and write data
        mar, mdw = {}, {}
        for cv, cyc in uc.items():
            m = cyc.get('mem')
            if m:
                mar.update(choices_of(cv, m[1]))
                if m[0] == 'W': mdw.update(choices_of(cv, m[2]))
        mar[(('F', 0), None)] = 'PC'
        self.stage3('K2 MAR', self.lin('MAR', mar, merge=True))
        self.stage3('K2 MDW', self.lin('MDW', mdw, merge=True))
        # ---- K3: memory (ring cache)
        Lt = lambda f: P.types[f'L.{f}']
        P.stage('K3 init', [MAP('minit', [Lt(f) for f in [f'G{b}' for b in range(20)] + ['GH', 'GF', 'VS', 'WH', 'WE', 'GS0']] +
                                [P.types[f'MDRB{b}'] for b in range(20)] + [P.types[n] for n in ['HIT', 'FAIL', 'VANY']] +
                                [P.types[f'MDR{j}'] for j in range(5)], lambda t, v: t.values[0])])
        def bcast(name, src, field, val):
            return DA(name, [dict(src=src, targets=[ln[field] for ln in L], gates={})], {'src': lambda v: v},
                      lambda it, k: [(i, ('SET', val(k['src']))) for i in range(N)])
        # one lookup per broadcast: a match consumes its whole input sequence, and contexts are capped at 64 glyphs
        assert N <= 63
        P.stage('K3 busOP', [bcast('BOPb', core['MOP'], 'BOP', lambda v: v)])
        for j in range(4): P.stage(f'K3 busA{j}', [bcast(f'BA{j}b', core[f'MAR{j}'], f'BA{j}', lambda v: (v[0], 0))])
        for j in range(5): P.stage(f'K3 busD{j}', [bcast(f'BD{j}b', core[f'MDW{j}'], f'BD{j}', lambda v: (v[0], 0))])
        # tag compare: TAG0 holds address bits 2-3, so it is compared with BA0 >> 2; BA_j becomes (d, 1) while the prefix matches
        eq = []
        for j in range(4):
            eq.append(A(f'EQ{j}', [ln[f'BA{j}'] for ln in L],
                        (lambda j: lambda cell: {'self': cell, 'tag': L[cell.line][f'TAG{j}'], 'ch': L[cell.line]['VD' if j == 0 else f'BA{j-1}']})(j),
                        {'self': lambda v: v[0], 'tag': lambda v: v[0], 'ch': (lambda j: (lambda v: v != 0) if j == 0 else (lambda v: v[1] == 1))(j)},
                        (lambda j: lambda cell, k: (k['self'], 1) if k['ch'] and k['tag'] == (k['self'] >> 2 if j == 0 else k['self']) else None)(j)))
        P.stage('K3 eq', eq)
        # WH (init 0): this line answers the access. Write: block present. Read: block present and the word valid.
        P.stage('K3 wh', [A('WHw', [ln['WH'] for ln in L], lambda cell: {'op': L[cell.line]['BOP'], 'h': L[cell.line]['BA3']},
                            {'op': lambda v: v == 'W', 'h': lambda v: v[1]}, lambda cell, k: 1 if k['op'] and k['h'] else None)] +
                          [A(f'WHr{w}', [ln['WH'] for ln in L],
                             (lambda w: lambda cell: {'op': L[cell.line]['BOP'], 'sel': L[cell.line]['BA0'], 'h': L[cell.line]['BA3'], 'ws': L[cell.line][f'WS{w}']})(w),
                             {'op': lambda v: v == 'R', 'sel': (lambda w: lambda v: (v[0] & 3) == w)(w), 'h': lambda v: v[1], 'ws': lambda v: v != 0},
                             lambda cell, k: 1 if k['op'] and k['sel'] and k['h'] and k['ws'] else None) for w in range(WB)])
        nx = lambda cell, f: (L[0] if cell.region == 'core' else L[cell.line + 1])[f]
        P.stage('K3 any', [
            RA('GHsrc', [ln['GH'] for ln in L], lambda cell: [(L[cell.line]['WH'], lambda v: v == 1)], lambda cell, v: 1),
            RA('GHpass', [ln['GH'] for ln in L[:N - 1]] + [core['HIT']], lambda cell: [(nx(cell, 'GH'), lambda v: v == 1)], lambda cell, v: 1),
            RA('VSsrc', [ln['VS'] for ln in L], lambda cell: [(L[cell.line]['VF'], lambda v: v == 1)], lambda cell, v: 1),
            RA('VSpass', [ln['VS'] for ln in L[:N - 1]] + [core['VANY']], lambda cell: [(nx(cell, 'VS'), lambda v: v == 1)], lambda cell, v: 1)])
        P.stage('K3 decide', [
            A('MBC', [core['MBC']], lambda c: {'m': core['MOP'], 'h': core['HIT'], 'v': core['VANY']}, {'m': lambda v: v == 'W', 'h': lambda v: v, 'v': lambda v: v},
              lambda cell, k: int(k['m'] and not k['h'] and k['v'])),
            A('FAIL0', [core['FAIL0']], lambda c: {'m': core['MOP'], 'h': core['HIT'], 'v': core['VANY']}, {'m': lambda v: v == 'W', 'h': lambda v: v, 'v': lambda v: v},
              lambda cell, k: int(k['m'] and not k['h'] and not k['v']))])
        P.stage('K3 mb', [bcast('MBb', core['MBC'], 'MB', lambda v: v)])
        P.stage('K3 alloc', [
            A('VF', [ln['VF'] for ln in L], lambda cell: {'self': cell, 'mb': L[cell.line]['MB'], 'vd': L[cell.line]['VD']},
              {'self': lambda v: v, 'mb': lambda v: v, 'vd': lambda v: v}, lambda cell, k: 2 if (k['self'] == 1 and k['mb'] and k['vd'] != 2) else None),
            A('GFv', [ln['GF'] for ln in L], lambda cell: {'vf': L[cell.line]['VF'], 'mb': L[cell.line]['MB'], 'vd': L[cell.line]['VD']},
              {'vf': lambda v: v, 'mb': lambda v: v, 'vd': lambda v: v}, lambda cell, k: 1 if (k['vf'] == 1 and k['mb'] and k['vd'] == 2) else None)])
        P.stage('K3 vfmove', [DA('VFmove', [dict(src=L[k]['VF'], targets=[L[k + 1]['VF']], gates={}) for k in range(N - 1)], {'src': lambda v: v},
                                 lambda it, k: [(0, ('SET', 3))] if k['src'] == 2 else None)])
        # WE (init 0) = 1 + word written on this line: the freshly allocated line, or the line holding the block
        P.stage('K3 we', [A('WEa', [ln['WE'] for ln in L], lambda cell: {'vf': L[cell.line]['VF'], 'sel': L[cell.line]['BA0']},
                            {'vf': lambda v: v == 2, 'sel': lambda v: v[0] & 3}, lambda cell, k: 1 + k['sel'] if k['vf'] else None),
                          A('WEh', [ln['WE'] for ln in L], lambda cell: {'op': L[cell.line]['BOP'], 'h': L[cell.line]['BA3'], 'sel': L[cell.line]['BA0']},
                            {'op': lambda v: v == 'W', 'h': lambda v: v[1], 'sel': lambda v: v[0] & 3}, lambda cell, k: 1 + k['sel'] if k['op'] and k['h'] else None)])
        # GS_j (init 0), a per-digit copy of what this line does with the access:
        #   1 read, not this line;  2+w read hit on word w;  6+w write word w;  10+w write word w into a fresh line
        P.stage('K3 gs', [A('GSw', [ln['GS0'] for ln in L], lambda cell: {'we': L[cell.line]['WE'], 'vf': L[cell.line]['VF']},
                            {'we': lambda v: v, 'vf': lambda v: v == 2}, lambda cell, k: (5 + k['we'] + 4 * k['vf']) if k['we'] else None),
                          A('GSr', [ln['GS0'] for ln in L], lambda cell: {'op': L[cell.line]['BOP'], 'h': L[cell.line]['WH'], 'sel': L[cell.line]['BA0']},
                            {'op': lambda v: v == 'R', 'h': lambda v: v, 'sel': lambda v: v[0] & 3},
                            lambda cell, k: (2 + k['sel'] if k['h'] else 1) if k['op'] else None)])
        P.stage('K3 gsc', [DA('GScopy', [dict(src=ln['GS0'], targets=[ln[f'GS{j}'] for j in range(1, 5)], gates={}) for ln in L], {'src': lambda v: v},
                              lambda it, k: [(j, ('SET', k['src'])) for j in range(4)])])
        wrote = lambda g, w: g in (6 + w, 10 + w)
        self.split_stage('K3 write', [
            DA('TAGw', [dict(src=ln[f'BA{j}'], targets=[ln[f'TAG{j}']], gates={'vf': ln['VF']}, j=j) for ln in L for j in range(4)],
               {'src': lambda v: v[0], 'vf': lambda v: v == 2},
               lambda it, k: [(0, ('SET', ((k['src'] >> 2) if it['j'] == 0 else k['src'], 0)))] if k['vf'] else None),
            DA('VALw', [dict(src=ln[f'BD{j}'], targets=[ln[f'VAL{w}_{j}']], gates={'gs': ln[f'GS{j}']}, w=w) for ln in L for j in range(5) for w in range(WB)],
               {'src': lambda v: v[0], 'gs': lambda v: v}, lambda it, k: [(0, ('SET', (k['src'], 0)))] if wrote(k['gs'], it['w']) else None),
            A('VDw', [ln['VD'] for ln in L], lambda cell: {'we': L[cell.line]['WE']}, {'we': lambda v: v != 0}, lambda cell, k: 2 if k['we'] else None),
            *[A(f'WS{w}w', [ln[f'WS{w}'] for ln in L], lambda cell: {'g': L[cell.line]['GS4']}, {'g': lambda v: v},
                (lambda w: lambda cell, k: 2 if wrote(k['g'], w) else (0 if k['g'] >= 10 else None))(w)) for w in range(WB)]])
        ga = []
        for b in range(20):
            j, bit = divmod(b, 4)
            for w in range(WB):
                ga.append(RA(f'Gsrc{b}.{w}', [ln[f'G{b}'] for ln in L],
                             lambda cell, j=j, bit=bit, w=w: [(L[cell.line][f'GS{j}'], lambda v, w=w: v == 2 + w), (L[cell.line][f'VAL{w}_{j}'], lambda v, bit=bit: (v[0] >> bit) & 1)],
                             lambda cell, v: 1))
            ga.append(RA(f'Gpass{b}', [ln[f'G{b}'] for ln in L[:N - 1]],
                         lambda cell, b=b, j=j: [(L[cell.line][f'GS{j}'], lambda v: v == 1), (nx(cell, f'G{b}'), lambda v: v == 1)], lambda cell, v: 1))
            ga.append(RA(f'Gcore{b}', [core[f'MDRB{b}']], lambda cell, b=b: [(core['MOP'], lambda v: v == 'R'), (L[0][f'G{b}'], lambda v: v == 1)], lambda cell, v: 1))
        ga.append(RA('GFpass', [ln['GF'] for ln in L[:N - 1]], lambda cell: [(L[cell.line]['BOP'], lambda v: v == 'W'), (nx(cell, 'GF'), lambda v: v == 1)], lambda cell, v: 1))
        ga.append(RA('GFcore', [core['FAIL']], lambda cell: [(L[0]['GF'], lambda v: v == 1)], lambda cell, v: 1))
        self.split_stage('K3 gather', ga, lambda s_: re.sub(r'^G(src|pass|core)(\d+).*', r'G\2', s_.name))
        # ---- K4: read data bits -> MDR digits (four passes, one per bit position)
        for bit in range(4):
            P.stage(f'K4 mdr{bit}', [DA(f'MDR.b{bit}', [dict(src=core[f'MDRB{4*j+bit}'], targets=[core[f'MDR{j}']], gates={}) for j in range(5)],
                                        {'src': lambda v: v}, (lambda bit: lambda it, k: [(0, ('ADD', 1 << bit))] if k['src'] else None)(bit))])
        # ---- K5: execute
        waitc = {cv for cv, cyc in uc.items() if cyc.get('ext') or cyc.get('putc')}
        def ok1(cell, k):
            if k['mop'] == 'R' and not k['hit']: return 'miss'
            if k['mop'] == 'W' and (k['fail'] or k['f0']): return 'wfail'
            return 'ok'
        P.stage('K5 ok1', [A('OK1', [core['OK1']], lambda c: {'mop': core['MOP'], 'hit': core['HIT'], 'fail': core['FAIL'], 'f0': core['FAIL0']},
                             {'mop': lambda v: v, 'hit': lambda v: v, 'fail': lambda v: v, 'f0': lambda v: v}, ok1)])
        P.stage('K5 ok', [A('OK', [core['OK']], lambda c: {'o': core['OK1'], 'c': C, 'resv': core['RESV']},
                            {'o': lambda v: v, 'c': lambda v: v in waitc, 'resv': lambda v: v},
                            lambda cell, k: 'wait' if (k['o'] == 'ok' and k['c'] and not k['resv']) else k['o'])])
        P.stage('K5 okj', [A(f'OKJ{j}', [core[f'OKJ{j}']], lambda c: {'o': core['OK']}, {'o': lambda v: v}, lambda cell, k: k['o']) for j in range(5)])
        loads, loadsx = [], []
        for tr in ['T1', 'T2', 'T3']:
            # loads from MDR, and plain copies of another register (SCANI: T1 := IMM) in a lookup of their own: a rule consumes
            # its input span (MDR_j .. T3_j covers IMM_j and T1_j), so two loads in one cycle cannot share a lookup
            for src, out in (('MDR', loads), (None, loadsx)):
                ch = {(cv, None): e for cv, cyc in uc.items() for t_, e in cyc.get('t', {}).items() if t_ == tr and (e == 'MDR') == (src == 'MDR')}
                if not ch: continue
                r1, r2, r3 = self.lin(tr, ch)
                assert not r2 and not r3, ('a temp load must be a plain copy', tr)
                out += r1
        loads += self.lin('IMM', {(('F', 0), None): 'MDR'}, commit=True)[0]
        P.stage('K5 loads', loads)
        if loadsx: P.stage('K5 loadsx', loadsx)
        commit = {cv: cyc.get('commit', {}) for cv, cyc in uc.items() if last[cv]}
        def chooser(reg, pred):
            out = {}
            for cv, cm in commit.items():
                if reg not in cm or not pred(str(cm[reg])): continue
                e = cm[reg]
                if isinstance(e, dict): out.update(choices_of(cv, e)); continue
                m = re.fullmatch(r'Z\(T1\)\?(.*):(.*)', e)
                if m: out[(cv, 1)] = m.group(1); out[(cv, 0)] = m.group(2)
                else: out[(cv, None)] = e
            return out
        self.stage3('K5 spE', self.lin('SP', chooser('SP', lambda e: 'FP' in e), commit=True))
        P.stage('K5 spE.norm', [MAP('spnorm', [P.types[f'SP{j}'] for j in range(4)], lambda t, v: ((v[0] & topmask('SP3')) if t.name == 'SP3' else v[0], 0))])
        P.stage('K5 fp', self.lin('FP', chooser('FP', lambda e: True), commit=True)[0])
        r_sp = self.lin('SP', chooser('SP', lambda e: 'FP' not in e), commit=True)
        r_pc = self.lin('PC', chooser('PC', lambda e: True), commit=True)
        self.split_stage('K5 sppc.1', r_sp[0] + r_pc[0]); P.stage('K5 sppc.2', r_sp[1] + r_pc[1]); P.stage('K5 sppc.3', r_sp[2] + r_pc[2])
        P.stage('K5 resv', [A('RESV', [core['RESV']], lambda c: {'c': C, 'ok': core['OK']}, {'c': lambda v: v in waitc, 'ok': lambda v: v},
                              lambda cell, k: 0 if k['c'] and k['ok'] == 'ok' else None)])
        def next_c(cell, k):
            cv, ok = k['self'], k['ok']
            if cv[0] in ('S', 'T', 'F'): return None
            cyc = uc[cv]
            if cyc.get('halt'): return ('T', 'HALT')
            if ok == 'miss': return ('T', 'MISS')
            if ok == 'wfail': return ('T', 'WFAIL')
            if ok == 'wait': return ('T', 'EXT_' + cyc['ext']) if cyc.get('ext') else ('T', 'PUTC')
            return ('S',) if last[cv] else (cv[0], cv[1] + 1)
        def fetch_c(cell, k):
            if k['self'] != ('F', 0): return None
            if k['ok'] == 'miss': return ('T', 'MISS')
            op = (k['m3'] >> 1) + 8 * k['m4']
            return (OPN[op], 0) if op < len(OPN) else ('T', 'HALT')
        P.stage('K5 count', [A('NI', [core['NI']], lambda c: {'self': core['NI'], 'c': C, 'ok': core['OK']},
                               {'self': lambda v: v, 'c': lambda v: last.get(v, False) and not uc[v].get('halt'), 'ok': lambda v: v == 'ok'},
                               lambda cell, k: k['self'] + 1 if (k['c'] and k['ok'] and k['self'] < 63) else None)])
        P.stage('K5 next', [A('Cnext', [C], lambda c: {'self': C, 'ok': core['OK']}, {'self': lambda v: v, 'ok': lambda v: v}, next_c),
                            A('Cfetch', [C], lambda c: {'self': C, 'ok': core['OK'], 'm3': core['MDR3'], 'm4': core['MDR4']},
                              {'self': lambda v: v if v == ('F', 0) else None, 'ok': lambda v: v, 'm3': lambda v: v[0], 'm4': lambda v: v[0]}, fetch_c)])
        norm = [P.types[f'{r}{j}'] for r in BLOCK for j in range(width(r))]
        def normf(t, v):
            d = v[0] & topmask(t.name) if t.name in self.top13 else v[0]
            return (d, 0)
        P.stage('K5 norm', [MAP('norm', norm, normf), ])
        P.stage('K5 vf', [MAP('vfclr', [Lt('VF')], lambda t, v: {2: 0, 3: 1}.get(v, v))])

    def io_stages(self):
        P, core = self.P, self.core
        pro = []
        for h, r in [('HPC', 'PC'), ('HSP', 'SP'), ('HFP', 'FP'), ('HRES', 'RES')]:
            for j in range(width(r)):
                pro.append(A(f'{r}{j}<-{h}', [core[f'{r}{j}']], (lambda s_: lambda c: {'h': s_})(core[f'{h}{j}']), {'h': lambda v: v[0]},
                             lambda cell, k: (k['h'], 0)))
        P.pre('prologue', pro)
        epi = []
        for h, r in [('HPC', 'PC'), ('HSP', 'SP'), ('HFP', 'FP'), ('HMAR', 'MAR'), ('HT1', 'T1'), ('HT2', 'T2')]:
            for j in range(width(r)):
                epi.append(A(f'{h}{j}<-{r}', [core[f'{h}{j}']], (lambda s_: lambda c: {'r': s_})(core[f'{r}{j}']), {'r': lambda v: v[0]},
                             lambda cell, k: (k['r'], 0)))
        P.post('epilogue', epi)
        tw = self.twin
        self.export = ('export', [MAP('export', [P.types[tn] for tn in tw], lambda t, v: ('@', tw[t.name], v))])

    def advances(self):
        adv = {}
        for tn, t in self.twin.items():
            for v in t.values: adv[t.g(v)] = self.weights[tn](v)
        return adv

    def span_values(self, gids, adv):
        out = {}
        pos = {c.pos: i for i, c in enumerate(self.P.cells)}
        for name, cells in self.spans:
            out[name] = sum(adv.get(gids[pos[c.pos]], 0) for c in cells)
        return out

    # ------------------------------------------------------------ state <-> glyph string
    def encode(self, st):
        P = self.P
        val = {c.pos: c.type.values[0] for c in P.cells}
        def sethdr(h, v, w):
            for j, d in enumerate(digits(v, w)): val[self.core[f'{h}{j}'].pos] = (d, 0)
        val[self.core['C'].pos] = ('S',)
        val[self.core['RESV'].pos] = st['resv']
        sethdr('HPC', st['pc'], 4); sethdr('HSP', st['sp'], 4); sethdr('HFP', st['fp'], 4); sethdr('HRES', st['res'], 5)
        for k, (ln, cl) in enumerate(zip(st['lines'], self.lines)):
            if ln:
                b, vs, ds = ln
                val[cl['VD'].pos] = 2 if any(ds) else 1
                for j, dd in enumerate([b & 3, (b >> 2) & 15, (b >> 6) & 15, (b >> 10) & 15]): val[cl[f'TAG{j}'].pos] = (dd, 0)
                for w in range(WB):
                    val[cl[f'WS{w}'].pos] = 2 if ds[w] else (1 if vs[w] is not None else 0)
                    if vs[w] is not None:
                        for j, dd in enumerate(digits(vs[w], 5)): val[cl[f'VAL{w}_{j}'].pos] = (dd, 0)
            if st['vp'] == k: val[cl['VF'].pos] = 1
        return [c.type.g(val[c.pos]) for c in P.cells]

    def decode_spans(self, sv):
        """State from span widths (what the CSS side sees)."""
        cr = sv['CR']; C = CVALS[cr % 256]; resv = cr // 256
        def s(x, bits=20): return x - (1 << bits) if x >= 1 << (bits - 1) else x
        lines, vp = [], None
        for k in range(self.N):
            a = sv[f'L{k}A']; tag = a % 8192; vf = a // 8192
            sp = [sv[f'L{k}V{i}'] for i in range(7)]
            nib = []
            for i in range(20): nib.append((sp[i // 3] >> (4 * (i % 3))) & 15)
            st6 = sp[6] // 256
            ws = [st6 % 3, st6 // 3 % 3, st6 // 9 % 3, st6 // 27 % 3]
            vals = [s(sum(nib[4 * j + w] << (4 * j) for j in range(5))) for w in range(WB)]
            if any(ws): lines.append([tag, [vals[w] if ws[w] else None for w in range(WB)], [int(x == 2) for x in ws]])
            else: lines.append(None)
            if vf: vp = k
        return dict(C=C, resv=resv, ni=sv['NI'], pc=sv['HPC'], sp=sv['HSP'], fp=sv['HFP'], mar=sv['HMAR'],
                    t1=s(sv['HT1lo'] + (sv['HT1hi'] << 12)), t2=s(sv['HT2lo'] + (sv['HT2hi'] << 12)), t3=0, lines=lines, vp=vp)

    def decode(self, gids):
        """State from glyph ids after export (twins)."""
        vals = []
        for g in gids:
            t, v = self.P.by_gid[g]; vals.append(v)
        V = lambda cell: vals[cell.pos]
        def hdr(h, w, signed=False):
            x = sum(V(self.core[f'{h}{j}'])[0] << (4 * j) for j in range(w))
            return s20(x) if signed else x
        def line(cl):
            ws = [V(cl[f'WS{w}']) for w in range(WB)]
            if not any(ws): return None
            t = V(cl['TAG0'])[0] + 4 * V(cl['TAG1'])[0] + 64 * V(cl['TAG2'])[0] + 1024 * V(cl['TAG3'])[0]
            vs = [s20(sum(V(cl[f'VAL{w}_{j}'])[0] << (4 * j) for j in range(5))) if ws[w] else None for w in range(WB)]
            return [t, vs, [int(x == 2) for x in ws]]
        vp = next((k for k, cl in enumerate(self.lines) if V(cl['VF']) == 1), None)
        return dict(C=V(self.core['C']), ni=V(self.core['NI']), pc=hdr('HPC', 4), sp=hdr('HSP', 4), fp=hdr('HFP', 4), resv=V(self.core['RESV']),
                    mar=hdr('HMAR', 4), t1=hdr('HT1', 5, True), t2=hdr('HT2', 5, True), t3=0,
                    lines=[line(cl) for cl in self.lines], vp=vp)
