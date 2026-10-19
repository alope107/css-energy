# mkpage2.py MODE out.html : the CPU state line (173 spans) with every input cell changing each frame.
# MODE ctr: counters (counter-set on the span, counter() in ::before) ; if: content: if(style(--cP: d): "glyph"; ...)
import json, sys, itertools
mode, out = sys.argv[1], sys.argv[2]
m = json.load(open('f4cc_16.json')); cells = m['cells']
groups = []
for c in cells:
    if groups and groups[-1][0] == c['span']: groups[-1][1].append(c)
    else: groups.append((c['span'], [c]))
css, html, styles, props = [], [], {}, []
for gi, (name, cs) in enumerate(groups):
    parts, sets = [], []
    for c in cs:
        if c['input']:
            val = f"mod(var(--x) + {c['pos']}, {len(c['symbols'])})"
            if mode == 'ctr':
                sty = 'st-' + c['type'].replace('.', '-'); styles[sty] = c['symbols']
                sets.append(f"c{c['pos']} {val}"); parts.append(f"counter(c{c['pos']}, {sty})")
            else:
                props.append(f"@property --c{c['pos']} {{ syntax: '<integer>'; inherits: true; initial-value: 0; }}")
                sets.append(f"--c{c['pos']}: {val};")
                parts.append('if(' + ' '.join(f'style(--c{c["pos"]}: {d}): "\\{s:X} ";' for d, s in enumerate(c['symbols'])) + ')')
        else:
            parts.append('"\\%X "' % c['static'])
    rule = f".s{gi}::before {{ content: {' '.join(parts)}; }}"
    if sets: rule += (f" .s{gi} {{ counter-set: {' '.join(sets)}; }}" if mode == 'ctr' else f" .s{gi} {{ {' '.join(sets)} }}")
    css.append(rule)
    an = f' style="anchor-name: --a-{name}"' if name else ''
    html.append(f'<span class="s{gi}"{an}></span>')
for sty, syms in styles.items():
    css.append(f"@counter-style {sty} {{ system: fixed 0; symbols: {' '.join(chr(34) + chr(92) + '%X ' % s + chr(34) for s in syms)}; }}")
page = f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: FontCPU; src: url(f4cc_16.woff2); }}
@property --x {{ syntax: "<integer>"; inherits: true; initial-value: 0; }}
{chr(10).join(props)}
@keyframes k {{ from {{ --x: 0; }} to {{ --x: 16000; }} }}
#state {{ animation: k 270s steps(16000) infinite; position: fixed; top: 0; left: 0; font: 1024px/1 FontCPU; font-feature-settings: "cv01" 0; white-space: pre; width: max-content; visibility: hidden; }}
{chr(10).join(css)}
</style></head><body><div id="state">{''.join(html)}</div></body></html>'''
open(out, 'w').write(page)
