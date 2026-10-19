// pagenet.js page www-dir prog.js — time a network program on the real page (harness only): words, modem loads, shapings.
//   node net/probe/pagenet.js build/net-www/js_in_css.xhtml build/net-www tests/suite/net_fetch.js
const fs = require('fs'), path = require('path');
const { launch } = require('../../tools/browser.js');
const { typeLines, consoleCodes, gridText } = require('../../tools/page.js');
const { serve } = require('../server.js');
(async () => {
  const [pg, www, prog] = process.argv.slice(2);
  let loads = 0, words = 0;
  const reqT = [];
  const log = (k) => { if (k === 'req') { words++; reqT.push(Date.now()); } };
  const srv = await serve(path.resolve(www), 0, {}, { log, oopif: process.env.OOPIF !== '0' });
  const origEmit = srv.emit.bind(srv);
  srv.emit = (ev, req, ...r) => { if (ev === 'request' && req.url.startsWith('/net/modem.html')) loads++; return origEmit(ev, req, ...r); };
  const b = await launch({ extraArgs: ['--enable-blink-features=ResponsiveIframes'] });
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } });
  await p.goto(`http://127.0.0.1:${srv.address().port}/${path.relative(www, pg)}`);
  await p.waitForTimeout(3000);
  const st = () => p.evaluate(() => { const c = getComputedStyle(document.querySelector('#cpu')); return { steps: +c.getPropertyValue('--steps'), nsh: +c.getPropertyValue('--nsh'),
    halted: +c.getPropertyValue('--isHALT') === 1, kind: +c.getPropertyValue('--kind'), status: getComputedStyle(document.querySelector('.cstv'), '::before').content }; });
  await typeLines(p, fs.readFileSync(prog, 'utf8').replace(/\n$/, '').split('\n'));
  await p.waitForTimeout(500);
  await p.click('.runbtn');
  const t0 = Date.now(); let tc = null, l0 = 0, w0 = 0, r;
  const frames = await p.evaluateHandle(() => { const f = { n: 0 }; const tick = () => { f.n++; requestAnimationFrame(tick); }; requestAnimationFrame(tick); return f; });
  while (Date.now() - t0 < 300000) {
    await p.waitForTimeout(250); r = await st();
    if (tc === null && /compiled/.test(r.status)) {
      tc = Date.now(); l0 = loads; w0 = words; await frames.evaluate(f => f.n = 0);
      if (process.env.TRACE) {      // TRACE=secs: a trace of the run's start, main-thread self time per event (../shared/js/trace.js)
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
  console.log(JSON.stringify({ prog: path.basename(prog), runS: +t.toFixed(1), words: words - w0, msPerWord: Math.round(1000 * t / Math.max(1, words - w0)),
    modemLoadsPerS: +((loads - l0) / t).toFixed(1), framesPerS: +(fr / t).toFixed(1), shapings: r.nsh, steps: r.steps }));
  const gaps = reqT.slice(1).map((t, i) => t - reqT[i]).sort((a, b) => a - b);
  console.log('ms between requests: min', gaps[0], 'p25', gaps[gaps.length >> 2], 'median', gaps[gaps.length >> 1], 'p75', gaps[(3 * gaps.length) >> 2], 'max', gaps[gaps.length - 1]);
  console.log(gridText(await consoleCodes(p)));
  await b.close(); srv.close();
})().catch(e => { console.error(e); process.exit(1); });
