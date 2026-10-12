const { chromium } = require('/tmp/claude-0/-home-claude/e04c5771-1429-5249-9a5c-3c0abfaaefc8/scratchpad/chr/node_modules/playwright-core');
(async () => { const b = await chromium.launch({ executablePath: '/tmp/chromium', args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } }); await p.goto('file://' + require('path').resolve(process.argv[2]), { timeout: 600000 });
  const fps = await p.evaluate(() => new Promise(r => { let n = 0; const t = performance.now(); const f = () => { n++; if (performance.now() - t < 1000) requestAnimationFrame(f); else r(n); }; requestAnimationFrame(f); }));
  await p.waitForTimeout(+(process.argv[3] || 4000));
  console.log('fps', fps); console.log(await p.evaluate(() => [...document.querySelectorAll('.probe')].filter(e => e.getClientRects().length).map(pr => [...pr.querySelectorAll('.row i')].map(i => { const v = +getComputedStyle(i).getPropertyValue('--lv'); return v > 0 ? String.fromCharCode(v) : '.'; }).join('').replace(/\.+$/, '')).join('\n')));
  await b.close(); })();
