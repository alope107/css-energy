# timeline-scope: one long list vs nests of 24 names; 420 register elements (2 view timelines each) restyle every frame.
import sys
out, mode = sys.argv[1], sys.argv[2]
N = 420; names = [f"--t{i}" for i in range(2 * N)]
css = ["@property --t{syntax:'<number>';inherits:true;initial-value:0}",
       "@keyframes tt{from{--t:0}to{--t:1000}}",
       "#R{animation:tt 10s linear infinite}",
       ".sc{position:relative;height:300px;width:300px;overflow:hidden}",
       ".sc>i{position:absolute;top:5px;left:5px;width:1px;height:1px;--z:calc(var(--t) + 1)}"]
for k in range(N):
    css.append(f"#r{k}{{view-timeline:--t{2*k} block,--t{2*k+1} inline}}")
wrappers_open = ""; wrappers_close = ""
if mode == 'single':
    css.append("#w0{timeline-scope:" + ",".join(names) + "}")
    wrappers_open = "<div id=w0>"; wrappers_close = "</div>"
elif mode == 'nest':
    G = 24; n = 0
    for s in range(0, 2 * N, G):
        css.append(f"#w{n}{{timeline-scope:" + ",".join(names[s:s+G]) + "}")
        wrappers_open += f"<div id=w{n}>"; wrappers_close += "</div>"; n += 1
regs = "".join(f"<i id=r{k}></i>" for k in range(N))
open(out, 'w').write("<!doctype html><style>" + "\n".join(css) + "</style><div id=R>" + wrappers_open + "<div class=sc>" + regs + "</div>" + wrappers_close + "</div>")
