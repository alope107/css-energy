// probe3.js — the modem and the gateway (net/server.js) without the CPU: the harness plays the page's NET service
// (sets the iframe's width, waits for the answer with its sequence bit) and runs fetch + read word by word.
//   node net/probe/probe3.js [url]
const fs = require('fs'), path = require('path');
const B = require('../../tools/browser.js');
const { serve } = require('../server.js');
const ROOT = path.join(__dirname, '..', '..', 'build', 'netprobe');
fs.mkdirSync(ROOT, { recursive: true });
fs.copyFileSync(path.join(__dirname, '..', '..', 'tests', 'net', 'hello.txt'), path.join(ROOT, 'hello.txt'));
fs.writeFileSync(path.join(ROOT, 'p3.xhtml'), `<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/><style>
iframe { position: fixed; left: 0; top: 0; border: 0; visibility: hidden; frame-sizing: content-height; width: 1px; }
</style></head><body><iframe id="m" loading="lazy" src="/net/modem.html"></iframe></body></html>`);

const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const srv = await serve(ROOT, 0, {}, { oopif: process.env.OOPIF !== '0', log: process.env.NETLOG ? console.log : undefined }), base = `http://127.0.0.1:${srv.address().port}/`;
  const b = await B.launch({ extraArgs: ['--enable-blink-features=ResponsiveIframes'] });
  const p = await b.newPage();
  await p.goto(base + 'p3.xhtml');
  let s = 0;
  const net = async x => {
    const K = 2 * (1 + (x % 4096)) + s, t = Date.now();
    await p.evaluate(K => document.getElementById('m').style.width = (1 + K) + 'px', K);
    for (;;) {
      const h = await p.evaluate(() => document.getElementById('m').getBoundingClientRect().height);
      const r = h % 4096;
      if (r % 2 === 1 && ((r >> 1) & 1) === s) { s ^= 1; const d = r >> 2; return [d >= 512 ? d - 1024 : d, Date.now() - t, h]; }
      if (Date.now() - t > 8000) throw new Error(`timeout on ${x}: height ${h}`);
      await sleep(2);
    }
  };
  const url = process.argv[2] || 'hello.txt';
  const t0 = Date.now(), lat = [];
  for (const c of Buffer.from(url)) { const [, ms] = await net(256 + c); lat.push(ms); }
  const [st, ms, h] = await net(512); lat.push(ms);
  let out = '';
  for (;;) { const [c, ms2] = await net(768); lat.push(ms2); if (c < 0) break; out += String.fromCharCode(c); }
  if (process.env.CHECK) { const want = fs.readFileSync(path.join(ROOT, url)).toString('latin1'); console.log('body matches the file:', out === want, out.length, want.length); }
  console.log(`status ${st}, body ${JSON.stringify(out.slice(0, 40))}; ${lat.length} words in ${Date.now() - t0} ms; per word ms: first ${lat[0]}, median ${lat.slice(1).sort((a, b) => a - b)[lat.length >> 1]}, max ${Math.max(...lat.slice(1))}; height ${h}`);
  await b.close(); srv.close();
})().catch(e => { console.error(e); process.exit(1); });
