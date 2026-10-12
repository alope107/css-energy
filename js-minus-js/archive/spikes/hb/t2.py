# Unambiguous budget probe: lookup n maps g{n}->g{n+1}. Final glyph index = lookups that fired.
import time, uharfbuzz as hb
from mk import build
import sys; N=int(sys.argv[1])
names=[f'g{i}' for i in range(N+1)]
fea=[f"lookup L{n} {{ sub g{n} by g{n+1}; }} L{n};" for n in range(N)]
fea.append("feature calt { " + " ".join(f"lookup L{n};" for n in range(N)) + " } calt;")
t=time.time(); build('t2.ttf', names, {n:1 for n in names}, {0xE000:'g0'}, "\n".join(fea)); print('build', time.time()-t)
f=hb.Font(hb.Face(hb.Blob.from_file_path('t2.ttf')))
for L in [1,2,16,64,256,1024]:
    buf=hb.Buffer(); buf.add_str(''*L); buf.guess_segment_properties()
    t=time.perf_counter(); hb.shape(f,buf,{}); dt=time.perf_counter()-t
    g=sorted(set(int(f.glyph_to_string(i.codepoint)[1:]) for i in buf.glyph_infos))
    print(L, 'fired', g[:3], f'{dt*1e3:.1f} ms', f'{dt/L/N*1e9:.1f} ns/glyph-lookup')
