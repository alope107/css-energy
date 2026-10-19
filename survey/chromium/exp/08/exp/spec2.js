const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const port = process.argv[2], base = `http://localhost:${port}`;
  const ctx = await chromium.launchPersistentContext(__dirname + '/prof-' + Date.now(), { executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await ctx.newPage();
  const getlog = async () => (await (await fetch(base + '/log')).json());
  const names = L => L.log.filter(e => e.p.startsWith('/d/')).map(e => e.p);
  await p.goto(base + '/'); await p.waitForTimeout(2000);
  const r = { load: names(await getlog()) };
  for (let i = 0; i < 2; i++) { await p.click('#t'); await p.waitForTimeout(1200); await p.click('#t'); await p.waitForTimeout(1200); }
  r.toggled = names(await getlog());
  for (const id of ['m3', 'm4', 'm5', 'm3', 'm4']) { await p.hover('#' + id); await p.waitForTimeout(700); await p.mouse.move(5, 600); await p.waitForTimeout(200); }
  r.hovered = names(await getlog());
  console.log(JSON.stringify(r)); await ctx.close();
})();
