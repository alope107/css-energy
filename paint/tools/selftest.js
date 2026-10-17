// selftest.js — checks that selftest/site reports a correct host as all PASS and lights the right test for each
// simulated host fault (serve.js --fault). ~1 min.
//
//   node tools/selftest.js
//
// Expected:            A     B     C     D
//   correct host       PASS  PASS  PASS  PASS
//   --fault target     PASS  PASS  WAIT  PASS     (_headers matched on the rewrite target)
//   --fault strip      FAIL  WAIT  WAIT  WAIT     (Use-As-Dictionary stripped; A reads "NO DCZ")
//   --fault vary       PASS  PASS  PASS  STALE    (Vary: * dropped)
const path = require('path');
const { PAINT, serve, profileDir, sleep } = require('./lib.js');

const LIGHT = id => getComputedStyle(document.querySelector('#' + id + ' .v b'), '::after').content.replace(/"/g, '');
const EXPECT = {
  none:   { ta: 'PASS', tb: 'PASS', tc: 'PASS', td: 'PASS' },
  target: { ta: 'PASS', tb: 'PASS', tc: 'WAIT', td: 'PASS' },
  strip:  { ta: 'NO DCZ', tb: 'WAIT', tc: 'WAIT', td: 'WAIT' },
  vary:   { ta: 'PASS', tb: 'PASS', tc: 'PASS', td: 'STALE' },
};

(async () => {
  let bad = 0;
  for (const fault of Object.keys(EXPECT)) {
    const srv = await serve(path.join(PAINT, 'selftest', 'site'), ...(fault === 'none' ? [] : ['--fault', fault]));
    const prof = await profileDir();
    try {
      const c = await prof.ctx(), pg = c.pages()[0] || await c.newPage();
      await pg.goto(srv.base + '/'); await sleep(2000);
      await pg.reload(); await sleep(2000);                          // first load writes, the reload reads
      const got = {};
      for (const t of ['ta', 'tb', 'tc']) got[t] = await pg.evaluate(LIGHT, t);
      await pg.click('text=start the chain');
      for (let i = 0; i < 3; i++) { await sleep(1200); await pg.click('text=next'); }
      await sleep(2000); got.td = await pg.evaluate(LIGHT, 'td');
      const ok = Object.keys(EXPECT[fault]).every(t => got[t] === EXPECT[fault][t]);
      if (!ok) bad++;
      console.log(`${ok ? 'ok  ' : 'FAIL'} ${fault.padEnd(6)} A ${got.ta}  B ${got.tb}  C ${got.tc}  D ${got.td}`);
      await c.close();
    } finally { srv.stop(); prof.remove(); }
  }
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
