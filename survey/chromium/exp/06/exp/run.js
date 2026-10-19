// node run.js page.html [seconds] -> median UpdateLayoutTree / Layout / frame stats from a trace
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path'), fs = require('fs');
(async () => {
  const file = process.argv[2], secs = +(process.argv[3] || 3);
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', ...(process.env.FLAGS ? process.env.FLAGS.split(' ') : [])] });
  const p = await b.newPage();
  await p.goto('file://' + path.resolve(file));
  await p.waitForTimeout(800);
  const tp = path.resolve(file + '.trace.json');
  await b.startTracing(p, { path: tp, categories: ['devtools.timeline', 'blink', 'blink_style'] });
  await p.waitForTimeout(secs * 1000);
  await b.stopTracing();
  await b.close();
  const ev = JSON.parse(fs.readFileSync(tp)).traceEvents;
  const med = a => { a = a.slice().sort((x, y) => x - y); return a.length ? a[a.length >> 1] : 0; };
  const sum = a => a.reduce((x, y) => x + y, 0);
  const pick = n => ev.filter(e => e.name === n && e.ph === 'X').map(e => e.dur / 1000);
  const ult = pick('UpdateLayoutTree'), lay = pick('Layout'), rs = pick('Document::recalcStyle'), rb = pick('Document::rebuildLayoutTree');
  console.log(path.basename(file), `ULT n=${ult.length} med=${med(ult).toFixed(3)} ms, recalcStyle med=${med(rs).toFixed(3)}, rebuild med=${med(rb).toFixed(3)}, Layout n=${lay.length} med=${med(lay).toFixed(3)} ms`);
  fs.unlinkSync(tp);
})();
