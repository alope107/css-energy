#!/usr/bin/env python3
"""static.py built.html out.html: a copy of a built page with no engine, for checking how a browser draws the scene.

The solver (.rz: #LS and every level below it) is display:none and the bodies' pose animations (#w<i>, which read the
registers) are removed, so each body stays at its scene's start pose. probe.html links out/static16.html:
  python3 experiments/safari/static.py out/rigid3d-16.html out/static16.html
"""
import re, sys
src, dst = sys.argv[1:3]
s = open(src, encoding='utf-8').read()
s, n = re.subn(r'(#[A-Za-z]*w\d+\{)animation-name:[^;]*;animation-timeline:[^;]*;', r'\1', s)
if not n:
    sys.exit('no #w pose animations found: not a built rigid3d page?')
s = s.replace('</style>', '/* === Probe: no engine (experiments/safari/static.py) === */\n.rz{display:none!important}</style>', 1)
open(dst, 'w', encoding='utf-8').write(s)
print(f'{dst}: {n} bodies held at their start poses, solver off')
