const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu', ...(process.env.FLAGS ? process.env.FLAGS.split(' ') : [])] });
  const p = await b.newPage({ viewport: null }); await p.goto('file://' + require('path').resolve(process.argv[2])); await p.waitForTimeout(2500);
  console.log(await p.evaluate(() => devicePixelRatio + ' ' + [...document.querySelectorAll('.rv')].filter(e => getComputedStyle(e).getPropertyValue('--d') != '0').length + ' bad'));
  await b.close(); })();
