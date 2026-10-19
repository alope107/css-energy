const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage({ viewport: { width: 400, height: 400 } }); await p.goto('file://' + __dirname + '/sit.html'); await p.waitForTimeout(300);
  const st = async () => [await p.evaluate(() => scrollY), await p.$eval('#sc', e => e.scrollTop)];
  const r = { load: await st() };
  await p.click('#k'); await p.waitForTimeout(300); r.toggled = await st();
  await p.reload(); await p.waitForTimeout(500); r.reload = await st();
  await p.click('#k2'); await p.waitForTimeout(300); r.k2AfterReload = await st(); await p.mouse.wheel(0, 100); await p.waitForTimeout(400); r.wheeled = await st(); await p.click('#k2'); await p.waitForTimeout(300); r.k2offAfterWheel = await st();
  console.log(JSON.stringify(r)); await b.close();
})();
