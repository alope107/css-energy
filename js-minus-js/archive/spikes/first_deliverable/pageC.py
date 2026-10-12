# N lookup units, either via LUT font or via nested if() mux (64x64), same function f.
import base64, sys
f = lambda x: (x*x*7 + 3) % 65536
mode, N = sys.argv[1], int(sys.argv[2])
b64 = base64.b64encode(open('b.ttf','rb').read()).decode()
syms = " ".join(f'"\\{0xE000+i:X}"' for i in range(64))
units = "".join(f'<div class=u style="--i:{i}"><div class=probe></div><div class=rd><div class=out></div></div></div>' for i in range(N))
if mode == 'font':
    css = f"""
.u {{ position: relative; anchor-scope: --a; --xi: mod(calc(var(--x) + var(--i) * 37), 4096); height: 20px; }}
.probe {{ font: 16px LUT; font-feature-settings: "ss02" 1, "kern" 1; anchor-name: --a; width: fit-content; white-space: pre; counter-reset: c var(--xi); }}
.probe::before {{ content: counter(c, b64); }}
.rd {{ position: absolute; top: 0; left: 0; width: anchor-size(--a width); height: 1px; container-type: inline-size; }}
.out {{ --y: calc(100cqw * 64 / 1px); }}"""
else:
    hi = []
    for a in range(64):
        lo = "; ".join(f"style(--lo: {b}): {f(a*64+b)}" for b in range(64))
        hi.append(f"style(--hi: {a}): if({lo})")
    css = f"""
.u {{ --xi: mod(calc(var(--x) + var(--i) * 37), 4096); height: 20px; }}
.out {{ --hi: round(down, calc(var(--xi) / 64)); --lo: mod(var(--xi), 64); --y: if({'; '.join(hi)}); }}"""
html = f"""<!doctype html><meta charset=utf-8><style>
@font-face {{ font-family: LUT; src: url(data:font/ttf;base64,{b64}); }}
@property --x {{ syntax: '<integer>'; inherits: true; initial-value: 0; }}
@property --xi {{ syntax: '<integer>'; inherits: true; initial-value: 0; }}
@property --hi {{ syntax: '<integer>'; inherits: true; initial-value: 0; }}
@property --lo {{ syntax: '<integer>'; inherits: true; initial-value: 0; }}
@property --y {{ syntax: '<integer>'; inherits: false; initial-value: -1; }}
@counter-style b64 {{ system: numeric; symbols: {syms}; pad: 2 "\\E000"; }}
body {{ margin: 0; }} {css}
</style><div id=m>{units}</div>"""
open(f'C_{mode}_{N}.html','w').write(html)
