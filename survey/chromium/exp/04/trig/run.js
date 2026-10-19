const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const [,, file, ...flags] = process.argv;
(async () => {
  const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', ...flags] });
  const p = await b.newPage();
  p.on('crash', () => console.log('PAGE CRASHED'));
  p.on('console', m => console.log('console:', m.text()));
  await p.goto('file://' + require('path').resolve(file));
  try { await p.waitForFunction(() => window.done, null, { timeout: 20000 }); } catch (e) { console.log('ERR', e.message.split('\n')[0]); }
  try { console.log((await p.evaluate(() => window.log)).join('\n')); } catch (e) { console.log('ERR', e.message.split('\n')[0]); }
  await b.close();
})();
