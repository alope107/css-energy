#!/usr/bin/env python3
"""cpu.py — the font CPU: glyph types, string layout, and per-cycle stages (semantics = uarch.py).

Layout:  [core] [E: evict buffer] [L1 .. LN: FIFO cache, L1 oldest] [IN: allocation staging]
Every line (E, L, IN) has the same fields:
  VD(0 invalid,1 clean,2 dirty) TAG0-3 VAL0-4 | BA0-3 BD0-4 BOP (request bus) | SH (shift) | G0-19 GH GF (gather)
"""
import re, json, sys
from cpugen import Program, A, RA, MAP
from uarch import OPN, UCODE, ROM, MASK, s20

D16 = [(d, 0) for d in range(16)]
D48 = [(d, c) for c in range(3) for d in range(16)]      # index c*16+d, so (d,0) has index d everywhere
BAV = [(d, e) for e in (0, 1) for d in range(16)]
BIT = [0, 1]
CMPV = ['lt', 'eq', 'gt']
BOPV = [(op, s, v, f) for op in 'NRW' for s in (0, 1) for v in (0, 1) for f in (0, 1)]
EXTOPS = ['MUL', 'DIV', 'MOD', 'SHL13']
CVALS = [('S',), ('F', 0)] + [(n, u) for n in OPN for u in range(len(UCODE[n]))] + \
        [('T', k) for k in ['MISS', 'WFAIL', 'PUTC', 'HALT'] + ['EXT_' + e for e in EXTOPS]]
REG13 = ['PC', 'SP', 'FP', 'IMM', 'MAR']
REG20 = ['T1', 'T2', 'T3', 'RES', 'MDW', 'D', 'MDR']
def width(r): return 4 if r in REG13 else 5
LINEF = (['VD'] + [f'TAG{j}' for j in range(4)] + [f'VAL{j}' for j in range(5)] + [f'BA{j}' for j in range(4)] +
         [f'BD{j}' for j in range(5)] + ['BOP', 'SH'] + [f'G{b}' for b in range(20)] + ['GH', 'GF'])
FAMS = ['E', 'L', 'I']

def digits(v, n): v &= (1 << (4 * n)) - 1; return [(v >> (4 * j)) & 15 for j in range(n)]

