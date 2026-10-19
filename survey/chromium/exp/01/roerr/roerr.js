const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  for (const f of process.argv.slice(2)) {
    const p = await b.newPage(); const msgs = []; let errs = 0;
    p.on('console', m => msgs.push(m.type() + ': ' + m.text())); p.on('pageerror', e => { errs++; msgs.push('pageerror: ' + e.message); });
    await p.goto('file://' + path.resolve(f)); await p.waitForTimeout(1500);
    const n = await p.evaluate(() => { let e = 0; let m = ''; window.addEventListener('error', ev => { e++; m = ev.message; }); return new Promise(r => setTimeout(() => r(e + ' ' + m), 1000)); });
    console.log(f, 'window error events in 1 s:', n, '| console:', [...new Set(msgs)].slice(0, 3).join(' || '));
    await p.close();
  }
  await b.close();
})();
