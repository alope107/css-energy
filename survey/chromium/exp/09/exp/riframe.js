const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const fs = require('fs'), path = require('path'), http = require('http');
const child = (h, anim) => `<!doctype html><meta name="responsive-embedded-sizing" content="*"><style>body{margin:0}#b{height:${h}px;${anim ? 'animation:g 1s linear forwards' : ''}}@keyframes g{to{height:400px}}</style><body><div id=b></div></body>`;
const pages = {
  '/c1.html': child(123, false), '/c2.html': child(50, true),
  '/c3.html': child(77, false).replace('allow-origins=*', "allow-origins='self'"),
  '/c4.html': child(99, false).replace('allow-origins=*', 'allow-origins=http://127.0.0.1:8790'),
  '/p.html': `<!doctype html><style>iframe{frame-sizing:content-height;width:200px;border:0;display:block}</style>
    <iframe id=a src="/c1.html"></iframe><iframe id=b src="/c2.html"></iframe><iframe id=c src="/c3.html"></iframe><iframe id=d src="/c4.html"></iframe>`,
};
(async () => {
  const srv = http.createServer((q, r) => { const b = pages[q.url]; r.writeHead(b ? 200 : 404, { 'content-type': 'text/html' }); r.end(b || ''); });
  await new Promise(r => srv.listen(8790, '127.0.0.1', r));
  for (const f of ['', 'ResponsiveIframes']) {
    const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', ...(f ? ['--enable-blink-features=' + f] : [])] });
    const p = await b.newPage(); await p.goto('http://127.0.0.1:8790/p.html');
    const h = () => p.evaluate(() => ['a', 'b', 'c', 'd'].map(i => document.getElementById(i).getBoundingClientRect().height));
    const t0 = await h(); await p.waitForTimeout(1500); const t1 = await h();
    console.log(f || 'no flag', 'at load', t0, 'after 1.5 s', t1, await p.evaluate(() => getComputedStyle(document.getElementById('a')).frameSizing));
    await b.close();
  }
  srv.close();
})();
