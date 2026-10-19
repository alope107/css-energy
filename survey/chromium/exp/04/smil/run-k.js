const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.goto('file://' + path.join(__dirname, 'k.html'));
  await page.waitForTimeout(200);
  await page.evaluate(() => { window.__c = 0; document.getElementById('bk').addEventListener('click', () => __c++); document.getElementById('bk').addEventListener('focus', () => __c += 100); });
  await page.keyboard.press('Alt+k');
  await page.keyboard.down('Alt'); await page.keyboard.down('Shift'); await page.keyboard.press('k'); await page.keyboard.up('Shift'); await page.keyboard.up('Alt');
  await page.waitForTimeout(100);
  console.log('after Alt+k:', await page.evaluate(() => [document.getElementById('flag').className.animVal, __c]));
  await browser.close();
})();
