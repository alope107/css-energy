// pagenet.js page www-dir prog.js — time a network program on the real page (harness only): words, modem loads, frames.
//   node net/probe/pagenet.js build/net-www/js_in_css.xhtml build/net-www tests/suite/net_fetch.js
// Run → compiled → HALT; per word: the gaps between the gateway's requests (the time a word costs end to end).
// TRACE=secs: main-thread self time per event over a window starting 1.5 s after compiling (../shared/js/trace.js).
// FRAMES=1: count the page's frames with a requestAnimationFrame loop. It runs the page faster than a user sees it (the
// loop makes Chrome update the page more often: net_long 1.5x; ENGINE_NOTES 64), so time without it.
const fs = require('fs'), path = require('path');
const { launch } = require('../../tools/browser.js');
const { typeLines, consoleCodes, gridText } = require('../../tools/page.js');
const { serve } = require('../server.js');
(async () => {
  const [pg, www, prog] = process.argv.slice(2);
  let loads = 0, words = 0;
  const reqT = [];
  const seq = []; const log = (k, ...a) => { if (k === 'req') { words++; reqT.push(Date.now()); seq.push(a.join(':')); } };
  const srv = await serve(path.resolve(www), 0, {}, { log });
  const origEmit = srv.emit.bind(srv);
  srv.emit = (ev, req, ...r) => { if (ev === 'request' && /\/net\/s\/\d+\/m[01]\.html/.test(req.url)) loads++; return origEmit(ev, req, ...r); };
  const b = await launch();
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } });
  await p.goto(`http://127.0.0.1:${srv.address().port}/${path.relative(www, pg)}`);
  await p.waitForTimeout(3000);
  const st = () => p.evaluate(() => { const c = getComputedStyle(document.querySelector('#cpu')); return { steps: +c.getPropertyValue('--steps'),
    halted: +c.getPropertyValue('--isHALT') === 1, status: getComputedStyle(document.querySelector('.cstv'), '::before').content }; });
  await typeLines(p, fs.readFileSync(prog, 'utf8').replace(/\n$/, '').split('\n'));
  await p.waitForTimeout(500);
  await p.click('.runbtn');
  const t0 = Date.now(); let tc = null, l0 = 0, w0 = 0, r;
  const frames = await p.evaluateHandle(F => { const f = { n: 0 }; const tick = () => { f.n++; requestAnimationFrame(tick); }; if (F) requestAnimationFrame(tick); return f; }, !!process.env.FRAMES);
  while (Date.now() - t0 < 300000) {
    await p.waitForTimeout(100); r = await st();
    if (tc === null && /compiled/.test(r.status)) {
      tc = Date.now(); l0 = loads; w0 = words; await frames.evaluate(f => f.n = 0);
      if (process.env.TRACE) {
        const { selfTime } = require('../../../shared/js/trace.js'), tf = path.join(www, 'trace.json');
        await p.waitForTimeout(1500);
        await b.startTracing(p, { path: tf, categories: ['blink', 'devtools.timeline', 'disabled-by-default-devtools.timeline', 'cc', 'blink_style', 'navigation', 'loading'] });
        await p.waitForTimeout(+process.env.TRACE * 1000); await b.stopTracing();
        for (const [n, t, s, c] of selfTime(JSON.parse(fs.readFileSync(tf)).traceEvents).sort((a, b) => b[2] - a[2]).slice(0, 18)) console.log(n, t.toFixed(0), s.toFixed(0), c);
      }
    }
    if (r.halted || /error/.test(r.status)) break;
  }
  const t = (Date.now() - (tc || t0)) / 1000, fr = await frames.evaluate(f => f.n);
  const gaps = reqT.slice(1).map((x, i) => x - reqT[i]).sort((a, b) => a - b), q = f => gaps[Math.floor(f * (gaps.length - 1))];
  console.log(JSON.stringify({ prog: path.basename(prog), runS: +t.toFixed(2), words: words - w0, msPerWord: Math.round(1000 * t / Math.max(1, words - w0)),
    gapMs: { min: gaps[0], p25: q(0.25), median: q(0.5), p75: q(0.75), max: gaps[gaps.length - 1] },
    modemLoadsPerS: +((loads - l0) / t).toFixed(1), ...(process.env.FRAMES ? { framesPerS: +(fr / t).toFixed(1) } : {}), steps: r.steps }));
  if (process.env.SEQ) console.log(reqT.map((x, i) => `${seq[i]}@${i ? x - reqT[i - 1] : 0}`).join(' '));
  if (!process.env.QUIET) console.log(gridText(await consoleCodes(p)));
  await b.close(); srv.close();
})().catch(e => { console.error(e); process.exit(1); });
