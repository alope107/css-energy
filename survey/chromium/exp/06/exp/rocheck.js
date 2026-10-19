// chained-shaping correctness as rendered: ResizeObserver on every level's readers (no forced layout)
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  for (const f of process.argv.slice(2)) {
    const p = await b.newPage(); await p.goto('file://' + path.resolve(f)); await p.waitForTimeout(800);
    const r = await p.evaluate(() => new Promise(res => {
      const rd = [...document.querySelectorAll('.rd')];
      const K = Math.max(...rd.map(e => +[...e.classList].find(c => /^L\d+$/.test(c)).slice(1))) + 1;
      const val = new Map(); const out = [];
      const ro = new ResizeObserver(entries => {
        for (const e of entries) val.set(e.target, [Math.round(e.contentRect.width), Math.round(e.contentRect.height)]);
        // per level, reader values
        const L = []; for (const e of rd) { const k = +[...e.classList].find(c => /^L\d+$/.test(c)).slice(1); (L[k] = L[k] || []).push(...(val.get(e) || [NaN, NaN])); }
        let bad = 0; for (let k = 1; k < K; k++) for (let i = 0; i < L[0].length; i++) { const v = L[0][i], e = v - (v % 16) + ((v % 16) + k) % 16; if (L[k][i] !== e) bad++; }
        out.push(bad);
        if (out.length >= 30) { ro.disconnect(); res({ K, bad: out }); }
      });
      rd.forEach(e => ro.observe(e));
    }));
    console.log(path.basename(f).padEnd(16), JSON.stringify(r)); await p.close();
  }
  await b.close();
})();
