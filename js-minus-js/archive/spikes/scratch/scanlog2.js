const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } });
  await p.addInitScript(() => { window.__log = []; const f = (ts) => { const app = document.querySelector('#app'); if (app) { const c = getComputedStyle(app); __log.push([Math.round(ts), c.getPropertyValue('--rbclk'), c.getPropertyValue('--rbtp'), c.getPropertyValue('--rbsc'), c.getPropertyValue('--rbscan'), c.getPropertyValue('--rbsr')].join(',')); } requestAnimationFrame(f); }; requestAnimationFrame(f); });
  await p.goto('file://' + require('path').resolve(process.argv[2])); await p.waitForTimeout(1500);
  console.log((await p.evaluate(() => __log.slice(-30))).join(' | ')); await b.close(); })();
