// haltdump.js page.html outIndex — run to HALT (GC each 10s), then dump console/memory internals
const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
const path = require('path');
(async () => {
  const [pg, oi] = process.argv.slice(2);
  const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--no-proxy-server', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  const cdp = await p.context().newCDPSession(p); await cdp.send('HeapProfiler.enable');
  await p.goto('file://' + path.resolve(pg), { timeout: 600000 });
  for (;;) { await p.waitForTimeout(10000); await cdp.send('HeapProfiler.collectGarbage');
    const k = await p.evaluate(() => +getComputedStyle(document.querySelector('#cpu')).getPropertyValue('--kind'));
    if (k === 97) break; }
  const r = await p.evaluate(oi => { oi = +oi; const cs = getComputedStyle(document.querySelector('#cpu'));
    const ws = [...document.querySelectorAll('.mem .w')].slice(oi, oi + 12).map(e => e.getBoundingClientRect().width);
    const cells = [...document.querySelectorAll('.mem .cell')].slice(oi, oi + 12).map(e => [e.getBoundingClientRect().width, getComputedStyle(e).contentVisibility]);
    const ocs = [...document.querySelectorAll('.oc')].slice(0, 12).map(e => [e.getBoundingClientRect().width, getComputedStyle(e.firstElementChild).getPropertyValue('--code'), getComputedStyle(e).position]);
    return { optr: cs.getPropertyValue('--optr'), wa: ['A','B','C','D'].map(c => cs.getPropertyValue('--wa' + c) + '/' + cs.getPropertyValue('--wd' + c)), ws, cells, ocs }; }, oi);
  console.log(JSON.stringify(r));
  await b.close();
})();
