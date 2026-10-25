// restyles.js page.html — elements restyled (StyleResolver::ResolveStyle) and laid out per read trial on an mkread.py page,
// from an invalidation trace over TRIALS trials. Harness only.
const path = require('path');
const B = require(path.join(__dirname, '..', '..', '..', 'shared', 'js', 'browser.js')).profile('fontcpu');
const { record, CATS } = require(path.join(__dirname, '..', '..', '..', 'shared', 'js', 'trace.js'));
(async () => {
  const TRIALS = +(process.env.TRIALS || 10), WRITE = process.env.WRITE !== '0';
  const b = await B.launch();
  for (const f of process.argv.slice(2)) {
    const p = await B.open(b, f); await p.waitForTimeout(300);
    const run = () => p.evaluate(({ TRIALS, WRITE }) => {
      const N = document.querySelectorAll('.w > i').length, rp = document.getElementById('rp'); let s = 99;
      const rnd = n => { s = (s * 1103515245 + 12345) % 2147483648; return s % n; };
      for (let j = 0; j < TRIALS; j++) {
        const a = rnd(N), w = rnd(N);
        if (WRITE) document.getElementById('v' + w).style.width = (1 + rnd(9999)) + 'px';
        for (const e of document.querySelectorAll('#mem, #rp, .gp, #probe')) e.style.setProperty('--addr', a); const ad = document.getElementById('adr'); if (ad) ad.style.width = (a + 1) + 'px';
        rp.getBoundingClientRect();
      }
    }, { TRIALS, WRITE });
    await run();
    const { events } = await record(p, { categories: CATS.invalidation }, run);
    const rs = events.filter(e => e.name === 'StyleResolver::ResolveStyle').length;
    const lay = events.filter(e => e.name === 'Layout' && e.ph === 'X');
    const objs = lay.reduce((s, e) => s + ((e.args.beginData && e.args.beginData.dirtyObjects) || 0), 0);
    console.log(JSON.stringify({ page: path.basename(f), restylesPerTrial: +(rs / TRIALS).toFixed(1), dirtyObjectsPerTrial: +(objs / TRIALS).toFixed(1), layouts: lay.length }));
    await p.close();
  }
  await b.close();
})();
