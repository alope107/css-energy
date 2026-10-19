// node probe.js <port> <mode: cross|same>
const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const port = +process.argv[2] || 8931, mode = process.argv[3] || 'cross';
const srv = http.createServer((q, s) => {
  const f = path.join(__dirname, q.url.split('?')[0]);
  if (!fs.existsSync(f)) { s.writeHead(404); return s.end(); }
  let body = fs.readFileSync(f, 'utf8');
  const childHost = mode === 'cross' ? 'localhost' : '127.0.0.1';
  body = body.replace('CHILD', `http://${childHost}:${port}/child2.svg`);
  s.writeHead(200, { 'content-type': f.endsWith('.svg') ? 'image/svg+xml' : 'text/html' }); s.end(body);
}).listen(port, '127.0.0.1');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage();
  await p.goto(`http://127.0.0.1:${port}/parent2.html`);
  await p.waitForTimeout(1500);
  const cdp = await b.newBrowserCDPSession();
  const t = await cdp.send('Target.getTargets');
  console.log('targets:', t.targetInfos.map(x => x.type + ' ' + x.url).join(' | '));
  const rows = await p.evaluate(() => new Promise(r => {
    const out = []; const o = document.getElementById('o'), n = document.getElementById('n');
    (function f(ts) { out.push([Math.round(performance.now()), o.offsetHeight, o.getBoundingClientRect().width, o.getBoundingClientRect().height, getComputedStyle(n).getPropertyValue("--v")]);
      if (out.length < 150) requestAnimationFrame(f); else r(out); })();
  }));
  // print transitions
  let last = null, lastH = null, hFrame = 0;
  rows.forEach((x, i) => { if (x[1] !== lastH) { hFrame = i; lastH = x[1]; console.log(`frame ${i} t=${x[0]} height -> ${x[1]}, width ${x[2]}, cssnum ${x[3]}`); }
    const key = x[2] + '/' + x[3]; if (key !== last) { console.log(`frame ${i} t=${x[0]} width -> ${x[2]} (cssnum ${x[4]}) expected ${1000*(x[1]/14+0.123)}; frames since height change: ${i - hFrame}`); last = key; } });
  await b.close(); srv.close();
})();
