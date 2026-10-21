// halttime.js page.html [maxSec] — time from navigation to HALT (the page's --isHALT), polled every POLL ms (default 250); runMs: first step -> HALT; a run that doesn't halt prints the CPU's registers; checks console output against IMG (harness only)
const { launch, fileUrl, envArgs } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const { consoleCodes, gridRows } = require(require('path').join(__dirname, '..', 'tools', 'page.js'));
const fs = require('fs');
(async () => {
  const [pg, maxs = '300'] = process.argv.slice(2); const im = JSON.parse(fs.readFileSync(process.env.IMG || 'image.json'));
  const b = await launch({ extraArgs: envArgs('FLAGS') });
  const p = await b.newPage(process.env.FLAGS ? { viewport: null } : { viewport: { width: 1200, height: 800 }, deviceScaleFactor: +(process.env.DPR || 1) });
  const t0 = Date.now(); await p.goto(fileUrl(pg), { timeout: 600000 }); const tl = Date.now() - t0;
  let r, first = null;
  while ((Date.now() - t0) / 1000 < +maxs) {
    await p.waitForTimeout(+(process.env.POLL || 250));
    r = await p.evaluate(() => { const cs = getComputedStyle(document.querySelector('#cpu')); return { steps: +cs.getPropertyValue('--steps'), kind: +cs.getPropertyValue('--kind'), halted: +cs.getPropertyValue('--isHALT') === 1 }; });
    if (first === null && r.steps > 0) first = Date.now() - t0;
    if (r.halted) break;
  }
  const th = Date.now() - t0;
  const rows = gridRows(await consoleCodes(p), im.rows, im.cols);
  const ok = rows.join('\n').replace(/\s+$/, '') === im.expected.replace(/\s+$/, '');
  console.log(JSON.stringify({ page: pg, loadMs: tl, firstStepMs: first, haltMs: th, runMs: first === null ? null : th - first, steps: r.steps, kind: r.kind, outputOk: ok }));
  if (!ok) console.log(JSON.stringify({ got: rows.join('\n'), want: im.expected }));
  if (!r.halted) console.log(JSON.stringify({ notHalted: await p.evaluate(() => { const cs = getComputedStyle(document.querySelector('#cpu'));
    return Object.fromEntries(['steps', 'pc', 'rpc', 'sp', 'fp', 'pend', 'optr', 'pst', 'k', 'par', 'go', 'init', 'rLm', 'stale', 'pstale', 't', 'tprev']
      .map(n => [n, cs.getPropertyValue('--' + n).trim()])); }) }));
  await b.close();
})();
