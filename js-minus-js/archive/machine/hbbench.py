"""hbbench.py image.json N S — robust full-shaping time (cv01): min of 7 runs per state over 25 sampled states."""
import json, sys, os, time, importlib
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
def shape(t):
    b = hb.Buffer(); b.add_str(t); b.guess_segment_properties(); hb.shape(font, b, {'cv01': True})
tot = 0
for t in texts:
    best = 1e9
    for _ in range(7):
        t0 = time.perf_counter(); shape(t); best = min(best, time.perf_counter() - t0)
    tot += best
print(f'{os.environ.get("CPUMOD", "cpu2")} N={N} S={S}: {tot / len(texts) * 1e3:.2f} ms/shaping (min-of-7, {len(texts)} states)')
