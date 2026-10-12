// prof.js page.html seconds — style vs layout time share via CDP Performance metrics
const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => {
  const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--no-proxy-server', '--disable-gpu'] });
  const p = await b.newPage(); const c = await p.context().newCDPSession(p);
  await c.send('Performance.enable');
  await p.goto('file://' + require('path').resolve(process.argv[2]));
  await p.waitForTimeout(3000);
  const m = async () => Object.fromEntries((await c.send('Performance.getMetrics')).metrics.map(x => [x.name, x.value]));
  const a = await m(); await p.waitForTimeout((+process.argv[3] || 20) * 1000); const z = await m();
  const d = k => +(z[k] - a[k]).toFixed(3);
  console.log(JSON.stringify({ wall: +(z.Timestamp - a.Timestamp).toFixed(2), style: d('RecalcStyleDuration'), layout: d('LayoutDuration'), script: d('ScriptDuration'), task: d('TaskDuration'), layouts: d('LayoutCount'), styles: d('RecalcStyleCount') }));
  await b.close();
})();
