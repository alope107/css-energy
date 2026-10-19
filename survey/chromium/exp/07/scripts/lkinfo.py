"""Static info per distinct lookup of the CPU font, from the generator objects. -> lkinfo.json"""
import sys, os, json, struct
W = os.path.dirname(os.path.abspath(__file__)) + '/../repo/js-minus-js/machine'
sys.path.insert(0, W); os.environ['CPUMOD'] = 'cpu4'
import cpu4
image = json.load(open(sys.argv[1])); N, S = 16, 32
cpu = cpu4.CPU(image, N); P = cpu.P
P.build(S, top13=cpu.top13, ptype='P', export_stage=cpu.export, debug_features=0)
L = P.all_lookups; lc = P.lookup_counts
nL, nP, nC, nT = lc['lib'], lc['pre'], lc['cycle'], lc['tail']
def u16(b, o): return struct.unpack_from('>H', b, o)[0]
def cov_info(b, o):
    f = u16(b, o); n = u16(b, o + 2)
    return dict(fmt=f, n=n)
def cd_info(b, o):
    f = u16(b, o); n = u16(b, o + 2)
    if f == 2:
        cls = set(u16(b, o + 4 + 6 * i + 4) for i in range(n)); return dict(fmt=2, ranges=n, maxcls=max(cls) if cls else 0)
    return dict(fmt=f, n=n)
out = []
for i, lk in enumerate(L):
    d = dict(i=i, name=lk.name, type=lk.type, nsub=len(lk.subtables), mark_set=lk.mark_set)
    if lk.mark_set is not None:
        ms = sorted(P.mark_sets[lk.mark_set]); d['ms_n'] = len(ms); d['ms_span'] = ms[-1] - ms[0] + 1
    subs = []
    for st in lk.subtables:
        s = dict(len=len(st))
        if lk.type == 6:
            fmt = u16(st, 0); s['fmt'] = fmt
            if fmt == 2:
                ncls = u16(st, 10); s['nsets'] = ncls
                s['cov'] = cov_info(st, u16(st, 2)); s['bt'] = cd_info(st, u16(st, 4)); s['in'] = cd_info(st, u16(st, 6)); s['la'] = cd_info(st, u16(st, 8))
                nr = 0; bl = []; il = []; ll = []; rulesper = []
                for k in range(ncls):
                    so = u16(st, 12 + 2 * k)
                    if not so: continue
                    n = u16(st, so); nr += n; rulesper.append(n)
                    for r in range(n):
                        ro = so + u16(st, so + 2 + 2 * r)
                        b = u16(st, ro); il_ = u16(st, ro + 2 + 2 * b); l_ = u16(st, ro + 4 + 2 * b + 2 * (il_ - 1))
                        bl.append(b); il.append(il_); ll.append(l_)
                s['rules'] = nr; s['maxrules'] = max(rulesper) if rulesper else 0
                s['bt_len'] = sum(bl) / max(1, len(bl)); s['in_len'] = sum(il) / max(1, len(il)); s['la_len'] = sum(ll) / max(1, len(ll))
        elif lk.type == 8:
            s['cov'] = cov_info(st, u16(st, 2)); nb = u16(st, 4); nl = u16(st, 6 + 2 * nb); s['bt_len'] = nb; s['la_len'] = nl
        elif lk.type == 1:
            s['fmt'] = u16(st, 0)
        subs.append(s)
    d['subs'] = subs
    if lk.type == 6: d['rules'] = sum(s.get('rules', 0) for s in subs)
    out.append(d)
idx = list(range(nL)) + [nL + i for i in range(nP)] + [nL + nP + i for _ in range(S) for i in range(nC)] + [nL + nP + nC + i for i in range(nT)]
json.dump(dict(lookups=out, index_list=idx, counts=lc, nglyphs=P.nglyphs, cells=len(P.cells)), open(sys.argv[2], 'w'))
print(len(out), len(idx), P.nglyphs)
