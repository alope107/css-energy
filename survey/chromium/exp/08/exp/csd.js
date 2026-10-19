const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const port = process.argv[2], base = `http://localhost:${port}`;
  const ctx = await chromium.launchPersistentContext(__dirname + '/prof-' + Date.now(), { executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await ctx.newPage();
  for (const path of ['/write', '/probe', '/reset', '/probe']) { await p.goto(base + path); await p.waitForTimeout(1200); }
  console.log(JSON.stringify(await (await fetch(base + '/log')).json())); await ctx.close();
})();
