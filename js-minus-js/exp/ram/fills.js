// fills.js page.html [frames] — every frame's steps, pc, pending miss and the read ports' words (--mv0..7) on a CPU-only
// page, as JSON lines: diff two builds of one program to find the first fill that differs. Harness only.
const path = require('path');
const B = require(path.join(__dirname, '..', '..', '..', 'shared', 'js', 'browser.js')).profile('fontcpu');
(async () => {
  const [pg, n = '400'] = process.argv.slice(2);
  const b = await B.launch(); const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  await p.addInitScript(N => {
    window.__log = [];
    const names = ['--steps', '--pc', '--pend', '--halt'].concat(Array.from({ length: 8 }, (_, i) => '--mv' + i));
    const f = () => { const e = document.querySelector('#cpu'); if (e) { const cs = getComputedStyle(e); window.__log.push(names.map(x => +cs.getPropertyValue(x))); }
                      if (window.__log.length < N && !(window.__log.length && window.__log[window.__log.length - 1][3] === 1)) requestAnimationFrame(f); };
    requestAnimationFrame(f);
  }, +n);
  await p.goto('file://' + path.resolve(pg));
  await p.waitForFunction(N => window.__log.length >= N || (window.__log.length && window.__log[window.__log.length - 1][3] === 1), +n, { timeout: 120000 });
  for (const r of await p.evaluate(() => window.__log)) console.log(r.join(' '));
  await b.close();
})();
