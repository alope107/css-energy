async () => {
  const m = document.getElementById('m'), pr = [...document.querySelectorAll('.probe')];
  const T = [];
  for (let k = 0; k < 200; k++) { const x = (k * 1237) % 4096; const t0 = performance.now();
    m.style.setProperty('--x', x); pr[0].offsetWidth; T.push(performance.now() - t0); }
  T.sort((a,b)=>a-b); return { units: pr.length, per_unit_us: +(T[100] / pr.length * 1000).toFixed(1), w: pr[3].getBoundingClientRect().width };
}
