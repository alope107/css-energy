async () => {
  const PROG = [['JODD',3],['SHR1',0],['JMP',5],['SHR1',0],['XORI',0xB8],['XORI',0x2D],['JZ',9],['XORI',0x2D],['JMP',0],['HALT',0]];
  const step = (p, a) => { if (p >= PROG.length) return [p,a]; const [op,k] = PROG[p];
    switch (op) { case 'JODD': return [a&1 ? k : p+1, a]; case 'SHR1': return [p+1, a>>1]; case 'JMP': return [k, a];
      case 'XORI': return [p+1, a^k]; case 'JZ': return [a===0 ? k : p+1, a]; default: return [p, a]; } };
  const ref = (s, n) => { let p = s >> 8, a = s & 255; for (let i = 0; i < n; i++) [p, a] = step(p, a); return p*256 + a; };
  const m = document.getElementById('m'), o = document.querySelector('.out');
  const KS = [1, 100, 1000, 10000, 16000]; const res = {};
  for (let i = 0; i < KS.length; i++) {
    m.style.setProperty('--feat', `"ss0${i+1}" 1`);
    let bad = 0, first = null; const T = [];
    for (let t = 0; t < 60; t++) {
      const s = t < 30 ? (t * 37) % 256 : (t * 7919) % 16384;
      const t0 = performance.now(); m.style.setProperty('--s', s);
      const y = +getComputedStyle(o).getPropertyValue('--y'); T.push(performance.now() - t0);
      const want = ref(s, KS[i]); if (y !== want) { bad++; if (!first) first = {s, y, want}; }
    }
    T.sort((a,b)=>a-b);
    res['K' + KS[i]] = { bad, first, median_us: +(T[30]*1000).toFixed(0) };
  }
  return res;
}
