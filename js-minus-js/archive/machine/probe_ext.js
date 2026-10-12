const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage();
  await p.addInitScript(() => { window.__log = []; const names = (window.__names = ['--kind', '--isEXT', '--isMUL', '--isDIV', '--isMOD', '--T1', '--T2', '--a2', '--b1', '--bs', '--q', '--ext', '--resT', '--steps', '--go']);
    const f = () => { const e = document.querySelector('.vp3'); if (e) { const c = getComputedStyle(e); const r = names.map(n => c.getPropertyValue(n)).join(' '); if (__log[__log.length - 1] !== r) __log.push(r); } requestAnimationFrame(f); }; requestAnimationFrame(f); });
  await p.goto('file://' + require('path').resolve(process.argv[2])); await p.waitForTimeout(+(process.argv[3] || 6000));
  const r = await p.evaluate(() => [window.__names.join(' '), ...window.__log]);
  console.log(r.join('\n')); await b.close(); })();
