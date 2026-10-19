const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
const { execSync } = require('child_process');
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  const file = process.argv[2] || 'm.html';
  await page.goto('file://' + path.join(__dirname, file));
  const cdp = await page.context().newCDPSession(page);
  const bcdp = await browser.newBrowserCDPSession();
  const info = await bcdp.send('SystemInfo.getProcessInfo');
  const rpids = info.processInfo.filter(p => p.type === 'renderer').map(p => p.id);
  const rss = () => rpids.map(pid => { try { const m = require('fs').readFileSync(`/proc/${pid}/status`, 'utf8').match(/VmRSS:\s+(\d+)/); return m ? +m[1] : 0; } catch (e) { return 0; } }).reduce((a, b) => a + b, 0);
  const sample = async () => {
    const fr = await page.evaluate(() => new Promise(r => { let n = 0; const t0 = performance.now();
      (function f() { n++; if (performance.now() - t0 < 1000) requestAnimationFrame(f); else r(n); })(); }));
    const t = await page.evaluate(() => document.querySelector('svg').getCurrentTime().toFixed(2));
    return { svgTime: t, fps: fr, rendererRssMB: (rss() / 1024).toFixed(1) };
  };
  console.log(JSON.stringify(await sample()));
  await page.waitForTimeout(8000);
  console.log(JSON.stringify(await sample()));
  await page.waitForTimeout(8000);
  console.log(JSON.stringify(await sample()));
  await browser.close();
})();
