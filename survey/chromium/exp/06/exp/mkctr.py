# mkctr.py MODE N out.html : MODE = ctr (counter-set changes every frame) | wid (width changes every frame, no counters)
import sys
mode, n, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
groups = max(1, n // 250)
per = n // groups if n else 0
big = ''.join('<div>' + '<i></i>' * per + '</div>' for _ in range(groups)) if n else ''
if mode == 'ctr':
    s_css = '.s { animation: k 1s linear infinite; counter-set: c var(--x); } .s::before { content: counter(c); }'
else:
    s_css = '.s { animation: k 1s linear infinite; display: inline-block; width: calc(var(--x) * 0.01px); } .s::before { content: "7"; }'
html = f'''<!doctype html><html><head><meta charset="utf-8"><style>
@property --x {{ syntax: "<integer>"; inherits: false; initial-value: 0; }}
@keyframes k {{ from {{ --x: 0; }} to {{ --x: 100000; }} }}
#big i {{ display: block; height: 0; }}
{s_css}
</style></head><body><span class="s"></span><div id="big">{big}</div></body></html>'''
open(out, 'w').write(html)
