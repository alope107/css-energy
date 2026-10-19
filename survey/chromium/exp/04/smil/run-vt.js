const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.goto('file://' + path.join(__dirname, 'vt.html'));
  const r = await page.evaluate(async () => {
    const rd = () => ({ w: getComputedStyle(document.getElementById('pr')).getPropertyValue('--w'),
      probe2Left: getComputedStyle(document.getElementById('probe2')).left,
      groupWidth: getComputedStyle(document.documentElement, '::view-transition-group(box)').width,
      activeVT: document.documentElement.matches(':active-view-transition') });
    const before = rd();
    const t = document.startViewTransition(() => { document.getElementById('box').style.width = '300px'; });
    await t.ready;
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const during = rd();
    t.skipTransition();
    await t.finished.catch(() => {});
    return { before, during, after: rd() };
  });
  console.log(JSON.stringify(r, null, 1));
  await browser.close();
})();
