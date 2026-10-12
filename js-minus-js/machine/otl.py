"""otl.py — a small OpenType layout assembler (GSUB + GDEF) with byte-level control.

Why hand-assembled: the CPU needs one cycle's lookups referenced many times from the LookupList
(aliasing), which fontTools' compiler can't express. Every lookup is wrapped in Extension subtables
so subtable payloads can live anywhere (32-bit offsets).
"""
import struct

def u16(*xs): return b''.join(struct.pack('>H', x) for x in xs)

def coverage(glyphs):
    gs = sorted(set(glyphs)); assert gs
    ranges = []
    for g in gs:
        if ranges and ranges[-1][1] == g - 1: ranges[-1][1] = g
        else: ranges.append([g, g])
    if len(ranges) * 3 < len(gs):
        out = u16(2, len(ranges)); idx = 0
        for s, e in ranges: out += u16(s, e, idx); idx += e - s + 1
        return out, gs
    return u16(1, len(gs)) + u16(*gs), gs

def classdef(mapping):
    """mapping: glyph -> class (>0). Format 2 ranges."""
    items = sorted((g, c) for g, c in mapping.items() if c)
    ranges = []
    for g, c in items:
        if ranges and ranges[-1][1] == g - 1 and ranges[-1][2] == c: ranges[-1][1] = g
        else: ranges.append([g, g, c])
    return u16(2, len(ranges)) + b''.join(u16(s, e, c) for s, e, c in ranges)

class Blob:
    """Build a table from parts with deferred offsets. parts: bytes or ('off16'|'off32', Blob, base_label)."""
    pass

def single_subst(mapping):
    cov, gs = coverage(mapping.keys())
    head = 6 + 2 * len(gs)
    return u16(2, head, len(gs)) + u16(*[mapping[g] for g in gs]) + cov

def multiple_subst(mapping):
    """glyph -> list of glyphs."""
    cov, gs = coverage(mapping.keys())
    n = len(gs); off = 6 + 2 * n; seqs = b''; offs = []
    for g in gs:
        offs.append(off + len(seqs)); s = mapping[g]; seqs += u16(len(s), *s)
    cov_off = off + len(seqs)
    return u16(1, cov_off, n) + u16(*offs) + seqs + cov

def chain_class(*a):
    try: return _chain_class(*a)
    except struct.error: raise OverflowError

def _chain_class(cov_glyphs, bt_cd, in_cd, la_cd, rules):
    """ChainContextSubst format 2. rules: list of (bt_classes (closest first), in_class, la_classes, [(seqIndex, lookupIndex)]).
    Returns bytes, or raises OverflowError if offsets don't fit."""
    cov, _ = coverage(cov_glyphs)
    ncls = max([0] + list(in_cd.values())) + 1
    by_in = {}
    for bt, ic, la, recs in rules:
        seq = []
        if isinstance(ic, tuple): seq, ic = ic
        by_in.setdefault(ic, []).append((bt, seq, la, recs))
    head = 12 + 2 * ncls
    body = b''; set_offs = [0] * ncls
    for ic in range(ncls):
        if ic not in by_in: continue
        rs = by_in[ic]; set_offs[ic] = head + len(body)
        sb = u16(len(rs)); rb = b''; roffs = []
        for bt, seq, la, recs in rs:
            roffs.append(2 + 2 * len(rs) + len(rb))
            rb += u16(len(bt), *bt) + u16(1 + len(seq), *seq) + u16(len(la), *la) + u16(len(recs)) + b''.join(u16(s, l) for s, l in recs)
        sb += u16(*roffs) + rb
        body += sb
    o_cov = head + len(body); body += cov
    o_bt = head + len(body); body += classdef(bt_cd)
    o_in = head + len(body); body += classdef(in_cd)
    o_la = head + len(body); body += classdef(la_cd)
    if max(o_la, max(set_offs)) >= 65536: raise OverflowError
    return u16(2, o_cov, o_bt, o_in, o_la, ncls) + u16(*set_offs) + body

