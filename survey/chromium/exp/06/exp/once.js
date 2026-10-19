const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  for (const f of process.argv.slice(2)) {
    const p = await b.newPage(); p.on('crash', () => console.log('CRASH', f));
    try {
      await p.goto('file://' + path.resolve(f)); await p.waitForTimeout(1500);
      const r = await p.evaluate(() => [...document.querySelectorAll('.st')].map(s => [...s.children].map(x => Math.round(x.getBoundingClientRect().width)).join(',')));
      console.log(path.basename(f), r);
    } catch (e) { console.log(path.basename(f), 'ERR', e.message.split('\n')[0]); }
    await p.close().catch(() => {});
  }
  await b.close();
})();
