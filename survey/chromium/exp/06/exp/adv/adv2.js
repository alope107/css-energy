const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage();
  await p.goto('file://' + path.resolve('adv1000.html')); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(300);
  const r = await p.evaluate(() => [...document.querySelectorAll('.r')].map(e => { const n = e.dataset.n, s = +e.dataset.s; const k = n.endsWith('x64') ? 64 : 1; const units = parseInt(n) * k; const exp = units * s / 1000; const w = e.getBoundingClientRect().width; return `${s}px ${n}: got ${w} exp ${exp} diff ${(w - exp).toFixed(6)}`; }));
  console.log(r.join('\n')); await b.close();
})();
