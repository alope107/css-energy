import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../repo/js-minus-js/machine')
import uarch, uarch4
image = json.load(open(sys.argv[1])); m = uarch4.Machine4(image, 16)
cnt = collections.Counter(); orig = uarch.UCODE
# wrap: count mem kind per executed micro-cycle by instrumenting c_read/c_write calls
cr, cw = m.c_read, m.c_write
def r(*a): cnt['R'] += 1; return cr(*a)
def w(*a): cnt['W'] += 1; return cw(*a)
m.c_read, m.c_write = r, w
sh = 0
while not m.halted:
    c0 = m.cycles; t = m.shaping(32); cnt['cycles'] += 32; cnt['used'] += m.cycles - c0; m.service(t); sh += 1
print(sh, dict(cnt), 'R frac of 32-slot', cnt['R'] / cnt['cycles'], 'W frac', cnt['W'] / cnt['cycles'], 'used frac', cnt['used'] / cnt['cycles'])
