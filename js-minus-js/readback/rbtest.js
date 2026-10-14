// type a program into #ed, wait, read back the latches line by line (harness only)
const { launch, open } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const { typeLines } = require(require('path').join(__dirname, '..', 'tools', 'page.js'));
const fs = require('fs');
(async () => { const b = await launch({ args: ['--no-sandbox'] });
  const p = await open(b, process.argv[2], { viewport: { width: 1300, height: 900 } });
  const src = fs.readFileSync(process.argv[3], 'utf8').replace(/\n$/, '');
  await typeLines(p, src.split('\n'));
  console.log('editor html:', (await p.evaluate(() => document.querySelector('#ed').innerHTML)).slice(0, 200));
  await p.waitForTimeout(+(process.argv[4] || 4000));
  const got = await p.evaluate(() => [...document.querySelectorAll('.probe')].filter(e => getComputedStyle(e).display !== 'none').map(pr => [...pr.querySelectorAll('.row i')].map(i => { const v = +getComputedStyle(i).getPropertyValue('--v'); return v > 0 ? String.fromCharCode(v) : ''; }).join('').replace(/\s+$/, '')));
  console.log(got.join('\n')); console.log('match', got.join('\n').replace(/\s+$/, '') === src.split('\n').map(l => l.replace(/\s+$/, '')).join('\n'));
  await b.close(); })();
