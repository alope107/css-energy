const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage(); const cdp = await p.context().newCDPSession(p); await cdp.send('Performance.enable');
  const t0 = Date.now(); await p.goto('file://' + require('path').resolve(process.argv[2]), { timeout: 600000 }); const t1 = Date.now();
  const r = await p.evaluate(() => {
    const out = { code: {}, data: {}, err: (() => { const c = getComputedStyle(document.querySelector('.ccerr')); return 'err=' + c.getPropertyValue('--e') + ' cp=' + c.getPropertyValue('--n'); })() };
    for (const e of document.querySelectorAll('.ov, .ovd, .ovs, .ovn')) { const cs = getComputedStyle(e); const an = cs.anchorName;
      if (an && an !== 'none' && an !== '--none') { const w = Math.round(e.getBoundingClientRect().width) - 1048576; ((e.classList.contains('ovd') || e.classList.contains('ovs') || e.classList.contains('ovn')) ? out.data : out.code)[an] = w; } }
    return out; });
  const m = Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(x => [x.name, x.value]));
  console.log(JSON.stringify({ loadMs: t1 - t0, recalcMs: Math.round(m.RecalcStyleDuration * 1000), layoutMs: Math.round(m.LayoutDuration * 1000), ...r }));
  await b.close(); })();
