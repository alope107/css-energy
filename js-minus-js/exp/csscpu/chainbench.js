// chainbench.js page.html — the CSS CPU's chain alone (machine/gen_css.py BENCH=1). Checks the end state against page.html.json,
// then times full recalcs: each trial changes --steps in the root's inline style, which every level depends on, and reads
// the end (style only, no layout). Harness only.
const path = require('path');
const { launch, fileUrl } = require(path.join(__dirname, '..', '..', 'tools', 'browser.js'));
const fs = require('fs');
(async () => {
  const [pg] = process.argv.slice(2); const want = JSON.parse(fs.readFileSync(pg + '.json'));
  const b = await launch({}); const p = await b.newPage({ viewport: { width: 400, height: 300 } });
  await p.goto(fileUrl(pg));
  const r = await p.evaluate(want => {
    const root = document.querySelector('#root'), end = document.querySelector('.end');
    const s0 = +root.style.getPropertyValue('--steps');
    const get = () => { const c = getComputedStyle(end), g = n => +c.getPropertyValue('--' + n); return { pc: g('pc'), sp: g('sp'), fp: g('fp'), steps: g('steps') }; };
    const g0 = get(); const bad = ['pc', 'sp', 'fp', 'steps'].filter(n => g0[n] !== want[n]).map(n => `${n} ${g0[n]}/${want[n]}`);
    const t = [];
    for (let i = 1; i <= 41; i++) {
      const t0 = performance.now(); root.style.setProperty('--steps', String(s0 + 1000 * i)); const g = get(); t.push(performance.now() - t0);
      if (g.steps !== want.steps + 1000 * i || g.pc !== want.pc) bad.push(`trial ${i}: steps ${g.steps} pc ${g.pc}`);
    }
    t.sort((a, b) => a - b);
    return { ok: bad.length === 0, bad: bad.slice(0, 3), medianMs: +t[t.length >> 1].toFixed(2), minMs: +t[0].toFixed(2) };
  }, want);
  console.log(JSON.stringify({ page: path.basename(pg), K: want.K, stall: want.stall, ...r, usPerLevel: +(r.medianMs * 1000 / want.K).toFixed(1) }));
  await b.close();
})();
