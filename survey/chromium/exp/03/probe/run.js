// node run.js page.html [page2 ...] -> prints JSON of every element with an id: its --o / --d custom properties
// Harness only. Usage: run from this directory. ARGS="--enable-blink-features=X" adds flags.
const path = require('path');
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium',
    args: ['--no-sandbox', ...(process.env.ARGS ? process.env.ARGS.split(' ') : [])] });
  for (const f of process.argv.slice(2)) {
    const p = await b.newPage({ viewport: { width: 1000, height: 800 } });
    await p.goto('file://' + path.resolve(f));
    await p.evaluate(() => document.fonts.ready);
    await p.waitForTimeout(+(process.env.WAIT || 300));
    const r = await p.evaluate(() => {
      const out = {};
      for (const el of document.querySelectorAll('[id]')) {
        const cs = getComputedStyle(el);
        const o = {};
        for (const n of (el.dataset.read || '--o --d').split(' ')) { const v = cs.getPropertyValue(n).trim(); if (v !== '') o[n] = v; }
        if (el.dataset.w !== undefined) o.w = el.getBoundingClientRect().width;
        out[el.id] = o;
      }
      return out;
    });
    console.log('==', f);
    for (const [k, v] of Object.entries(r)) console.log(k.padEnd(14), JSON.stringify(v));
    await p.close();
  }
  await b.close();
})();
