const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  for (const flags of [[], ['--enable-blink-features=EventTrigger']]) {
    const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', ...flags] });
    const p = await b.newPage();
    await p.goto('file://' + __dirname + '/ev.html');
    await p.evaluate(() => setup());
    for (let i = 1; i <= 3; i++) {
      await p.click('#b');
      await p.evaluate(i => snap('after click ' + i + ' (same task)'), i);
      await p.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
      await p.evaluate(i => snap('after click ' + i + ' +2 frames'), i);
      await p.waitForTimeout(150);
      await p.evaluate(i => snap('after click ' + i + ' +150ms'), i);
    }
    console.log(JSON.stringify(flags)); console.log((await p.evaluate(() => log)).join('\n'));
    await b.close();
  }
})();
