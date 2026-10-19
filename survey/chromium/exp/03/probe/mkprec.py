# precision probes: each element computes --d (registered <number>) from a value that crossed var()
P = lambda n, s, init='0', inh='false': f"@property --{n}{{syntax:'{s}';inherits:{inh};initial-value:{init}}}"
regs = [P('d', '<number>'), P('a', '<integer>'), P('xi', '<integer>'), P('xn', '<number>'), P('xl', '<length>', '0px'),
        P('xp', '<percentage>', '0%'), P('xlp', '<length-percentage>', '0px'), P('xa', '<integer>'), P('xan', '<number>'),
        P('xc', '<number>'), P('xci', '<integer>'), P('xt', '<time>', '0s'), P('xg', '<angle>', '0deg')]
regs.append("@property --xu{syntax:'*';inherits:false}")
css = ''.join(regs) + '''
i{display:block}
#p1{--xi:1048575;--d:calc(var(--xi) - 1048570)}
#p2{--a:1048000;--xi:calc(var(--a) + 575);--d:calc(var(--xi) - 1048570)}
#p3{--xn:1048575;--d:calc(var(--xn) - 1048570)}
#p3b{--xn:1234.5678;--d:calc((var(--xn) - 1234) * 10000)}
#p3c{--xn:999999;--d:calc(var(--xn) - 999990)}
#p3d{--xn:1000001;--d:calc(var(--xn) - 999990)}
#p4{--xl:1048575px;--d:calc((var(--xl) - 1048570px) / 1px)}
#p4b{--a:1048000;--xl:calc(var(--a) * 1px + 575px);--d:calc((var(--xl) - 1048570px) / 1px)}
#p4c{--xl:16777217px;--d:calc((var(--xl) - 16777210px) / 1px)}
#p5{--xp:1048575%;--d:calc((var(--xp) - 1048570%) / 1%)}
#p6{--xlp:1048575px;--d:calc((var(--xlp) - 1048570px) / 1px)}
#p7{--a:1048000;--xu:calc(var(--a) + 575);--d:calc(var(--xu) - 1048570)}
#p8{--a:1048000;--xr:calc(var(--a) + 575);--d:calc(var(--xr) - 1048570)}
@keyframes ki{from{--xa:0}to{--xa:2097150}}
@keyframes kn{from{--xan:0}to{--xan:2097150}}
#p9{animation:ki 1s linear -0.5s paused both;--d:calc(var(--xa) - 1048570)}
#p9b{animation:kn 1s linear -0.5s paused both;--d:calc(var(--xan) - 1048570)}
#p10{--d:calc(attr(data-v type(<integer>)) - 1048570)}
#p10b{--d:calc(attr(data-v type(<number>)) - 1048570)}
#p10c{--d:calc(attr(data-v type(*)) - 1048570)}
#p11{--xi:3000000000;--d:calc(var(--xi) - 2147483640)}
#p12{--a:-1048000;--xi:calc(var(--a) - 575);--d:calc(var(--xi) + 1048570)}
#p13{--xn:0.1234567;--d:calc((var(--xn) - 0.1234) * 10000000)}
.box{position:relative;width:1048575px;height:10px;container-type:size}
#p14{--xc:calc(100cqw / 1px);--d:calc(var(--xc) - 1048570)}
#p14b{--xcu:calc(100cqw / 1px);--d:calc(var(--xcu) - 1048570)}
#p14c{--xci:calc(100cqw / 1px);--d:calc(var(--xci) - 1048570)}
#p15{--xt:1048.575s;--d:calc((var(--xt) - 1048.57s) / 1ms)}
#p16{--a:1048000;--xi:calc(var(--a) + 575);--d:calc(var(--xi) - 1048570);--ser:var(--xi)}
'''
body = ''.join(f'<i id={i}></i>' for i in ['p1','p2','p3','p3b','p3c','p3d','p4','p4b','p4c','p5','p6','p7','p8','p9','p9b','p11','p12','p13','p15'])
body += '<i id=p10 data-v="1048575"></i><i id=p10b data-v="1048575"></i><i id=p10c data-v="1048575"></i>'
body += '<div class=box><i id=p14></i><i id=p14b></i><i id=p14c></i></div><i id=p16 data-read="--d --xi --ser"></i>'
open('prec.html', 'w').write(f'<!doctype html><style>{css}</style><body style="margin:0;overflow:hidden">{body}</body>')
