import json, sys, os, time
import uharfbuzz as hb
import hbtest
from hbtest import state_of
image = json.load(open(sys.argv[1])); N = int(sys.argv[2])
res = {}
for S, feat in [(2, 'cv01'), (16, 'ss02'), (4, 'cv01'), (16, 'ss04'), (16, 'cv01')]:
    cpu = hbtest.build(image, N, S, path=f'b{S}.ttf')
    font = hb.Font(hb.Face(hb.Blob.from_file_path(f'b{S}.ttf')))
    m = hbtest.MACH(image, N); texts = []; i = 0
    while not m.halted and len(texts) < 20:
        if i % 37 == 0: texts.append(''.join(chr(0xF0000 + g) for g in cpu.encode(state_of(m))))
        m.service(m.shaping(16)); i += 1
    tot = 0
    for t in texts:
        best = 1e9
        for _ in range(7):
            b = hb.Buffer(); b.add_str(t); b.guess_segment_properties()
            t0 = time.perf_counter(); hb.shape(font, b, {feat: True}); best = min(best, time.perf_counter() - t0)
        tot += best
    res[f'S={S} {feat}'] = round(tot / len(texts) * 1e3, 2)
print(res)
