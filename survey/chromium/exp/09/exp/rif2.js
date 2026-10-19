const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const http = require('http');
const pages = {
  '/c.html': `<!doctype html><html><head><meta name="responsive-embedded-sizing" content="*"></head><body style="margin:0"><div style="height:123px"></div></body></html>`,
  '/p.html': `<!doctype html><style>iframe{frame-sizing:content-height;width:200px;border:0;display:block}</style><iframe id=a src="/c.html"></iframe>`,
};
(async () => {
  const srv = http.createServer((q, r) => { const b = pages[q.url]; r.writeHead(b ? 200 : 404, { 'content-type': 'text/html' }); r.end(b || ''); });
  await new Promise(r => srv.listen(8791, '127.0.0.1', r));
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', ...(process.env.FL||'--enable-blink-features=ResponsiveIframes').split(' ')] });
  const p = await b.newPage(); await p.goto('http://127.0.0.1:8791/p.html'); await p.waitForTimeout(300);
  const fr = p.frames()[1];
  console.log('child requestResize:', await fr.evaluate(() => { try { window.requestResize(); return 'ok'; } catch (e) { return String(e); } }));
  await p.waitForTimeout(300);
  console.log('height', await p.evaluate(() => a.getBoundingClientRect().height));
  await b.close(); srv.close();
})();
