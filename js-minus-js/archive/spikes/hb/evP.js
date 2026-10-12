() => {
  const p = document.getElementById('probe'), o = document.getElementById('out'), u = document.getElementById('u');
  const res = {};
  // scale s: 1 font unit = 1/s px. font-size = 1024/s px. k = s.
  for (const s of [1, 64]) {
    u.style.setProperty('--fs', (1024 / s) + 'px'); u.style.setProperty('--k', s);
    let firstBad = null, ok = 0; let maxOk = 0;
    for (let e = 4; e <= 31; e++) {
      for (let t = 0; t < 6; t++) {
        const W = Math.floor(2 ** e * (0.5 + Math.random() * 0.5));
        const q = Math.floor(W / 32768), r = W % 32768;
        let s2 = ''.repeat(q); for (let k = 0; k < 15; k++) if (r & (1 << k)) s2 += String.fromCharCode(0xE000 + k);
        p.textContent = s2;
        const y = +getComputedStyle(o).getPropertyValue('--y');
        if (y === W) { ok++; maxOk = Math.max(maxOk, W); } else if (!firstBad) firstBad = { e, W, y, diff: y - W, glyphs: s2.length };
        if (q > 3000) break;
      }
    }
    res['scale' + s] = { ok, maxExact: maxOk, log2maxExact: +Math.log2(maxOk).toFixed(2), firstBad };
  }
  return res;
}
