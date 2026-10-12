const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox'] });
  for (const f of process.argv.slice(2)) { const p = await b.newPage(); const cdp = await p.context().newCDPSession(p); await cdp.send('Performance.enable');
    await p.goto('file://' + require('path').resolve(f)); const m = Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(x => [x.name, x.value]));
    console.log(f, 'recalc', Math.round(m.RecalcStyleDuration * 1000)); await p.close(); }
  await b.close(); })();
