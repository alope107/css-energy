const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } }); await p.goto('file://' + require('path').resolve(process.argv[2]), { timeout: 600000 }); await p.waitForTimeout(4000);
  await p.click('.runbtn');
  for (let i = 0; i < 14; i++) { await p.waitForTimeout(700);
    console.log(await p.evaluate(() => { const w = getComputedStyle(document.querySelector('#ccw')); const ls = document.querySelector('.ls'); const t1 = document.querySelector('.tpB'); const tcr = document.querySelector('#tcr');
      const g = n => (e => e ? getComputedStyle(e).getPropertyValue(n) : 'x');
      return ['go=' + w.getPropertyValue('--ccgo'), 'fz=' + w.getPropertyValue('--ccfz'), 'dt=' + w.getPropertyValue('--ccdt'), 'lc0=' + g('--lc0')(ls), 'ntf=' + g('--ntf')(tcr), 'has1=' + g('--has')(t1), 'kc0_0=' + g('--kc0_0')(t1), 'aps=' + (ls ? getComputedStyle(ls).animationPlayState.slice(0, 20) + ' lsfz=' + getComputedStyle(ls).getPropertyValue('--ccfz') + ' ccfz=' + getComputedStyle(document.querySelector('#cc')).getPropertyValue('--ccfz') : ''), 'anims=' + (ls ? ls.getAnimations().length + ':' + (ls.getAnimations()[0] ? ls.getAnimations()[0].playState + ':' + ls.getAnimations()[0].currentTime : '-') : '')].join(' '); })); }
  await b.close(); })();
