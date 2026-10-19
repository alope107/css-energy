const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const port = process.argv[2], base = `http://localhost:${port}`;
  const ctx = await chromium.launchPersistentContext(__dirname + '/prof-' + Date.now(), { executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await ctx.newPage();
  const getlog = async () => (await (await fetch(base + '/log')).json());
  await p.goto(base + '/'); await p.waitForTimeout(2500);
  const s1 = (await getlog()).log.map(e => e.p + (e.purpose ? '[' + e.purpose + ']' : ''));
  await p.click('#t'); await p.waitForTimeout(2500);
  const s2 = (await getlog()).log.map(e => e.p + (e.purpose ? '[' + e.purpose + ']' : ''));
  await p.hover('#m'); await p.waitForTimeout(1500);
  const s3 = (await getlog()).log.map(e => e.p + (e.purpose ? '[' + e.purpose + ']' : ''));
  const p2 = await ctx.newPage(); await p2.goto(base + '/probe?n=1'); await p2.waitForTimeout(1000);
  const L = await getlog();
  const probe = L.log.filter(e => e.p.startsWith('/r/'));
  console.log(JSON.stringify({ s1, s2, s3, probe, hashes: L.hashes }, null, 1));
  await ctx.close();
})();