def reverse_chain(input_map, bt_covs, la_covs):
    """ReverseChainSingleSubst format 1. input_map: glyph->substitute; bt_covs/la_covs: lists of glyph sets (closest first)."""
    cov, gs = coverage(input_map.keys())
    nb, nl = len(bt_covs), len(la_covs)
    head = 2 + 2 + 2 + 2 * nb + 2 + 2 * nl + 2 + 2 * len(gs)
    body = b''; o_cov = head + len(body); body += cov
    bo = []
    for c in bt_covs: bo.append(head + len(body)); body += coverage(c)[0]
    lo = []
    for c in la_covs: lo.append(head + len(body)); body += coverage(c)[0]
    return (u16(1, o_cov, nb) + u16(*bo) + u16(nl) + u16(*lo) + u16(len(gs)) + u16(*[input_map[g] for g in gs]) + body)

class Lookup:
    def __init__(self, ltype, subtables, mark_set=None, name=''):
        self.type, self.subtables, self.mark_set, self.name = ltype, subtables, mark_set, name

def build_gsub(lookups, index_list, features):
    """lookups: list of Lookup (distinct tables). index_list: list of positions into `lookups` — the LookupList
    (entries may repeat: aliasing). features: list of (tag, [LookupList indices]). Returns GSUB bytes."""
    nl = len(index_list)
    # LookupList head: count, offsets, then each distinct Lookup table + its extension headers
    tables = []; pos = 2 + 2 * nl
    for lk in lookups:
        flag = 0x10 if lk.mark_set is not None else 0
        tlen = 6 + 2 * len(lk.subtables) + (2 if flag else 0)
        tables.append((pos, flag, tlen)); pos += tlen + 8 * len(lk.subtables)
    ll_head_len = pos
    assert ll_head_len < 65536, ll_head_len
    langsys = u16(0, 0xFFFF, len(features)) + u16(*range(len(features)))
    scriptlist = u16(1) + b'DFLT' + u16(8) + u16(4, 0) + langsys
    SL = 10; LL = SL + len(scriptlist); FL = LL + ll_head_len
    assert FL < 65536
    recs = b''; ftabs = b''; base = 2 + 6 * len(features)
    for tag, idxs in features:
        assert base + len(ftabs) < 65536
        recs += tag.encode() + u16(base + len(ftabs)); ftabs += u16(0, len(idxs)) + u16(*idxs)
    featurelist = u16(len(features)) + recs + ftabs
    PAY = FL + len(featurelist)
    payload = b''; ll = u16(nl) + u16(*[tables[i][0] for i in index_list])
    for lk, (tpos, flag, tlen) in zip(lookups, tables):
        n = len(lk.subtables)
        ext_base = tpos + tlen
        t = u16(7, flag, n) + u16(*[ext_base + 8 * k - tpos for k in range(n)])
        if flag: t += u16(lk.mark_set)
        ext = b''
        for k, st in enumerate(lk.subtables):
            hdr_abs = LL + ext_base + 8 * k
            ext += struct.pack('>HHI', 1, lk.type, PAY + len(payload) - hdr_abs)
            payload += st
            if len(payload) % 2: payload += b'\0'
        ll += t + ext
    assert len(ll) == ll_head_len, (len(ll), ll_head_len)
    return struct.pack('>HHHHH', 1, 0, SL, FL, LL) + scriptlist + ll + featurelist + payload

def build_gdef(glyph_classes, mark_sets):
    """glyph_classes: glyph->class (1 base, 3 mark). mark_sets: list of glyph sets."""
    cd = classdef(glyph_classes)
    hdr = 14
    o_cd = hdr; o_ms = hdr + len(cd)
    msd_head = 4 + 4 * len(mark_sets)
    covs = b''; coffs = []
    for s in mark_sets:
        coffs.append(msd_head + len(covs)); covs += coverage(s)[0]
        if len(covs) % 2: covs += b'\0'
    msd = u16(1, len(mark_sets)) + b''.join(struct.pack('>I', o) for o in coffs) + covs
    return u16(1, 2, o_cd, 0, 0, 0, o_ms) + cd + msd
