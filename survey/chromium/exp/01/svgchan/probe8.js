// count lifecycle-loop iterations in the frames of a same-process SVG <object> feedback loop
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const port = +process.argv[2], file = process.argv[3] || 'loop1000.svg', host = process.argv[4] || '127.0.0.1';
const parent = `<!doctype html><style>body{margin:0} #o{display:block;height:20px}</style><div id="go"></div>`;
const srv = http.createServer((q, s) => {
  if (q.url.startsWith('/parent')) { s.writeHead(200, { 'content-type': 'text/html' }); return s.end(parent); }
  const f = path.join(__dirname, q.url.split('?')[0]); if (!fs.existsSync(f)) { s.writeHead(404); return s.end(); }
  s.writeHead(200, { 'content-type': 'image/svg+xml' }); s.end(fs.readFileSync(f));
}).listen(port, '127.0.0.1');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage(); await p.goto(`http://127.0.0.1:${port}/parent.html`);
  const cdp = await p.context().newCDPSession(p); const ev = []; cdp.on('Tracing.dataCollected', d => ev.push(...d.value));
  await cdp.send('Tracing.start', { categories: 'blink,benchmark,cc,devtools.timeline', transferMode: 'ReportEvents' });
  // insert the object from the harness (the page itself has no script); wait for it to load and converge
  await p.evaluate(([h, port, file]) => { document.getElementById('go').innerHTML = `<object id="o" data="http://${h}:${port}/${file}" type="image/svg+xml"></object>`; }, [host, port, file]);
  await p.waitForTimeout(2500);
  const w = await p.evaluate(() => document.getElementById('o').getBoundingClientRect().width);
  const done = new Promise(r => cdp.once('Tracing.tracingComplete', r)); await cdp.send('Tracing.end'); await done;
  const bmf = ev.filter(e => e.name === 'ProxyMain::BeginMainFrame' && e.ph === 'X');
  const it = ev.filter(e => e.name === 'LocalFrameView::RunStyleAndLayoutLifecyclePhases' && e.ph === 'X');
  const ro = ev.filter(e => e.name === 'LocalFrameView::NotifyResizeObservers' && e.ph === 'X'); const pp = ev.filter(e => e.name === 'PrePaint' && e.ph === 'X').length; const io = ev.filter(e => e.name === 'IntersectionObserverController::computeIntersections' && e.ph === 'X').length; const ul = ev.filter(e => e.name === 'LocalFrameView::UpdateStyleAndLayout' && e.ph === 'X').length; console.log('PrePaint', pp, 'IO compute', io, 'UpdateStyleAndLayout', ul);
  const per = bmf.map(f => [it.filter(e => e.ts >= f.ts && e.ts < f.ts + f.dur && e.tid === f.tid).length, (f.dur / 1000).toFixed(1)]).filter(x => x[0] > 1);
  console.log(`${file} via ${host}: final width ${w}; frames with >1 loop iteration: ${JSON.stringify(per.slice(0, 6))}; NotifyResizeObservers events ${ro.length}`);
  await b.close(); srv.close();
})();
