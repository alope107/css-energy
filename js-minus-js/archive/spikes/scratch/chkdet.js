const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } }); await p.goto('file://' + require('path').resolve(process.argv[2]), { timeout: 600000 }); await p.waitForTimeout(4000);
  await p.click('.runbtn'); await p.waitForTimeout(12000);
  console.log(await p.evaluate(() => { const c = document.querySelector('.cr > .c1'); const app = getComputedStyle(document.querySelector('#app'));
    const ls = document.querySelector('.ls'); return [getComputedStyle(c).viewTimelineName, getComputedStyle(c).getPropertyValue('--rbdet'), app.getPropertyValue('--rbdet'), app.getPropertyValue('--rbsr'), app.getPropertyValue('--rbR'), ls && getComputedStyle(ls).animationPlayState.slice(0, 12), ls && getComputedStyle(ls).getPropertyValue('--lc0'), document.getAnimations().length, document.getAnimations().filter(a => a.playState === 'running').length].join(' | '); }));
  await b.close(); })();
