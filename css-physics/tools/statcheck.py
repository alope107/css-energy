#!/usr/bin/env python3
"""Static regression checks on a PLAIN single-engine page (no browser; exit 1 on failure).

  python3 tools/statcheck.py out/p16.html [more pages]

1. Scene start states: every scene's #INI rule declares the start sleep counter (--isc<i>) of EVERY body, and a body
   starts asleep (isc > 45) only if it rests on the floor in that scene. The scene rules cascade over the first
   scene's, so a counter one rule leaves undeclared keeps another scene's value: bodies then start asleep in mid-air
   (this bug has come back more than once).
2. Gates: a container query of the boolean form style(--x) (true when --x differs from 0) must only test a 0/1
   flag. --GIr holds the held body's index + 1; style(--GIr) as body 0's grab gate made every drag pull body 0 too.
"""
import json, re, sys

SLEEP_K = 45


def check(path):
    s = open(path).read()
    errs = []
    info = json.loads(re.search(r'<!--BODYINFO (.*?)-->', s).group(1))
    n = len(info)
    # ---- 1. scene start states
    rules = re.findall(r'(#INI|#app:has\(#(?:sc|lb)-[a-z]+:(?:checked|active)\) #INI)\{([^}]*)\}', s)
    if not rules:
        errs.append('no #INI rules found')
    for sel, body in rules:
        d = dict(kv.split(':', 1) for kv in body.split(';') if ':' in kv)
        for i, b in enumerate(info):
            isc = d.get(f'--isc{i}')
            if isc is None:
                errs.append(f'{sel}: --isc{i} not declared (inherits another scene\'s start state)')
                continue
            if float(isc) <= SLEEP_K:
                continue
            y = float(d[f'--iy{i}'])
            if b['k'] == 'sph':
                ext = b['r']
            else:
                w, x, yq, z = (float(d[f'--iq{c}{i}']) for c in 'wxyz')
                r1 = (2 * (x * yq + w * z), 1 - 2 * (x * x + z * z), 2 * (yq * z - w * x))
                ext = sum(abs(a) * h for a, h in zip(r1, b['h']))
            if abs(y + ext) > 0.5:
                errs.append(f'{sel}: body {i} starts asleep {-(y + ext):.1f} px above the floor')
    # ---- 2. boolean gates only on 0/1 flags
    valued = {}
    for name, val in re.findall(r'@container (?:[\w-]+ )?style\(--([\w]+): ([^)]+)\)', s):
        valued.setdefault(name, set()).add(val.strip())
    for name in set(re.findall(r'@container (?:[\w-]+ )?style\(--([\w]+)\)', s)):
        bad = {v for v in valued.get(name, ()) if v not in ('0', '1')}
        if bad or name == 'GIr':
            errs.append(f'boolean gate style(--{name}) on a multi-valued flag (also tested as {sorted(bad)[:4]})')
    return errs


fail = 0
for pth in sys.argv[1:]:
    e = check(pth)
    print(('FAIL ' if e else 'PASS ') + pth + ('' if not e else ': ' + '; '.join(e[:8]) + (f' (+{len(e) - 8} more)' if len(e) > 8 else '')))
    fail |= bool(e)
sys.exit(fail)
