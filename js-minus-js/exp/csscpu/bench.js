// bench.js page.xhtml — the CSS CPU toy (harness only). Checks the end state as built against page.json, then times
// full recalcs: each trial changes the loop's increment (the immediate of a code word) in the root's inline style and reads the
// whole end state (style only, no layout), checking it against the stepper's.
const { launch, open } = require('../../tools/browser.js');
const fs = require('fs');
(async () => {
  const [pg] = process.argv.slice(2);
  const want = JSON.parse(fs.readFileSync(pg + '.json'));
  const b = await launch(); const p = await open(b, pg, { viewport: { width: 400, height: 300 } });
  const r = await p.evaluate(want => {
    const root = document.querySelector('#root'), end = document.querySelector('.end');
    const L = document.querySelectorAll('.x').length, par = root.getAttribute('style').includes('--pcA');
    const Q = par ? 'AB'[L % 2] : '', S = par ? 'A' : '';
    const tag = {}; for (const m of root.getAttribute('style').matchAll(/--t(\d+): (\d+)/g)) tag[m[2]] = +m[1];
    const state = () => { const c = getComputedStyle(end), g = n => +c.getPropertyValue('--' + n);
      const o = { pc: g('pc' + Q), sp: g('sp' + Q), fp: g('fp' + Q), mem: {} };
      for (const a of Object.keys(want.mem)) o.mem[a] = g(`w${tag[Math.floor(a / 4)]}_${a % 4}${Q}`); return o; };
    const diff = (got, exp) => { const d = []; for (const n of ['pc', 'sp', 'fp']) if (got[n] !== exp[n]) d.push(`${n} ${got[n]}/${exp[n]}`);
      for (const [a, v] of Object.entries(exp.mem)) if (got.mem[a] !== v) d.push(`mem[${a}] ${got.mem[a]}/${v}`); return d; };
    const bad = diff(state(), want), t = [];
    for (const [i0, exp] of want.trials) {
      const t0 = performance.now(); root.style.setProperty(`--w${tag[Math.floor(want.tweak / 4)]}_${want.tweak % 4}${S}`, String(8192 + i0)); const got = state(); t.push(performance.now() - t0);
      const d = diff(got, exp); if (d.length) bad.push(`i0 ${i0}: ` + d.slice(0, 3).join(', '));
    }
    t.sort((a, b) => a - b);
    return { L, ok: bad.length === 0, bad: bad.slice(0, 4), medianMs: t[t.length >> 1], minMs: t[0] };
  }, want);
  console.log(JSON.stringify({ page: pg, ...r, usPerInstruction: +(r.medianMs * 1000 / r.L).toFixed(1) }));
  await b.close();
})();
