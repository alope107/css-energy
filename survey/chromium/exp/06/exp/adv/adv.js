const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', ...(process.env.FLAGS ? process.env.FLAGS.split(' ') : [])] });
  const p = await b.newPage({ deviceScaleFactor: +(process.env.DSF || 1) });
  await p.goto('file://' + path.resolve('adv.html'));
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(300);
  const r = await p.evaluate(() => [...document.querySelectorAll('.r')].map(e => `${e.id}=${e.getBoundingClientRect().width}`).join('  '));
  console.log('DSF', process.env.DSF || 1, process.env.FLAGS || '', '\n ', r);
  await b.close();
})();
