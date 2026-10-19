# mkpage.py FONT NAXES MODE TR out.html ; MODE: anim (new coords per element per frame) | fixed | nofont
import sys
font, n, mode, tr, out = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
N = 400
t = 'var(--t)' if mode == 'anim' else '0'
fvs = ', '.join(f'"A{j:03d}" calc(mod({t} * {7 + j} + sibling-index() * {13 + 2 * j}, 1000))' for j in range(n))
el = (f'font-variation-settings: {fvs}; width: 1ch; height: 1ex;' if mode != 'nofont'
      else f'width: calc(mod({t} * 7 + sibling-index() * 13, 1000) * 0.01px); height: 1px;')
page = f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: VF; src: url({font}); }}
@property --t {{ syntax: "<number>"; inherits: true; initial-value: 0; }}
@keyframes k {{ from {{ --t: 0; }} to {{ --t: 10000; }} }}
#w {{ animation: k 100s linear infinite; font: 16px VF; text-rendering: {tr}; }}
#w i {{ display: block; {el} }}
</style></head><body><span style="font: 16px VF">0x</span><div id="w">{'<i></i>' * N}</div></body></html>'''
open(out, 'w').write(page)
