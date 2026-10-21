// hang.js page.html [runs] [maxSec] — runs a CPU-only page to HALT `runs` times (a fresh page each); a run that hasn't
// halted after maxSec prints the CPU's registers then, and twice more a second apart (is it still moving?). FRESH=1: a
// fresh browser per run (as ab.js runs halttime.js). Harness only.
const path = require('path');
const { launch, fileUrl } = require(path.join(__dirname, '..', '..', 'tools', 'browser.js'));
(async () => {
  const [pg, runs = '10', maxs = '30'] = process.argv.slice(2);
  const names = ['steps', 'pc', 'rpc', 'fp', 'rfp', 'pend', 'optr', 'pst', 'halt', 'k', 'par', 'go', 'fresh', 'init', 'rLm', 'rLf', 'rLg', 'rLx', 'rLy', 'rLz',
                 'stale', 'pstale', 'fon', 'fb', 'fk1', 'gk1', 't', 'tprev'].concat(Array.from({ length: 32 }, (_, k) => 'T' + k));
  let b = await launch({});
  for (let i = 0; i < +runs; i++) {
    if (process.env.FRESH && i) { await b.close(); b = await launch({}); }
    const p = await b.newPage({ viewport: { width: 1200, height: 800 } }); const t0 = Date.now();
    await p.goto(fileUrl(pg));
    const regs = () => p.evaluate(ns => { const cs = getComputedStyle(document.querySelector('#cpu')); return Object.fromEntries(ns.map(n => [n, +cs.getPropertyValue('--' + n)])); }, names);
    let r;
    while (true) {
      await p.waitForTimeout(50); r = await regs();
      if (r.halt === 1 || Date.now() - t0 > 1000 * +maxs) break;
    }
    if (r.halt === 1) console.log(`run ${i}: halted ${Date.now() - t0} ms, steps ${r.steps}`);
    else {
      console.log(`run ${i}: NOT halted after ${maxs} s`);
      for (let j = 0; j < 3; j++) { console.log(JSON.stringify(r)); await p.waitForTimeout(1000); r = await regs(); }
    }
    await p.close();
  }
  await b.close();
})();
