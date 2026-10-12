// type a program into #ed, wait, read back the latches line by line (harness only)
const { chromium } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const fs = require('fs');
(async () => { const b = await chromium.launch({ args: ['--no-sandbox'] });
  const p = await b.newPage({ viewport: { width: 1300, height: 900 } }); await p.goto('file://' + require('path').resolve(process.argv[2]));
  const src = fs.readFileSync(process.argv[3], 'utf8').replace(/\n$/, '');
  await p.click('#ed'); await p.keyboard.press('Control+A'); await p.keyboard.press('Delete');
  const lines = src.split('\n');
  for (let i = 0; i < lines.length; i++) { if (i) await p.keyboard.press('Enter'); await p.keyboard.insertText(lines[i]); }
  console.log('editor html:', (await p.evaluate(() => document.querySelector('#ed').innerHTML)).slice(0, 200));
  await p.waitForTimeout(+(process.argv[4] || 4000));
  const got = await p.evaluate(() => [...document.querySelectorAll('.probe')].filter(e => getComputedStyle(e).display !== 'none').map(pr => [...pr.querySelectorAll('.row i')].map(i => { const v = +getComputedStyle(i).getPropertyValue('--v'); return v > 0 ? String.fromCharCode(v) : ''; }).join('').replace(/\s+$/, '')));
  console.log(got.join('\n')); console.log('match', got.join('\n').replace(/\s+$/, '') === src.split('\n').map(l => l.replace(/\s+$/, '')).join('\n'));
  await b.close(); })();
