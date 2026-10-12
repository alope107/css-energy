// usage: node run.js page.html [evalfile.js]  -> prints JSON result of the eval
const { chromium } = require('playwright-core');
const fs = require('fs');
(async () => {
  const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox','--no-proxy-server','--disable-gpu','--font-render-hinting=none'] });
  const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  p.on('console', m => console.error('console:', m.text()));
  await p.goto('file://' + require('path').resolve(process.argv[2]));
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(+process.env.WAIT || 300);
  const src = process.argv[3] ? fs.readFileSync(process.argv[3], 'utf8') : '() => document.title';
  const r = await p.evaluate(eval(src));
  console.log(JSON.stringify(r, null, 1));
  if (process.env.SHOT) await p.screenshot({ path: process.env.SHOT });
  await b.close();
})();
