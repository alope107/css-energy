import subprocess, time, sys, statistics, re
W = sys.argv[1]; core = sys.argv[2]; rounds = int(sys.argv[3]); font = sys.argv[4]
def hr(binp, n):
    t0 = time.perf_counter(); subprocess.run(['taskset', '-c', core, binp, '--font-file', font, '--text-file', f'{W}/texts_fizz_utf8.txt', '--features', 'cv01', '-n', str(n), '--no-glyph-names'], stdout=subprocess.DEVNULL, check=True); return time.perf_counter() - t0
def hb():
    out = subprocess.run(['taskset', '-c', core, f'{W}/drv/drv_c', font, f'{W}/texts_fizz.txt', '1'], capture_output=True, text=True).stdout
    return float(re.search(r'min ([\d.]+)', out).group(1))
res = {'hb': [], 'hr0.14.0': [], 'hrHEAD': []}
for r in range(rounds):
    res['hb'].append(hb())
    for v in ('0.14.0', 'HEAD'):
        b = f'{W}/hr/{v}/target/release/hr-shape'
        t1 = hr(b, 1); t4 = hr(b, 4)
        res['hr' + v].append((t4 - t1) / 3 / 94 * 1e3)
for k, v in res.items(): print(f'{k:10s} ms/shaping med {statistics.median(v):.2f}  all {[round(x, 2) for x in v]}')
