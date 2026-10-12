# LUT font: x in [0,4096) rendered as two base-64 PUA digits (U+E000+d). width = f(x) units.
# adv(hi digit)=32768, adv(lo)=0, kern(hi,lo)=f(x)-32768. upem 1024 -> at 16px, 1 unit = 1/64 px.
from mk import build
f = lambda x: (x*x*7 + 3) % 65536
D=[f'd{i}' for i in range(64)]; H=[f'h{i}' for i in range(64)]
names = D + H
adv = {**{d:0 for d in D}, **{h:32768 for h in H}}
fea = ["@D = [" + " ".join(D) + "];", "lookup HI { " + " ".join(f"sub d{i}' @D by h{i};" for i in range(64)) + " } HI;"]  # mark the first digit as 'hi'
fea.append("feature ss02 { lookup HI; } ss02;")
fea.append("feature kern { " + " ".join(f"pos h{a} d{b} {f(a*64+b)-32768};" for a in range(64) for b in range(64)) + " } kern;")
build('b.ttf', names, adv, {0xE000+i:D[i] for i in range(64)}, "\n".join(fea), upem=1024, box=False)
import uharfbuzz as hb
F=hb.Font(hb.Face(hb.Blob.from_file_path('b.ttf')))
bad=0
for x in range(4096):
    b=hb.Buffer(); b.add_str(chr(0xE000+x//64)+chr(0xE000+x%64)); b.guess_segment_properties(); hb.shape(F,b,{'ss02':True})
    w=sum(p.x_advance for p in b.glyph_positions); bad += (w != f(x))
print('harfbuzz mismatches', bad)
