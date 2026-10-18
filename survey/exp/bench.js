// node bench.js [--rounds R] [--dur ms] [--probe 'js expr'] page.html ... — interleaved rounds; per page the median over
// rounds of: median UpdateLayoutTree (style) ms, median Layout ms, style+layout per frame, fps (as css-physics stylebench)
const { launch } = require('./lib.js');
const { record, durations, median } = require('/workspaces/css-energy/shared/js/trace.js');
const { countFrames } = require('/workspaces/css-energy/shared/js/page.js');
const url = require('url');
(async () => {
  const a = process.argv.slice(2); let R = 3, dur = 1500, probe = null; const pages = [];
  for (let i = 0; i < a.length; i++) { if (a[i] === '--rounds') R = +a[++i]; else if (a[i] === '--dur') dur = +a[++i]; else if (a[i] === '--probe') probe = a[++i]; else pages.push(a[i]); }
  const b = await launch(['--no-zygote', '--disable-setuid-sandbox']);
  const res = {};
  for (let r = 0; r < R; r++) for (let j = 0; j < pages.length; j++) {
    const f = pages[(j + r) % pages.length];
    const p = await b.newPage({ viewport: { width: 1000, height: 800 } });
    await p.goto(url.pathToFileURL(require('path').resolve(f)).href); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(600);
    const { events, result: fr } = await record(p, {}, () => countFrames(p, dur));
    const st = durations(events, 'UpdateLayoutTree'), ly = durations(events, 'Layout');
    const pr = probe ? await p.evaluate(s => eval(s), probe) : '';
    (res[f] = res[f] || []).push([median(st), median(ly), (st.reduce((x, y) => x + y, 0) + ly.reduce((x, y) => x + y, 0)) / Math.max(1, fr), fr / dur * 1000, pr]);
    await p.close();
  }
  for (const f of pages) {
    const m = k => median(res[f].map(x => x[k]));
    console.log(`${require('path').basename(f).padEnd(28)} style ${m(0).toFixed(3)}  layout ${m(1).toFixed(3)}  s+l/frame ${m(2).toFixed(2)}  fps ${m(3).toFixed(1)}  ${res[f].map(x => x[4]).join(' | ')}`);
  }
  await b.close();
})();
