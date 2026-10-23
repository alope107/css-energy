// probe2.js — a self-reloading quirks child as a modem (harness only; exploratory).
//   node net/probe/probe2.js     (adds --enable-blink-features=ResponsiveIframes)
// The parent sets the iframe's width; the child reads it (100vw), fires one CSS-chosen request per bit, loads the
// server's answer as a JSON-typed "stylesheet", reports it as its content height, and reloads itself.
const fs = require('fs'), path = require('path');
const B = require('../../tools/browser.js');
const { serve } = require('../server.js');
const ROOT = path.join(__dirname, '..', '..', 'build', 'netprobe');
fs.mkdirSync(ROOT, { recursive: true });
const NB = 8, M = 1024;
const bits = [...Array(NB).keys()].map(k => `#b${k}{background-image:if(style(--b${k}: 1): url(/s/${k}/1); else: url(/s/${k}/0))}`).join('\n');
fs.writeFileSync(path.join(ROOT, 'modem.html'), `<html><head>
<meta name="responsive-embedded-sizing" content="*">
<meta name="responsive-embedded-sizing" content="allow-origins=*">
<meta http-equiv="refresh" content="${process.env.REFRESH || 0}">
<link rel="stylesheet" href="/rx">
<style>
html,body{margin:0}
@property --w{syntax:"<integer>";inherits:true;initial-value:0}
:root{--w:calc(100vw / 1px)}
${[...Array(NB).keys()].map(k => `@property --b${k}{syntax:"<integer>";inherits:false;initial-value:0}`).join('\n')}
${[...Array(NB).keys()].map(k => `#b${k}{--b${k}:mod(round(down, calc(var(--w) / ${2 ** k})), 2)}`).join('\n')}
${bits}
i{position:absolute;width:1px;height:1px}
#v{height:calc(100vh + mod(var(--rx, 0) * 1px - 100vh, ${M}px))}
</style></head><body>${[...Array(NB).keys()].map(k => `<i id="b${k}"></i>`).join('')}<div id="v"></div></body></html>`);
fs.writeFileSync(path.join(ROOT, 'p2.xhtml'), `<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/><style>
iframe{border:0;frame-sizing:content-height}
</style></head><body><iframe id="m" src="modem.html" style="width:5px"></iframe></body></html>`);

const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  // server: /s/<k>/<b> records bit k of the current request; /rx answers the request seen so far, as CSS typed JSON
  let cur = 0, loads = 0;
  const srv = await serve(ROOT, 0, {
    '/s/': (req, res, u) => { const [, , k, b] = u.pathname.split('/'); cur = b === '1' ? cur | 1 << +k : cur & ~(1 << +k); res.writeHead(204, { 'Cache-Control': 'no-store' }); res.end(); },
    '/rx': (req, res) => { loads++; res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); res.end(`:root{--rx:${cur * 3 + 100}}`); },
  });
  const base = `http://127.0.0.1:${srv.address().port}/`;
  const b = await B.launch({ extraArgs: ['--enable-blink-features=ResponsiveIframes'] });
  const p = await b.newPage();
  await p.goto(base + 'p2.xhtml');
  const t0 = Date.now();
  const h = () => p.evaluate(M => document.getElementById('m').getBoundingClientRect().height % M, M);
  for (const w of [5, 77, 200, 13, 255]) {
    await p.evaluate(w => document.getElementById('m').style.width = w + 'px', w);
    const ts = Date.now(), want = w * 3 + 100;
    let got; while ((got = await h()) !== want && Date.now() - ts < 5000) await sleep(5);
    console.log(`w=${w} → height ${got} (want ${want}) after ${Date.now() - ts} ms; child loads so far ${loads}; server cur ${cur}`);
  }
  const l0 = loads; await sleep(2000);
  console.log(`reload rate: ${(loads - l0) / 2} loads/s`);
  await b.close(); srv.close();
})().catch(e => { console.error(e); process.exit(1); });
