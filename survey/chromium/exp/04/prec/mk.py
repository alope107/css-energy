import sys
# view-timeline register precision probe: subject at top = base + k/64 px in a scroller of height V
V=int(sys.argv[2]); base=float(sys.argv[3]); out=sys.argv[1]; OFF=int(sys.argv[4]) if len(sys.argv)>4 else 0
css=["@property --x{syntax:'<number>';inherits:false;initial-value:-1}",
     f"@keyframes q{{from{{--x:{-OFF}}}to{{--x:{16*V-OFF}}}}}",
     f".sc{{position:relative;height:{V}px;width:20px;overflow:hidden;display:inline-block}}",
     ".sc>i{position:absolute;left:0;width:1px;height:0;view-timeline:--t block;animation:q auto linear both;animation-timeline:--t}"]
cells=[]
for k in range(16):
    css.append(f"#c{k}{{top:{base + k/64}px}}")
    cells.append(f'<div class=sc><i id=c{k}></i></div>')
open(out,'w').write("<!doctype html><style>"+"\n".join(css)+"</style>"+"".join(cells))
