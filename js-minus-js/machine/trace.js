// trace.js page.html secs — Chrome trace, aggregate self time of top events (harness only). Writes trace.json in the cwd.
// The window must sit inside the run: WAIT (default 3000 ms after load) and, with RUN=1, RUNWAIT (default 8000 ms after Run).
// RUN=1 clicks Run (.runbtn) after load, so on the typed-input page the trace covers compile and CPU frames, not the idle scan.
const { launch, open } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const fs = require('fs');
const { selfTime } = require(require('path').join(__dirname, '..', '..', 'shared', 'js', 'trace.js'));
(async () => {
  const [pg, secs = '6'] = process.argv.slice(2);
  const b = await launch();
  const p = await open(b, pg, { viewport: { width: 1200, height: 800 } });
  await p.waitForTimeout(+(process.env.WAIT || 3000));   // WAIT ms after load before Run / tracing (a CPU-only page starts at load)
  if (process.env.RUN) { await p.click('.runbtn'); await p.waitForTimeout(+(process.env.RUNWAIT || 8000)); }   // past the readback sweep + compile
  await b.startTracing(p, { path: 'trace.json', categories: ['blink', 'devtools.timeline', 'disabled-by-default-devtools.timeline', 'blink.animations', 'fonts', 'benchmark', 'cc', 'blink_style'] });
  await p.waitForTimeout(+secs * 1000);
  await b.stopTracing();
  await b.close();
  // self time on the main thread (shared/js/trace.js): total ms, self ms, count
  const rows = selfTime(JSON.parse(fs.readFileSync('trace.json')).traceEvents).map(([n, t, s, c]) => [n, t.toFixed(0), s.toFixed(0), c]).sort((a, b) => b[2] - a[2]).slice(0, 30);
  for (const r of rows) console.log(r.join('\t'));
})();
