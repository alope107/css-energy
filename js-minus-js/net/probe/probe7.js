// probe7.js — would several modem children read in parallel? (harness only; exploratory)
//   node net/probe/probe7.js build/net-www/js_in_css.xhtml build/net-www        SECS=12 (per window)
// The real page runs a long read() loop through its own modem (the CPU drives it). The harness adds N more modem
// children (each a slot + iframe like the page's, with its own gateway session) and drives each through its own fetch +
// read loop, as the page's NET service would: height = 1 + K, then wait for the slot's scrollLeft to carry the word's
// sequence bit. Per window: the page's words per second, each extra child's, and their total. The harness polls every
// POLL ms (one evaluate for all children), which costs the page's main thread a little too.
const fs = require('fs'), path = require('path');
const { launch } = require('../../tools/browser.js');
const { typeLines } = require('../../tools/page.js');
const { serve } = require('../server.js');
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const [pg, www] = process.argv.slice(2), SECS = +(process.env.SECS || 12), POLL = +(process.env.POLL || 4);
  fs.writeFileSync(path.join(www, 'big.bin'), Buffer.from([...Array(20000).keys()].map(i => 33 + i % 90)));
  const sess = new Map();                      // gateway session id -> words acted on
  let cur = null;
  const srv = await serve(path.resolve(www), 0, {}, { log: k => { if (k === 'req' && cur !== null) sess.set(cur, (sess.get(cur) || 0) + 1); } });
  const emit = srv.emit.bind(srv);             // attribute each word to its session (the request that leads to act())
  srv.emit = (ev, req, ...r) => { const m = ev === 'request' && req.url.match(/\/net\/s\/(\d+)\/m[01]\.html/); cur = m ? +m[1] : cur; return emit(ev, req, ...r); };
  const b = await launch();
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } });
  await p.goto(`http://127.0.0.1:${srv.address().port}/${path.relative(www, pg)}`); await sleep(3000);
  await typeLines(p, ['fetch("big.bin");', 'var c = read(), n = 0;', 'while (c >= 0) { n++; c = read(); }', 'console.log(n);']);
  await sleep(500); await p.click('.runbtn');
  while ([...sess.values()].reduce((a, b) => a + b, 0) < 20) await sleep(200);
  const mainId = [...sess.keys()][0];
  const frames = await p.evaluateHandle(() => { const f = { n: 0 }; const tick = () => { f.n++; requestAnimationFrame(tick); }; requestAnimationFrame(tick); return f; });

  // N extra children, each with a word queue: the URL's bytes, GO, then READs for ever
  let kids = [], stop = false;
  async function drive(n) {
    stop = true; await sleep(50); stop = false;
    await p.evaluate(n => {
      document.querySelectorAll('.xslot').forEach(e => e.remove());
      for (let i = 0; i < n; i++) {
        const d = document.createElement('div'); d.className = 'xslot';
        d.style.cssText = 'position:fixed;left:0;top:0;width:100px;height:1px;overflow:hidden;visibility:hidden';
        const f = document.createElement('iframe'); f.src = '/net/m0.html#t'; f.style.cssText = `display:block;border:0;width:${(1 << 20) + 100}px;height:1px`;
        d.appendChild(f); document.querySelector('#cpu').appendChild(d);
      }
    }, n);
    kids = Array.from({ length: n }, () => ({ s: 0, q: [...Buffer.from('big.bin')].map(c => 256 + c).concat([512]), words: 0, t: 0 }));
    if (!n) return;
    (async () => {
      const send = async () => p.evaluate(ks => ks.forEach(([i, K]) => { document.querySelectorAll('.xslot iframe')[i].style.height = (1 + K) + 'px'; }),
        kids.map((k, i) => { k.s ^= 1; return [i, 1 + (((k.q.length ? k.q.shift() : 768) + 4096 * k.s) % 8192)]; }));
      await send();
      while (!stop) {
        await sleep(POLL);
        const sc = await p.evaluate(() => [...document.querySelectorAll('.xslot')].map(d => d.scrollLeft)).catch(() => null);
        if (!sc || stop) break;
        const ready = kids.map((k, i) => sc[i] % 2 === 1 && ((sc[i] >> 1) & 1) === k.s);
        const go = [];
        kids.forEach((k, i) => { if (ready[i]) { k.words++; k.s ^= 1; go.push([i, 1 + (((k.q.length ? k.q.shift() : 768) + 4096 * k.s) % 8192)]); } });
        if (go.length) await p.evaluate(ks => ks.forEach(([i, K]) => { document.querySelectorAll('.xslot iframe')[i].style.height = (1 + K) + 'px'; }), go).catch(() => {});
      }
    })();
  }
  const window_ = async label => {
    const w0 = new Map(sess), k0 = kids.map(k => k.words), t0 = Date.now(); await frames.evaluate(f => f.n = 0);
    await sleep(SECS * 1000);
    const t = (Date.now() - t0) / 1000, fr = await frames.evaluate(f => f.n);
    const main = ((sess.get(mainId) || 0) - (w0.get(mainId) || 0)) / t, ex = kids.map((k, i) => (k.words - k0[i]) / t);
    const halt = await p.evaluate(() => +getComputedStyle(document.querySelector('#cpu')).getPropertyValue('--halt'));
    console.log(JSON.stringify({ label, halt, pageWordsPerS: +main.toFixed(2), extraWordsPerS: ex.map(x => +x.toFixed(2)), totalWordsPerS: +(main + ex.reduce((a, b) => a + b, 0)).toFixed(2), framesPerS: +(fr / t).toFixed(1) }));
  };
  for (const n of (process.env.NS || '0,1,0,1,3,0').split(',').map(Number)) { await drive(n); await sleep(2000); await window_(`page + ${n} extra`); }
  stop = true; await sleep(100);
  await b.close(); srv.close();
})().catch(e => { console.error(e); process.exit(1); });
