const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage(); await p.goto('file://' + require('path').resolve(process.argv[2])); await p.waitForTimeout(300);
  const r = await p.evaluate(() => new Promise(res => { const out = []; document.getElementById('go').checked = true; let n = 0;
    const f = () => { out.push([getComputedStyle(a).getPropertyValue('--w'), getComputedStyle(b).getPropertyValue('--w')].join(',')); if (++n < 5) requestAnimationFrame(f); else res(out); };
    out.push('sync:' + [getComputedStyle(a).getPropertyValue('--w'), getComputedStyle(b).getPropertyValue('--w')].join(',')); requestAnimationFrame(f); }));
  console.log(r.join(' | ')); await b.close(); })();
