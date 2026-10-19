// renderer process count: objects from same-site, different-origin (other ports), with/without OAC / CSP sandbox
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const base = +process.argv[2], kind = process.argv[3];
const ports = [base + 1, base + 2, base + 3];
const objs = ports.map(p => `<object data="http://127.0.0.1:${p}/child3.svg?${kind}" type="image/svg+xml" style="height:100px"></object>`).join('');
const servers = [base, ...ports].map(port => http.createServer((q, s) => {
  if (q.url.startsWith('/parent')) { s.writeHead(200, { 'content-type': 'text/html' }); return s.end('<!doctype html>' + objs); }
  const f = path.join(__dirname, q.url.split('?')[0]); if (!fs.existsSync(f)) { s.writeHead(404); return s.end(); }
  const h = { 'content-type': 'image/svg+xml' };
  if (q.url.includes('?csp')) h['content-security-policy'] = 'sandbox';
  if (q.url.includes('?oac')) h['origin-agent-cluster'] = '?1';
  s.writeHead(200, h); s.end(fs.readFileSync(f));
}).listen(port, '127.0.0.1'));
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage();
  await p.goto(`http://127.0.0.1:${base}/parent.html`); await p.waitForTimeout(2000);
  const cdp = await b.newBrowserCDPSession();
  const info = await cdp.send('SystemInfo.getProcessInfo');
  const t = await cdp.send('Target.getTargets');
  console.log(`${kind} (3 other-port origins): renderer processes ${info.processInfo.filter(x => x.type === 'renderer').length}, OOPIF targets ${t.targetInfos.filter(x => x.type === 'iframe').length}`);
  await b.close(); servers.forEach(s => s.close());
})();
