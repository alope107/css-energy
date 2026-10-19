// node frames.js page — per-frame counts of Layout, UpdateLayoutTree, shapings (>0.01 ms), and whether shapings nest in Layout
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path'), fs = require('fs');
(async () => {
  const file = process.argv[2];
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage();
  await p.goto('file://' + path.resolve(file));
  await p.waitForTimeout(1000);
  const tp = path.resolve(file + '.trace.json');
  await b.startTracing(p, { path: tp, categories: ['devtools.timeline', 'blink', 'blink_style', 'disabled-by-default-devtools.timeline'] });
  await p.waitForTimeout(1500);
  await b.stopTracing(); await b.close();
  const ev = JSON.parse(fs.readFileSync(tp)).traceEvents; fs.unlinkSync(tp);
  const X = ev.filter(e => e.ph === 'X');
  const tidc = {}; for (const e of X) if (e.name === 'Layout') tidc[e.tid] = (tidc[e.tid] || 0) + 1;
  const tid = +Object.entries(tidc).sort((a, b) => b[1] - a[1])[0][0];
  const M = X.filter(e => e.tid === tid);
  const commits = M.filter(e => e.name === 'Commit').map(e => e.ts).sort((a, b) => a - b);
  const lay = M.filter(e => e.name === 'Layout'), sh = M.filter(e => e.name === 'InlineNode::ShapeTextIncludingFirstLine' && e.dur > 5);
  const ult = M.filter(e => e.name === 'UpdateLayoutTree'), uc = ev.filter(e => e.name === 'UpdateCounters');
  const rows = [];
  for (let i = 1; i < commits.length; i++) {
    const a = commits[i - 1], z = commits[i], inr = e => e.ts >= a && e.ts < z;
    const L = lay.filter(inr), S = sh.filter(inr);
    const perLayout = L.map(l => S.filter(s => s.ts >= l.ts && s.ts < l.ts + l.dur).length);
    rows.push(`layouts=${L.length} ULT=${ult.filter(inr).length} shapings=${S.length} perLayout=[${perLayout}]`);
  }
  console.log(path.basename(file), 'UpdateCounters events:', uc.length); console.log(rows.slice(2, 8).join('\n'));
})();
