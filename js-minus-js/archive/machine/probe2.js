const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
const path = require('path');
(async () => {
  const [pg, expr] = process.argv.slice(2);
  const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--no-proxy-server', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  await p.goto('file://' + path.resolve(pg), { timeout: 600000 });
  await p.waitForTimeout(3000);
  console.log(JSON.stringify(await p.evaluate(expr), null, 0));
  await b.close();
})();
