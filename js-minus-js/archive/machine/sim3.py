import json, sys
from sim2 import Block, run
from uarch import Machine
for img in sys.argv[1:]:
    image = json.load(open(img)); print('==', img)
    for N in (8, 12, 16):
        for B in (2, 4):
            for S in (16, 24, 32):
                r, tk = run(Block, image, N, S, B=B)
                print(f'N={N:2} B={B} words={N*B:3} S={S:2} {r:5.2f}  {tk}', flush=True)
