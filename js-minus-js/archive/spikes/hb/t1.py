# Budget probe: N chained "increment every glyph" lookups; read how many ran.
import time, uharfbuzz as hb, sys
from mk import build
K=16
names=[f'g{i}' for i in range(K)]
def font(N):
    fea=[]
    for n in range(N):
        fea.append(f"lookup L{n} {{ sub [{' '.join(names)}] by [{' '.join(names[1:]+names[:1])}]; }} L{n};")
    fea.append("feature calt { " + " ".join(f"lookup L{n};" for n in range(N)) + " } calt;")
    build('t1.ttf', names, {n:100 for n in names}, {0xE000+i:names[i] for i in range(K)}, "\n".join(fea))
    blob=hb.Blob.from_file_path('t1.ttf'); return hb.Font(hb.Face(blob))
for N in [16000]:
    f=font(N)
    for L in [1,4,8,16,64,256]:
        buf=hb.Buffer(); buf.add_str(''*L); buf.guess_segment_properties()
        t=time.perf_counter(); hb.shape(f,buf,{}); dt=time.perf_counter()-t
        g=[f.glyph_to_string(i.codepoint) for i in buf.glyph_infos]
        ran = int(g[-1][1:]) # mod 16 only; refine below
        print(N, L, 'last', g[-1], 'first', g[0], f'{dt*1e3:.2f} ms')
