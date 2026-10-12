// bench.js page.html seconds [stepsProp] — load a CSS VM page in headless Chromium and sample its
// step counter and frame rate. The page itself runs no script; sampling is done from the harness.
const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
const path = require('path');
(async () => {
  const [page_, secs = '60', prop = '--steps', sel = '#cpu'] = process.argv.slice(2);
  const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--no-proxy-server', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  p.on('console', m => console.error('console:', m.text()));
  const t0 = Date.now();
  await p.goto('file://' + path.resolve(page_), { timeout: 600000 });
  const loadMs = Date.now() - t0;
  const sample = () => p.evaluate(([prop, sel]) => {
    const v = +getComputedStyle(document.querySelector(sel)).getPropertyValue(prop);
    return v;
  }, [prop, sel]);
  const fps = () => p.evaluate(() => new Promise(r => { let n = 0; const s = performance.now();
    const f = () => { n++; if (performance.now() - s < 2000) requestAnimationFrame(f); else r(n / ((performance.now() - s) / 1000)); };
    requestAnimationFrame(f); }));
  const rows = []; const start = Date.now();
  while ((Date.now() - start) / 1000 < +secs) {
    const s = await sample(); rows.push([+((Date.now() - start) / 1000).toFixed(1), s]);
    await p.waitForTimeout(5000);
  }
  const f = await fps();
  const s1 = rows[1] || rows[0], s2 = rows[rows.length - 1];
  const rate = (s2[1] - s1[1]) / (s2[0] - s1[0]);
  console.log(JSON.stringify({ page: page_, loadMs, fps: +f.toFixed(2), stepsPerSec: +rate.toFixed(2), samples: rows }));
  await b.close();
})();
