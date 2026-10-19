const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const port = +process.argv[2];
const parent = `<!doctype html><style>body{margin:0} #o{display:block;height:50px}</style><object id="o" data="http://localhost:${port}/child5.svg" type="image/svg+xml"></object>`;
const srv = http.createServer((q, s) => {
  if (q.url.startsWith('/parent')) { s.writeHead(200, { 'content-type': 'text/html' }); return s.end(parent); }
  const f = path.join(__dirname, q.url.split('?')[0]); if (!fs.existsSync(f)) { s.writeHead(404); return s.end(); }
  s.writeHead(200, { 'content-type': 'image/svg+xml' }); s.end(fs.readFileSync(f));
}).listen(port, '127.0.0.1');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage(); await p.goto(`http://127.0.0.1:${port}/parent.html`); await p.waitForTimeout(1000);
  const t = await (await b.newBrowserCDPSession()).send('Target.getTargets');
  const w = await p.evaluate(() => new Promise(r => { const out = []; const o = document.getElementById('o');
    (function f() { out.push(o.getBoundingClientRect().width); if (out.length < 150) requestAnimationFrame(f); else r([...new Set(out)]); })(); }));
  console.log('OOPIF:', t.targetInfos.filter(x => x.type === 'iframe').length, 'distinct widths seen by parent:', w.join(', '));
  await b.close(); srv.close();
})();
