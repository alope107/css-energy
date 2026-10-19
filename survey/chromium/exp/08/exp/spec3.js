const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const port = process.argv[2], base = `http://localhost:${port}`;
  const ctx = await chromium.launchPersistentContext(__dirname + '/prof-' + Date.now(), { executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await ctx.newPage();
  const n = async pre => (await (await fetch(base + '/log')).json()).filter(x => x.startsWith('/d/' + pre)).length;
  const t0 = Date.now(); await p.goto(base + '/'); await p.waitForTimeout(3000);
  const r = { a: await n('a'), b: await n('b') };
  await p.click('#t'); await p.waitForTimeout(3000);
  r.after = { a: await n('a'), b: await n('b') };
  await p.click('#t'); await p.waitForTimeout(3000);
  r.back = { a: await n('a'), b: await n('b') };
  console.log(JSON.stringify(r)); await ctx.close();
})();
