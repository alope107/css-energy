// bench2.js page.html secs — sample steps, shapings (--nsh) and frames over a window (harness only; page has no script)
const { chromium } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const path = require('path');
(async () => {
  const [pg, secs = '60'] = process.argv.slice(2);
  const b = await chromium.launch({ args: ['--no-sandbox', '--no-proxy-server', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  await p.addInitScript(() => { window.__fr = 0; const f = () => { __fr++; requestAnimationFrame(f); }; requestAnimationFrame(f); });
  await p.goto('file://' + path.resolve(pg), { timeout: 600000 });
  await p.waitForTimeout(5000);
  const s = () => p.evaluate(() => { const cs = getComputedStyle(document.querySelector('#cpu'));
    return { t: performance.now() / 1000, fr: __fr, steps: +cs.getPropertyValue('--steps'), nsh: +cs.getPropertyValue('--nsh') }; });
  const a = await s(); await p.waitForTimeout(+secs * 1000); const z = await s();
  const dt = z.t - a.t;
  console.log(JSON.stringify({ page: pg, secs: +dt.toFixed(1), fps: +((z.fr - a.fr) / dt).toFixed(2), stepsPerSec: +((z.steps - a.steps) / dt).toFixed(2),
    shapingsPerSec: +((z.nsh - a.nsh) / dt).toFixed(2), stepsPerFrame: +((z.steps - a.steps) / (z.fr - a.fr)).toFixed(2), a, z }));
  await b.close();
})();
