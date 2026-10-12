# per-cycle compare from the start state of shaping X (model-driven)
import sys, json, copy
import uharfbuzz as hb
from cpu2 import CPU
import uarch
from hbtest import state_of
image = json.load(open('image.json')); N, S, X, K = map(int, sys.argv[1:5]); fields = sys.argv[5].split(',') if len(sys.argv) > 5 else []
cpu = CPU(image, N); cpu.P.assign_gids()
font = hb.Font(hb.Face(hb.Blob.from_file_path('cpu.ttf')))
m = uarch.Machine(image, N)
for _ in range(X): m.service(m.shaping(S))
st0 = state_of(m)
print('start', {k: st0[k] for k in ['pc', 'sp', 'fp', 'vp']}, st0['lines'])
text = ''.join(chr(0xF0000 + g) for g in cpu.encode(st0))
for k in range(1, K + 1):
    b = hb.Buffer(); b.add_str(text); b.guess_segment_properties(); hb.shape(font, b, {f'ss{k:02d}': True})
    gids = [i.codepoint for i in b.glyph_infos]; st = cpu.decode(gids)
    r = {(c.field if c.region == 'core' else f'L{c.line}.{c.field}'): cpu.P.by_gid[g][1] for c, g in zip(cpu.P.cells, gids)}
    ref = copy.deepcopy(m); t = ref.shaping(k)
    print(f'cycle {k}: C={st["C"]} pc={st["pc"]} sp={st["sp"]} fp={st["fp"]} MAR={st["mar"]} T1={st["t1"]} T2={st["t2"]} T3={st["t3"]} ' + ' '.join(f'{f}={r[f]}' for f in fields))
    print(f'   font  {st["lines"]} vp={st["vp"]}')
    print(f'   model {ref.lines} vp={ref.vp} pc={ref.pc} sp={ref.sp} fp={ref.fp} trap={t}')
