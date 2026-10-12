import json, sys, time
import uharfbuzz as hb
import hbtest
from hbtest import state_of
image = json.load(open('image.json')); N = 16
cpu = hbtest.build(image, N, 2, path='b2.ttf')
f1 = hb.Font(hb.Face(hb.Blob.from_file_path('b2.ttf'))); f2 = hb.Font(hb.Face(hb.Blob.from_file_path('ablk.ttf')))
m = hbtest.MACH(image, N); texts = []; i = 0
while not m.halted and len(texts) < 10:
    if i % 61 == 0: texts.append(''.join(chr(0xF0000 + g) for g in cpu.encode(state_of(m))))
    m.service(m.shaping(16)); i += 1
for f, name, ft in [(f1, 'b2 cv01', 'cv01'), (f2, 'ablk cvtt', 'cvtt'), (f2, 'ablk cv01', 'cv01')]:
    tot = 0; outs = []
    for t in texts:
        best = 1e9
        for _ in range(5):
            b = hb.Buffer(); b.add_str(t); b.guess_segment_properties()
            t0 = time.perf_counter(); hb.shape(f, b, {ft: True}); best = min(best, time.perf_counter() - t0)
        tot += best; outs.append([x.codepoint for x in b.glyph_infos])
    print(name, round(tot / len(texts) * 1e3, 2), 'ms', hash(str(outs[3][:400])))
