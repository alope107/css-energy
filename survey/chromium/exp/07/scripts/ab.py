"""ab.py core nrounds font texts drvA drvB [drvC ...]: interleaved runs; prints per-binary min and median ratio vs A."""
import sys, subprocess, statistics, re
core, n, font, texts = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]; bins = sys.argv[5:]
res = {b: [] for b in bins}; cks = {}
for r in range(n):
    for b in (bins if r % 2 == 0 else bins[::-1]):
        out = subprocess.run(['taskset', '-c', core, b, font, texts, '1'], capture_output=True, text=True).stdout
        m = re.search(r'min ([\d.]+).*checksum (\w+)', out); res[b].append(float(m.group(1))); cks[b] = m.group(2)
base = res[bins[0]]
for b in bins:
    ratios = [x / y for x, y in zip(res[b], base)]
    print(f'{b.split("/")[-1]:14s} min {min(res[b]):7.3f} med {statistics.median(res[b]):7.3f}  ratio med {statistics.median(ratios):.3f} [{min(ratios):.3f}..{max(ratios):.3f}] ck {cks[b][:8]}')
