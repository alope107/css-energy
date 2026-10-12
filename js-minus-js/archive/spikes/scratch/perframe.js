const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage(); const cdp = await p.context().newCDPSession(p); await cdp.send('Performance.enable');
  const met = async () => Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(x => [x.name, x.value]));
  const t0 = Date.now(); await p.goto('file://' + require('path').resolve(process.argv[2]), { timeout: 600000 });
  let m0 = await met(); console.log('load', Date.now() - t0, 'recalc', Math.round(m0.RecalcStyleDuration * 1000), 'count', m0.RecalcStyleCount);
  for (let i = 0; i < 4; i++) { await p.waitForTimeout(1000); const m = await met();
    console.log('+1s recalc', Math.round((m.RecalcStyleDuration - m0.RecalcStyleDuration) * 1000), 'count', m.RecalcStyleCount - m0.RecalcStyleCount, 'layout', Math.round((m.LayoutDuration - m0.LayoutDuration) * 1000)); m0 = m; }
  await b.close(); })();
