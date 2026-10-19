const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage();
  for (const u of ['chrome://version', 'chrome://system']) {
    try { await p.goto(u); const t = await p.evaluate(() => document.body.innerText); console.log('==', u, '\n', t.slice(0, 3000)); } catch (e) { console.log(u, String(e).split('\n')[0]); }
  }
  await b.close();
})();
