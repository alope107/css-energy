#!/usr/bin/env python3
"""diag.py out.html — pure-CSS diagnostic: shape known CPU states with the real fonts and show, per span,
the width Chrome measures next to the width HarfBuzz (uharfbuzz) computes. No script in the page."""
import json, sys, base64, copy
import uharfbuzz as hb
import uarch, zoomfix
from cpu2 import CPU
from hbtest import state_of

def states_for(image, N, S, picks):
    m = uarch.Machine(image, N); out = {}; n = 0
    while not m.halted and n <= max(picks):
        if n in picks: out[n] = state_of(m)
        t = m.shaping(S); m.service(t); n += 1
    return out

blocks = []      # (title, font_family, feature, text_spans[(name, text)], expected{name: w})
fonts = []
for img, pre, N, S, picks in [('direct.json', 'fdir', 16, 16, [0, 120]), ('direct.json', 'fdir32', 32, 32, [0, 80])]:
    image = json.load(open(img)); meta = json.load(open(pre + '.json'))
    cpu = CPU(image, N); cpu.P.assign_gids()
    font = hb.Font(hb.Face(hb.Blob.from_file_path(pre + '.ttf')))
    fam = 'F' + pre; fonts.append(f"@font-face {{ font-family: {fam}; src: url(data:font/woff2;base64,{base64.b64encode(open(pre + '.woff2', 'rb').read()).decode()}); }}")
    for sh, st in states_for(image, N, S, picks).items():
        gl = cpu.encode(st)
        text = ''.join(chr(0xF0000 + g) for g in gl)
        for feat in ['cv02', 'cv01']:
            b = hb.Buffer(); b.add_str(text); b.guess_segment_properties(); hb.shape(font, b, {feat: True})
            exp = {}
            for c, p in zip(meta['cells'], b.glyph_positions):
                if c['span']: exp[c['span']] = exp.get(c['span'], 0) + p.x_advance
            # group cells into spans of the page
            groups = []
            for c, g in zip(meta['cells'], gl):
                key = c['span']
                if groups and groups[-1][0] == key: groups[-1][1].append(g)
                else: groups.append((key, [g]))
            blocks.append((f'{pre} #{sh} {feat}', fam, feat, groups, exp, list(dict.fromkeys(c["span"] for c in meta["cells"] if c["span"]))))

css = ["""@property --m { syntax: "<integer>"; inherits: true; initial-value: -1; }
@property --d { syntax: "<integer>"; inherits: true; initial-value: -1; }
html { overflow-x: clip; } body { font: 13px/1.3 ui-monospace, monospace; margin: 16px; overflow-x: clip; }
.st { position: fixed; top: 0; left: 0; font-size: calc(1024px / var(--R)); line-height: 1; white-space: pre; width: max-content; visibility: hidden; }
.rb { position: absolute; height: 15px; container-type: inline-size; }
.rv { --d: calc(var(--m) - var(--e)); counter-set: m var(--m) d var(--d); white-space: pre; width: max-content;
      color: if(style(--d: 0): #070; else: #c00); font-weight: if(style(--d: 0): 400; else: 700); }
.rv::after { content: var(--n) " " counter(m) " (" counter(d) ")"; }
h2 { font-size: 13px; position: absolute; margin: 0; }
p { max-width: 60em; }"""] + [zoomfix.css()] + fonts
html = []
ROW, COLW, TOP = 16, 230, 120
col = 0; sec_top = TOP; prev_pre = None; maxrows = 0
for bi, (title, fam, feat, groups, exp, names) in enumerate(blocks):
    pre = title.split()[0]
    if prev_pre and pre != prev_pre: sec_top += (maxrows + 3) * ROW; col = 0; maxrows = 0
    prev_pre = pre
    spans = ''.join(f'<span style="anchor-name: --b{bi}-{k}">' + ''.join('&#x%X;' % (0xF0000 + g) for g in gs) + '</span>' if k else
                    '<span>' + ''.join('&#x%X;' % (0xF0000 + g) for g in gs) + '</span>' for k, gs in groups)
    html.append(f'<div class="st" style="font-family: {fam}; font-feature-settings: \'{feat}\' 1">{spans}</div>')
    x = 16 + col * COLW
    html.append(f'<h2 style="left: {x}px; top: {sec_top - ROW - 4}px">{title}</h2>')
    for r, n in enumerate(names):
        html.append(f'<div class="rb" style="left: {x}px; top: {sec_top + r * ROW}px; width: anchor-size(--b{bi}-{n} width)">'
                    f'<div class="rv" style="--m: calc(100cqi / 1px * var(--R)); --e: {exp[n]}; --n: \'{n}\'"></div></div>')
    maxrows = max(maxrows, len(names)); col += 1
page = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Font CPU diagnostic</title>
<style>{chr(10).join(css)}</style>
<p><b>Font CPU diagnostic.</b> Each line: span name, width Chrome measured (in px, 1 font unit = 1px), and in brackets
measured minus what HarfBuzz computes. Green (0) = match, red = mismatch. <b>cv02</b> = no CPU cycles (tests glyph metrics only);
<b>cv01</b> = full shaping (tests GSUB). Screenshot the whole page, including anything red.</p>
{chr(10).join(html)}
<div style="height: {sec_top + (maxrows + 4) * ROW}px"></div></html>"""
open(sys.argv[1], 'w').write(page)
print(len(page), 'bytes', len(blocks), 'blocks')
