const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage(); await p.goto('file://' + process.argv[2]);
  console.log(await p.evaluate(() => { const c = getComputedStyle(document.getElementById('c')); return 'abcdefghij'.split('').map(n => n + ':' + c.getPropertyValue('--' + n) + '/' + c.getPropertyValue('--z' + n)).join(' '); }));
  await b.close(); })();
