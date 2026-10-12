import base64, sys, html

FONT, P, L, GS, OUT = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
assert P % GS == 0
NG = P // GS
font64 = base64.b64encode(open(FONT, 'rb').read()).decode()

def css_str(ch):
    return '"' + ch.replace('\\', '\\\\').replace('"', '\\"') + '"'
ascii_symbols = ' '.join(css_str(chr(c)) for c in range(32, 127))

gen = ['#ed::before { anchor-name: --s0; }']
for k in range(1, L):
    gen.append(f'#ed > div:nth-of-type({k})::after {{ anchor-name: --s{k}; }}')
for k in range(L):
    gen.append(f'.probe:nth-child({k + 1}) {{ --k: {k}; height: anchor-size(--s{k} width, 0px); }}')
for k in range(1, L):
    gen.append(f'#app:has(#ed > div:nth-of-type({k})) {{ --lines: {k + 1}; }}')
    gen.append(f'#app:not(:has(#ed > div:nth-of-type({k}))) .probe:nth-child({k + 1}) {{ display: none; }}')
gen.append(f'#app:has(#ed > div:nth-of-type({L})) .limit {{ display: block; }}')
# Scan position k (1-based column) -> font axis, group, local column, status counter.
for k in range(1, P + 1):
    if k <= P:
        G, j = (k - 1) // GS + 1, (k - 1) % GS + 1
        grp = f' .row > b:nth-child({G}) {{ --gj: {j}; }}'
    else:
        grp = ''
    axis = min(k, P)
    gen.append(f'@container scan style(--scan: {k}) {{ #ed {{ font-variation-settings: "SCAN" {axis}; }}{grp} .meta b {{ --col: {k}; }} }}')
# Scan range: hide groups past it (they are no longer refreshed) and show it in the status line.
for n in range(1, NG + 1):
    gen.append(f'@container scan style(--ng: {n}) {{ .row > b:nth-child({n}) ~ b {{ display: none; }} .meta s::before {{ content: "{n * GS}"; }} }}')
gen = '\n'.join(gen)

cells = ('<b>' + '<i></i>' * GS + '</b>') * NG
probes = '\n'.join(f'<div class="probe"><div class="row">{cells}</div></div>' for _ in range(L))

sample = ['Hello, World!',
          'Every character here is read back by CSS.',
          '',
          '  x = [1, 2, 3]; // {braces} "quotes" ~tilde']
editor_html = html.escape(sample[0]) + ''.join(f'<div>{html.escape(s) if s else "<br>"}</div>' for s in sample[1:])

page = open('template.html').read()
for k, v in {'__FONT__': font64, '__ASCII__': ascii_symbols, '__GEN__': gen, '__PROBES__': probes,
             '__EDITOR__': editor_html, '__P__': str(P), '__L__': str(L), '__GS__': str(GS),
             '__GSW__': str(GS * 10), '__NG__': str(NG)}.items():
    page = page.replace(k, v)
open(OUT, 'w').write(page)
print(OUT, len(page), 'bytes')
