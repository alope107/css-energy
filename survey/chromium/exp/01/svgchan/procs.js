// node procs.js <port> <n> <kind: csp|plain|cross> : renderer process count with n child objects
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const http = require('http'), fs = require('fs'), path = require('path'), cp = require('child_process');
const port = +process.argv[2], n = +process.argv[3], kind = process.argv[4];
const hosts = ['127.0.0.2', '127.0.0.3', '127.0.0.4', '127.0.0.5'];
let objs = '';
for (let i = 0; i < n; i++) {
  const host = kind === 'cross' ? hosts[i % 4] : '127.0.0.1';
  objs += `<object data="http://${host}:${port}/child3.svg?${kind === 'csp' ? 'csp' : 'x'}&i=${i}" type="image/svg+xml" style="height:100px"></object>`;
}
const srv = http.createServer((q, s) => {
  if (q.url.startsWith('/parent')) { s.writeHead(200, { 'content-type': 'text/html' }); return s.end('<!doctype html>' + objs); }
  const f = path.join(__dirname, q.url.split('?')[0]); if (!fs.existsSync(f)) { s.writeHead(404); return s.end(); }
  const h = { 'content-type': 'image/svg+xml' }; if (q.url.includes('?csp')) h['content-security-policy'] = 'sandbox';
  s.writeHead(200, h); s.end(fs.readFileSync(f));
}).listen(port, '0.0.0.0');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage();
  await p.goto(`http://127.0.0.1:${port}/parent.html`); await p.waitForTimeout(2000);
  const cdp = await b.newBrowserCDPSession();
  const info = await cdp.send('SystemInfo.getProcessInfo');
  const t = await cdp.send('Target.getTargets');
  console.log(`${kind} n=${n}: renderer processes ${info.processInfo.filter(x => x.type === 'renderer').length}, OOPIF targets ${t.targetInfos.filter(x => x.type === 'iframe').length}`);
  await b.close(); srv.close();
})();
