import base64
b64 = base64.b64encode(open('b.ttf','rb').read()).decode()
syms = " ".join(f'"\\{0xE000+i:X}"' for i in range(64))
html = f"""<!doctype html><meta charset=utf-8><style>
@font-face {{ font-family: LUT; src: url(data:font/ttf;base64,{b64}); }}
@property --x {{ syntax: '<integer>'; inherits: true; initial-value: 0; }}
@property --y {{ syntax: '<integer>'; inherits: true; initial-value: 0; }}
@counter-style b64 {{ system: numeric; symbols: {syms}; pad: 2 "\\E000"; }}
@keyframes run {{ from {{ --x: 0; }} to {{ --x: 4096; }} }}
body {{ margin: 0; }}
#m {{ animation: run 68.2667s linear infinite; position: relative; }}
#probe {{ font: 16px LUT; font-feature-settings: "ss02" 1, "kern" 1; anchor-name: --a; width: fit-content;
          white-space: pre; counter-reset: c var(--x); }}
#probe::before {{ content: counter(c, b64); }}
#rd {{ position: absolute; top: 40px; left: 0; width: anchor-size(--a width); height: 10px; container-type: inline-size; }}
#out {{ --y: calc(100cqw * 64 / 1px); counter-reset: y var(--y); font: 14px monospace; }}
#out::after {{ content: "y=" counter(y); }}
</style>
<div id=m><div id=probe></div><div id=rd><div id=out></div></div></div>"""
open('B.html','w').write(html)
