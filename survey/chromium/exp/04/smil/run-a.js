const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 800, height: 600 } });
  await page.goto('file://' + path.join(__dirname, 'a.html'));
  await page.waitForTimeout(500);
  const read = () => page.evaluate(() => {
    const g = (id, p) => getComputedStyle(document.getElementById(id)).getPropertyValue(p).trim();
    return { w: g('cqread', '--w'), s: g('s2read', '--s'), c: g('out', '--c'), h: g('out', '--h'), e: g('out', '--e'), k: g('out', '--k'), f: g('fread', '--f'),
      flagClass: document.getElementById('flag').getAttribute('class'), flagClassName: document.getElementById('flag').className.animVal,
      foWidthAttr: document.getElementById('fo').getAttribute('width'), foAnim: document.getElementById('fo').width.animVal.value,
      foCSSWidth: getComputedStyle(document.getElementById('fo')).width };
  });
  console.log('before', JSON.stringify(await read()));
  // timing probe on #r click
  await page.evaluate(() => {
    window.__log = [];
    const g = () => getComputedStyle(document.getElementById('cqread')).getPropertyValue('--w').trim() + '/' +
      getComputedStyle(document.getElementById('out')).getPropertyValue('--c').trim() + '/' + getComputedStyle(document.getElementById('s2read')).getPropertyValue('--s').trim();
    document.getElementById('r').addEventListener('click', () => {
      const t0 = performance.now();
      __log.push(['sync-in-handler', g()]);
      queueMicrotask(() => __log.push(['microtask', g()]));
      setTimeout(() => __log.push(['setTimeout0', g(), (performance.now() - t0).toFixed(1)]), 0);
      requestAnimationFrame(() => { __log.push(['rAF1', g(), (performance.now() - t0).toFixed(1)]);
        requestAnimationFrame(() => __log.push(['rAF2', g()])); });
    });
    document.getElementById('setflag').addEventListener('beginEvent', () => __log.push(['beginEvent(flag set)', g()]));
  });
  await page.mouse.click(25, 25); // #r
  await page.waitForTimeout(200);
  console.log('log', JSON.stringify(await page.evaluate(() => __log)));
  console.log('after r click', JSON.stringify(await read()));
  await page.mouse.click(85, 25); // #r2
  await page.mouse.click(50, 215); // #hb
  await page.mouse.click(150, 215); // #my-btn
  await page.waitForTimeout(200);
  console.log('after r2/hb/my-btn', JSON.stringify(await read()));
  await browser.close();
})();
