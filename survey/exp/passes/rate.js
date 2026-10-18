// useful passes per frame: counter increments / frames over 2 s (only two forced style reads, at the ends)
const { launch } = require('../lib.js'); const url = require('url'), path = require('path');
(async () => {
  const b = await launch(process.env.FLAGS ? process.env.FLAGS.split(' ') : []);
  for (const f of process.argv.slice(2)) {
    const p = await b.newPage(); await p.goto(url.pathToFileURL(path.resolve(f)).href); await p.waitForTimeout(500);
    const r = await p.evaluate(() => new Promise(res => {
      const n = () => +getComputedStyle(document.getElementById('top')).getPropertyValue('--n');
      const n0 = n(); let fr = 0; const t0 = performance.now();
      const tick = () => { fr++; if (performance.now() - t0 < 2000) requestAnimationFrame(tick); else { const n1 = n(); res({ frames: fr, inc: n1 - n0, perFrame: +((n1 - n0) / fr).toFixed(2) }); } };
      requestAnimationFrame(tick); }));
    console.log(path.basename(f).padEnd(12), JSON.stringify(r)); await p.close();
  }
  await b.close();
})();
