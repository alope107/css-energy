// probe3.js — the modems and the gateway (net/server.js) without the CPU: the harness plays the page's NET service (sets
// the iframes' extra height to the request, waits for every part's answer to carry the word's sequence bit) and runs
// fetch + read. Modem i answers parts 2i and 2i + 1 on its slot's scrollLeft and scrollTop, as on the page.
//   node net/probe/probe3.js [url]        N=4 (parts), CHECK=1: compare the body with the file
const fs = require('fs'), path = require('path');
const B = require('../../tools/browser.js');
const { serve, SLOT, NW } = require('../server.js');
const ROOT = path.join(__dirname, '..', '..', 'build', 'netprobe'), N = +(process.env.N || 4), M = (N + 1) >> 1;
fs.mkdirSync(ROOT, { recursive: true });
for (const f of ['hello.txt', 'long.txt']) fs.copyFileSync(path.join(__dirname, '..', '..', 'tests', 'net', f), path.join(ROOT, f));
fs.writeFileSync(path.join(ROOT, 'p3.xhtml'), `<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/><style>
.slot { position: fixed; left: 0; top: 0; width: ${SLOT}px; height: ${SLOT}px; overflow: hidden; visibility: hidden; }
.clip { width: ${NW}px; height: ${NW}px; overflow: clip; }
iframe { display: block; border: 0; width: ${NW}px; height: ${NW}px; }
</style></head><body>${[...Array(M).keys()].map(i => `<div class="slot"><div class="clip"><iframe loading="lazy" src="/net/m0.html?g=x&amp;part=${i}&amp;n=${N}#t"></iframe></div></div>`).join('')}</body></html>`);

const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const srv = await serve(ROOT, 0, {}, { log: process.env.NETLOG ? console.log : undefined }), base = `http://127.0.0.1:${srv.address().port}/`;
  const b = await B.launch();
  const p = await b.newPage();
  await p.goto(base + 'p3.xhtml');
  let s = 0;
  const net = async pl => {                // a payload -> every part's answer
    s ^= 1; const K = 1 + 2 * pl + s, t = Date.now();
    await p.evaluate(([K, NW]) => document.querySelectorAll('iframe').forEach(f => f.style.height = (NW + K) + 'px'), [K, NW]);
    for (;;) {
      const r = (await p.evaluate(() => [...document.querySelectorAll('.slot')].flatMap(e => [e.scrollLeft, e.scrollTop]))).slice(0, N);
      if (r.every(x => x % 2 === 1 && ((x >> 1) & 1) === s)) return [r.map(x => x >> 2), Date.now() - t];
      if (Date.now() - t > 8000) throw new Error(`timeout on ${pl}: ${r}`);
      await sleep(1);
    }
  };
  const url = Buffer.from(process.argv[2] || 'hello.txt');
  const t0 = Date.now(), lat = [];
  for (let i = 0; i < url.length; i += 2) { const [, ms] = await net(4 * (url[i] + 256 * (url[i + 1] || 0))); lat.push(ms); }
  const [[st], ms] = await net(1); lat.push(ms);
  const out = [];
  for (;;) {
    const [a, ms2] = await net(2); lat.push(ms2);
    const got = a.flatMap(d => [d & 255, (d >> 8) & 255].slice(0, d >> 16));
    if (!got.length) break; out.push(...got);
  }
  const body = Buffer.from(out).toString('latin1');
  if (process.env.CHECK) { const want = fs.readFileSync(path.join(ROOT, url.toString())).toString('latin1'); console.log('body matches the file:', body === want, body.length, want.length); }
  const rest = lat.slice(1).sort((a, b) => a - b);
  console.log(`${N} parts (${M} modems): status ${st - 1}, body ${JSON.stringify(body.slice(0, 40))}; ${lat.length} words in ${Date.now() - t0} ms; per word ms: first ${lat[0]}, median ${rest[rest.length >> 1]}, max ${rest[rest.length - 1]}`);
  await b.close(); srv.close();
})().catch(e => { console.error(e); process.exit(1); });
