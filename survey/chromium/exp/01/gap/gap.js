// node gap.js <extra chromium flags...> : BeginMainFrame durations and gaps on the renderer main thread
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', ...process.argv.slice(2)] });
  const p = await b.newPage();
  await p.goto('file://' + path.join(__dirname, 'heavy.html'));
  await p.waitForTimeout(1000);
  const cdp = await b.newBrowserCDPSession();
  const ev = []; cdp.on('Tracing.dataCollected', d => ev.push(...d.value));
  await cdp.send('Tracing.start', { categories: 'cc,blink,devtools.timeline,viz,benchmark', transferMode: 'ReportEvents' });
  const raf = await p.evaluate(() => new Promise(r => { let n = 0; const t0 = performance.now(); (function f() { n++; if (performance.now() - t0 < 3000) requestAnimationFrame(f); else r(n / 3) })() }));
  const done = new Promise(r => cdp.once('Tracing.tracingComplete', r)); await cdp.send('Tracing.end'); await done;
  const bmf = ev.filter(e => e.name === 'ProxyMain::BeginMainFrame' && e.ph === 'X').sort((a, b) => a.ts - b.ts);
  // keep the renderer main thread with the most BMFs
  const byTid = {}; bmf.forEach(e => (byTid[e.pid + ':' + e.tid] ||= []).push(e));
  const main = Object.values(byTid).sort((a, b) => b.length - a.length)[0] || [];
  const durs = main.map(e => e.dur / 1000), gaps = main.slice(1).map((e, i) => (e.ts - (main[i].ts + main[i].dur)) / 1000);
  const med = a => { const v = [...a].sort((x, y) => x - y); return v.length ? v[v.length >> 1].toFixed(1) : 'n/a'; };
  const sum = a => a.reduce((x, y) => x + y, 0);
  console.log(`flags [${process.argv.slice(2).join(' ')}]: rAF/s ${raf.toFixed(1)}, BMFs ${main.length}, BMF median ${med(durs)} ms, gap median ${med(gaps)} ms, gap share ${(100 * sum(gaps) / (sum(gaps) + sum(durs.slice(1)))).toFixed(1)}%`);
  await b.close();
})();
