// probe5.js — the fragment-scroll return channel (net/xhtml-tests/readback, 2026-10-16) as a modem answer path (harness only).
//   node net/probe/probe5.js
// A child document navigated to `#t` scrolls its ancestors so that #t is in view, including the page's overflow: hidden
// slot around the <object>; #t sits after a span whose width is the answer, so the slot's scrollLeft is the answer,
// read by a scroll-timeline. No responsive-iframes flag. Measured here: latency, cross-origin and data: children,
// <iframe> vs <object>, a same-URL self-refresh, the value range, the reload rate, #t through a form GET.
const fs = require('fs'), path = require('path');
const { launch } = require('../../tools/browser.js');
const { serve } = require('../server.js');
const D = path.join(__dirname, '..', '..', 'build', 'netprobe'); fs.mkdirSync(D, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  let v = 1234, apiHits = 0, loads = {};
  const route = (req, res, u) => { apiHits++; res.writeHead(200, { 'Content-Type': 'text/plain', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store' }); res.end(`.v{width:${v}px}`); };
  const count = (req, res, u) => { loads[u.pathname] = (loads[u.pathname] || 0) + 1; res.writeHead(200, { 'Content-Type': 'text/html', 'Cache-Control': 'no-store' }); res.end(fs.readFileSync(path.join(D, path.basename(u.pathname)))); };
  const page = await serve(D, 0, { '/api': route, '/c/': count }, { net: false }), P = page.address().port, base = `http://127.0.0.1:${P}/`;
  const api = await serve(D, 0, { '/api': route, '/c/': count }, { net: false }), A = api.address().port, xbase = `http://localhost:${A}/`;
  const child = (next, refresh = '2', apiAt = xbase) => `<html><head><meta charset="utf-8">${next ? `<meta http-equiv="refresh" content="${refresh}; url=${next}#t">` : `<meta http-equiv="refresh" content="${refresh}">`}
<style>html,body{margin:0;overflow:hidden} body{white-space:nowrap;height:1px;font-size:0} span{display:inline-block;height:1px} .base{width:100px} .v{width:0} #t{width:100px}</style>
<link rel="stylesheet" crossorigin="anonymous" href="${apiAt}api"></head><body><span class="base"></span><span class="v"></span><span id="t"></span></body></html>`;
  for (const [n, nx] of [['ca', 'cb'], ['cb', 'ca']]) fs.writeFileSync(`${D}/${n}.html`, child(`${nx}.html`));
  for (const [n, nx] of [['fa', 'fb'], ['fb', 'fa']]) fs.writeFileSync(`${D}/${n}.html`, child(`/c/${nx}.html`, '0'));   // as fast as it goes (counted: /c/)
  fs.writeFileSync(`${D}/self.html`, child(null, '0'));                                                          // same URL, reloads itself
  const parent = (inner, W = 3200) => `<!doctype html><style>
    @property --r{syntax:"<integer>";inherits:true;initial-value:0} @keyframes rd{from{--r:0}to{--r:${W - 100}}}
    body{margin:16px;timeline-scope:--s} .slot{width:100px;height:4px;overflow:hidden;scroll-timeline:--s x}
    .slot object,.slot iframe{display:block;width:${W}px;height:4px;border:0} .out{animation:rd 1s linear both;animation-timeline:--s}</style>
    <div class="slot">${inner}</div><p class="out"></p>`;
  const b = await launch();
  const pg = await b.newPage();
  const read = () => pg.evaluate(() => [document.querySelector('.slot').scrollLeft, +getComputedStyle(document.querySelector('.out')).getPropertyValue('--r')]);
  const open = async (label, inner, W) => { fs.writeFileSync(`${D}/par.html`, parent(inner, W)); const t = Date.now(); await pg.goto(base + 'par.html'); return t; };
  const until = async (pred, ms = 4000) => { const t = Date.now(); let r; while (!pred(r = await read()) && Date.now() - t < ms) await sleep(5); return [r, Date.now() - t]; };

  // latency from navigation start to the slot scrolled; the child's stylesheet is cross-origin (CORS), the child same-origin
  v = 1234; let t0 = await open('latency', `<object data="ca.html#t"></object>`);
  let [r, ms] = await until(r => r[0] > 0); console.log(`1. same-origin <object> child: scrollLeft ${r[0]} (want ${v + 100}), --r ${r[1]}, ${Date.now() - t0} ms after goto`);
  // a value change: the alternating children reload every 2 s
  v = 57; [r, ms] = await until(r => r[0] === 157, 6000); console.log(`   after v -> 57: scrollLeft ${r[0]} after ${ms} ms (2 s refresh)`);
  // cross-origin child documents
  v = 2000; await open('xo', `<object data="${xbase}c/ca.html#t"></object>`); [r, ms] = await until(r => r[0] > 0); console.log(`2. cross-origin <object> child: scrollLeft ${r[0]} (want ${v + 100}) after ${ms} ms`);
  await open('xi', `<iframe src="${xbase}c/ca.html#t"></iframe>`); [r, ms] = await until(r => r[0] > 0); console.log(`   cross-origin <iframe> child: scrollLeft ${r[0]} (want ${v + 100}) after ${ms} ms`);
  const du = `data:text/html,${encodeURIComponent(child(null, '999'))}#t`;
  await open('data', `<iframe src="${du}"></iframe>`); [r, ms] = await until(r => r[0] > 0); console.log(`3. data: <iframe> child with #t: scrollLeft ${r[0]} (want ${v + 100}) after ${ms} ms`);
  await open('iframe', `<iframe src="ca.html#t"></iframe>`); [r, ms] = await until(r => r[0] > 0); console.log(`4. same-origin <iframe> child: scrollLeft ${r[0]} after ${ms} ms`);
  // same URL, self-refresh at 0: does each reload re-scroll, and do value changes show?
  v = 300; await open('self', `<object data="self.html#t"></object>`); [r, ms] = await until(r => r[0] === 400); console.log(`5. self-refreshing child: first ${r[0]} after ${ms} ms`);
  v = 500; [r, ms] = await until(r => r[0] === 600, 3000); console.log(`   after v -> 500: ${r[0]} after ${ms} ms`);
  v = 200; [r, ms] = await until(r => r[0] === 300, 3000); console.log(`   after v -> 200 (smaller): ${r[0]} after ${ms} ms`);
  // range: a very wide object
  for (const [W, val] of [[1 << 20, 1000000], [1 << 24, 16000000], [1 << 25, 33000000]]) {
    v = val; await open('wide', `<object data="ca.html#t"></object>`, W); [r, ms] = await until(r => r[0] > 0); console.log(`6. object ${W} px wide, value ${val}: scrollLeft ${r[0]}, --r ${r[1]} (want ${val + 100}) after ${ms} ms`);
  }
  // rate: alternating children at refresh 0
  v = 10; loads = {}; await open('rate', `<object data="/c/fa.html#t"></object>`); await sleep(500); loads = {}; apiHits = 0; await sleep(2000);
  console.log(`7. alternating self-reload at 0 s: ${((loads['/c/fa.html'] || 0) + (loads['/c/fb.html'] || 0)) / 2} loads/s, ${apiHits / 2} API hits/s`);
  // ... and the value tracks through it, up and down; --r (the scroll timeline) a frame later
  for (const val of [500, 200, 7000]) { v = val; [r, ms] = await until(r => r[0] === val + 100, 3000); await sleep(50); console.log(`   v -> ${val}: scrollLeft ${r[0]} after ${ms} ms; --r now ${(await read())[1]}`); }
  // did the same-URL self-refresh (5) reload at all?
  v = 1; await open('self2', `<object data="self.html#t"></object>`); await sleep(500); apiHits = 0; await sleep(1000); console.log(`9. self.html (same URL, refresh 0): ${apiHits} API hits/s, scrollLeft ${(await read())[0]} (want ${v + 100})`);
  // the slot hidden and fixed, as the page's modem would be; --r precision on wide values after a frame
  fs.writeFileSync(`${D}/par.html`, parent(`<object data="/c/fa.html#t"></object>`, 1 << 25).replace('.slot{', '.slot{position:fixed;left:0;top:0;visibility:hidden;'));
  v = 33000000; await pg.goto(base + 'par.html'); [r, ms] = await until(r => r[0] > 0); await sleep(100); r = await read();
  console.log(`10. hidden fixed slot, 2^25 wide, value ${v}: scrollLeft ${r[0]}, --r ${r[1]} (want ${v + 100}; registered integers are floats, 2^24 precision)`);
  v = 16000000; await sleep(300); r = await read(); console.log(`    value 16000000: scrollLeft ${r[0]}, --r ${r[1]} (want 16000100)`);
  // the two-click path: a form GET into the object's frame, action with #t
  fs.writeFileSync(`${D}/par.html`, parent(`<iframe name="ch"></iframe>`) + `<form method=get action="ca.html#t" target=ch><button id=go>go</button></form>`);
  v = 2222; await pg.goto(base + 'par.html'); await sleep(200); await pg.click('#go'); [r, ms] = await until(r => r[0] > 0);
  console.log(`8. form GET to ca.html#t into the slot's iframe: scrollLeft ${r[0]} (want ${v + 100}) after ${ms} ms; frame URL ends with #t: ${pg.frames()[1].url().endsWith('#t')}`);
  await b.close(); page.close(); api.close();
})().catch(e => { console.error(e); process.exit(1); });
// Results (2026-10-20, Chromium 153.0.8010.12, no flags; the page served over http):
// 1. A same-origin child navigated to #t scrolls the page's slot to 100 + value: 44 ms after the page's goto, 2 ms after
//    the child loads; through <object> and <iframe> alike; the slot may be position: fixed and visibility: hidden.
// 2. Not across origins: a child from another origin, or a data: child, scrolls nothing (so not the two-click stage-2
//    document). The child's own stylesheet may be cross-origin (CORS + quirks, as in net/xhtml-tests).
// 3. Range: a 2^25 px wide object scrolls to 33,000,100 exactly; the scroll timeline's --r is off by 2-4 px above 2^24
//    (floats): keep answers below 2^20, which read exactly.
// 4. Reloads: <meta refresh content="0"> to the same URL#t does not reload at all (0 loads); alternating two URLs reloads
//    118 times a second, and a new value (larger or smaller) is in the slot 15 ms after the API starts serving it.
// 5. The fragment survives a form GET (action="x.html#t"): a same-origin child reached that way scrolls the slot too.
