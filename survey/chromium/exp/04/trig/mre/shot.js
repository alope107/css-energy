const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage();
  await p.goto('file://' + __dirname + '/chrome-zero-duration-stale-phase.html');
  await p.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 100)))));
  console.log(await p.evaluate(() => ['a','a2','c'].map(id => id + '=' + getComputedStyle(document.getElementById(id)).backgroundColor).join(' ')));
  await b.close();
})();
