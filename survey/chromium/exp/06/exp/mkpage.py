# mkpage.py MERGE FEAT out.html : the CPU page's state-line structure (173 spans, ::before counters + statics)
import json, sys, itertools
merge, feat, out = sys.argv[1] == '1', sys.argv[2], sys.argv[3]
m = json.load(open('f4cc_16.json')); cells = m['cells']
groups = []
for c in cells:
    if groups and groups[-1][0] == c['span']: groups[-1][1].append(c)
    else: groups.append((c['span'], [c]))
css, html, styles = [], [], {}
first = True
for gi, (name, cs) in enumerate(groups):
    parts, sets = [], []
    for isinp, g in itertools.groupby(cs, key=lambda c: bool(c['input'])):
        g = list(g)
        if isinp:
            for c in g:
                sty = 'st-' + c['type'].replace('.', '-'); styles[sty] = c['symbols']
                val = 'var(--x)' if first else '0'; first = False
                sets.append(f"c{c['pos']} {val}"); parts.append(f"counter(c{c['pos']}, {sty})")
        else:
            if merge: parts.append('"' + ''.join('\\%X ' % c['static'] for c in g) + '"')
            else: parts += ['"\\%X "' % c['static'] for c in g]
    css.append(f".s{gi}::before {{ content: {' '.join(parts)}; }}" + (f" .s{gi} {{ counter-set: {' '.join(sets)}; }}" if sets else ''))
    an = f' style="anchor-name: --a-{name}"' if name else ''
    html.append(f'<span class="s{gi}"{an}></span>')
for sty, syms in styles.items():
    css.append(f"@counter-style {sty} {{ system: fixed 0; symbols: {' '.join(chr(34) + chr(92) + '%X ' % s + chr(34) for s in syms)}; }}")
page = f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: FontCPU; src: url(f4cc_16.woff2); }}
@property --x {{ syntax: "<integer>"; inherits: true; initial-value: 0; }}
@keyframes k {{ from {{ --x: 0; }} to {{ --x: 1600; }} }}
#state {{ animation: k 1s steps(1600) infinite; position: fixed; top: 0; left: 0; font: 1024px/1 FontCPU; font-feature-settings: "cv01" {feat}; white-space: pre; width: max-content; visibility: hidden; }}
{chr(10).join(css)}
</style></head><body><div id="state">{''.join(html)}</div></body></html>'''
open(out, 'w').write(page)
