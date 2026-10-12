() => {
  const out = {};
  for (const i of [0,1]) {
    const s = document.getElementById('s'+i);
    out['on'+i] = s.getBoundingClientRect().width; out['off'+i] = document.getElementById('o'+i).getBoundingClientRect().width;
    // timing: distinct strings each iteration to dodge shape caching (length L or L+1 alternating with suffix variety)
    for (const L of [1, 8, 64]) {
      let n = 0; const t0 = performance.now(); let w=0;
      for (let k = 0; k < 40; k++) { s.textContent = ''.repeat(L + (k % 2)) ; w += s.offsetWidth; n++; }
      out[`f${i}_L${L}_ms`] = +((performance.now() - t0) / n).toFixed(3);
      // cached: same string twice alternating with another cached one
      const t1 = performance.now();
      for (let k = 0; k < 40; k++) { s.textContent = ''.repeat(L + (k % 2)); w += s.offsetWidth; }
      out[`f${i}_L${L}_cached_ms`] = +((performance.now() - t1) / 40).toFixed(3);
    }
  }
  return out;
}
