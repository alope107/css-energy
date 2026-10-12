const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage(); await p.goto('file://' + require('path').resolve('tl2.html')); await p.waitForTimeout(300);
  const v = () => p.evaluate(() => getComputedStyle(a).getPropertyValue('--w'));
  console.log('start', await v());
  await p.evaluate(() => pz.checked = true); await p.waitForTimeout(200); console.log('paused', await v());
  await p.evaluate(() => mv.checked = true); await p.waitForTimeout(200); console.log('paused+moved', await v());
  await p.evaluate(() => det.checked = true); await p.waitForTimeout(200); console.log('paused+detached', await v());
  await b.close(); })();
