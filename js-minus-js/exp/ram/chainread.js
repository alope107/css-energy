// chainread.js page.html [page.html …] — mkchain.py's pages: set --addr, force one style + layout, read the last level's
// width; times it and checks it against the list walked in script. Pages interleaved round by round. Harness only.
const path = require('path');
const B = require(path.join(__dirname, '..', '..', '..', 'shared', 'js', 'browser.js')).profile('fontcpu');
const median = a => { const s = [...a].sort((x, y) => x - y); return s.length ? s[s.length >> 1] : NaN; };
(async () => {
  const pages = process.argv.slice(2), ROUNDS = +(process.env.ROUNDS || 5), TRIALS = +(process.env.TRIALS || 20);
  const b = await B.launch({ extraArgs: (process.env.FLAGS || '').split(' ').filter(Boolean) });
  const tabs = []; for (const f of pages) { const p = await B.open(b, f); await p.waitForTimeout(200); tabs.push(p); }
  const res = pages.map(() => ({ meds: [], bad: 0, n: 0 }));
  for (let r = 0; r < ROUNDS; r++) for (let i = 0; i < pages.length; i++) {
    const o = await tabs[i].evaluate(({ TRIALS, seed }) => {
      const N = document.querySelectorAll('.w').length, lv = document.querySelectorAll('.lv'), K = lv.length, last = lv[K - 1];
      const nxt = k => parseFloat(document.getElementById('v' + k).style.width) - 1;
      let s = seed; const rnd = n => { s = (s * 1103515245 + 12345) % 2147483648; return s % n; };
      last.getBoundingClientRect(); const t = []; let bad = 0, ex = [];
      for (let j = 0; j < TRIALS; j++) {
        const a = rnd(N); let e = a; for (let q = 0; q < K; q++) e = nxt(e);
        const t0 = performance.now();
        document.getElementById('chain').style.setProperty('--addr', a);
        const got = last.getBoundingClientRect().width - 1;
        t.push(performance.now() - t0);
        if (got !== e) { bad++; if (ex.length < 3) ex.push([a, got, e, [...lv].slice(0, 4).map(x => x.getBoundingClientRect().width - 1)]); }
      }
      return { t, bad, ex };
    }, { TRIALS, seed: 1 + r * 7919 + i });
    res[i].meds.push(median(o.t)); res[i].bad += o.bad; res[i].n += TRIALS; if (o.ex.length) res[i].ex = o.ex;
  }
  for (let i = 0; i < pages.length; i++)
    console.log(JSON.stringify({ page: path.basename(pages[i]), ms: +median(res[i].meds).toFixed(3), rounds: res[i].meds.map(x => +x.toFixed(2)), bad: res[i].bad, of: res[i].n, ex: res[i].ex }));
  await b.close();
})();
