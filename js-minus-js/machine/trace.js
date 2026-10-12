// trace.js page.html secs — Chrome trace, aggregate self time of top events (harness only). Writes trace.json in the cwd.
// RUN=1 clicks Run (.runbtn) after load, so on the typed-input page the trace covers compile and CPU frames, not the idle scan.
const { chromium } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const fs = require('fs');
(async () => {
  const [pg, secs = '6'] = process.argv.slice(2);
  const b = await chromium.launch({ args: ['--no-sandbox', '--no-proxy-server', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  await p.goto('file://' + require('path').resolve(pg));
  await p.waitForTimeout(3000);
  if (process.env.RUN) { await p.click('.runbtn'); await p.waitForTimeout(+(process.env.RUNWAIT || 8000)); }   // past the readback sweep + compile
  await b.startTracing(p, { path: 'trace.json', categories: ['blink', 'devtools.timeline', 'disabled-by-default-devtools.timeline', 'blink.animations', 'fonts', 'benchmark', 'cc', 'blink_style'] });
  await p.waitForTimeout(+secs * 1000);
  await b.stopTracing();
  await b.close();
  const ev = JSON.parse(fs.readFileSync('trace.json')).traceEvents.filter(e => e.ph === 'X' && e.dur);
  const main = {}; for (const e of ev) if (e.name === 'ThreadControllerImpl::RunTask' || e.name === 'Layout') main[e.tid] = (main[e.tid] || 0) + e.dur;
  const tid = +Object.entries(main).sort((a, b) => b[1] - a[1])[0][0];
  const es = ev.filter(e => e.tid === tid).sort((a, b) => a.ts - b.ts || b.dur - a.dur);
  // self time via stack
  const self = {}, tot = {}, cnt = {}; const st = [];
  for (const e of es) { while (st.length && st[st.length - 1].ts + st[st.length - 1].dur <= e.ts) st.pop();
    if (st.length) self[st[st.length - 1].name] -= e.dur; self[e.name] = (self[e.name] || 0) + e.dur; tot[e.name] = (tot[e.name] || 0) + e.dur; cnt[e.name] = (cnt[e.name] || 0) + 1; st.push(e); }
  const rows = Object.keys(tot).map(n => [n, (tot[n] / 1e3).toFixed(0), (self[n] / 1e3).toFixed(0), cnt[n]]).sort((a, b) => b[2] - a[2]).slice(0, 30);
  for (const r of rows) console.log(r.join('\t'));
})();
