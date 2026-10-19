import sys, os
out=sys.argv[1]; E=100
def page(name,R,K):
    css=[f"@property --u{i}{{syntax:'<number>';inherits:false;initial-value:0}}" for i in range(R)]
    css+=["@property --t{syntax:'<number>';inherits:true;initial-value:0}","@keyframes tt{from{--t:0}to{--t:1000}}","#p{animation:tt 10s linear infinite}",
          "@property --odd{syntax:'<integer>';inherits:false;initial-value:0}",".c{width:4px;height:4px;display:inline-block}"]
    for k in range(K):
        css.append(f"@property --x{k}{{syntax:'<number>';inherits:false;initial-value:0}}")
        css.append(f"@keyframes a{k}{{from{{--x{k}:0}}to{{--x{k}:1}}}}")
    names=",".join(f"a{k}" for k in range(K))
    css.append(f".c{{--odd:calc(mod(round(var(--t) * 7), 2));animation-name:{names};animation-timing-function:linear;animation-iteration-count:infinite;animation-duration:if(style(--odd: 1): 1000ms; else: 1001ms)}}")
    open(os.path.join(out,name),'w').write("<!doctype html><style>"+"\n".join(css)+"</style><div id=p>"+"<i class=c></i>"*E+"</div>")
for R in (0,4000):
    for K in (1,16):
        page(f"m_R{R}_K{K}.html",R,K)
