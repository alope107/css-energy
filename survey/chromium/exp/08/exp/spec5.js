const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  const port = process.argv[2], base = `http://localhost:${port}`;
  const ctx = await chromium.launchPersistentContext(__dirname + '/prof-' + Date.now(), { executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const p = await ctx.newPage(); p.on('crash', () => console.log('CRASH at', cur)); let cur; const modes = ['anim_hidden','anim_vis','toggle_hidden','toggle_opacity','anim_forwards'];
  for (const m of modes) { cur = m; await p.goto(`${base}/page?k=${m}&ms=1500&mode=${m}`); await p.waitForTimeout(400); await p.click('#t'); await p.waitForTimeout(2200); }
  await p.goto(base + '/probe'); await p.waitForTimeout(800);
  const log = await (await fetch(base + '/log')).json(); const h = await (await fetch(base + '/hash')).json();
  const inv = Object.fromEntries(Object.entries(h).map(([k, v]) => [v, k]));
  console.log(JSON.stringify(log.filter(e => /\/(d|r)\//.test(e.p)).map(e => e.p + ' ' + (inv[e.ad] || (e.ad ? '?' : '-')))));
  await ctx.close();
})();
