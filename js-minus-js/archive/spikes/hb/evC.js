async () => {
  const m = document.getElementById('m'), outs = [...document.querySelectorAll('.out')];
  const f = x => (x*x*7 + 3) % 65536;
  let bad = 0; const T = [];
  for (let k = 0; k < 300; k++) {
    const x = (k * 1237) % 4096;
    const t0 = performance.now();
    m.style.setProperty('--x', x);
    const y0 = +getComputedStyle(outs[0]).getPropertyValue('--y');   // forces style+layout as needed
    T.push(performance.now() - t0);
    for (let i = 0; i < outs.length; i += Math.max(1, outs.length >> 3)) {
      const y = +getComputedStyle(outs[i]).getPropertyValue('--y');
      if (y !== f((x + i*37) % 4096)) bad++;
    }
  }
  T.sort((a,b)=>a-b);
  return { units: outs.length, bad, median_ms: +T[150].toFixed(3), p90_ms: +T[270].toFixed(3) };
}
