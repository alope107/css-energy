async () => {
  const m = document.getElementById('m'), outs = [...document.querySelectorAll('.out')];
  const f = x => (x*x*7 + 3) % 32768;
  let bad = 0, first = null; const T = [];
  const xs = outs.length === 1 ? [...Array(4096).keys()] : [...Array(200).keys()].map(k => (k*1237) % 4096);
  for (const x of xs) {
    const t0 = performance.now(); m.style.setProperty('--x', x);
    const y = +getComputedStyle(outs[0]).getPropertyValue('--y'); T.push(performance.now() - t0);
    if (y !== f(x)) { bad++; if (!first) first = {x, y, want: f(x)}; }
  }
  // revisit same values (font instance cache warm)
  const T2 = [];
  for (const x of xs.slice(0, 200)) { const t0 = performance.now(); m.style.setProperty('--x', x); getComputedStyle(outs[0]).getPropertyValue('--y'); T2.push(performance.now() - t0); }
  T.sort((a,b)=>a-b); T2.sort((a,b)=>a-b);
  return { units: outs.length, n: xs.length, bad, first, cold_per_unit_us: +(T[T.length>>1]/outs.length*1000).toFixed(1), warm_per_unit_us: +(T2[T2.length>>1]/outs.length*1000).toFixed(1) };
}
