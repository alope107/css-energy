const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage(); await p.goto('file://' + require('path').resolve(process.argv[2])); await p.waitForTimeout(2500);
  console.log(JSON.stringify(await p.evaluate(() => [...document.querySelectorAll('.rv')].map(e => { const c = getComputedStyle(e); return [c.getPropertyValue('--n'), +c.getPropertyValue('--e'), +c.getPropertyValue('--d')]; }).filter(x => x[2]).slice(0, 25))));
  await b.close(); })();
