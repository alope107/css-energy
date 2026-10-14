// rbtest.js page.xhtml prog.js [timeoutMs=30000] — type a program into #ed, set Run (the scan reads the editor only then),
// wait until the scan reports --rbready, and print what the latches read, line by line, then whether it matches the file
// (harness only). Unread cells print as '.', cells that read as nothing as '_'. rbsweep.js repeats this and counts misses.
const { launch, open } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const { typeLines } = require(require('path').join(__dirname, '..', 'tools', 'page.js'));
const fs = require('fs');
(async () => { const b = await launch({ args: ['--no-sandbox'] });
  const p = await open(b, process.argv[2], { viewport: { width: 1300, height: 900 } });
  await p.waitForTimeout(1500);
  const src = fs.readFileSync(process.argv[3], 'utf8').replace(/\n$/, '');
  await p.evaluate(() => { document.getElementById('run').checked = false; }); await p.waitForTimeout(200);
  await typeLines(p, src.split('\n'));
  console.log('editor html:', (await p.evaluate(() => document.querySelector('#ed').innerHTML)).slice(0, 200));
  await p.evaluate(() => { document.getElementById('run').checked = true; });
  const t = Date.now(); let ready = 0;
  while (Date.now() - t < +(process.argv[4] || 30000)) { await p.waitForTimeout(100); ready = await p.evaluate(() => +getComputedStyle(document.querySelector('#app')).getPropertyValue('--rbready')); if (ready === 1) break; }
  console.log(ready === 1 ? `scan done in ${Date.now() - t} ms` : `no --rbready after ${Date.now() - t} ms`);
  const got = await p.evaluate(() => [...document.querySelectorAll('.probe')].filter(e => e.getClientRects().length).map(pr => [...pr.querySelectorAll('.row i')].map(i => { const v = +getComputedStyle(i).getPropertyValue('--lv'); return v > 0 ? String.fromCharCode(v) : (v < 0 ? '_' : '.'); }).join('').replace(/[ .]+$/, '')));
  console.log(got.join('\n'));
  const want = src.split('\n').map(l => l.replace(/\s+$/, '')).join('\n');
  console.log('match', got.slice(0, src.split('\n').length).join('\n').replace(/\s+$/, '') === want);
  await b.close(); })();
