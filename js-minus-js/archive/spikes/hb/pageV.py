import base64, sys
N=int(sys.argv[1])
b64 = base64.b64encode(open('v.ttf','rb').read()).decode()
units = "".join(f'<div class=u style="--i:{i}"><div class=probe>&#xE000;</div><div class=rd><div class=out></div></div></div>' for i in range(N))
open(f'V_{N}.html','w').write(f"""<!doctype html><meta charset=utf-8><style>
@font-face {{ font-family: VLUT; src: url(data:font/ttf;base64,{b64}); }}
@property --x {{ syntax: '<integer>'; inherits: true; initial-value: 0; }}
@property --xi {{ syntax: '<integer>'; inherits: true; initial-value: 0; }}
@property --y {{ syntax: '<integer>'; inherits: false; initial-value: -1; }}
body {{ margin: 0; }}
.u {{ position: relative; anchor-scope: --a; --xi: mod(calc(var(--x) + var(--i) * 37), 4096); height: 20px; }}
.probe {{ font: 16px VLUT; font-variation-settings: "XVAL" calc(var(--xi) * 4); anchor-name: --a; width: fit-content; white-space: pre; color: transparent; }}
.rd {{ position: absolute; top: 0; left: 0; width: anchor-size(--a width); height: 1px; container-type: inline-size; }}
.out {{ --y: calc(100cqw * 64 / 1px); }}
</style><div id=m>{units}</div>""")
