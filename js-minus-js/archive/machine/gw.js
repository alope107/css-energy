const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu', ...(process.env.FLAGS ? process.env.FLAGS.split(' ') : [])] });
  const p = await b.newPage(); for (const f of process.argv.slice(2)) { await p.goto('file://' + require('path').resolve(f)); await p.waitForTimeout(1500);
  console.log(f.split('/').pop(), JSON.stringify(await p.evaluate(() => [...document.querySelectorAll('#s span')].map(e => [+e.dataset.v, +(e.getBoundingClientRect().width - e.dataset.v).toFixed(4)]).filter(x => x[1])))); }
  await b.close(); })();
