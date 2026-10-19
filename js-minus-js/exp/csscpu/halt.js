// halt.js page.html image.json [maxSec] — time from navigation to HALT on a CPU-only page, the CSS CPU's (--halt) or the
// font CPU's (--isHALT), polled every POLL ms (default 250, as machine/halttime.js); checks the console against the image's
// expected output. DEBUG=1 logs the registers at each poll; FRAMES=1 counts frames (a rAF loop). Harness only.
const path = require('path');
const { launch, fileUrl, envArgs } = require(path.join(__dirname, '..', '..', 'tools', 'browser.js'));
const { consoleCodes, gridRows } = require(path.join(__dirname, '..', '..', 'tools', 'page.js'));
const fs = require('fs');
(async () => {
  const [pg, img, maxs = '120'] = process.argv.slice(2); const im = JSON.parse(fs.readFileSync(img));
  const poll = +(process.env.POLL || 250);
  const b = await launch({ extraArgs: envArgs('FLAGS') });
  const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  if (process.env.FRAMES) await p.addInitScript(() => { window.__fr = []; const f = t => { window.__fr.push(t); requestAnimationFrame(f); }; requestAnimationFrame(f); });
  const t0 = Date.now(); await p.goto(fileUrl(pg), { timeout: 600000 }); const tl = Date.now() - t0;
  let r, first = null;
  while ((Date.now() - t0) / 1000 < +maxs) {
    await p.waitForTimeout(poll);
    r = await p.evaluate(() => {
      const cs = getComputedStyle(document.querySelector('#cpu')); const g = n => +cs.getPropertyValue(n);
      return { steps: g('--steps'), pc: g('--pc'), sp: g('--sp'), pend: g('--pend'), halted: g('--halt') === 1 || g('--isHALT') === 1 };
    });
    if (process.env.DEBUG) console.log(Date.now() - t0, JSON.stringify(r));
    if (first === null && r.steps > 0) first = Date.now() - t0;
    if (r.halted) break;
  }
  const th = Date.now() - t0;
  if (process.env.FRAMES) { const fr = await p.evaluate(() => window.__fr); const d = fr.slice(1).map((t, i) => t - fr[i]).sort((a, b) => a - b);
    console.log(JSON.stringify({ frames: fr.length, medianFrameMs: +d[d.length >> 1].toFixed(1), p90: +d[Math.floor(d.length * .9)].toFixed(1) })); }
  const rows = gridRows(await consoleCodes(p), im.rows, im.cols);
  const ok = rows.join('\n').replace(/\s+$/, '') === im.expected.replace(/\s+$/, '');
  console.log(JSON.stringify({ page: path.basename(pg), loadMs: tl, firstStepMs: first, haltMs: th, halted: r.halted, steps: r.steps, want: im.steps, outputOk: ok }));
  if (!ok) console.log(JSON.stringify({ got: rows.join('\n'), want: im.expected }));
  await b.close();
})();
