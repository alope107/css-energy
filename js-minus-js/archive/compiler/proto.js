const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage(); const cdp = await p.context().newCDPSession(p); await cdp.send('Performance.enable');
  const t0 = Date.now(); await p.goto('file:///root/cc/proto.xhtml'); const t1 = Date.now();
  const r = await p.evaluate(() => { const t = performance.now(); const cs = getComputedStyle(document.getElementById('out'));
     const v = [...Array(20).keys()].map(i => cs.getPropertyValue('--s' + i + (document.getElementById('out').parentElement.className.endsWith('A') ? 'A' : 'B'))); return [v, performance.now() - t]; });
  const m = Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(x => [x.name, x.value]));
  console.log(JSON.stringify(r), 'expected', require('fs').readFileSync('/root/cc/proto.json', 'utf8'), 'load ms', t1 - t0, 'recalcStyle ms', (m.RecalcStyleDuration * 1000).toFixed(0));
  await b.close(); })();
