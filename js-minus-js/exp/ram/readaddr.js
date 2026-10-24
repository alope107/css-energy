// readaddr.js page.html [page.html …] — times one read at a random address per trial on mkread.py's probe pages, each
// trial also writing one random cell (WRITE=0: no write), the pages interleaved round by round in one browser.
// Prints per page: median ms per trial (style + layout, forced by reading the port), and wrong reads. Harness only.
// ROUNDS (5), TRIALS (40 per round), FLAGS (extra Chromium flags; ident needs --enable-blink-features=CSSIdentFunction).
const path = require('path');
const B = require(path.join(__dirname, '..', '..', '..', 'shared', 'js', 'browser.js')).profile('fontcpu');
const median = a => { const s = [...a].sort((x, y) => x - y); return s.length ? s[s.length >> 1] : NaN; };
(async () => {
  const pages = process.argv.slice(2), ROUNDS = +(process.env.ROUNDS || 5), TRIALS = +(process.env.TRIALS || 40);
  const WRITE = process.env.WRITE !== '0';
  const b = await B.launch({ extraArgs: (process.env.FLAGS || '').split(' ').filter(Boolean) });
  const tabs = [];
  for (const f of pages) { const p = await B.open(b, f); await p.waitForTimeout(200); tabs.push(p); }
  const res = pages.map(() => ({ meds: [], bad: 0, n: 0 }));
  for (let r = 0; r < ROUNDS; r++) for (let i = 0; i < pages.length; i++) {
    const o = await tabs[i].evaluate(({ TRIALS, WRITE, seed }) => {
      const N = document.querySelectorAll('.w > i').length, rp = document.getElementById('rp');
      const grid = !!document.getElementById('probe');
      let s = seed; const rnd = n => { s = (s * 1103515245 + 12345) % 2147483648; return s % n; };
      const val = k => { const e = document.getElementById('v' + k); return grid ? parseFloat(e.style.getPropertyValue('--hv')) : parseFloat(e.style.width); };
      rp.getBoundingClientRect();
      const t = []; let bad = 0, ex = [];
      for (let j = 0; j < TRIALS; j++) {
        const a = rnd(N), w = rnd(N), nv = 1 + rnd(grid ? 996 : 99990);
        const t0 = performance.now();
        if (WRITE) { const e = document.getElementById('v' + w); if (grid) e.style.setProperty('--hv', nv + 'px'); else e.style.width = nv + 'px'; }
        for (const e of document.querySelectorAll('#mem, #rp, .gp, #probe')) e.style.setProperty('--addr', a); const ad = document.getElementById('adr'); if (ad) ad.style.width = (a + 1) + 'px';
        const got = rp.getBoundingClientRect().width;
        t.push(performance.now() - t0);
        if (Math.abs(got - val(a)) > 0.01) { bad++; if (ex.length < 3) ex.push([a, got, val(a)]); }
      }
      return { t, bad, ex };
    }, { TRIALS, WRITE, seed: 1 + r * 7919 + i });
    res[i].meds.push(median(o.t)); res[i].bad += o.bad; res[i].n += TRIALS; if (o.ex.length) res[i].ex = o.ex;
  }
  for (let i = 0; i < pages.length; i++)
    console.log(JSON.stringify({ page: path.basename(pages[i]), ms: +median(res[i].meds).toFixed(3), rounds: res[i].meds.map(x => +x.toFixed(2)), bad: res[i].bad, of: res[i].n, ex: res[i].ex }));
  await b.close();
})();
