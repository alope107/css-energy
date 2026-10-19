const { chromium } = require('/workspaces/css-energy/css-physics/node_modules/playwright');
const path = require('path');
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 600, height: 500 } });
  await page.goto('file://' + path.join(__dirname, 't.html'));
  await page.waitForTimeout(300);
  const st = () => page.evaluate(() => {
    const o = getComputedStyle(document.getElementById('out'));
    const e = getComputedStyle(document.getElementById('ev'));
    return `t1=${o.getPropertyValue('--t1')} t2=${o.getPropertyValue('--t2')} | change:${e.fontSize} toggle:${e.letterSpacing} input:${e.wordSpacing} scrollend:${e.strokeWidth} transitionend:${e.strokeDashoffset} focus:${e.opacity} keydown:${e.fillOpacity} accessKey:${e.strokeOpacity} wallclock:${e.strokeMiterlimit}`;
  });
  console.log('init      ', await st());
  for (let i = 1; i <= 4; i++) {
    await page.mouse.click(25, 25); await page.mouse.click(125, 25);
    await page.waitForTimeout(50);
    console.log('click #' + i, await st());
  }
  await page.mouse.click(5, 158);            // checkbox
  await page.click('#det summary');          // details toggle
  await page.click('#inp'); await page.keyboard.type('a');
  await page.keyboard.press('q');
  await page.keyboard.press('Alt+q');
  await page.mouse.move(255, 155);           // hover -> transition
  await page.mouse.move(40, 330); await page.mouse.wheel(0, 200);
  await page.waitForTimeout(600);
  console.log('events    ', await st());
  await browser.close();
})();
