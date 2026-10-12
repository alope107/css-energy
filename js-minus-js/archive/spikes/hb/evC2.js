async () => {
  const m = document.getElementById('m'), outs = [...document.querySelectorAll('.out')];
  const T = [];
  for (let k = 0; k < 200; k++) {
    const x = (k * 1237) % 4096; const t0 = performance.now();
    m.style.setProperty('--x', x); getComputedStyle(outs[0]).getPropertyValue('--y'); T.push(performance.now() - t0);
  }
  T.sort((a,b)=>a-b);
  return { units: outs.length, per_unit_us: +(T[100] / outs.length * 1000).toFixed(1), sampleY: getComputedStyle(outs[5]).getPropertyValue('--y') };
}
