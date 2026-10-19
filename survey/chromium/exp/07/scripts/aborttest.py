"""Does a self-recursive contextual lookup (nesting > 64) abort the rest of GSUB? Toy font via otl.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../repo/js-minus-js/machine')
from otl import chain_class, single_subst, reverse_chain, Lookup, build_gsub, build_gdef
from fontbase import make_font
import uharfbuzz as hb
names = ['.notdef', 'a', 'b', 'c', 'd']; A, B, C, D = 1, 2, 3, 4
def font(path, with_abort):
    lk = [Lookup(6, [chain_class([A], {}, {A: 1}, {}, [([], 1, [], [(0, 0)])])], None, 'abort'),
          Lookup(1, [single_subst({B: C})], None, 'b2c'),
          Lookup(8, [reverse_chain({B: D}, [], [])], None, 'rb2d')]
    feats = [('cv01', [0, 1, 2] if with_abort else [1, 2])]
    gsub = build_gsub(lk, [0, 1, 2], feats)
    gdef = build_gdef({g: 1 for g in range(1, 5)}, [])
    make_font(path, names, {n: 100 * i for i, n in enumerate(names)}, {0x61: 'a', 0x62: 'b'}, gsub, gdef)
for wa in (0, 1):
    p = f'{sys.argv[1]}/abort{wa}.ttf'; font(p, wa)
    f = hb.Font(hb.Face(hb.Blob.from_file_path(p)))
    for text in ('ab', 'ba', 'bab'):
        buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
        hb.shape(f, buf, {'cv01': True})
        print('abort lookup' if wa else 'no abort    ', text, [names[i.codepoint] for i in buf.glyph_infos], [p.x_advance for p in buf.glyph_positions])
