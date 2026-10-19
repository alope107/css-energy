const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path'), fs = require('fs');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  for (const file of process.argv.slice(2)) {
    const p = await b.newPage();
    await p.goto('file://' + path.resolve(file));
    await p.waitForTimeout(1000);
    const w = await p.evaluate(() => [...document.querySelectorAll('#w i')].slice(0, 3).map(e => e.getBoundingClientRect().width.toFixed(3)).join(','));
    const tp = path.resolve(file + '.trace.json');
    await b.startTracing(p, { path: tp, categories: ['devtools.timeline', 'blink', 'blink_style'] });
    await p.waitForTimeout(2500);
    await b.stopTracing();
    await p.close();
    const ev = JSON.parse(fs.readFileSync(tp)).traceEvents; fs.unlinkSync(tp);
    const med = a => { a = a.slice().sort((x, y) => x - y); return a.length ? a[a.length >> 1] : 0; };
    const pick = n => ev.filter(e => e.name === n && e.ph === 'X').map(e => e.dur / 1000);
    const rs = pick('Document::recalcStyle'), ult = pick('UpdateLayoutTree'), lay = pick('Layout');
    console.log(file.padEnd(34), `w=${w} recalcStyle n=${rs.length} med=${med(rs).toFixed(3)} ms  ULT med=${med(ult).toFixed(3)}  Layout med=${med(lay).toFixed(3)}`);
  }
  await b.close();
})();
