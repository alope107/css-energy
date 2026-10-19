const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const port = process.argv[2], base = `http://localhost:${port}`, m = process.argv[3];
  const ctx = await chromium.launchPersistentContext(__dirname + '/prof-' + Date.now() + m, { executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await ctx.newPage(); let crashed = false; p.on('crash', () => crashed = true);
  try { await p.goto(`${base}/page?k=${m}&ms=1500&mode=${m}`); await p.waitForTimeout(400); await p.click('#t'); await p.waitForTimeout(2200); } catch (e) { }
  const log = await (await fetch(base + '/log')).json();
  console.log(m, 'crashed=' + crashed, JSON.stringify(log.filter(e => e.p.startsWith('/' + m + '/')).map(e => e.p)));
  await ctx.close();
})();
