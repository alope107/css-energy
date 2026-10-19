"""Run the font CPU (uharfbuzz) on an image like hbtest.py and dump each shaping's input text (glyph ids as codepoints)
and timing. usage: dumptexts.py image.json font.ttf out.json [max]"""
import sys, json, copy, time, os
W = os.path.dirname(os.path.abspath(__file__)) + '/../repo/js-minus-js/machine'
sys.path.insert(0, W)
os.environ['CPUMOD'] = 'cpu4'
import uharfbuzz as hb
import cpu4, uarch4, hbtest
image = json.load(open(sys.argv[1])); fontp = sys.argv[2]; out = sys.argv[3]
maxsh = int(sys.argv[4]) if len(sys.argv) > 4 else 10**9
N, S = 16, 32
cpu = cpu4.CPU(image, N)
cpu.P.build(S, top13=cpu.top13, ptype='P', export_stage=cpu.export, debug_features=0)
cpu.adv = cpu.advances()
font = hb.Font(hb.Face(hb.Blob.from_file_path(fontp)))
m = uarch4.Machine4(image, N)
texts = []; t_hb = 0; shp = 0
while not m.halted and shp < maxsh:
    m.prologue(); st0 = hbtest.state_of(m); ref = copy.deepcopy(m); t_ref = ref.shaping(S)
    gl = cpu.encode(st0); text = ''.join(chr(0xF0000 + g) for g in gl)
    buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
    t0 = time.perf_counter(); hb.shape(font, buf, {'cv01': True}); t_hb += time.perf_counter() - t0
    gids = [i.codepoint for i in buf.glyph_infos]; st = cpu.decode(gids)
    texts.append(gl)
    m = ref; m.service(t_ref); shp += 1
print(f'{shp} shapings, {m.steps} steps, halted={m.halted}, hb {t_hb/shp*1e3:.2f} ms/shaping, script={buf.script} dir={buf.direction}')
json.dump(texts, open(out, 'w'))
