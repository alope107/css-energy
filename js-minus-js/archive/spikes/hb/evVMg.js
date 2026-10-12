async () => {
  const m = document.getElementById('m'), pr = [...document.querySelectorAll('.probe')];
  const last = pr[pr.length - 1]; const n = 200; const seen = new Set();
  const t0 = performance.now();
  for (let t = 0; t < n; t++) { m.style.setProperty('--s', (t * 7919 + 11) % 16384); seen.add(Math.round(last.getBoundingClientRect().width*64)); }
  const ms = (performance.now() - t0) / n;
  // distinct inputs seen per level (cache-hit estimate): count distinct probe texts across run is hard; report distinct final outputs
  return { levels: pr.length, ms_per_update: +ms.toFixed(2), us_per_level: +(ms * 1000 / pr.length).toFixed(0), distinct_final: seen.size };
}
