// halttime.js page.html [maxSec] — time from navigation to HALT (kind 97), polled every 250 ms; checks console output against IMG (harness only)
const { chromium } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const path = require('path'), fs = require('fs');
(async () => {
  const [pg, maxs = '300'] = process.argv.slice(2); const im = JSON.parse(fs.readFileSync(process.env.IMG || 'image.json'));
  const b = await chromium.launch({ args: ['--no-sandbox', '--no-proxy-server', '--disable-gpu', ...(process.env.FLAGS ? process.env.FLAGS.split(' ') : [])] });
  const p = await b.newPage(process.env.FLAGS ? { viewport: null } : { viewport: { width: 1200, height: 800 }, deviceScaleFactor: +(process.env.DPR || 1) });
  const t0 = Date.now(); await p.goto('file://' + path.resolve(pg), { timeout: 600000 }); const tl = Date.now() - t0;
  let r, first = null;
  while ((Date.now() - t0) / 1000 < +maxs) {
    await p.waitForTimeout(250);
    r = await p.evaluate(() => { const cs = getComputedStyle(document.querySelector('#cpu')); return { steps: +cs.getPropertyValue('--steps'), kind: +cs.getPropertyValue('--kind') }; });
    if (first === null && r.steps > 0) first = Date.now() - t0;
    if (r.kind === 97) break;
  }
  const th = Date.now() - t0;
  const codes = await p.evaluate(() => [...document.querySelectorAll('.oc > b')].map(e => Math.round(e.parentElement.getBoundingClientRect().width) - 1048576));
  const rows = []; for (let i = 0; i < im.rows; i++) rows.push(codes.slice(i * im.cols, (i + 1) * im.cols).map(c => c >= 32 && c < 127 ? String.fromCharCode(c) : ' ').join('').replace(/\s+$/, ''));
  const ok = rows.join('\n').replace(/\s+$/, '') === im.expected.replace(/\s+$/, '');
  console.log(JSON.stringify({ page: pg, loadMs: tl, firstStepMs: first, haltMs: th, steps: r.steps, kind: r.kind, outputOk: ok }));
  if (!ok) console.log(JSON.stringify({ got: rows.join('\n'), want: im.expected }));
  await b.close();
})();
