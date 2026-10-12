const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage();
  await p.addInitScript(() => { window.__log = [];
    const f = () => { const rv = [...document.querySelectorAll('.rv')].find(e => (e.getAttribute('style') || '').includes('--next-T1:'));
      if (rv) { const c = getComputedStyle(rv); const o = getComputedStyle(rv.parentElement.parentElement); const cpu = getComputedStyle(document.querySelector('.vp3'));
        const r = [cpu.getPropertyValue('--kind'), cpu.getPropertyValue('--T1'), c.getPropertyValue('--next-T1'), o.getPropertyValue('--rblo'), rv.parentElement.getBoundingClientRect().width, rv.parentElement.parentElement.parentElement.getBoundingClientRect().width].join(' ');
        if (__log[__log.length - 1] !== r) __log.push(r); }
      requestAnimationFrame(f); }; requestAnimationFrame(f); });
  await p.goto('file://' + require('path').resolve(process.argv[2])); await p.waitForTimeout(+(process.argv[3] || 6000));
  console.log('kind T1 next-T1 rblo hiW loW'); console.log((await p.evaluate(() => window.__log)).join('\n')); await b.close(); })();
