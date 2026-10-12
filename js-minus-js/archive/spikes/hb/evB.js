async () => {
  const m = document.getElementById('m'), o = document.getElementById('out');
  const f = x => (x*x*7 + 3) % 65536;
  const rows = []; let ok = 0, bad = 0, lag1 = 0;
  let prev = null;
  for (let k = 0; k < 240; k++) {
    await new Promise(r => requestAnimationFrame(r));
    const x = +getComputedStyle(m).getPropertyValue('--x'), y = +getComputedStyle(o).getPropertyValue('--y');
    if (y === f(x)) ok++; else { bad++; if (prev !== null && y === f(prev)) lag1++; if (rows.length < 5) rows.push({x, y, want: f(x)}); }
    prev = x;
  }
  return { ok, bad, lag1, rows, distinctX: prev };
}
