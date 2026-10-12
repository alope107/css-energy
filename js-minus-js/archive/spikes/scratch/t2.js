const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage(); await p.goto('file://' + process.argv[2]);
  console.log(await p.evaluate(() => { const c = getComputedStyle(document.getElementById('c')); const bad = []; for (let i = 0; i < 1100; i++) if (c.getPropertyValue('--z' + i) !== '1') bad.push(i); return bad.length + ' fail: ' + bad.slice(0, 40).join(','); }));
  await b.close(); })();
