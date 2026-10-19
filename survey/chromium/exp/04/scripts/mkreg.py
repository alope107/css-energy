# Generate pages probing per-registered-property animation costs.
import sys, os
out = sys.argv[1]
E = 200
def page(name, R, mode, star=False):
    css = []
    for i in range(R):
        if star:
            css.append(f"@property --u{i}{{syntax:'*';inherits:false}}")
        else:
            css.append(f"@property --u{i}{{syntax:'<number>';inherits:false;initial-value:0}}")
    css.append("@property --t{syntax:'<number>';inherits:true;initial-value:0}")
    css.append("@property --x{syntax:'<number>';inherits:false;initial-value:0}")
    css.append("@property --y{syntax:'<number>';inherits:false;initial-value:0}")
    css.append("@keyframes tt{from{--t:0}to{--t:1000}}")
    css.append("@keyframes ax{from{--x:0}to{--x:1}}")
    css.append("#p{animation:tt 10s linear infinite}")
    css.append(".c{width:4px;height:4px;display:inline-block}")
    if mode == 'steady':      # each child runs its own time-driven animation, created once
        css.append(".c{animation:ax 1s linear infinite}")
    elif mode == 'trans':     # each child's transition restarts every frame
        css.append(".c{--y:calc(var(--t) * 1);transition:--y 10s linear}")
    elif mode == 'animupd':   # each child's animation is rebuilt every frame (timing depends on --t)
        css.append("@property --odd{syntax:'<integer>';inherits:false;initial-value:0}")
        css.append(".c{--odd:calc(mod(round(var(--t) * 7), 2));animation:ax 1s linear infinite;animation-duration:if(style(--odd: 1): 1000ms; else: 1001ms)}")
    elif mode == 'inh':       # control: children only inherit (no animations of their own)
        css.append(".c{--y:calc(var(--t) * 1)}")
    html = "<!doctype html><style>" + "\n".join(css) + "</style><div id=p>" + "<i class=c></i>"*E + "</div>"
    open(os.path.join(out, name), 'w').write(html)
for R in (0, 4000):
    for mode in ('steady', 'trans', 'animupd', 'inh'):
        page(f"{mode}_R{R}.html", R, mode)
page("trans_R4000star.html", 4000, 'trans', star=True)
page("animupd_R4000star.html", 4000, 'animupd', star=True)
