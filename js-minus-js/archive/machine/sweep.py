import json, uarch, sys, collections
im = json.load(open('image.json'))
for N in (16, 32):
    for S in (16, 24, 32, 48, 64):
        m = uarch.Machine(im, N); n = 0; tr = collections.Counter()
        while not m.halted:
            t = m.shaping(S); m.service(t); n += 1; tr[t[0] if t else None] += 1
        print(N, S, n, m.steps, round(m.steps / n, 2), dict(tr), flush=True)
