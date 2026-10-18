// check chained-shaping pages: in one forced layout, every level's span widths must be level 0's + k in the low digit;
// sampled in several frames (rAF), with the clock running
const { launch } = require('../lib.js'); const url = require('url'), path = require('path');
(async () => {
  const b = await launch();
  for (const f of process.argv.slice(2)) {
    const p = await b.newPage(); await p.goto(url.pathToFileURL(path.resolve(f)).href); await p.waitForTimeout(500);
    const r = await p.evaluate(() => new Promise(res => { const out = []; let n = 0;
      const tick = () => { const L = [...document.querySelectorAll('.st')].map(s => [...s.children].map(x => Math.round(x.getBoundingClientRect().width)));
        let bad = 0; for (let k = 1; k < L.length; k++) for (let i = 0; i < L[0].length; i++) { const v = L[0][i], e = v - (v % 16) + ((v % 16) + k) % 16; if (L[k][i] !== e) bad++; }
        out.push(bad); if (++n < 10) requestAnimationFrame(tick); else res({ K: L.length, R: L[0].length, bad: out }); };
      requestAnimationFrame(tick); }));
    console.log(path.basename(f).padEnd(20), JSON.stringify(r)); await p.close();
  }
  await b.close();
})();
