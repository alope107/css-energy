const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 400, height: 300 } });
  await page.goto('file://' + path.join(__dirname, 'c.html'));
  const r = await page.evaluate(() => new Promise(res => {
    const cnt = { a16: 0, b16: 0, a1: 0, b1: 0, rep: 0 };
    for (const id of ['a16', 'b16', 'a1', 'b1']) document.getElementById(id).addEventListener('beginEvent', () => cnt[id]++);
    document.getElementById('cnt').addEventListener('repeatEvent', () => cnt.rep++);
    const x = id => document.getElementById(id).x.animVal.value;
    let frames = 0, ch16 = 0, ch1 = 0, last16 = x('t16'), last1 = x('t1');
    const xc0 = x('tc'), t0 = performance.now();
    const ft = [];
    function f(ts) {
      frames++; ft.push(ts);
      const v16 = x('t16'), v1 = x('t1');
      if (v16 !== last16) ch16++; if (v1 !== last1) ch1++;
      last16 = v16; last1 = v1;
      if (performance.now() - t0 < 2000) requestAnimationFrame(f);
      else {
        const dt = (performance.now() - t0) / 1000;
        const gaps = ft.slice(1).map((t, i) => t - ft[i]).sort((a, b) => a - b);
        res({ secs: dt.toFixed(2), frames, medianFrameMs: gaps[gaps.length >> 1].toFixed(2),
          beginEvents: cnt, perSec: Object.fromEntries(Object.entries(cnt).map(([k, v]) => [k, (v / dt).toFixed(0)])),
          valueChangesSeenPerFrame16: (ch16 / frames).toFixed(2), valueChangesSeenPerFrame1: (ch1 / frames).toFixed(2),
          counterStart: xc0, counterEnd: x('tc'), svgTime: document.querySelector('svg').getCurrentTime().toFixed(3) });
      }
    }
    requestAnimationFrame(f);
  }));
  console.log(JSON.stringify(r, null, 1));
  await browser.close();
})();
