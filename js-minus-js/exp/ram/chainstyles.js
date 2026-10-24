// chainstyles.js page.html … — elements restyled per trial on mkchain.py pages (invalidation trace): K levels restyled once
// each is linear; K(K+1)/2 would mean each container's layout restyles every level below it. Harness only.
const path = require('path');
const B = require(path.join(__dirname, '..', '..', '..', 'shared', 'js', 'browser.js')).profile('fontcpu');
const { record, CATS } = require(path.join(__dirname, '..', '..', '..', 'shared', 'js', 'trace.js'));
(async () => {
  const b = await B.launch({ extraArgs: (process.env.FLAGS || '').split(' ').filter(Boolean) }), T = 10;
  for (const f of process.argv.slice(2)) {
    const p = await B.open(b, f); await p.waitForTimeout(300);
    const run = () => p.evaluate(T => { const lv = document.querySelectorAll('.lv'), N = document.querySelectorAll('.w').length; let s = 5;
      for (let j = 0; j < T; j++) { s = (s * 1103515245 + 12345) % 2147483648; document.getElementById('chain').style.setProperty('--addr', s % N); lv[lv.length - 1].getBoundingClientRect(); } }, T);
    await run();
    const { events } = await record(p, { categories: CATS.invalidation }, run);
    const rs = events.filter(e => e.name === 'StyleResolver::ResolveStyle').length;
    console.log(JSON.stringify({ page: path.basename(f), levels: await p.evaluate(() => document.querySelectorAll('.lv').length), restylesPerTrial: rs / T }));
    await p.close();
  }
  await b.close();
})();
