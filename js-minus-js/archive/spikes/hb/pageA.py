import base64, sys
fonts = sys.argv[1:]
css = "".join(f"@font-face{{font-family:F{i};src:url(data:font/ttf;base64,{base64.b64encode(open(f,'rb').read()).decode()})}}\n.f{i}{{font-family:F{i}}}\n" for i,f in enumerate(fonts))
open('A.html','w').write(f"""<!doctype html><style>{css}
span{{font-size:100px;white-space:pre;font-feature-settings:"ss01" 1;font-kerning:none}}
.off{{font-feature-settings:normal}}</style>
""" + "".join(f'<div><span id=s{i} class="f{i}">&#xE000;</span></div><div><span id=o{i} class="f{i} off">&#xE000;</span></div>' for i in range(len(fonts))))
