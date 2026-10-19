const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.goto('file://' + path.join(__dirname, 'bug-smil-escaped-hyphen.html'));
  await page.waitForTimeout(300);
  console.log(await page.evaluate(() => [...document.querySelectorAll('rect')].map(r => getComputedStyle(r).fill).join(' | ')));
  await browser.close();
})();
