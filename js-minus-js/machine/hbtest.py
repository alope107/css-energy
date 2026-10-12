#!/usr/bin/env python3
"""hbtest.py image.json N S [maxshapings] — build the font CPU and run it in real HarfBuzz against uarch.py.

Each shaping: encode the model state as text, shape with cv01 (S cycles), decode, compare persistent state
and trap with the model's own shaping(S) from the same start state; then service with the model's code.
"""
import sys, json, copy, time
import uharfbuzz as hb
import importlib, os
CPU = importlib.import_module(os.environ.get('CPUMOD', 'cpu2')).CPU
from fontbase import make_font
import uarch, uarch4
MACH = uarch4.Machine4 if os.environ.get('CPUMOD', 'cpu2') == 'cpu4' else uarch.Machine

def build(image, N, S, path='cpu.ttf'):
    t0 = time.time()
    cpu = CPU(image, N)
    gsub = cpu.P.build(S, top13=cpu.top13, ptype='P', export_stage=cpu.export, debug_features=int(os.environ.get('DBGF', 0)))
    from otl import build_gdef
    twins = {g for t in cpu.twin.values() for g in t.gl()}
    gdef = build_gdef({g: (1 if g in twins else 3) for g in range(1, cpu.P.nglyphs)}, cpu.P.mark_sets)
    names = ['.notdef'] + [f'g{g}' for g in range(1, cpu.P.nglyphs)]
    cmap = {0xF0000 + g: f'g{g}' for g in range(1, cpu.P.nglyphs) if g not in twins}
    cpu.adv = cpu.advances()
    make_font(path, names, {names[g]: a for g, a in cpu.adv.items()}, cmap, gsub, gdef)
    print(f'built: {cpu.P.nglyphs} glyphs, {len(cpu.P.cells)} cells, {len(cpu.P.cycle_lookups)} lookups/cycle, '
          f'{cpu.P.subtables_per_cycle} subtables/cycle, {cpu.P.lib_subtables} lib, GSUB {len(gsub)/1e6:.2f} MB, {time.time()-t0:.1f}s', flush=True)
    return cpu

def state_of(m):
    return dict(pc=m.pc, sp=m.sp, fp=m.fp, res=m.res, resv=m.resv, lines=copy.deepcopy(m.lines), vp=m.vp)

def trap_of(st):
    C = st['C']
    if C[0] != 'T': return None
    k = C[1]
    if k == 'MISS': return ('MISS', st['mar'])
    if k.startswith('EXT_'):
        op = k[4:]
        return ('EXT', op, st['t1'] if op == 'SHL13' else st['t2'], st['t1'])
    if k == 'PUTC': return ('PUTC', st['t1'])
    return (k,)

def main():
    image = json.load(open(sys.argv[1])); N = int(sys.argv[2]); S = int(sys.argv[3])
    maxsh = int(sys.argv[4]) if len(sys.argv) > 4 else 10 ** 9
    cpu = build(image, N, S)
    font = hb.Font(hb.Face(hb.Blob.from_file_path('cpu.ttf')))
    m = MACH(image, N)
    shp = 0; t_hb = 0.0
    while not m.halted and shp < maxsh:
        m.prologue()
        st0 = state_of(m)
        ref = copy.deepcopy(m)
        t_ref = ref.shaping(S)
        assert st0 is not None
        text = ''.join(chr(0xF0000 + g) for g in cpu.encode(st0))
        buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
        t0 = time.perf_counter(); hb.shape(font, buf, {'cv01': True}); t_hb += time.perf_counter() - t0
        gids = [i.codepoint for i in buf.glyph_infos]
        st = cpu.decode(gids)
        sw = cpu.decode_spans(cpu.span_values(gids, cpu.adv))
        hbw = sum(p.x_advance for p in buf.glyph_positions); assert hbw == sum(cpu.span_values(gids, cpu.adv).values()), 'advance mismatch'
        for key in ['C', 'resv', 'ni', 'pc', 'sp', 'fp', 'mar', 't1', 't2', 'lines', 'vp']:
            assert sw[key] == st[key], ('span decode', key, sw[key], st[key])
        tr = trap_of(st)
        want = dict(pc=ref.pc, sp=ref.sp, fp=ref.fp, resv=ref.resv, lines=ref.lines, vp=ref.vp)
        got = {k: st[k] for k in want}
        if sw['ni'] != ref.steps - m.steps: print('NI mismatch', sw['ni'], ref.steps - m.steps); return 1
        if got != want or tr != t_ref:
            print(f'MISMATCH at shaping {shp}: trap font={tr} model={t_ref}')
            for k in want:
                if got[k] != want[k]: print(f'  {k}: font={got[k]}\n  {" " * len(k)}  model={want[k]}')
            print('  start state pc', st0['pc'], 'sp', st0['sp'], 'fp', st0['fp'], 'font C', st['C'])
            return 1
        m = ref; m.service(t_ref); shp += 1
        if shp % 200 == 0: print(f'  {shp} shapings ok, {m.steps} steps, hb {t_hb/shp*1e3:.2f} ms/shaping', flush=True)
    out = ''.join(map(chr, m.out))
    print(f'done: {shp} shapings, {m.steps} steps, halted={m.halted}, output ok={out == image["expected"]}, hb {t_hb/max(1,shp)*1e3:.2f} ms/shaping')
    return 0

if __name__ == '__main__':
    sys.exit(main())
