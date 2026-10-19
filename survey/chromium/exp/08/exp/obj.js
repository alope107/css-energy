const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage(); await p.goto('file://' + __dirname + '/obj.html', { waitUntil: 'load' });
  await p.waitForTimeout(1500);
  const n = () => p.evaluate(() => window.length);
  const loaded = cls => p.evaluate(c => [...document.querySelectorAll('object.' + c)].filter(o => o.contentDocument && o.contentDocument.title === 's').length, cls);
  const r = { start: [await n(), await loaded('a'), await loaded('b')] };
  await p.click('#t'); await p.waitForTimeout(3000);
  r.swapped = [await n(), await loaded('a'), await loaded('b')];
  await p.click('#t'); await p.waitForTimeout(2000);
  r.back = [await n(), await loaded('a'), await loaded('b')];
  console.log(JSON.stringify(r)); await b.close();
})();
