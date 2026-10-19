P = lambda n, s, init='0', inh='false': f"@property --{n}{{syntax:'{s}';inherits:{inh};initial-value:{init}}}"
regs = ''.join([P('v', '<integer>'), P('w', '<integer>'), P('n', '<number>'), P('a', '<integer>'), P('an', '<number>'),
                P('o', '<integer>', '0'), P('f', '<integer>', '0'), P('g', '<integer>', '7'), P('if1', '<integer>'), P('if2', '<integer>'),
                P('if3', '<integer>'), P('if4', '<integer>')])
cases = [  # id, container decls, query
 ('s1', '--a:256;--v:calc(var(--a) * 1)', 'style(--v: 256)'),
 ('s2', '--a:-1;--v:calc(var(--a) * 1)', 'style(--v: -1)'),
 ('s2b', '--v:-1', 'style(--v: -1)'),
 ('s3', '--a:300;--v:calc(var(--a) * 1)', 'style(--v: calc(300))'),
 ('s4', '--v:300', 'style(--v: calc(300))'),
 ('s5', '--an:300;--n:calc(var(--an) * 1)', 'style(--n: 300)'),
 ('s6', '--an:300.5;--n:calc(var(--an) * 1)', 'style(--n: 300.5)'),
 ('s7', '--a:1000;--v:calc(var(--a) * 1);--w:calc(var(--a) * 1)', 'style(--v: var(--w))'),
 ('s7b', '--a:1000;--v:calc(var(--a) * 1);--w:1000', 'style(--v: var(--w))'),
 ('s8', 'animation:kv 1s linear -0.5s paused both', 'style(--v: 1000)'),
 ('s9', '--a:300;--v:calc(var(--a) * 1)', 'style(--v >= 300) and style(--v <= 300)'),
 ('s10', '--a:255;--v:calc(var(--a) * 1)', 'style(--v: 255)'),
 ('s11', '--a:0;--v:calc(var(--a) * 1)', 'style(--v: 0)'),
 ('s12', '--a:300;--v:calc(var(--a) + 0)', 'style(--v: 300)'),
 ('s13', '--a:2;--v:calc(var(--a) * 128)', 'style(--v: 256)'),
 ('s14', '--v:calc(256)', 'style(--v: 256)'),
]
css = regs + '@keyframes kv{from{--v:0}to{--v:2000}}i{display:block;--o:0}'
for cid, decl, q in cases:
    css += f'#c{cid}{{container-type:normal;{decl}}}@container {q}{{#{cid}{{--o:1}}}}'
# if() variants, evaluated on the element itself (values set on the element)
css += '#f1{--a:256;--v:calc(var(--a) * 1);--o:if(style(--v: 256): 1; else: 0)}'
css += '#f2{--a:-1;--v:calc(var(--a) * 1);--o:if(style(--v: -1): 1; else: 0)}'
css += '#f3{--o:if(style(--f): 1; else: 0)}'          # registered, at initial 0
css += '#f4{--g:7;--o:if(style(--g): 1; else: 0)}'    # registered, explicitly at initial 7
css += '#f5{--o:if(style(--u): 1; else: 0)}'          # unregistered, undeclared
css += '#f6{--n:1048575;--o:if(style(--n: 1048580): 1; else: 0)}'  # false positive through 6 digits?
css += '@container style(--f){#b1{--o:1}}#cb1{container-type:normal}'
body = ''.join(f'<div id=c{c}><i id={c}></i></div>' for c, _, _ in cases)
body += ''.join(f'<i id=f{k}></i>' for k in range(1, 7)) + '<div id=cb1><i id=b1></i></div>'
open('style.html', 'w').write(f'<!doctype html><style>{css}</style>{body}')
