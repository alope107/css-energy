"""Build a CPU-font variant. usage: variant.py image.json out.ttf [opts...]
opts: abort   - append a self-recursive 'abort' lookup at the end of each cycle (fires when C is a trap value)
      rvrn    - also reference pre+cycles from feature rvrn (stage 0), cycles+tail from cv01 (stage 1): 2S cycles
      S=<n>   - cycles aliased per feature
      noexport- drop the export tail"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../repo/js-minus-js/machine'); os.environ['CPUMOD'] = 'cpu4'
import cpu4, cpugen as _cg
if os.environ.get('ORDER'):
    _order = json.load(open(os.environ['ORDER']))
    def _assign(self, start=1):
        g = start; names = [n for n in _order if n in self.types] + [n for n in self.types if n not in set(_order)]
        for n in names: t = self.types[n]; t.gid0 = g; g += len(t.values)
        self.nglyphs = g; self.by_gid = {}
        for t in self.types.values():
            for v in t.values: self.by_gid[t.g(v)] = (t, v)
    _cg.Program.assign_gids = _assign
import cpu4, cpugen, otl
from otl import chain_class, Lookup, build_gdef
from fontbase import make_font
image = json.load(open(sys.argv[1])); out = sys.argv[2]; opts = sys.argv[3:]
S = int(next((o[2:] for o in opts if o.startswith('S=')), 32))
cpu = cpu4.CPU(image, 16); P = cpu.P
orig = cpugen.build_gsub
def hook(lookups, index_list, features):
    lc = P.lookup_counts; nL, nP, nC, nT = lc['lib'], lc['pre'], lc['cycle'], lc['tail']
    lib, pre, cyc, tail = lookups[:nL], lookups[nL:nL + nP], lookups[nL + nP:nL + nP + nC], lookups[nL + nP + nC:]
    if 'noexport' in opts: tail = []
    if 'abort' in opts:
        C = cpu.core['C']; traps = [C.type.g(v) for v in C.type.values if v[0] == 'T']
        first_copy = nL + nP + nC          # LookupList index of cycle 0's copy of the new last cycle lookup
        cyc = cyc + [Lookup(6, [chain_class(traps, {}, {g: 1 for g in traps}, {}, [([], 1, [], [(0, first_copy)])])], None, 'abort')]
    nC = len(cyc); nT = len(tail)
    lookups = lib + pre + cyc + tail
    il = list(range(nL)) + [nL + i for i in range(nP)] + [nL + nP + i for _ in range(S) for i in range(nC)] + [nL + nP + nC + i for i in range(nT)]
    c0 = nL + nP; t0 = nL + nP + S * nC
    pre_ix = list(range(nL, nL + nP)); cyc_ix = list(range(c0, c0 + S * nC)); tail_ix = list(range(t0, t0 + nT))
    if 'arab' in opts:
        feats = [('rvrn', pre_ix + cyc_ix), ('stch', cyc_ix), ('ccmp', cyc_ix), ('rlig', cyc_ix), ('calt', cyc_ix), ('cv01', cyc_ix + tail_ix)]
        feats += [(t, []) for t in ('isol', 'fina', 'fin2', 'fin3', 'medi', 'med2', 'init')]
    elif 'rvrn' in opts: feats = [('cv01', cyc_ix + tail_ix), ('rvrn', pre_ix + cyc_ix)]
    else: feats = [('cv01', pre_ix + cyc_ix + tail_ix)]
    feats.append(('cv02', pre_ix + tail_ix))
    feats.sort()
    nsub = sum(len(lookups[i].subtables) for i in il)
    print(f'variant {opts}: {len(il)} LookupList entries, {nsub} subtables referenced')
    return orig(lookups, il, feats)
cpugen.build_gsub = hook
gsub = P.build(S, top13=cpu.top13, ptype='P', export_stage=cpu.export, debug_features=0)
twins = {g for t in cpu.twin.values() for g in t.gl()}
gdef = build_gdef({g: (1 if g in twins else 3) for g in range(1, P.nglyphs)}, P.mark_sets)
names = ['.notdef'] + [f'g{g}' for g in range(1, P.nglyphs)]
adv = cpu.advances()
cmap = {0xF0000 + g: f'g{g}' for g in range(1, P.nglyphs) if g not in twins}
if 'arab' in opts:
    meta = json.load(open(os.path.dirname(os.path.abspath(__file__)) + '/../repo/js-minus-js/build/f4cc_16.json'))
    used = set()
    for c in meta['cells']:
        used.add(c['static']); used.update(c['symbols'] or [])
    import uharfbuzz as hb
    cps = []
    for c in map(int, open(os.path.dirname(os.path.abspath(__file__)) + '/../arab_cps.txt').read().split()):
        b = hb.Buffer(); b.add_str(chr(c)); b.guess_segment_properties()
        if b.script == 'Arab': cps.append(c)
    m = dict(zip(sorted(used), cps)); assert len(m) == len(used)
    json.dump(m, open(out + '.map.json', 'w'))
    cmap = {m[cp]: n for cp, n in cmap.items() if cp in m}
make_font(out, names, {names[g]: a for g, a in adv.items()}, cmap, gsub, gdef)
