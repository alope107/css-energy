const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } });
  await p.addInitScript(() => { window.__log = []; const f = () => { const app = document.querySelector('#app'); const pr = document.querySelector('.probe'); const cell = pr && pr.querySelector('.row i');
      if (app && cell) { const s = +getComputedStyle(app).getPropertyValue('--rbscan'); if (s <= 3) __log.push([s, Math.round(pr.getBoundingClientRect().height), getComputedStyle(cell).getPropertyValue('--lv'), getComputedStyle(pr.querySelector('.row > b')).getPropertyValue('--rbgj'), getComputedStyle(pr.querySelector('.row > b')).getPropertyValue('--rbglive')].join(',')); }
      requestAnimationFrame(f); }; requestAnimationFrame(f); });
  await p.goto('file://' + require('path').resolve(process.argv[2]), { timeout: 600000 }); await p.waitForTimeout(6000);
  console.log((await p.evaluate(() => __log)).join(' | ')); await b.close(); })();
