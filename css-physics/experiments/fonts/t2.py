import vf, sys
A = {'AAAA': vf.POS}; B = {'BBBB': vf.POS}; AB = {'AAAA': vf.POS, 'BBBB': vf.POS}
font = vf.build(['AAAA', 'BBBB'], [(0x30, 'zero', 4096, [(A, 8192)]), (0x6C34, 'water', 4096, [(AB, 8192)])], mvar={'xhgt': [(B, 4000)], 'cpht': [(A, 2000)]})
css = f"@font-face{{font-family:C;src:url(data:font/ttf;base64,{vf.b64(font)})}}"
for K in (100, 400):
    for mode in ('font4', 'font1', 'fontonly', 'calc', 'fontconst'):
        items = []
        for i in range(K):
            items.append(f'<i style="--k:{i}"></i>')
        if mode == 'calc':
            rule = "--o1:calc(var(--a) * 0.5 + 3);--o2:calc(var(--a) * var(--b) * 0.5);--o3:calc(var(--b) * 0.2);--o4:calc(var(--a) * 0.1)"
        elif mode == 'font4':
            rule = "font-variation-settings:'AAAA' var(--a),'BBBB' var(--b);--o1:1ch;--o2:1ic;--o3:1ex;--o4:1cap"
        elif mode == 'font1':
            rule = "font-variation-settings:'AAAA' var(--a),'BBBB' var(--b);--o1:1ch"
        elif mode == 'fontconst':
            rule = "font-variation-settings:'AAAA' calc(var(--k) * 30),'BBBB' 5;--o1:1ch;--o2:1ic"
        else:
            rule = "font-variation-settings:'AAAA' var(--a),'BBBB' var(--b)"
        html = f'''<!doctype html><style>{css}
@property --t{{syntax:'<number>';inherits:true;initial-value:0}}
@property --a{{syntax:'<number>';inherits:false;initial-value:0}}
@property --b{{syntax:'<number>';inherits:false;initial-value:0}}
@property --o1{{syntax:'<length>';inherits:false;initial-value:0px}}
@property --o2{{syntax:'<length>';inherits:false;initial-value:0px}}
@property --o3{{syntax:'<length>';inherits:false;initial-value:0px}}
@property --o4{{syntax:'<length>';inherits:false;initial-value:0px}}
@keyframes t{{from{{--t:0}}to{{--t:1000}}}}
#r{{animation:t 1000s linear infinite;font-family:C;font-size:16px;position:absolute;width:0;height:0;overflow:hidden;visibility:hidden}}
#r i{{--a:round(calc(sin(var(--t) + var(--k)) * 16000), 1);--b:round(calc(cos(var(--t) * 1.3 + var(--k)) * 16000), 1);{rule}}}
</style><div id=r>{''.join(items)}</div>'''
        open(f't2_{mode}_{K}.html', 'w').write(html)
