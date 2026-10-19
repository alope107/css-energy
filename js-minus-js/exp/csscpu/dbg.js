// dbg.js page.html [frames] — the CSS CPU's registers at every frame (a rAF loop in the page reads #cpu), for comparing
// with sim.py pass by pass. Harness only.
const path = require('path');
const { launch, fileUrl } = require(path.join(__dirname, '..', '..', 'tools', 'browser.js'));
(async () => {
  const [pg, n = '40'] = process.argv.slice(2);
  const b = await launch({}); const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  await p.addInitScript(N => {
    window.__log = [];
    const names = ['--steps', '--pc', '--sp', '--fp', '--pend', '--optr', '--pst', '--halt', '--k', '--go'].concat(
      Array.from({ length: 32 }, (_, k) => '--T' + k), Array.from({ length: 16 }, (_, k) => '--F' + k), Array.from({ length: 128 }, (_, k) => `--W${k >> 2}_${k & 3}`));
    const f = () => { const e = document.querySelector('#cpu'); if (e) { const cs = getComputedStyle(e); window.__log.push(names.map(x => +cs.getPropertyValue(x))); }
                      if (window.__log.length < N) requestAnimationFrame(f); };
    requestAnimationFrame(f);
  }, +n);
  await p.goto(fileUrl(pg)); await p.waitForFunction(N => window.__log.length >= N, +n, { timeout: 120000 });
  console.log(JSON.stringify(await p.evaluate(() => window.__log)));
  await b.close();
})();
