"""One SingleSubst lookup (n_k -> n_k+1) referenced from features in different shaping stages: count how many
times it runs, per script, from the advance of the result (n_k advance = 100 (k+1))."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../repo/js-minus-js/machine')
from otl import single_subst, Lookup, build_gsub, build_gdef
from fontbase import make_font
K = 16; names = ['.notdef'] + [f'n{k}' for k in range(K)]
lk = [Lookup(1, [single_subst({k: k + 1 for k in range(1, K)})], None, 'inc')]
tags = ['rvrn', 'stch', 'ccmp', 'locl', 'rlig', 'calt', 'liga', 'clig', 'cv01', 'kern', 'mark', 'abvs', 'pres', 'psts', 'haln']
feats = [(t, [0]) for t in tags] + [(t, []) for t in ('isol', 'fina', 'fin2', 'fin3', 'medi', 'med2', 'init')]
feats.sort()
gsub = build_gsub(lk, [0], feats); gdef = build_gdef({g: 1 for g in range(1, K + 1)}, [])
cmap = {0x61: 'n1', 0x0628: 'n1', 0xFB50: 'n1', 0x0915: 'n1', 0x1000: 'n1', 0x1780: 'n1', 0x05D0: 'n1', 0x0E01: 'n1'}
make_font(sys.argv[1], names, {f'n{k}': 100 * (k + 1) for k in range(K)} | {'.notdef': 50}, cmap, gsub, gdef)
import uharfbuzz as hb
f = hb.Font(hb.Face(hb.Blob.from_file_path(sys.argv[1])))
for ch, nm in [('a', 'Latin'), ('ب', 'Arabic beh'), ('ﭐ', 'Arabic pres. form'), ('א', 'Hebrew'), ('ก', 'Thai')]:
    b = hb.Buffer(); b.add_str(ch); b.guess_segment_properties(); hb.shape(f, b, {})
    print(f'{nm:20s} script={b.script} glyph={names[b.glyph_infos[0].codepoint]} runs={b.glyph_infos[0].codepoint - 1}')
