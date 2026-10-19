"""Make trapped-from-start variants of the dumped texts: set the control cell C to ('T','HALT')."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../repo/js-minus-js/machine'); os.environ['CPUMOD'] = 'cpu4'
import cpu4
image = json.load(open(sys.argv[1])); cpu = cpu4.CPU(image, 16); P = cpu.P; P.assign_gids()
C = cpu.core['C']; pos = C.pos; g = C.type.g(('T', 'HALT'))
texts = json.load(open(sys.argv[2]))
with open(sys.argv[3], 'w') as f:
    for t in texts:
        t = list(t); t[pos] = g; f.write(' '.join(str(0xF0000 + x) for x in t) + '\n')
print('C at', pos, 'glyph', g, 'was', texts[0][pos])