class CPU:
    def __init__(self, image, N=32):
        self.image, self.N = image, N
        self.outbase = image['outBase']
        P = self.P = Program()
        t = P.T
        # ---- core types (order of creation = gid order only; layout order below)
        t('C', CVALS); t('RESV', BIT)
        for r in REG13 + REG20:
            for j in range(width(r)): t(f'{r}{j}', D48)
        for f in ['ZT1', 'ZT2', 'ZD', 'SD', 'VDL', 'EFREE', 'HIT', 'FAIL']: t(f, BIT)
        for j in range(4): t(f'CMS{j}', CMPV); t(f'CMO{j}', CMPV)
        t('MOP', ['N', 'R', 'W']); t('OK', ['ok', 'miss', 'wfail', 'wait'])
        for b in range(20): t(f'MDRB{b}', BIT)
        for fam in FAMS:
            for f in LINEF:
                vals = {'VD': [0, 1, 2], 'BOP': BOPV, 'SH': [0, 1, 2]}.get(f)
                if vals is None:
                    vals = BAV if f.startswith('BA') else BIT if f[0] == 'G' else D16
                t(f'{fam}.{f}', vals)
        # ---- layout
        self.core = {}
        order = (['C', 'RESV'] + [f'{r}{j}' for r in ['PC', 'SP', 'FP', 'IMM', 'T1', 'T2', 'T3', 'RES', 'D'] for j in range(width(r))] +
                 ['ZT1', 'ZT2', 'ZD', 'SD'] + [f'CMS{j}' for j in range(4)] + [f'CMO{j}' for j in range(4)] + ['VDL', 'EFREE'] +
                 [f'MAR{j}' for j in range(4)] + [f'MDW{j}' for j in range(5)] + ['MOP'] +
                 [f'MDRB{b}' for b in range(20)] + ['HIT', 'FAIL'] + [f'MDR{j}' for j in range(5)] + ['OK'])
        assert len(order) == len(set(order))
        for n in order: self.core[n] = P.cell(P.types[n], 'core', None, n)
        self.lines = []
        for k in range(N + 2):
            fam = 'E' if k == 0 else 'I' if k == N + 1 else 'L'
            self.lines.append({f: P.cell(P.types[f'{fam}.{f}'], fam, k, f) for f in LINEF})
        self.E, self.IN = self.lines[0], self.lines[N + 1]
        self.Ls = self.lines[1:N + 1]
        self.stages()

    # ------------------------------------------------------------ helpers
    def c(self, n): return self.core[n]
    def reg(self, r): return [self.core[f'{r}{j}'] for j in range(width(r))]

    def lin_specs(self, target, choices, gate=None):
        """target register := linear expr chosen by C. choices: C value -> expr string.
        gate: None (any) or 'commit' (needs OK=='ok'). Returns list of A specs (one per operand-group x digit)."""
        tw = width(target)
        groups = {}
        for cv, e in choices.items():
            terms, K, special = parse(e)
            key = ('S', special) if special else tuple(sorted(terms))
            groups.setdefault(key, {})[cv] = (terms, K, special)
        ungated = list(choices) == ['*']
        specs = []
        for gk, members in groups.items():
            for j in range(tw):
                tc = self.core[f'{target}{j}']
                res = {} if ungated else {'C': self.c('C')}
                # control values with identical semantics share a key (fewer rules)
                canon = {}
                for cv_, sem in members.items(): canon.setdefault(repr(sem), cv_)
                ckey = {cv_: canon[repr(sem)] for cv_, sem in members.items()}
                keys = {} if ungated else {'C': (lambda ck: (lambda v: ck.get(v)))(ckey)}
                neg = sum(1 for sg, _ in gk if sg < 0) if not (bool(gk) and gk[0] == 'S') else 0
                need_carry = (bool(gk) and gk[0] == 'S' and gk[1] == 'COND') or (not (bool(gk) and gk[0] == 'S') and
                              (len(gk) > 1 or neg or any(sem[1] for sem in members.values())))
                special = bool(gk) and gk[0] == 'S' and gk[1]
                if gate == 'commit': res['ok'] = self.c('OK'); keys['ok'] = lambda v: v
                if special == 'BOOL':
                    if j == 0:
                        for f in ['SD', 'ZD', 'ZT1', 'ZT2']: res[f] = self.c(f); keys[f] = lambda v: v
                elif special == 'COND':
                    res['imm'] = self.c(f'IMM{j}'); keys['imm'] = lambda v: v[0]
                    res['pc'] = self.c(f'PC{j}'); keys['pc'] = lambda v: v[0]
                    res['z'] = self.c('ZT1'); keys['z'] = lambda v: v
                    if j: res['cy'] = self.core[f'{target}{j-1}']; keys['cy'] = lambda v: v[1]
                else:
                    pass
                if not special or special not in ('BOOL', 'COND'):
                    for si, (sg, r) in enumerate(gk):
                        if j < width(r): res[f'o{si}'] = self.c(f'{r}{j}'); keys[f'o{si}'] = lambda v: v[0]
                    if j and need_carry: res['cy'] = self.core[f'{target}{j-1}']; keys['cy'] = lambda v: v[1]
                fn = self.lin_fn(target, j, tw, gk, members, gate)
                specs.append(A(f'{target}{j}<-{gk}', [tc], (lambda r_: (lambda c: r_))(res), keys, fn))
        return specs

    def lin_fn(self, target, j, tw, gk, members, gate):
        def fn(cell, k):
            cv = k.get('C', '*')
            if cv is None: return None
            if gate == 'commit' and k['ok'] != 'ok': return None
            terms, K, special = members[cv]
            cin = k.get('cy', 0) if j else 0
            if special == 'BOOL':
                if j: return (0, 0)
                sd, zd, z1, z2 = k['SD'], k['ZD'], k['ZT1'], k['ZT2']
                b = {'LT': sd, 'GT': (not sd) and (not zd), 'LE': sd or zd, 'GE': not sd, 'EQ': zd, 'NE': not zd,
                     'AND': (not z2) and (not z1), 'OR': not (z2 and z1), 'Z': z1}[K]
                return (int(bool(b)), 0)
            if special == 'COND':
                pick_imm = (k['z'] == 1) == (K == 'ZIMM')
                if pick_imm: tot = k['imm']; cin = 0
                else: tot = k['pc'] + (1 if j == 0 else 0) + cin
                d, c = tot % 16, tot // 16
                if pick_imm: c = 0
            else:
                neg = sum(1 for sg, _ in gk if sg < 0)
                kd = digits((K + neg) & MASK, 5)[j]
                tot = kd + cin
                for si, (sg, r) in enumerate(gk):
                    if j < width(r):
                        dv = k[f'o{si}']; tot += dv if sg > 0 else 15 - dv
                    elif sg < 0: tot += 15
                d, c = tot % 16, tot // 16
            if j == tw - 1:
                if tw == 4: d &= 1
                c = 0
            return (d, c)
        return fn

    # ------------------------------------------------------------ the cycle
    def stages(self):
        P, C, N = self.P, self.c('C'), self.N
        core = self.core
        uc = {(n, u): cyc for n in OPN for u, cyc in enumerate(UCODE[n])}
        last = {(n, u): u == len(UCODE[n]) - 1 for n in OPN for u in range(len(UCODE[n]))}
        rom = self.image['rom']

        # ---- K0: instruction start: ROM lookup of op and imm, or switch to a RAM fetch cycle
        pcd = self.reg('PC')
        def lut_res(target):
            return {'C': C, **{f'p{j}': pcd[j] for j in range(4)}}
        lutkeys = {'C': lambda v: v == ('S',), **{f'p{j}': (lambda v: v[0]) for j in range(4)}}
        def rom_word(k):
            if not k['C'] or k['p3'] != 0: return None
            pc = k['p0'] + 16 * k['p1'] + 256 * k['p2']
            return rom[pc] if pc < len(rom) else None
        k0a = []
        for j in range(4):
            def fn(cell, k, j=j):
                w = rom_word(k)
                if w is None: return None
                imm = w % 8192; return (digits(imm, 4)[j], 0)
            k0a.append(A(f'IMM{j}<-ROM', [core[f'IMM{j}']], lambda c: lut_res(None), lutkeys, fn))
        P.stage('K0 imm', k0a)
        def fn_c(cell, k):
            w = rom_word(k)
            return None if w is None else (OPN[w // 8192], 0)
        k0b = [A('C<-ROM', [C], lambda c: lut_res(None), lutkeys, fn_c),
               A('C<-FETCH', [C], lambda c: {'C': C, 'p3': pcd[3]}, {'C': lambda v: v == ('S',), 'p3': lambda v: v[0] != 0},
                 lambda cell, k: ('F', 0) if k['C'] and k['p3'] else None)]
        P.stage('K0 op', k0b)

        # ---- K1: flags
        k1 = []
        def ztest(target, src):
            regs = self.reg(src)
            return A(f'{target}', [core[target]], lambda c: {f'd{j}': regs[j] for j in range(5)},
                     {f'd{j}': (lambda v: v[0] == 0) for j in range(5)}, lambda cell, k: int(all(k.values())))
        k1 += self.lin_specs('D', {'*': 'T2-T1'})
        k1 += [ztest('ZT1', 'T1'), ztest('ZT2', 'T2'), ztest('ZD', 'D')]
        k1.append(A('SD', [core['SD']], lambda c: {'d': core['D4']}, {'d': lambda v: v[0] >= 8}, lambda cell, k: int(k['d'])))
        L1 = self.Ls[0]
        ob = digits(self.outbase, 4)
        for j in range(4):
            res = {'tag': L1[f'TAG{j}'], 'sp': core[f'SP{j}']}
            if j: res['prev'] = core[f'CMS{j-1}']
            def fn(cell, k, j=j):
                if k['tag'] < k['sp']: return 'lt'
                if k['tag'] > k['sp']: return 'gt'
                return k['prev'] if j else 'eq'
            k1.append(A(f'CMS{j}', [core[f'CMS{j}']], (lambda r: lambda c: r)(res),
                        {'tag': lambda v: v[0], 'sp': lambda v: v[0], 'prev': lambda v: v}, fn))
            res = {'tag': L1[f'TAG{j}']}
            if j: res['prev'] = core[f'CMO{j-1}']
            def fn(cell, k, j=j):
                if k['tag'] < ob[j]: return 'lt'
                if k['tag'] > ob[j]: return 'gt'
                return k['prev'] if j else 'eq'
            k1.append(A(f'CMO{j}', [core[f'CMO{j}']], (lambda r: lambda c: r)(res), {'tag': lambda v: v[0], 'prev': lambda v: v}, fn))
        k1.append(A('VDL', [core['VDL']], lambda c: {'vd': L1['VD'], 's': core['CMS3'], 'o': core['CMO3']},
                    {'vd': lambda v: v, 's': lambda v: v, 'o': lambda v: v},
                    lambda cell, k: int(k['vd'] == 2 and not (k['s'] in ('eq', 'gt') and k['o'] == 'lt'))))
        k1.append(A('EFREE', [core['EFREE']], lambda c: {'vd': self.E['VD']}, {'vd': lambda v: v}, lambda cell, k: int(k['vd'] == 0)))
        P.stage('K1 flags', k1)

        # ---- K2: address, write data, memory op
        mar, mdw, mop = {}, {}, {}
        for cv, cyc in uc.items():
            m = cyc.get('mem')
            if m:
                mar[cv] = m[1]
                if m[0] == 'W': mdw[cv] = m[2]
        mar[('F', 0)] = 'PC'
        k2 = self.lin_specs('MAR', mar) + self.lin_specs('MDW', mdw)
        def fn_mop(cell, k):
            cv = k['C']; cyc = uc.get(cv)
            if cv == ('F', 0): return 'R'
            if cyc is None or not cyc.get('mem'): return 'N'
            if cyc.get('ext') and not k['resv']: return 'N'
            return cyc['mem'][0]
        k2.append(A('MOP', [core['MOP']], lambda c: {'C': C, 'resv': core['RESV']}, {'C': lambda v: v, 'resv': lambda v: v}, fn_mop))
        P.stage('K2 addr/data', k2)

        # ---- K3: memory
        lines = self.lines
        def prevline(k): return lines[k - 1] if k > 0 else None
        gtypes = [P.types[f'{fam}.{f}'] for fam in FAMS for f in [f'G{b}' for b in range(20)] + ['GH', 'GF']]
        gtypes += [P.types[f'MDRB{b}'] for b in range(20)] + [P.types['HIT'], P.types['FAIL']]
        gtypes += [P.types[f'{fam}.SH'] for fam in FAMS]
        P.stage('K3 gather init', [MAP('ginit', gtypes, lambda t, v: 0)])
        bus = []
        for j in range(4):
            tg = [ln[f'BA{j}'] for ln in lines]
            def res(cell, j=j):
                k = cell.line; ln = lines[k]
                r = {'prev': core[f'MAR{j}'] if k == 0 else lines[k - 1][f'BA{j}'], 'tag': ln[f'TAG{j}'],
                     'chain': ln['VD'] if j == 0 else ln[f'BA{j-1}']}
                return r
            def kprev(v): return v[0]
            def kchain(v, j=j): return (v != 0) if j == 0 else bool(v[1])
            def fn(cell, k, j=j):
                d = k['prev']
                if cell.region == 'core': pass
                return (d, int(k['chain'] and d == k['tag']))
            bus.append(A(f'BA{j}', tg, res, {'prev': kprev, 'tag': lambda v: v[0], 'chain': kchain}, fn))
        for j in range(5):
            tg = [ln[f'BD{j}'] for ln in lines]
            bus.append(A(f'BD{j}', tg, lambda cell, j=j: {'prev': core[f'MDW{j}'] if cell.line == 0 else lines[cell.line - 1][f'BD{j}']},
                         {'prev': lambda v: v[0]}, lambda cell, k: (k['prev'], 0)))
        def bop_res(cell):
            k = cell.line; ln = lines[k]
            if k == 0: return {'mop': core['MOP'], 'vdl': core['VDL'], 'ef': core['EFREE'], 'hit': ln['BA3']}
            return {'prev': lines[k - 1]['BOP'], 'hit': ln['BA3']}
        def bop_fn(cell, k):
            if cell.line == 0: return (k['mop'], k['hit'], k['vdl'], k['ef'])
            op, s, v, f = k['prev']; return (op, int(s or k['hit']), v, f)
        bus.append(A('BOP', [ln['BOP'] for ln in lines], bop_res,
                     {'mop': lambda v: v, 'vdl': lambda v: v, 'ef': lambda v: v, 'hit': lambda v: v[1], 'prev': lambda v: v}, bop_fn))
        P.stage('K3 bus', bus)
        wh = []
        for j in range(5):
            wh.append(A(f'whVAL{j}', [ln[f'VAL{j}'] for ln in lines[:N + 1]],
                        lambda cell, j=j: {'hit': lines[cell.line]['BA3'], 'op': lines[cell.line]['BOP'], 'd': lines[cell.line][f'BD{j}']},
                        {'hit': lambda v: v[1], 'op': lambda v: v[0], 'd': lambda v: v[0]},
                        lambda cell, k: (k['d'], 0) if k['hit'] and k['op'] == 'W' else None))
        wh.append(A('whVD', [ln['VD'] for ln in lines[:N + 1]],
                    lambda cell: {'hit': lines[cell.line]['BA3'], 'op': lines[cell.line]['BOP']},
                    {'hit': lambda v: v[1], 'op': lambda v: v[0]}, lambda cell, k: 2 if k['hit'] and k['op'] == 'W' else None))
        IN = self.IN
        def dec(k):          # IN decision from its BOP: None, 'alloc', 'park', 'fail'
            op, s, v, f = k['b']
            if op != 'W' or s: return None
            if v and not f: return 'fail'
            return 'park' if v else 'alloc'
        bk = {'b': lambda v: v}
        for j in range(4):
            wh.append(A(f'inTAG{j}', [IN[f'TAG{j}']], lambda c, j=j: {'b': IN['BOP'], 'a': IN[f'BA{j}']}, {**bk, 'a': lambda v: v[0]},
                        lambda cell, k: (k['a'], 0) if dec(k) in ('alloc', 'park') else None))
        for j in range(5):
            wh.append(A(f'inVAL{j}', [IN[f'VAL{j}']], lambda c, j=j: {'b': IN['BOP'], 'd': IN[f'BD{j}']}, {**bk, 'd': lambda v: v[0]},
                        lambda cell, k: (k['d'], 0) if dec(k) in ('alloc', 'park') else None))
        wh.append(A('inVD', [IN['VD']], lambda c: {'b': IN['BOP']}, bk, lambda cell, k: 2 if dec(k) in ('alloc', 'park') else None))
        wh.append(A('inSH', [IN['SH']], lambda c: {'b': IN['BOP']}, bk, lambda cell, k: {'alloc': 1, 'park': 2}.get(dec(k))))
        wh.append(A('inGF', [IN['GF']], lambda c: {'b': IN['BOP']}, bk, lambda cell, k: 1 if dec(k) == 'fail' else None))
        P.stage('K3 write/alloc', wh)
        # SH flows left from IN to every line and E
        shc = [RA(f'SH{v}', [ln['SH'] for ln in lines[:N + 1]], (lambda v: lambda cell: [(lines[cell.line + 1]['SH'], lambda x, v=v: x == v)])(v),
                  (lambda v: lambda cell, x: v)(v)) for v in (1, 2)]
        P.stage('K3 shift flag', shc)
        sh = []
        for f in ['VD'] + [f'TAG{j}' for j in range(4)] + [f'VAL{j}' for j in range(5)]:
            sh.append(A(f'sh{f}', [ln[f] for ln in lines[:N + 1]],
                        lambda cell, f=f: {'sh': lines[cell.line]['SH'], 'nx': lines[cell.line + 1][f]},
                        {'sh': lambda v: v, 'nx': lambda v: v},
                        lambda cell, k: k['nx'] if (k['sh'] == 2 if cell.line == 0 else k['sh'] >= 1) else None))
        P.stage('K3 shift', sh)
        P.stage('K3 in clear', [MAP('inclr', [P.types['I.VD'], P.types['I.SH']], lambda t, v: 0)])
        # gather: read data bits, hit and fail flow left to the core
        ga = []
        for b in range(20):
            j, bit = divmod(b, 4)
            ga.append(RA(f'Gsrc{b}', [ln[f'G{b}'] for ln in lines[:N + 1]],
                         lambda cell, j=j, bit=bit: [(lines[cell.line]['BA3'], lambda v: v[1] == 1), (lines[cell.line]['BOP'], lambda v: v[0] == 'R'),
                                                     (lines[cell.line][f'VAL{j}'], lambda v, bit=bit: (v[0] >> bit) & 1)],
                         lambda cell, v: 1))
            ga.append(RA(f'Gpass{b}', [ln[f'G{b}'] for ln in lines[:N + 1]] + [core[f'MDRB{b}']],
                         lambda cell, b=b: [((lines[0] if cell.region == 'core' else lines[cell.line + 1])[f'G{b}'], lambda v: v == 1)],
                         lambda cell, v: 1))
        ga.append(RA('GHsrc', [ln['GH'] for ln in lines[:N + 1]],
                     lambda cell: [(lines[cell.line]['BA3'], lambda v: v[1] == 1), (lines[cell.line]['BOP'], lambda v: v[0] == 'R')], lambda cell, v: 1))
        ga.append(RA('GHpass', [ln['GH'] for ln in lines[:N + 1]] + [core['HIT']],
                     lambda cell: [((lines[0] if cell.region == 'core' else lines[cell.line + 1])['GH'], lambda v: v == 1)], lambda cell, v: 1))
        ga.append(RA('GFpass', [ln['GF'] for ln in lines[:N + 1]] + [core['FAIL']],
                     lambda cell: [((lines[0] if cell.region == 'core' else lines[cell.line + 1])['GF'], lambda v: v == 1)], lambda cell, v: 1))
        P.stage('K3 gather', ga)

        # ---- K4: read data bits -> hex digits
        k4 = []
        for j in range(5):
            k4.append(A(f'MDR{j}', [core[f'MDR{j}']], lambda c, j=j: {f'b{i}': core[f'MDRB{4*j+i}'] for i in range(4)},
                        {f'b{i}': (lambda v: v) for i in range(4)}, lambda cell, k: (k['b0'] + 2 * k['b1'] + 4 * k['b2'] + 8 * k['b3'], 0)))
        P.stage('K4 mdr', k4)

        # ---- K5: execute
        def ok_fn(cell, k):
            if k['mop'] == 'R' and not k['hit']: return 'miss'
            if k['mop'] == 'W' and k['fail']: return 'wfail'
            if k['C'] and not k['resv']: return 'wait'
            return 'ok'
        waitc = {cv for cv, cyc in uc.items() if cyc.get('ext') or cyc.get('putc')}
        P.stage('K5 ok', [A('OK', [core['OK']], lambda c: {'mop': core['MOP'], 'hit': core['HIT'], 'fail': core['FAIL'], 'C': C, 'resv': core['RESV']},
                            {'mop': lambda v: v, 'hit': lambda v: v, 'fail': lambda v: v, 'C': lambda v: v in waitc, 'resv': lambda v: v}, ok_fn)])
        k5b = []
        for tr in ['T1', 'T2', 'T3']:
            ch = {cv: 'MDR' for cv, cyc in uc.items() if tr in cyc.get('t', {})}
            k5b += self.lin_specs(tr, ch)
        fetch = {('F', 0): 'MDR'}
        for j in range(4):
            k5b.append(A(f'IMM{j}<-MDR', [core[f'IMM{j}']], lambda c, j=j: {'C': C, 'ok': core['OK'], 'm': core[f'MDR{j}']},
                         {'C': lambda v: v == ('F', 0), 'ok': lambda v: v, 'm': lambda v: v[0]},
                         lambda cell, k, j=j: ((k['m'] & 1) if j == 3 else k['m'], 0) if k['C'] and k['ok'] == 'ok' else None))
        commit = {cv: cyc.get('commit', {}) for cv, cyc in uc.items() if last[cv]}
        k5b += self.lin_specs('SP', {cv: c_['SP'] for cv, c_ in commit.items() if 'SP' in c_ and 'FP' in c_['SP']}, gate='commit')
        P.stage('K5 temps', k5b)
        P.stage('K5 fp', self.lin_specs('FP', {cv: c_['FP'] for cv, c_ in commit.items() if 'FP' in c_}, gate='commit'))
        k5d = self.lin_specs('SP', {cv: c_['SP'] for cv, c_ in commit.items() if 'SP' in c_ and 'FP' not in c_['SP']}, gate='commit')
        k5d += self.lin_specs('PC', {cv: c_['PC'] for cv, c_ in commit.items() if 'PC' in c_}, gate='commit')
        k5d.append(A('RESV', [core['RESV']], lambda c: {'C': C, 'ok': core['OK']}, {'C': lambda v: v in waitc, 'ok': lambda v: v},
                     lambda cell, k: 0 if k['C'] and k['ok'] == 'ok' else None))
        P.stage('K5 sp/pc', k5d)
        def next_c(cell, k):
            cv, ok = k['C'], k['ok']
            if cv[0] in ('S', 'T', 'F'): return None
            cyc = uc[cv]
            if cyc.get('halt'): return ('T', 'HALT')
            if ok == 'miss': return ('T', 'MISS')
            if ok == 'wfail': return ('T', 'WFAIL')
            if ok == 'wait': return ('T', 'EXT_' + cyc['ext']) if cyc.get('ext') else ('T', 'PUTC')
            return ('S',) if last[cv] else (cv[0], cv[1] + 1)
        def fetch_c(cell, k):
            if not k['C']: return None
            if k['ok'] == 'miss': return ('T', 'MISS')
            op = (k['m3'] >> 1) + 8 * k['m4']
            return (OPN[op], 0) if op < len(OPN) else ('T', 'HALT')
        P.stage('K5 next', [A('Cnext', [C], lambda c: {'C': C, 'ok': core['OK']}, {'C': lambda v: v, 'ok': lambda v: v}, next_c),
                            A('Cfetch', [C], lambda c: {'C': C, 'ok': core['OK'], 'm3': core['MDR3'], 'm4': core['MDR4']},
                              {'C': lambda v: v == ('F', 0), 'ok': lambda v: v, 'm3': lambda v: v[0], 'm4': lambda v: v[0]}, fetch_c)])

    # ------------------------------------------------------------ state <-> glyph string
    def encode(self, st):
        """st: dict with pc sp fp res resv lines(list N of [a,v,d]|None) evict([a,v,d]|None). -> list of gids."""
        P = self.P
        val = {}
        for c in P.cells: val[c.pos] = c.type.values[0]
        def setreg(r, v):
            for j, d in enumerate(digits(v, width(r))): val[self.core[f'{r}{j}'].pos] = (d, 0)
        val[self.core['C'].pos] = ('S',)
        val[self.core['RESV'].pos] = st['resv']
        setreg('PC', st['pc']); setreg('SP', st['sp']); setreg('FP', st['fp']); setreg('RES', st['res'])
        for ln, cl in zip([st['evict']] + st['lines'], self.lines[:self.N + 1]):
            if ln:
                a, v, d = ln
                val[cl['VD'].pos] = 2 if d else 1
                for j, dd in enumerate(digits(a, 4)): val[cl[f'TAG{j}'].pos] = (dd, 0)
                for j, dd in enumerate(digits(v, 5)): val[cl[f'VAL{j}'].pos] = (dd, 0)
        return [c.type.g(val[c.pos]) for c in P.cells]

    def decode(self, gids):
        P = self.P
        vals = []
        for g in gids:
            t, v = P.by_gid[g]; vals.append(v)
        V = lambda cell: vals[cell.pos]
        def reg(r, signed=False):
            x = sum(V(self.core[f'{r}{j}'])[0] << (4 * j) for j in range(width(r)))
            return s20(x) if signed else x
        def line(cl):
            vd = V(cl['VD'])
            if not vd: return None
            a = sum(V(cl[f'TAG{j}'])[0] << (4 * j) for j in range(4))
            v = s20(sum(V(cl[f'VAL{j}'])[0] << (4 * j) for j in range(5)))
            return [a, v, int(vd == 2)]
        st = dict(C=V(self.core['C']), pc=reg('PC'), sp=reg('SP'), fp=reg('FP'), resv=V(self.core['RESV']),
                  mar=reg('MAR'), t1=reg('T1', True), t2=reg('T2', True), t3=reg('T3', True),
                  evict=line(self.E), lines=[line(cl) for cl in self.Ls])
        return st

def parse(e):
    """-> (terms [(sign, reg)], K, special). special: None | 'BOOL' (K=name) | 'COND' (K='ZIMM'|'ZPC')."""
    m = re.fullmatch(r'(ADD|SUB|LT|GT|LE|GE|EQ|NE|AND|OR)\(T2,T1\)', e)
    if m:
        f = m.group(1)
        if f == 'ADD': return [(1, 'T2'), (1, 'T1')], 0, None
        if f == 'SUB': return [(1, 'T2'), (-1, 'T1')], 0, None
        return [], f, 'BOOL'
    if e == 'Z(T1)': return [], 'Z', 'BOOL'
    if e == 'Z(T1)?IMM:PC+1': return [], 'ZIMM', 'COND'
    if e == 'Z(T1)?PC+1:IMM': return [], 'ZPC', 'COND'
    terms, K = [], 0
    for sign, tok in re.findall(r'([+-]?)([A-Z0-9]+)', e):
        sg = -1 if sign == '-' else 1
        if tok.isdigit(): K += sg * int(tok)
        else: terms.append((sg, 'IMM' if tok == 'SIM' else tok))   # FP+SIM == FP+IMM mod 8192 (addresses only)
    return terms, K, None
