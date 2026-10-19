const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const port = process.argv[2], base = `http://localhost:${port}`;
  const ctx = await chromium.launchPersistentContext(__dirname + '/prof-' + Date.now(), { executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await ctx.newPage();
  for (const [k, ms] of [['short', 60], ['long', 1500]]) {
    await p.goto(`${base}/page?k=${k}&ms=${ms}`); await p.waitForTimeout(500);
    await p.click('#t'); await p.waitForTimeout(2500);
    console.log(k, 'still candidate?', await p.$eval('.w', e => getComputedStyle(e).display));
  }
  await p.goto(base + '/probe'); await p.waitForTimeout(800);
  const log = await (await fetch(base + '/log')).json(); const h = await (await fetch(base + '/hash')).json();
  console.log(JSON.stringify(log.filter(e => /\/(d|r)\//.test(e.p)).map(e => [e.p, e.ad === h.short ? 'AD=short' : e.ad === h.long ? 'AD=long' : e.ad ? 'AD=?' : '-'])));
  await ctx.close();
})();
