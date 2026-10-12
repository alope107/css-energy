import json, sys, os, time
import uharfbuzz as hb
import hbtest
from hbtest import state_of
image = json.load(open(sys.argv[1])); N, S = int(sys.argv[2]), int(sys.argv[3])
cpu = hbtest.build(image, N, S, path='bench.ttf')
font = hb.Font(hb.Face(hb.Blob.from_file_path('bench.ttf')))
m = hbtest.MACH(image, N); texts = []; i = 0
while not m.halted and len(texts) < 25:
    if i % 37 == 0: texts.append(''.join(chr(0xF0000 + g) for g in cpu.encode(state_of(m))))
    m.service(m.shaping(S)); i += 1
def run(feat):
    tot = 0
    for t in texts:
        best = 1e9
        for _ in range(7):
            b = hb.Buffer(); b.add_str(t); b.guess_segment_properties()
            t0 = time.perf_counter(); hb.shape(font, b, feat); best = min(best, time.perf_counter() - t0)
        tot += best
    return tot / len(texts) * 1e3
print({f: round(run({f: True} if f else {}), 2) for f in ['cv01', 'cv02', 'ss01', 'ss04', 'ss08', None]})
