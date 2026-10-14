// type a file, press Run (checkbox), wait until the scan stops, count unread/wrong cells (harness only)
const { launch, open } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const { typeLines } = require(require('path').join(__dirname, '..', 'tools', 'page.js'));
const fs = require('fs');
(async () => { const b = await launch({ args: ['--no-sandbox', '--disable-gpu'] });
  const p = await open(b, process.argv[2], { viewport: { width: 1300, height: 950 } });
  await p.waitForTimeout(1500); const src = fs.readFileSync(process.argv[3], 'utf8').replace(/\n$/, '');
  let bad = 0;
  for (let rep = 0; rep < +(process.argv[4] || 3); rep++) {
    await p.evaluate(() => { document.getElementById('run').checked = false; }); await p.waitForTimeout(200);
    await typeLines(p, src.split('\n'));
    await p.evaluate(() => { document.getElementById('run').checked = true; });
    const t = Date.now(); while (true) { await p.waitForTimeout(100); const r = await p.evaluate(() => +getComputedStyle(document.querySelector('#app')).getPropertyValue('--rbready')); if (r === 1 || Date.now() - t > 30000) break; }
    const ms = Date.now() - t;
    const got = await p.evaluate(() => [...document.querySelectorAll('.probe')].filter(e => e.getClientRects().length).map(pr => [...pr.querySelectorAll('.row i')].map(i => { const v = +getComputedStyle(i).getPropertyValue('--lv'); return v > 0 ? String.fromCharCode(v) : (v < 0 ? '_' : '.'); }).join('').replace(/[ .]+$/, '')));
    const want = src.split('\n'); let miss = 0; for (let k = 0; k < want.length; k++) for (let j = 0; j < want[k].length; j++) if ((got[k] || '')[j] !== want[k][j]) miss++;
    const pos = []; for (let k = 0; k < want.length; k++) for (let j = 0; j < want[k].length; j++) if ((got[k] || '')[j] !== want[k][j]) pos.push(k + ':' + j + '=' + JSON.stringify((got[k] || '')[j] || ''));
    bad += miss; console.log('rep', rep, 'sweep ms', ms, 'misses', miss, pos.slice(0, 12).join(' '));
  }
  await b.close(); })();
