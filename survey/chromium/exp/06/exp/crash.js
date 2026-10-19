const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  for (const f of process.argv.slice(2)) {
    const p = await b.newPage(); let crashed = false; p.on('crash', () => { crashed = true; });
    await p.goto('file://' + path.resolve(f)).catch(e => console.log('goto err', e.message.split('\n')[0]));
    const n = await Promise.race([p.evaluate(() => new Promise(res => { let n = 0; const ro = new ResizeObserver(() => { n++; }); document.querySelectorAll('.rd').forEach(e => ro.observe(e)); setTimeout(() => res(n), 3000); })).catch(e => 'ERR ' + e.message.split('\n')[0]), new Promise(r => setTimeout(() => r('timeout'), 8000))]);
    console.log(path.basename(f), 'RO deliveries in 3 s:', n, 'crashed:', crashed);
    await p.close().catch(() => {});
  }
  await b.close();
})();
