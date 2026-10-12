const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1000, height: 900 }, deviceScaleFactor: +(process.env.DPR || 1) }); await p.goto('file://' + require('path').resolve(process.argv[2]));
  await p.waitForTimeout(3000); await p.setViewportSize({ width: 1000, height: 3000 }); await p.waitForTimeout(500); await p.screenshot({ path: process.argv[3], clip: { x: 0, y: 0, width: 1000, height: 1300 } });
  console.log(await p.evaluate(() => { const r = [...document.querySelectorAll('.rv')]; return r.length + ' readers, bad ' + r.filter(e => getComputedStyle(e).getPropertyValue('--d') != '0').length; }));
  await b.close(); })();
