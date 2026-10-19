// oscillating feedback: does the renderer get stuck inside one frame? (closes its own browser)
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const port = +process.argv[2], file = process.argv[3];
const srv = http.createServer((q, s) => {
  if (q.url.startsWith('/parent')) { s.writeHead(200, { 'content-type': 'text/html' }); return s.end(`<!doctype html><object id="o" data="/${file}" type="image/svg+xml" style="display:block;height:20px"></object>`); }
  const f = path.join(__dirname, q.url.split('?')[0]); if (!fs.existsSync(f)) { s.writeHead(404); return s.end(); }
  s.writeHead(200, { 'content-type': 'image/svg+xml' }); s.end(fs.readFileSync(f));
}).listen(port, '127.0.0.1');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage(); const t0 = Date.now();
  const nav = p.goto(`http://127.0.0.1:${port}/parent.html`, { timeout: 10000 }).then(() => `load after ${Date.now() - t0} ms`).catch(e => 'goto: ' + e.message.split('\n')[0]);
  console.log(await nav);
  const r = await Promise.race([p.evaluate(() => new Promise(res => requestAnimationFrame(() => requestAnimationFrame(() => res('2 frames ran, width ' + document.getElementById('o').getBoundingClientRect().width))))),
    new Promise(res => setTimeout(() => res('no 2 frames within 8 s'), 8000))]);
  console.log(file, r, `at ${Date.now() - t0} ms`);
  await Promise.race([b.close(), new Promise(r => setTimeout(r, 3000))]); srv.close(); process.exit(0);
})();
