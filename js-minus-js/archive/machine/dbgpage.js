// dbgpage.js page.html secs — sample internals of fvm page (harness only)
const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
const path = require('path');
(async () => {
  const [pg, secs = '10'] = process.argv.slice(2);
  const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--no-proxy-server', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  p.on('console', m => console.error('console:', m.text()));
  await p.goto('file://' + path.resolve(pg), { timeout: 600000 });
  for (let i = 0; i < +secs; i++) {
    const r = await p.evaluate(() => {
      const cs = getComputedStyle(document.querySelector('#cpu'));
      const g = n => cs.getPropertyValue('--' + n).trim();
      const o = {}; for (const n of ['t','init','kind','go','k','PC','SP','FP','MAR','T1','T2','RES','steps','optr','A0','V0','A1']) o[n] = g(n);
      const vp = getComputedStyle(document.querySelector('.vp'));
      o.mval = vp.getPropertyValue('--mval'); o.nextPC = vp.getPropertyValue('--next-PC');
      const st = document.querySelector('#state'); o.stateW = st.getBoundingClientRect().width;
      o.spans = [...st.children].filter(e => e.style.anchorName).slice(0, 8).map(e => e.style.anchorName + '=' + e.getBoundingClientRect().width * 64);
      o.rb = [...document.querySelectorAll('.rb')].slice(0, 6).map(e => e.getBoundingClientRect().width * 64);
      o.font = document.fonts.check('16px FontCPU');
      return o;
    });
    console.log(JSON.stringify(r));
    await p.waitForTimeout(1000);
  }
  await p.screenshot({ path: 'fvm.png' });
  await b.close();
})();
