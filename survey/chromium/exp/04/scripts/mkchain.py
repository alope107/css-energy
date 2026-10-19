# Deep chain: every level has K animations whose timeline is looked up by name (walks to the root),
# vs. the same animations on the document timeline. Driver: an animated inherited prop at the root.
import sys, os
out, D, K, mode = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
css = ["@property --t{syntax:'<number>';inherits:true;initial-value:0}",
       "@keyframes tt{from{--t:0}to{--t:1000}}",
       "#root{animation:tt 10s linear infinite;timeline-scope:" + ",".join(f"--a{k}" for k in range(K)) + "}",
       ".sc{height:50px;width:50px;overflow:hidden;position:relative}",
       ".sc>i{position:absolute;top:10px;height:1px;width:1px}"]
for k in range(K):
    css.append(f"@property --o{k}{{syntax:'<number>';inherits:false;initial-value:0}}")
    css.append(f"@keyframes q{k}{{from{{--o{k}:0}}to{{--o{k}:1}}}}")
css.append(".sc>i{view-timeline:" + ",".join(f"--a{k} block" for k in range(K)) + "}")
names = ",".join(f"q{k}" for k in range(K))
if mode == 'named':
    tl = ",".join(f"--a{k}" for k in range(K))
    css.append(f".l{{animation-name:{names};animation-duration:1s;animation-fill-mode:both;animation-play-state:paused;animation-timeline:{tl}}}")
elif mode == 'doc':
    css.append(f".l{{animation-name:{names};animation-duration:1s;animation-fill-mode:both;animation-play-state:paused}}")
elif mode == 'none':
    pass
css.append(".l{--u:calc(var(--t) * 1)}")
html = "<!doctype html><style>" + "\n".join(css) + "</style><div id=root><div class=sc><i></i></div>" + "<div class=l>"*D + "</div>"*D + "</div>"
open(out, 'w').write(html)
