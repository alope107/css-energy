// feedback loop: child natural width = its viewport width + 1 px. Same-process vs cross-process growth per frame.
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const port = +process.argv[2], mode = process.argv[3];
const host = mode === 'cross' ? 'localhost' : '127.0.0.1';
const parent = `<!doctype html><style>body{margin:0} #o{display:block;height:20px}</style><object id="o" data="http://${host}:${port}/loop.svg" type="image/svg+xml"></object>`;
const srv = http.createServer((q, s) => {
  if (q.url.startsWith('/parent')) { s.writeHead(200, { 'content-type': 'text/html' }); return s.end(parent); }
  const f = path.join(__dirname, q.url.split('?')[0]); if (!fs.existsSync(f)) { s.writeHead(404); return s.end(); }
  s.writeHead(200, { 'content-type': 'image/svg+xml' }); s.end(fs.readFileSync(f));
}).listen(port, '127.0.0.1');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage(); const t0 = Date.now();
  await p.goto(`http://127.0.0.1:${port}/parent.html`);
  const rows = await p.evaluate(() => new Promise(r => { const out = []; const o = document.getElementById('o');
    (function f() { setTimeout(() => { out.push([Math.round(performance.now()), o.getBoundingClientRect().width]); if (out.length < 40) requestAnimationFrame(f); else r(out); }, 0); })(); }));
  console.log(mode, 'goto+40 frames took', Date.now() - t0, 'ms; widths:', rows.filter((x, i) => i < 5 || i > 35).map(x => x.join('@')).join(' '));
  await b.close(); srv.close();
})();
