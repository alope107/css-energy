const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.goto('file://' + path.join(__dirname, 'prec.html'));
  await page.waitForTimeout(300);
  console.log(await page.evaluate(() => ({ foWidth: getComputedStyle(document.getElementById('fo')).width, foAnimVal: document.getElementById('fo').width.animVal.value,
    gVisibility: getComputedStyle(document.getElementById('g')).visibility, g2Opacity: getComputedStyle(document.getElementById('g2')).opacity })));
  await browser.close();
})();
