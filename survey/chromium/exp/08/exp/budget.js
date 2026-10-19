const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const port = process.argv[2], k = +process.argv[3], n = +process.argv[4];
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage();
  const fails = {}; p.on('requestfailed', rq => { const e = rq.failure().errorText; fails[e] = (fails[e] || 0) + 1; });
  let started = 0; p.on('request', rq => { if (rq.url().includes('/img')) started++; });
  p.goto(`http://127.0.0.1:${port}/?k=${k}&n=${n}`).catch(() => {});
  await p.waitForTimeout(8000);
  console.log(JSON.stringify({ k, n, started, fails }));
  await b.close();
})();
