#!/usr/bin/env python3
"""uarch4.py — reference model of the font CPU with B-word cache lines (B = 4).

A line holds one aligned block: tag = addr // B, per word valid/dirty. Ring of N lines with a victim
pointer, as in uarch.py. Read hits need the word valid. A write to a present block writes the word (no trap);
otherwise it allocates the victim line (which must have no dirty words) with only that word valid+dirty.
Service (CSS): MISS on a present block fills its invalid words; MISS on an absent block writes back the
victim's dirty words (one per bank) and fills the victim with the whole block; WFAIL writes back the victim.
"""
import json, sys
from uarch import Machine, ROM

class Machine4(Machine):
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
                if ln:
                    for j in range(self.B):
                        if ln[1][j] is None: ln[1][j] = self.ram.get(ln[0] * self.B + j, 0)
                    return
            vic = self.lines[self.vp]
            if vic and any(vic[2]):
                self.wb(vic)
                if k == 'WFAIL': return
            if k == 'MISS':
                b = t[1] // self.B
                assert t[1] >= ROM
                self.lines[self.vp] = [b, [self.ram.get(b * self.B + j, 0) for j in range(self.B)], [0] * self.B]
                self.vp = (self.vp + 1) % self.N
        else:
            super().service(t)

if __name__ == '__main__':
    image = json.load(open(sys.argv[1]))
    for N, S in [(16, 16), (16, 32), (8, 32)]:
        m = Machine4(image, N).run(S)
        print(N, S, ''.join(map(chr, m.out)) == image['expected'], m.steps, m.shapings, round(m.steps / m.shapings, 2), m.trapkinds)
