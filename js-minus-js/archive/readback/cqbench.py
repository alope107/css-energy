import sys
mode, N, R = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
css = ['@property --k { syntax: "<integer>"; inherits: false; initial-value: 0; }', '@property --z { syntax: "<integer>"; inherits: false; initial-value: 0; }']
if mode == 'reg':
    css.append('.lv { --k: calc(mod(sibling-index() * 7, 5) + 1000); }')
    css += [f'@container style(--k: {i}) {{ .lv {{ --z: {i}; }} }}' for i in range(R)]
elif mode == 'unreg':
    css.append('.lv { --u: if(style(--k2: 1): a; else: b); }')
    css += [f'@container style(--u: x{i}) {{ .lv {{ --z: {i}; }} }}' for i in range(R)]
elif mode == 'none':
    css += [f'.lv.x{i} {{ --z: {i}; }}' for i in range(R)]
elif mode == 'name':
    css.append('.lv { container-name: zz; }')
    css += [f'@container q{i} style(--k: {i}) {{ .lv {{ --z: {i}; }} }}' for i in range(R)]
html = '<div class="lv">' * N + '</div>' * N
open(f'cq_{mode}.html', 'w').write(f'<!doctype html><style>{chr(10).join(css)}</style>{html}')
