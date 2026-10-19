"""verify.py image.json font.ttf S_eff [features]: run the model with S_eff cycles per shaping and check every shaping
of the font (uharfbuzz) against it, as hbtest.py does. Dumps texts to texts_<tag>.txt if a 5th arg is given."""
import sys, os, json, copy, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../repo/js-minus-js/machine'); os.environ['CPUMOD'] = 'cpu4'
import cpugen as _cg
if os.environ.get('ORDER'):
    _order = json.load(open(os.environ['ORDER']))
    def _assign(self, start=1):
        g = start; names = [n for n in _order if n in self.types] + [n for n in self.types if n not in set(_order)]
        for n in names: t = self.types[n]; t.gid0 = g; g += len(t.values)
        self.nglyphs = g; self.by_gid = {}
        for t in self.types.values():
            for v in t.values: self.by_gid[t.g(v)] = (t, v)
    _cg.Program.assign_gids = _assign
import uharfbuzz as hb, cpu4, uarch4, hbtest
image = json.load(open(sys.argv[1])); fontp = sys.argv[2]; S = int(sys.argv[3])
feats = dict((f, True) for f in (sys.argv[4].split(',') if len(sys.argv) > 4 else ['cv01']))
dump = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] != '-' else None
cmapm = {int(k): v for k, v in json.load(open(sys.argv[6])).items()} if len(sys.argv) > 6 else None
cpu = cpu4.CPU(image, 16); cpu.P.build(32, top13=cpu.top13, ptype='P', export_stage=cpu.export, debug_features=0); cpu.adv = cpu.advances()
font = hb.Font(hb.Face(hb.Blob.from_file_path(fontp)))
m = uarch4.Machine4(image, 16); shp = 0; t_hb = 0; texts = []
while not m.halted:
    m.prologue(); st0 = hbtest.state_of(m); ref = copy.deepcopy(m); t_ref = ref.shaping(S)
    gl = cpu.encode(st0); texts.append(gl)
    cps = [0xF0000 + g for g in gl]
    if cmapm: cps = [cmapm[c] for c in cps]
    buf = hb.Buffer(); buf.add_str(''.join(map(chr, cps))); buf.guess_segment_properties()
    t0 = time.perf_counter(); hb.shape(font, buf, feats); t_hb += time.perf_counter() - t0
    gids = [i.codepoint for i in buf.glyph_infos]
    if buf.direction == 'rtl': gids = gids[::-1]
    st = cpu.decode(gids)
    want = dict(pc=ref.pc, sp=ref.sp, fp=ref.fp, resv=ref.resv, lines=ref.lines, vp=ref.vp)
    got = {k: st[k] for k in want}
    if got != want or hbtest.trap_of(st) != t_ref:
        print(f'MISMATCH at shaping {shp}: trap font={hbtest.trap_of(st)} model={t_ref}'); sys.exit(1)
    m = ref; m.service(t_ref); shp += 1
print(f'script {buf.script} dir {buf.direction}'); print(f'{fontp} S_eff={S}: {shp} shapings, {m.steps} steps, all match, output ok={"".join(map(chr, m.out)) == image.get("rawExpected", image["expected"])}, uharfbuzz {t_hb/shp*1e3:.2f} ms/shaping')
if dump: open(dump, 'w').write(''.join(' '.join(str(cmapm[0xF0000 + g] if cmapm else 0xF0000 + g) for g in t) + '\n' for t in texts))
