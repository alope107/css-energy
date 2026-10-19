const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const port = process.argv[2], base = `http://localhost:${port}`;
  const ctx = await chromium.launchPersistentContext(__dirname + '/prof-' + Date.now(), { executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await ctx.newPage(); const out = {};
  // quick: show then hide after 100 ms (server answers after 400 ms)
  await p.goto(`${base}/page?k=quick&ms=0&mode=quick`); await p.waitForTimeout(400); await p.click('#t'); await p.waitForTimeout(100); await p.click('#t'); await p.waitForTimeout(1500);
  for (const m of ['anim_hide', 'cv_hide']) {
    await p.goto(`${base}/page?k=${m}&ms=1500&mode=${m}`); await p.waitForTimeout(400); await p.click('#t'); await p.waitForTimeout(500);
    out[m + '_at500'] = await p.$eval('.w', e => getComputedStyle(e).display); await p.waitForTimeout(1800);
    out[m + '_at2300'] = await p.$eval('.w', e => getComputedStyle(e).display);
  }
  await p.goto(base + '/probe'); await p.waitForTimeout(800);
  const log = await (await fetch(base + '/log')).json(); const h = await (await fetch(base + '/hash')).json();
  const inv = Object.fromEntries(Object.entries(h).map(([k, v]) => [v, k]));
  out.log = log.filter(e => /\/(d|r)\//.test(e.p)).map(e => e.p + ' ' + (inv[e.ad] || (e.ad ? '?' : '-')));
  console.log(JSON.stringify(out)); await ctx.close();
})();
