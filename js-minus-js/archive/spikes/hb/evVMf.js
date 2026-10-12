async () => {
  const PROG = [['JODD',3],['SHR1',0],['JMP',5],['SHR1',0],['XORI',0xB8],['XORI',0x2D],['JZ',9],['XORI',0x2D],['JMP',0],['HALT',0]];
  const step = (p, a) => { if (p >= PROG.length) return [p,a]; const [op,k] = PROG[p];
    switch (op) { case 'JODD': return [a&1 ? k : p+1, a]; case 'SHR1': return [p+1, a>>1]; case 'JMP': return [k, a];
      case 'XORI': return [p+1, a^k]; case 'JZ': return [a===0 ? k : p+1, a]; default: return [p, a]; } };
  const ref = (s, n) => { let p = s >> 8, a = s & 255; for (let i = 0; i < n; i++) [p, a] = step(p, a); return p*256 + a; };
  const m = document.getElementById('m'), pr = [...document.querySelectorAll('.probe')];
  const res = {};
  for (const mode of ['raf', 'sync']) {
    let bad = 0, first = null;
    for (let t = 0; t < 40; t++) {
      const s = mode === 'raf' ? (t * 53) % 256 : (t * 7919 + 11) % 16384;
      m.style.setProperty('--s', s);
      if (mode === 'raf') await new Promise(r => requestAnimationFrame(() => setTimeout(r, 0)));
      // probe i's width encodes the output of level i-1 ... read level outputs from the *next* probe input path: use probe widths = level outputs
      const ys = pr.map(p => Math.round(p.getBoundingClientRect().width * 64));
      ys.forEach((y, i) => { const want = ref(s, 16000 * (i + 1)); if (y !== want) { bad++; if (!first) first = { s, ys }; } });
    }
    res[mode] = { bad, first };
  }
  return res;
}
