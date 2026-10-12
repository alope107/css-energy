"""sim2.py — trap-distance levers on the uarch model: instructions per shaping for cache variants."""
import json, sys, uarch
from uarch import Machine, ROM

class Eager(Machine):
    """service also writes back up to E dirty lines ahead of the victim pointer (E extra write channels)."""
    E = 1
    def service(self, t):
        super().service(t)
        if t and t[0] in ('MISS', 'WFAIL', 'EXT', 'PUTC') or t is None:
            n = 0
            for i in range(self.N):
                ln = self.lines[(self.vp + i) % self.N]
                if n >= self.E: break
                if ln and ln[2]: self.ram[ln[0]] = ln[1]; ln[2] = 0; n += 1

class Block(Machine):
    """B-word lines (B banks): tag = addr // B; per-word valid/dirty. MISS fills the whole block (B bank reads);
    write-back writes every dirty word of the victim (B bank write channels). Same ring/victim policy."""
    B = 4
    def find(self, a):
        for ln in self.lines:
            if ln and ln[0] == a // self.B: return ln
    def c_read(self, a):
        ln = self.find(a)
        if ln and ln[1][a % self.B] is not None: return True, ln[1][a % self.B]
        return False, 0
    def c_write(self, a, v):
        ln = self.find(a)
        if ln: ln[1][a % self.B] = v; ln[2][a % self.B] = 1; return True
        if self.vp is None: return False
        vic = self.lines[self.vp]
        if vic and any(vic[2]): return False
        w = [None] * self.B; d = [0] * self.B; w[a % self.B] = v; d[a % self.B] = 1
        self.lines[self.vp] = [a // self.B, w, d]
        self.vp = self.vp + 1 if self.vp + 1 < self.N else None
        return True
    def wb(self, ln):
        for j in range(self.B):
            if ln[2][j]: self.ram[ln[0] * self.B + j] = ln[1][j]; ln[2][j] = 0
    def service(self, t):
        if self.vp is None: self.vp = 0
        if t is None: return
        k = t[0]
        if k in ('MISS', 'WFAIL'):
            if k == 'MISS':
                ln = self.find(t[1])
                if ln:                                   # block present, word invalid: fill the holes
                    for j in range(self.B):
                        if ln[1][j] is None: ln[1][j] = self.ram.get(ln[0] * self.B + j, 0)
                    return
            vic = self.lines[self.vp]
            if vic and any(vic[2]):
                self.wb(vic)
                if k == 'WFAIL': return
            if k == 'MISS':
                b = t[1] // self.B
                self.lines[self.vp] = [b, [self.ram.get(b * self.B + j, 0) for j in range(self.B)], [0] * self.B]
                self.vp = (self.vp + 1) % self.N
        else:
            super().service(t)

def run(cls, image, N, S, **kw):
    m = cls(image, N)
    for k, v in kw.items(): setattr(m, k, v)
    n = 0
    while not m.halted:
        m.service(m.shaping(S)); n += 1
    assert ''.join(map(chr, m.out)) == image['expected']
    return m.steps / n, m.trapkinds

if __name__ == "__main__":
  for img in sys.argv[1:]:
      image = json.load(open(img)); print('==', img)
      rows = [('baseline', Machine, {}), ('eager wb x1', Eager, dict(E=1)), ('eager wb x3', Eager, dict(E=3)),
              ('4-word lines', Block, dict(B=4)), ('8-word lines', Block, dict(B=8))]
      for N, S in [(16, 16), (16, 32), (32, 32)]:
          for name, cls, kw in rows:
              r, tk = run(cls, image, N, S, **kw)
              print(f'N={N:2} S={S:2} {name:13} {r:5.2f} instr/shaping  {tk}', flush=True)
