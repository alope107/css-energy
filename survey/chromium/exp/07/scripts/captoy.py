import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../repo/js-minus-js/machine')
from otl import single_subst, Lookup, build_gsub, build_gdef
from fontbase import make_font
names = ['.notdef', 'n1', 'n2']
N = int(sys.argv[2])
lk = [Lookup(1, [single_subst({1: 2, 2: 1})], None, 'tog')]
gsub = build_gsub(lk, [0] * N, [('cv01', list(range(N)))])
make_font(sys.argv[1], names, {'.notdef': 50, 'n1': 200, 'n2': 300}, {0x61: 'n1', 0x62: 'n1'}, gsub, build_gdef({1: 1, 2: 1}, []))
