// tracebench.js page.xhtml — like bench.js's trials, timed by Chrome's own trace (UpdateLayoutTree durations)
const { launch, open } = require('../../tools/browser.js');
const { record, durations, median } = require('../../../shared/js/trace.js');
(async () => {
  const [pg] = process.argv.slice(2);
  const b = await launch(); const p = await open(b, pg, { viewport: { width: 400, height: 300 } });
  const { events } = await record(p, {}, () => p.evaluate(() => {
    const root = document.querySelector('#root'), end = document.querySelector('.end');
    const k = [...root.getAttribute('style').matchAll(/--t(\d+): 256/g)][0][1], S = root.getAttribute('style').includes('--pcA') ? 'A' : '';
    for (let i = 0; i < 25; i++) { root.style.setProperty(`--w${k}_2${S}`, String(3 + 17 * i)); getComputedStyle(end).getPropertyValue('--pc'); }
  }));
  const d = durations(events, 'UpdateLayoutTree');
  console.log(pg, 'UpdateLayoutTree events', d.length, 'median ms', median(d).toFixed(2));
  await b.close();
})();
