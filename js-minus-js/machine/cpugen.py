#!/usr/bin/env python3
"""cpugen.py — compile the font CPU (see uarch.py) into GSUB.

The machine state is a string of glyphs (cells). Every cell has a glyph *type* (an alphabet). All state
glyphs are GDEF marks so each lookup can see only the types it uses (mark filtering sets); that keeps
contexts short no matter how far apart cells are. A stage is one lookup:
  A   forward assignment  target := f(sources)   (ChainContext format 2, rules enumerated from f)
  RA  reverse assignment  for leftward data flow  (ReverseChainSingleSubst)
  MAP glyph-to-glyph map                           (SingleSubst)
Outputs of assignments go through value-indexed SET lookups (SET_x maps any target glyph to value x of
its type). One cycle's lookups are referenced S times from the LookupList (aliasing) to run S cycles
per shaping; feature ssNN runs NN cycles (debug), cv01 runs S.
"""
import itertools, re, sys, json
from otl import coverage, single_subst, chain_class, reverse_chain, Lookup, build_gsub, build_gdef
import uarch
from uarch import OPN, UCODE, ROM

# ------------------------------------------------------------------ framework
class GType:
    def __init__(self, name, values):
        self.name, self.values = name, list(values)
        self.index = {v: i for i, v in enumerate(self.values)}
        self.gid0 = None
    def g(self, v): return self.gid0 + self.index[v]
    def gl(self): return list(range(self.gid0, self.gid0 + len(self.values)))
    def __repr__(self): return self.name

class Cell:
    __slots__ = ('type', 'region', 'line', 'field', 'pos')
    def __init__(self, t, region, line, field): self.type, self.region, self.line, self.field, self.pos = t, region, line, field, None
    def __repr__(self): return f'{self.region}{"" if self.line is None else self.line}.{self.field}'

class A:
    def __init__(self, name, targets, resolve, keys, fn):
        self.name, self.targets, self.resolve, self.keys, self.fn = name, targets, resolve, keys, fn
class RA:
    def __init__(self, name, targets, ctx, out):
        self.name, self.targets, self.ctx, self.out = name, targets, ctx, out
class Op:
    """Return from an A fn to apply a nested library op instead of SET."""
    def __init__(self, *op): self.op = op
    def __eq__(self, o): return isinstance(o, Op) and o.op == self.op
    def __hash__(self): return hash(self.op)
    def __repr__(self): return f'Op{self.op}'
class MAP:
    def __init__(self, name, types, fn): self.name, self.types, self.fn = name, types, fn
class DA:
    """Dispatch: a rule starts at a source glyph (one rule set per source class) and applies nested ops to
    targets later in its input sequence. items: [dict(src=cell, targets=[cells], gates={role: cell})].
    keys: {'src': f, role: f, 'tgt': f (optional, applied to every target)}. fn(item, k) -> [(target_idx, op)] | None,
    op in ('SET', value) ('ADD', x) ('ADDM', x) ('P16', x) ('P256', x) ('PRAM',)."""
    def __init__(self, name, items, keys, fn): self.name, self.items, self.keys, self.fn = name, items, keys, fn

class _TypedKeys:
    """a DA spec's keys, where a role's key function may be one function or {type name: function}: .of(role, type name)"""
    def __init__(self, keys): self.k = keys
    def of(self, r, tn):
        f = self.k[r]
        return f[tn] if isinstance(f, dict) else f
    def get(self, r, d=None): return self.k.get(r, d)
    def __getitem__(self, r): return self.k[r]
    def __contains__(self, r): return r in self.k

