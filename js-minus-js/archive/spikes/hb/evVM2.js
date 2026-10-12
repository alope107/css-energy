async () => {
  const m = document.getElementById('m'), o = document.querySelector('.out'); const res = {};
  const KS = [1, 100, 1000, 10000, 16000];
  for (let i = 0; i < KS.length; i++) {
    m.style.setProperty('--feat', `"ss0${i+1}" 1`); getComputedStyle(o).getPropertyValue('--y');
    const n = 300; const t0 = performance.now();
    for (let t = 0; t < n; t++) { m.style.setProperty('--s', (t * 7919) % 16384); getComputedStyle(o).getPropertyValue('--y'); }
    const us = (performance.now() - t0) / n * 1000;
    res['K' + KS[i]] = { us_per_readback: +us.toFixed(1) };
  }
  const b = res.K1.us_per_readback, e = res.K16000.us_per_readback;
  res.ns_per_step = +((e - b) / 15999 * 1000).toFixed(1);
  return res;
}
