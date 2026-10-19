const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const fs = require('fs'), path = require('path');
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  for (const mode of ['none', 'cb', 'cb+cb2']) {
    const page = await browser.newPage();
    await page.route('http://vt.test/**', r => r.fulfill({ contentType: 'text/html', body: fs.readFileSync(path.join(__dirname, 'vtx', path.basename(new URL(r.request().url()).pathname))) }));
    await page.goto('http://vt.test/old.html');
    await page.waitForTimeout(200);
    if (mode.includes('cb')) await page.check('#cb');
    if (mode.includes('cb2')) await page.check('#cb2');
    await page.waitForTimeout(100);
    await page.click('#go');
    await page.waitForURL('**/new.html');
    await page.waitForTimeout(2000);
    const t = await page.evaluate(() => ({ t: getComputedStyle(document.getElementById('meter')).getPropertyValue('--t'), active: document.documentElement.matches(':active-view-transition') }));
    console.log(mode, JSON.stringify(t));
    await page.close();
  }
  await browser.close();
})();
