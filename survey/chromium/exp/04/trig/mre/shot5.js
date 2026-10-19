const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
(async () => {
  for (const flags of [[], ['--disable-blink-features=CompositorTimelineTrigger']]) {
    const b = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox', ...flags] });
    const p = await b.newPage();
    await p.goto('file://' + __dirname + '/chrome-timeline-trigger-idle-page.html');
    const at = async () => p.evaluate(() => ["o2"].map(id => id + '=' + getComputedStyle(document.getElementById(id)).backgroundColor).join(' '));
    console.log(JSON.stringify(flags), 't0', await at());
    await p.waitForTimeout(800);
    console.log(JSON.stringify(flags), 't0.8s', await at());
    await b.close();
  }
})();
