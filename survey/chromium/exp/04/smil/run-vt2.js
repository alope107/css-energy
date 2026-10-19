const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.goto('file://' + path.join(__dirname, 'vt2.html'));
  const r = await page.evaluate(async () => {
    const t = document.startViewTransition(() => { document.getElementById('box').style.width = '300px'; });
    await t.ready;
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const cs = getComputedStyle(document.documentElement, '::view-transition-image-pair(box)');
    const out = { q: cs.getPropertyValue('--q'), dur: cs.animationDuration, groupW: getComputedStyle(document.documentElement, '::view-transition-group(box)').width };
    t.skipTransition(); await t.finished.catch(() => {});
    return out;
  });
  console.log(JSON.stringify(r));
  await browser.close();
})();
