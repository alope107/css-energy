// node probe3.js <port> <mode>  modes: obj-csp | iframe-sandbox | iframe-csp | obj-same | iframe-cross
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const port = +process.argv[2], mode = process.argv[3];
const exe = process.argv[4] || '/usr/local/bin/chromium';
const host = mode.endsWith('cross') ? 'localhost' : '127.0.0.1';
const el = {
  'obj-csp': `<object id="o" data="http://${host}:${port}/child3.svg?csp" type="image/svg+xml"></object>`,
  'obj-same': `<object id="o" data="http://${host}:${port}/child3.svg" type="image/svg+xml"></object>`,
  'iframe-sandbox': `<iframe id="o" sandbox src="http://${host}:${port}/child3.svg"></iframe>`,
  'iframe-csp': `<iframe id="o" src="http://${host}:${port}/child3.svg?csp"></iframe>`,
  'iframe-cross': `<iframe id="o" src="http://${host}:${port}/child3.svg"></iframe>`,
}[mode];
const parent = `<!doctype html><style>body{margin:0}
#o{display:block;border:0;frame-sizing:content-width;animation:h 1s steps(1) infinite}
@keyframes h{0%{height:100px}25%{height:200px}50%{height:300px}75%{height:50px}}</style>${el}`;
const srv = http.createServer((q, s) => {
  if (q.url.startsWith('/parent')) { s.writeHead(200, { 'content-type': 'text/html' }); return s.end(parent); }
  const f = path.join(__dirname, q.url.split('?')[0]); if (!fs.existsSync(f)) { s.writeHead(404); return s.end(); }
  const h = { 'content-type': 'image/svg+xml' };
  if (q.url.includes('?csp')) h['content-security-policy'] = 'sandbox';
  s.writeHead(200, h); s.end(fs.readFileSync(f));
}).listen(port, '127.0.0.1');
(async () => {
  const b = await chromium.launch({ executablePath: exe, args: ['--no-sandbox'] });
  const p = await b.newPage();
  await p.goto(`http://127.0.0.1:${port}/parent.html`);
  await p.waitForTimeout(1500);
  const cdp = await b.newBrowserCDPSession();
  const t = await cdp.send('Target.getTargets');
  const oopif = t.targetInfos.filter(x => x.type === 'iframe').map(x => x.url);
  const sup = await p.evaluate(() => CSS.supports('frame-sizing: content-width'));
  const rows = await p.evaluate(() => new Promise(r => {
    const out = []; const o = document.getElementById('o');
    (function f() { out.push([o.offsetHeight, o.getBoundingClientRect().width]); if (out.length < 80) requestAnimationFrame(f); else r(out); })();
  }));
  const tracks = rows.filter(([h, w]) => Math.abs(w - (0.5 * h + 7)) < 0.01).length;
  console.log(`${mode}: OOPIF targets: [${oopif.join(', ')}]; frame-sizing supported: ${sup}; frames where width == 0.5*height+7: ${tracks}/80; sample ${JSON.stringify(rows.slice(-3))}`);
  await b.close(); srv.close();
})();