class Program:
    def __init__(self):
        self.types = {}; self.cells = []; self.stages = []; self.pre_stages = []; self.post_stages = []
    def T(self, name, values):
        assert name not in self.types, name
        t = GType(name, values); self.types[name] = t; return t
    def cell(self, t, region, line, field):
        c = Cell(t, region, line, field); c.pos = len(self.cells); self.cells.append(c); return c
    def stage(self, name, specs):
        self.stages.append((name, specs))
    def pre(self, name, specs):
        self.pre_stages.append((name, specs))
    def post(self, name, specs):
        self.post_stages.append((name, specs))

    # ---- compile
    def assign_gids(self, start=1):
        g = start
        for t in self.types.values(): t.gid0 = g; g += len(t.values)
        self.nglyphs = g
        self.by_gid = {}
        for t in self.types.values():
            for v in t.values: self.by_gid[t.g(v)] = (t, v)

    def compile_stage(self, name, specs, set_index):
        """-> Lookup (or None if empty)."""
        kinds = {type(s) for s in specs}
        if kinds <= {A, DA}: kind = A if kinds == {A} else DA
        else:
            assert len(kinds) == 1, name
            kind = kinds.pop()
        if kind is MAP:
            m = {}
            for s in specs:
                for t in s.types:
                    for v in t.values:
                        nv = s.fn(t, v)
                        if nv is not None and nv != v: m[t.g(v)] = t.g(nv) if not isinstance(nv, tuple) or nv[0] != '@' else nv[1].g(nv[2])
            return Lookup(1, [single_subst(m)], None, name) if m else None
        # filter set = every type touched
        ftypes = set()
        for s in specs:
            if isinstance(s, DA):
                for it in s.items:
                    ftypes.add(it['src'].type); ftypes |= {c.type for c in it['targets']}; ftypes |= {c.type for c in it['gates'].values()}
                continue
            for c in s.targets:
                ftypes.add(c.type)
                srcs = s.resolve(c) if isinstance(s, A) else dict((f'r{i}', cc) for i, (cc, _) in enumerate(s.ctx(c) or []))
                if srcs is None: continue
                for cc in srcs.values(): ftypes.add(cc.type)
        view = [c for c in self.cells if c.type in ftypes]
        vidx = {c.pos: i for i, c in enumerate(view)}
        subtables = []
        for s in specs:
            if isinstance(s, A): subtables += self._compile_A(s, view, vidx, set_index)
            elif isinstance(s, DA): subtables += self._compile_DA(s, view, vidx)
            else: subtables += self._compile_RA(s, view, vidx)
        if not subtables: return None
        ms = len(self.mark_sets); self.mark_sets.append(set(g for t in ftypes for g in t.gl()))
        return Lookup(8 if kind is RA else 6, subtables, ms, name)

    def check_unique(self, name, view, vidx, groups, rolecells):
        """groups: {(typename, shape_types tuple of (offset, typename))): set of cell positions}. A rule applies by type, so any
        cell of the same type whose view context has the same types at the same offsets must be in that group."""
        bytype = {}
        for c in view: bytype.setdefault(c.type.name, []).append(c)
        for (tn, sig), members in groups.items():
            for c in bytype.get(tn, []):
                if c.pos in members: continue
                i0 = vidx[c.pos]; ok = True
                for o, ttn in sig:
                    if not (0 <= i0 + o < len(view)) or view[i0 + o].type.name != ttn: ok = False; break
                if ok: raise RuntimeError(f'{name}: rule for {tn} {sig} would also apply to {c}')

    def op_index(self, t, op):
        if op[0] == 'SET': return self.lib[('SET', t.index[op[1]])]
        return self.lib[op]

    def _compile_DA(self, s, view, vidx):
        # a key may be a function of the value, or {type name: function} (one spec dispatching from several cell types)
        from types import SimpleNamespace
        s = SimpleNamespace(name=s.name, items=s.items, fn=s.fn, keys=_TypedKeys(s.keys))
        groups = {}
        for it in s.items:
            i0 = vidx[it['src'].pos]
            tg = [(vidx[c.pos] - i0, 'T', ti, c.type.name) for ti, c in enumerate(it['targets'])]
            ga = [(vidx[c.pos] - i0, 'G', r, c.type.name) for r, c in it['gates'].items()]
            shape = tuple(sorted(tg + ga, key=repr))
            groups.setdefault((it['src'].type.name, shape), []).append(it)
        self.check_unique(s.name, view, vidx, {(stn, tuple((o, tn) for o, _, _, tn in sh)): {it['src'].pos for it in its} for (stn, sh), its in groups.items()}, None)
        out = []
        def build(items):
            in_cls, bt_cls, la_cls = {}, {}, {}
            rules = []; covg = set(); inkey = {}
            for (stn, shape), its in items:
                it = its[0]; st = self.types[stn]
                last = max([o for o, kd, _, _ in shape if kd == 'T'] + [0])
                roles = []          # (offset, rolekind, name, type, keyfn)
                for o, kd, r, tn in shape:
                    kf = (s.keys.of('tgt', tn) if 'tgt' in s.keys else (lambda v: None)) if kd == 'T' else s.keys.of(r, tn)
                    if kd == 'T' and tn == stn: kf = s.keys.of('src', tn)     # one class mapping per type
                    roles.append((o, kd, r, self.types[tn], kf))
                skf = s.keys.of('src', stn)
                for sk in sorted(set(skf(v) for v in st.values), key=repr):
                    # a target at offset 0 is the source glyph itself: its key is the source's, not enumerated (that made
                    # 16 identical copies of every rule of a self-update like PC := PC + 1, all tried when none applies)
                    doms = [[sk] if o == 0 else sorted(set(kf(v) for v in T_.values), key=repr) for (o, _, _, T_, kf) in roles]
                    for combo in itertools.product(*doms):
                        k = {'src': sk}
                        for (o, kd, r, T_, kf), kv in zip(roles, combo):
                            k[(kd, r)] = kv
                            if kd == 'G': k[r] = kv
                        k['tgts'] = {r: kv for (o, kd, r, T_, kf), kv in zip(roles, combo) if kd == 'T'}
                        ops = s.fn(it, k)
                        if not ops: continue
                        sc = in_cls.setdefault((stn, sk), len(in_cls) + 1)
                        seq = []
                        bypos = {o: (kd, r, T_, kv) for (o, kd, r, T_, kf), kv in zip(roles, combo)}
                        for o in range(1, last + 1):
                            if o in bypos:
                                kd, r, T_, kv = bypos[o]; seq.append(in_cls.setdefault((T_.name, kv), len(in_cls) + 1))
                            else: seq.append(0)
                        bt = [];  la = []
                        mn = min([0] + list(bypos)); mx = max([last] + list(bypos))
                        for o in range(-1, mn - 1, -1):
                            if o in bypos:
                                kd, r, T_, kv = bypos[o]; bt.append(bt_cls.setdefault((T_.name, kv), len(bt_cls) + 1))
                            else: bt.append(0)
                        for o in range(last + 1, mx + 1):
                            if o in bypos:
                                kd, r, T_, kv = bypos[o]; la.append(la_cls.setdefault((T_.name, kv), len(la_cls) + 1))
                            else: la.append(0)
                        recs = []
                        for ti, op in ops:
                            o = next(o for o, kd, r, _ in shape if kd == 'T' and r == ti)
                            recs.append((o, self.op_index(it['targets'][ti].type, op)))
                        rules.append((bt, (seq, sc), la, recs))
                        for v in st.values:
                            if skf(v) == sk: covg.add(st.g(v))
            # class defs: key functions per type (src, targets, gates)
            kfs = {}
            for (stn, shape), its in items:
                kfs.setdefault(stn, s.keys.of('src', stn))
                for o, kd, r, tn in shape:
                    kfs.setdefault(tn, s.keys.of('src', tn) if (kd == 'T' and tn == stn) else (s.keys.of('tgt', tn) if 'tgt' in s.keys else (lambda v: None)) if kd == 'T' else s.keys.of(r, tn))
            def mk(cls):
                m = {}
                for (tn, key), ci in cls.items():
                    T_ = self.types[tn]
                    for v in T_.values:
                        if kfs[tn](v) == key:
                            g = T_.g(v); assert m.get(g, ci) == ci, ('class clash', s.name, tn); m[g] = ci
                return m
            in_cd, bt_cd, la_cd = mk(in_cls), mk(bt_cls), mk(la_cls)
            cin = {tn for tn, _ in in_cls}; cbt = {tn for tn, _ in bt_cls}; cla = {tn for tn, _ in la_cls}
            for (stn, shape), its in items:
                offs = {o for o, _, _, _ in shape}
                last = max([o for o, kd, _, _ in shape if kd == 'T'] + [0])
                mn = min([0] + list(offs)); mx = max([last] + list(offs))
                for it in its:
                    i0 = vidx[it['src'].pos]
                    assert i0 + mn >= 0 and i0 + mx < len(view), ('context out of view', s.name)
                    for o in range(mn, mx + 1):
                        if o == 0 or o in offs: continue
                        vt = view[i0 + o].type.name
                        if (o < 0 and vt in cbt) or (0 < o <= last and vt in cin) or (o > last and vt in cla):
                            return ('conflict', (it['src'], o, view[i0 + o]))
            return covg, bt_cd, in_cd, la_cd, rules
        def emit(items):
            r = build(items)
            if r[0] == 'conflict':
                if len(items) == 1: raise RuntimeError(f'{s.name}: window conflict {r[1]}')
                h = len(items) // 2; emit(items[:h]); emit(items[h:]); return
            covg, bt_cd, in_cd, la_cd, rules = r
            if not rules: return
            def put(rs):
                try: out.append(chain_class(covg, bt_cd, in_cd, la_cd, rs))
                except OverflowError:
                    if len(rs) == 1: raise
                    h = len(rs) // 2; put(rs[:h]); put(rs[h:])
            try: out.append(chain_class(covg, bt_cd, in_cd, la_cd, rules))
            except OverflowError:
                if len(items) > 1: h = len(items) // 2; emit(items[:h]); emit(items[h:]); return
                put(rules)
        emit(list(groups.items()))
        return out

    def _compile_A(self, s, view, vidx, set_index):
        groups = {}
        for c in s.targets:
            srcs = s.resolve(c)
            if srcs is None: continue
            i0 = vidx[c.pos]
            shape = tuple(sorted((vidx[cc.pos] - i0, role, cc.type.name) for role, cc in srcs.items()))
            groups.setdefault((c.type.name, shape), []).append(c)
        self.check_unique(s.name, view, vidx, {(tn, tuple((o, t_) for o, _, t_ in sh)): {c.pos for c in cs} for (tn, sh), cs in groups.items()}, None)
        out = []
        # try all shapes in one subtable; split on window conflicts / overflow
        gl = list(groups.items())
        def build(items):
            bt_cls, la_cls, in_cls = {}, {}, {}
            rules = []; covg = set()
            for (tname, shape), cells in items:
                c = cells[0]; t = c.type
                selfrole = next((r for o, r, _ in shape if o == 0), None)
                roles = [r for o, r, _ in shape if o != 0]
                stypes = {r: self.types[tn] for _, r, tn in shape}
                offs = {r: o for o, r, _ in shape if o != 0}
                doms = []
                for r in roles:
                    kf = s.keys[r]
                    doms.append(sorted(set(kf(v) for v in stypes[r].values), key=repr))
                selfk = s.keys[selfrole] if selfrole else None
                sdom = sorted(set(selfk(v) for v in t.values), key=repr) if selfk else [None]
                for combo in itertools.product(*doms):
                    k = dict(zip(roles, combo))
                    for sk in sdom:
                        if selfk: k[selfrole] = sk
                        nv = s.fn(c, k)
                        if nv is None: continue
                        ic = in_cls.setdefault((t.name, sk), len(in_cls) + 1)
                        bt = []; la = []
                        mn = min([0] + [o for o in offs.values()]); mx = max([0] + [o for o in offs.values()])
                        rev = {o: r for r, o in offs.items()}
                        for o in range(-1, mn - 1, -1):
                            r = rev.get(o); bt.append(bt_cls.setdefault((stypes[r].name, k[r]), len(bt_cls) + 1) if r else 0)
                        for o in range(1, mx + 1):
                            r = rev.get(o); la.append(la_cls.setdefault((stypes[r].name, k[r]), len(la_cls) + 1) if r else 0)
                        rules.append((bt, ic, la, [(0, self.op_index(t, nv.op) if isinstance(nv, Op) else set_index[(t.name, nv)])]))
                        for v in t.values:
                            if selfk is None or selfk(v) == sk: covg.add(t.g(v))
            # ClassDefs
            def mk(cls, keyof):
                m = {}
                for (tn, key), ci in cls.items():
                    T_ = self.types[tn]
                    for v in T_.values:
                        if keyof(tn, v) == key:
                            g = T_.g(v); assert m.get(g, ci) == ci, ('class clash', s.name, tn); m[g] = ci
                return m
            def keyof_bt(tn, v):
                for (tn2, shape), cells in items:
                    for o, r, tt in shape:
                        if tt == tn and o != 0: return s.keys[r](v)
            bt_cd = mk(bt_cls, keyof_bt); la_cd = mk(la_cls, keyof_bt)
            def keyof_in(tn, v):
                for (tn2, shape), cells in items:
                    if tn2 == tn:
                        sr = next((r for o, r, _ in shape if o == 0), None)
                        return s.keys[sr](v) if sr else None
            in_cd = mk(in_cls, keyof_in)
            # window cleanliness
            classed_bt = {tn for tn, _ in bt_cls}; classed_la = {tn for tn, _ in la_cls}
            for (tname, shape), cells in items:
                for c in cells:
                    i0 = vidx[c.pos]; offs = {o for o, _, _ in shape}
                    mn = min([0] + list(offs)); mx = max([0] + list(offs))
                    for o in range(mn, mx + 1):
                        if o == 0 or o in offs: continue
                        vc = view[i0 + o]
                        if (o < 0 and vc.type.name in classed_bt) or (o > 0 and vc.type.name in classed_la):
                            return ('conflict', (c, o, vc))
                    assert i0 + mn >= 0 and i0 + mx < len(view), ('context out of view', s.name, c)
            return (covg, bt_cd, in_cd, la_cd, rules)
        def emit(items):
            r = build(items)
            if r[0] == 'conflict':
                if len(items) == 1: raise RuntimeError(f'{s.name}: window conflict {r[1]}')
                h = len(items) // 2; emit(items[:h]); emit(items[h:]); return
            covg, bt_cd, in_cd, la_cd, rules = r
            if not rules: return
            def put(rs):
                try:
                    out.append(chain_class(covg, bt_cd, in_cd, la_cd, rs))
                except OverflowError:
                    assert len(rs) > 1, 'single rule overflow'
                    h = len(rs) // 2; put(rs[:h]); put(rs[h:])
            try:
                out.append(chain_class(covg, bt_cd, in_cd, la_cd, rules))
            except OverflowError:
                if len(items) > 1:
                    h = len(items) // 2; emit(items[:h]); emit(items[h:]); return
                put(rules)
        emit(gl)
        return out

    def _compile_RA(self, s, view, vidx):
        groups = {}
        for c in s.targets:
            ctx = s.ctx(c)
            if ctx is None: continue
            i0 = vidx[c.pos]
            sig = tuple(sorted(vidx[cc.pos] - i0 for cc, _ in ctx))
            groups.setdefault(sig, []).append((c, ctx))
        chk = {}
        for sig, members in groups.items():
            for c, ctx in members:
                i0 = vidx[c.pos]
                key = (c.type.name, tuple(sorted((vidx[cc.pos] - i0, cc.type.name) for cc, _ in ctx)))
                chk.setdefault(key, set()).add(c.pos)
        self.check_unique(s.name, view, vidx, chk, None)
        out = []
        for sig, members in groups.items():
            mn = min([0] + list(sig)); mx = max([0] + list(sig))
            pos_cov = {o: set() for o in range(mn, mx + 1) if o}
            imap = {}
            for c, ctx in members:
                i0 = vidx[c.pos]
                cons = {vidx[cc.pos] - i0: (cc, p) for cc, p in ctx}
                for o in pos_cov:
                    vc = view[i0 + o]
                    if o in cons:
                        cc, p = cons[o]; pos_cov[o] |= {cc.type.g(v) for v in cc.type.values if p(v)}
                    else:
                        pos_cov[o] |= set(vc.type.gl())
                for v in c.type.values:
                    nv = s.out(c, v)
                    if nv is not None and nv != v: imap[c.type.g(v)] = c.type.g(nv)
            if not imap: continue
            bt = [pos_cov[o] for o in range(-1, mn - 1, -1)]
            la = [pos_cov[o] for o in range(1, mx + 1)]
            out.append(reverse_chain(imap, bt, la))
        return out

    def build(self, S, debug_features=20, export_stage=None, top13=(), ptype=None):
        self.assign_gids()
        self.mark_sets = []
        targets = set()
        for _, specs in self.stages + self.pre_stages + self.post_stages + ([export_stage] if export_stage else []):
            for s in specs:
                if isinstance(s, A): targets |= {c.type.name for c in s.targets}
                if isinstance(s, DA):
                    for it in s.items: targets |= {c.type.name for c in it['targets']}
        targets.discard(ptype)
        lib = []; self.lib = {}
        def add(key, mapping, name):
            if not mapping: return
            self.lib[key] = len(lib); lib.append(Lookup(1, [single_subst(mapping)], None, name))
        maxv = max(len(self.types[t].values) for t in targets)
        set_index = {}
        for x in range(maxv):
            m = {}
            for tn in targets:
                t = self.types[tn]
                if x < len(t.values):
                    for v in t.values: m[t.g(v)] = t.gid0 + x
                    set_index[(tn, t.values[x])] = x
            add(('SET', x), m, f'SET{x}')
        d48 = [self.types[tn] for tn in targets if len(self.types[tn].values) == 48]
        for x in range(1, 48):
            add(('ADD', x), {t.gid0 + i: t.gid0 + i + x for t in d48 for i in range(48 - x)}, f'ADD{x}')
        for x in range(3):
            tm = getattr(self, 'topmask', lambda tn: 1)      # the top digit's mask per register (cpu4.topmask)
            add(('ADDM', x), {self.types[tn].gid0 + i: self.types[tn].gid0 + (((i + x) % 16) & tm(tn)) for tn in top13 for i in range(48)}, f'ADDM{x}')
        if ptype:
            P = self.types[ptype]; n = len(P.values) - 1          # last value = RAM marker
            for x in range(16): add(('PSET', x), {P.g(v): P.gid0 + x for v in P.values}, f'PSET{x}')
            for x in range(1, 16):
                add(('P16', x), {P.gid0 + i: P.gid0 + i + 16 * x for i in range(n - 16 * x)}, f'P16_{x}')
                add(('P256', x), {P.gid0 + i: P.gid0 + i + 256 * x for i in range(n - 256 * x)}, f'P256_{x}')
            add(('PRAM',), {P.g(v): P.gid0 + n for v in P.values[:-1]}, 'PRAM')
        # A specs use SET by value: map (type, value) -> lib index
        self.set_index = {k: self.lib[('SET', x)] for k, x in set_index.items()}
        def comp(stages):
            out = []
            for name, specs in stages:
                lk = self.compile_stage(name, specs, self.set_index)
                if lk: out.append(lk)
            return out
        cyc = comp(self.stages); pre = comp(self.pre_stages); post = comp(self.post_stages)
        self.cycle_lookups = cyc
        ex = self.compile_stage(*export_stage, self.set_index) if export_stage else None
        tail = post + ([ex] if ex else [])
        lookups = lib + pre + cyc + tail
        self.all_lookups = lookups; self.nlib = len(lib) + len(pre)    # (debug tools treat pre as part of the prefix)
        nL, nP, nC, nT = len(lib), len(pre), len(cyc), len(tail)
        index_list = list(range(nL)) + [nL + i for i in range(nP)] + [nL + nP + i for _ in range(S) for i in range(nC)] + \
                     [nL + nP + nC + i for i in range(nT)]
        p0 = nL; c0 = nL + nP; t0 = nL + nP + S * nC
        def run(k): return list(range(p0, p0 + nP)) + list(range(c0, c0 + k * nC)) + list(range(t0, t0 + nT))
        feats = [(f'ss{k:02d}', run(k)) for k in range(1, min(debug_features, S) + 1)]
        feats.append(('cv01', run(S)))
        feats.append(('cv02', run(0)))
        self.lookup_counts = dict(lib=nL, pre=nP, cycle=nC, tail=nT)
        self.subtables_per_cycle = sum(len(l.subtables) for l in cyc)
        self.lib_subtables = len(lib)
        self.gsub = build_gsub(lookups, index_list, feats)
        return self.gsub
