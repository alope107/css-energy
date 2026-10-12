# prototype: D nested levels, each recomputing P registered integer props (parity A/B) with if()/calc
import sys
D, P = int(sys.argv[1]), int(sys.argv[2])
props = []
for p in range(P):
    for par in 'AB':
        props.append(f'@property --s{p}{par} {{ syntax: "<integer>"; inherits: true; initial-value: 0; }}')
props.append('@property --c { syntax: "<integer>"; inherits: false; initial-value: 0; }')
css = []
for par, oth in (('A', 'B'), ('B', 'A')):
    decl = []
    for p in range(P):
        src = f'var(--s{p}{oth})'; nb = f'var(--s{(p * 7 + 3) % P}{oth})'
        decl.append(f'--s{p}{par}: if(style(--c: {p % 50}): mod(calc({src} + {nb} + 1), 1000003); else: mod(calc({src} * 3 + var(--c) + {p}), 1000003));')
    css.append(f'.L{par} {{ {" ".join(decl)} }}')
css.append('#root { ' + ' '.join(f'--s{p}B: {p};' for p in range(P)) + ' }')
body = ''.join(f'<div class="L{"A" if i % 2 == 0 else "B"}" style="--c: {(i * 37) % 97}">' for i in range(D)) + '<i id="out"></i>' + '</div>' * D
page = f'<?xml version="1.0" encoding="UTF-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><style><![CDATA[{chr(10).join(props + css)}]]></style></head><body><div id="root">{body}</div></body></html>'
open('proto.xhtml', 'w').write(page)
# expected
s = list(range(P))
for i in range(D):
    c = (i * 37) % 97
    s = [(s[p] + s[(p * 7 + 3) % P] + 1) % 1000003 if c == p % 50 else (s[p] * 3 + c + p) % 1000003 for p in range(P)]
import json; json.dump(s, open('proto.json', 'w'))
