# wide-layer test: parent sets NA axes (animated); M children each pick a different font family
# (same axes) and read 1ch,1ic,1ex,1cap. Each output = sum over R random 1-2 axis regions.
import vf, random, sys
NA = int(sys.argv[1]); R = int(sys.argv[2]); M = int(sys.argv[3]); tag = sys.argv[4]
tags = [f'a{i:03d}' for i in range(NA)]
rng = random.Random(1)
def terms(n):
    out = []
    for _ in range(n):
        k = rng.choice([1, 2])
        ax = rng.sample(tags, k)
        out.append(({a: rng.choice([vf.POS, vf.NEG]) for a in ax}, rng.randint(-300, 300)))
    return out
faces = []
for m in range(M):
    f = vf.build(tags, [(0x30, 'zero', 8192, terms(R)), (0x6C34, 'water', 8192, terms(R))], mvar={'xhgt': terms(R), 'cpht': terms(R)}, family=f'F{m}')
    faces.append(f"@font-face{{font-family:F{m};src:url(data:font/ttf;base64,{vf.b64(f)})}}")
fvs = ','.join(f"'{t}' round(calc(sin(var(--t) * {1 + i % 7} + {i}) * 16000), 1)" for i, t in enumerate(tags))
kids = ''.join(f'<i style="font-family:F{m}"></i>' for m in range(M))
html = f'''<!doctype html><style>{''.join(faces)}
@property --t{{syntax:'<number>';inherits:true;initial-value:0}}
@property --o1{{syntax:'<length>';inherits:false;initial-value:0px}}
@property --o2{{syntax:'<length>';inherits:false;initial-value:0px}}
@property --o3{{syntax:'<length>';inherits:false;initial-value:0px}}
@property --o4{{syntax:'<length>';inherits:false;initial-value:0px}}
@keyframes t{{from{{--t:0}}to{{--t:1000}}}}
#r{{animation:t 1000s linear infinite;font-size:16px;position:absolute;width:0;height:0;overflow:hidden;visibility:hidden}}
#p{{font-variation-settings:{fvs}}}
#p i{{{'--o1:1ch;--o2:1ic;--o3:1ex;--o4:1cap' if tag != 'none' else ''}}}
</style><div id=r><div id=p>{kids}</div></div>'''
open(f't3_{tag}.html', 'w').write(html)
