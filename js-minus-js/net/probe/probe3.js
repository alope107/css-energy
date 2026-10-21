// probe3.js — the modem and the gateway (net/server.js) without the CPU: the harness plays the page's NET service (sets
// the iframe's height to the request, reads the slot's scrollLeft back) and runs fetch + read word by word.
//   node net/probe/probe3.js [url]        CHECK=1: compare the body with the file
const fs = require('fs'), path = require('path');
const B = require('../../tools/browser.js');
const { serve, SLOT } = require('../server.js');
const ROOT = path.join(__dirname, '..', '..', 'build', 'netprobe');
fs.mkdirSync(ROOT, { recursive: true });
fs.copyFileSync(path.join(__dirname, '..', '..', 'tests', 'net', 'hello.txt'), path.join(ROOT, 'hello.txt'));
const W = (1 << 20) + SLOT;
fs.writeFileSync(path.join(ROOT, 'p3.xhtml'), `<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/><style>
.slot { position: fixed; left: 0; top: 0; width: ${SLOT}px; height: 1px; overflow: hidden; visibility: hidden; }
iframe { display: block; border: 0; width: ${W}px; height: 1px; }
</style></head><body><div class="slot"><iframe id="m" loading="lazy" src="/net/m0.html#t"></iframe></div></body></html>`);

const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const srv = await serve(ROOT, 0, {}, { log: process.env.NETLOG ? console.log : undefined }), base = `http://127.0.0.1:${srv.address().port}/`;
  const b = await B.launch();
  const p = await b.newPage();
  await p.goto(base + 'p3.xhtml');
  let s = 0;
  const net = async x => {
    s ^= 1; const T = x + 4096 * s, K = 1 + (T % 8192), t = Date.now();
    await p.evaluate(K => document.getElementById('m').style.height = (1 + K) + 'px', K);
    for (;;) {
      const r = await p.evaluate(() => document.querySelector('.slot').scrollLeft);
      if (r % 2 === 1 && ((r >> 1) & 1) === s) { const d = r >> 2; return [d >= 1 << 17 ? d - (1 << 18) : d, Date.now() - t]; }
      if (Date.now() - t > 8000) throw new Error(`timeout on ${x}: scrollLeft ${r}`);
      await sleep(1);
    }
  };
  const url = process.argv[2] || 'hello.txt';
  const t0 = Date.now(), lat = [];
  for (const c of Buffer.from(url)) { const [, ms] = await net(256 + c); lat.push(ms); }
  const [st, ms] = await net(512); lat.push(ms);
  let out = '';
  for (;;) { const [c, ms2] = await net(768); lat.push(ms2); if (c < 0) break; out += String.fromCharCode(c); }
  if (process.env.CHECK) { const want = fs.readFileSync(path.join(ROOT, url)).toString('latin1'); console.log('body matches the file:', out === want, out.length, want.length); }
  const rest = lat.slice(1).sort((a, b) => a - b);
  console.log(`status ${st}, body ${JSON.stringify(out.slice(0, 40))}; ${lat.length} words in ${Date.now() - t0} ms; per word ms: first ${lat[0]}, median ${rest[rest.length >> 1]}, max ${rest[rest.length - 1]}`);
  await b.close(); srv.close();
})().catch(e => { console.error(e); process.exit(1); });
