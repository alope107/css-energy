"""zoomfix.py — CSS that finds the device-pixel ratio (screen scale × browser zoom) with resolution media queries.

The font CPU's state is read from glyph advances. Chrome positions glyphs in whole device pixels and HarfBuzz
positions are 16.16 fixed point, so one font unit must be exactly one device pixel (and no glyph may be 32768
device px or wider). The page sets font-size: calc(1024px / var(--R)) and reads values as 100cqi / 1px * R.
"""
ZOOMS = [0.25, 1 / 3, 0.5, 2 / 3, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 5.0]
SCALES = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5, 4.0]

def css():
    vals = sorted({round(z * s, 6) for z in ZOOMS for s in SCALES})
    out = ['@property --R { syntax: "<number>"; inherits: true; initial-value: 1; }',
           '@property --Rok { syntax: "<integer>"; inherits: true; initial-value: 0; }']
    for i, r in enumerate(vals):
        lo = (vals[i - 1] + r) / 2 if i else r * 0.999
        hi = (vals[i + 1] + r) / 2 if i + 1 < len(vals) else r * 1.001
        lo, hi = max(lo, r - 0.0005), min(hi, r + 0.0005)
        out.append(f'@media (min-resolution: {lo:.6f}dppx) and (max-resolution: {hi:.6f}dppx) {{ :root {{ --R: {r}; --Rok: 1; }} }}')
    return '\n'.join(out)
