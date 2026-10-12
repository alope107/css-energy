async () => {
  const PROG = [['JODD',3],['SHR1',0],['JMP',5],['SHR1',0],['XORI',0xB8],['XORI',0x2D],['JZ',9],['XORI',0x2D],['JMP',0],['HALT',0]];
  const step = (p, a) => { if (p >= PROG.length) return [p,a]; const [op,k] = PROG[p];
    switch (op) { case 'JODD': return [a&1 ? k : p+1, a]; case 'SHR1': return [p+1, a>>1]; case 'JMP': return [k, a];
      case 'XORI': return [p+1, a^k]; case 'JZ': return [a===0 ? k : p+1, a]; default: return [p, a]; } };
  const ref = (s, n) => { let p = s >> 8, a = s & 255; for (let i = 0; i < n; i++) [p, a] = step(p, a); return p*256 + a; };
  // start states chosen so the LFSR runs long (pc 0, varying acc) -- check every level's output
  const m = document.getElementById('m'), outs = [...document.querySelectorAll('.out')];
  let bad = 0, first = null, halted = 0; const T = [];
  for (let t = 0; t < 40; t++) {
    const s = (t * 53) % 256;
    const t0 = performance.now(); m.style.setProperty('--s', s);
    const ys = outs.map(o => +getComputedStyle(o).getPropertyValue('--y')); T.push(performance.now() - t0);
    ys.forEach((y, i) => { const want = ref(s, 16000 * (i + 1)); if (y !== want) { bad++; if (!first) first = { s, level: i, y, want }; } });
    if ((ys[ys.length-1] >> 8) === 9) halted++;
  }
  T.sort((a,b)=>a-b);
  return { levels: outs.length, steps_per_update: 16000 * outs.length, bad, first, halted_of_40: halted, median_ms: +T[20].toFixed(2) };
}
