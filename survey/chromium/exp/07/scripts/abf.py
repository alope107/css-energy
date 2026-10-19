"""abf.py core n drv texts fontA fontB ...: interleaved, same binary, different fonts."""
import sys, subprocess, statistics, re
core, n, drv, texts = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]; fonts = sys.argv[5:]
res = {f: [] for f in fonts}
for r in range(n):
    for f in (fonts if r % 2 == 0 else fonts[::-1]):
        t = texts if ':' not in f else f.split(':')[1]; ff = f.split(':')[0]
        out = subprocess.run(['taskset', '-c', core, drv, ff, t, '1'], capture_output=True, text=True).stdout
        res[f].append(float(re.search(r'min ([\d.]+)', out).group(1)))
base = res[fonts[0]]
for f in fonts:
    ratios = [x / y for x, y in zip(res[f], base)]
    print(f'{f.split("/")[-1][:40]:40s} min {min(res[f]):8.3f} med {statistics.median(res[f]):8.3f} ratio med {statistics.median(ratios):.3f} [{min(ratios):.3f}..{max(ratios):.3f}]')
