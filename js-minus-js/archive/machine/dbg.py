import sys, json, copy
import uharfbuzz as hb
from cpu import CPU
import uarch
from hbtest import state_of
image = json.load(open('image.json')); N = int(sys.argv[1]); K = int(sys.argv[2])
cpu = CPU(image, N); cpu.P.assign_gids()
font = hb.Font(hb.Face(hb.Blob.from_file_path('cpu.ttf')))
m = uarch.Machine(image, N); m.prologue(); st0 = state_of(m)
text = ''.join(chr(0xF0000 + g) for g in cpu.encode(st0))
def raw(gids):
    return {c.field if c.region == 'core' else f'{c.region}{c.line}.{c.field}': cpu.P.by_gid[g][1] for c, g in zip(cpu.P.cells, gids)}
for k in range(1, K + 1):
    b = hb.Buffer(); b.add_str(text); b.guess_segment_properties(); hb.shape(font, b, {f'ss{k:02d}': True})
    gids = [i.codepoint for i in b.glyph_infos]; st = cpu.decode(gids); r = raw(gids)
    ref = copy.deepcopy(m); t = ref.shaping(k)
    show = lambda pre: ' '.join(f'{f}={r[pre+f]}' for f in ['VD', 'BOP', 'SH'])
    print(f'cycle {k}: C={st["C"]} MOP={r["MOP"]} MAR={st["mar"]} T1={st["t1"]} OK={r["OK"]} HIT={r["HIT"]} FAIL={r["FAIL"]} VDL={r["VDL"]} EFREE={r["EFREE"]}')
    print(f'   font lines {st["lines"]} E={st["evict"]} pc={st["pc"]} sp={st["sp"]}')
    print(f'   model      {ref.lines} E={ref.evict} pc={ref.pc} sp={ref.sp}')
    for i in range(N + 2): print('     ', i, show(f'{"E" if i == 0 else "I" if i == N + 1 else "L"}{i}.'))
