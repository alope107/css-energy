# Chain font: lookup n maps g{n}->g{n+1}; advance(g{n}) = n units. upem 1000.
import sys
from mk import build
N=int(sys.argv[1]); out=sys.argv[2]
names=[f'g{i}' for i in range(N+1)]
fea=[f"lookup L{n} {{ sub g{n} by g{n+1}; }} L{n};" for n in range(N)]
fea.append("feature ss01 { " + " ".join(f"lookup L{n};" for n in range(N)) + " } ss01;")
build(out, names, {f'g{i}':i for i in range(N+1)}, {0xE000+i:'g0' for i in range(64)}, "\n".join(fea))
