// runs.js page www-dir prog.js [n] — run a network program n times on one page (Run, HALT, Edit, Run ...), served with
// the gateway (harness only): per run, compiled -> HALT, the words, and the gaps between the gateway's requests (ms).
//   node net/probe/runs.js build/net-www/js_in_css.xhtml build/net-www tests/suite/net_long.js 3
// No requestAnimationFrame loop in the page (it would run it ~1.5x faster: ENGINE_NOTES 64). SERVER=path: another
// gateway (an older net/server.js, to compare); POLL=ms between status reads (100); RAF=1 adds the loop.
const fs = require('fs'), path = require('path');
const { launch } = require('../../tools/browser.js');
const { typeLines } = require('../../tools/page.js');
const { serve } = require(process.env.SERVER ? path.resolve(process.env.SERVER) : '../server.js');
(async () => {
  const [pg, www, prog, n = 3] = process.argv.slice(2);
  const ev = [];
  const srv = await serve(path.resolve(www), 0, {}, { log: (...a) => ev.push([Date.now(), ...a]) });
  const b = await launch();
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } });
  await p.goto(`http://127.0.0.1:${srv.address().port}/${path.relative(www, pg)}`);
  await p.waitForTimeout(3000);
  await typeLines(p, fs.readFileSync(prog, 'utf8').replace(/\n$/, '').split('\n'));
  await p.waitForTimeout(500);
  const st = () => p.evaluate(() => { const c = getComputedStyle(document.querySelector('#cpu')); return { halted: +c.getPropertyValue('--isHALT') === 1, status: getComputedStyle(document.querySelector('.cstv'), '::before').content }; });
  if (process.env.RAF) await p.evaluate(() => { const tick = () => requestAnimationFrame(tick); requestAnimationFrame(tick); });
  for (let r = 0; r < +n; r++) {
    if (r) { await p.click('.runbtn'); await p.waitForTimeout(300); }      // Edit
    const e0 = ev.length; await p.click('.runbtn'); const t = Date.now(); let tc = null, s;
    for (;;) { await p.waitForTimeout(+(process.env.POLL || 100)); s = await st(); if (tc === null && /compiled/.test(s.status)) tc = Date.now(); if (s.halted || Date.now() - t > 90000) break; }
    const reqs = ev.slice(e0).filter(e => e[1] === 'req').map(e => e[0]);
    console.log(`run ${r}: compile ${tc - t} ms, run ${Date.now() - tc} ms, words ${reqs.length}, first word at +${reqs[0] - tc} ms, gaps ${reqs.slice(1).map((x, i) => x - reqs[i]).join(' ')}`);
  }
  await b.close(); srv.close();
})().catch(e => { console.error(e); process.exit(1); });
