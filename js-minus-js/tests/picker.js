// picker.js page.xhtml [sample...] — the sample picker (harness only): for each sample (samples/<name>.js; default: the
// quick ones), click its chip, check that the editor which shows holds that program, Run, wait for HALT and compare
// the console with Node's output laid out on the console grid; then Edit. Last, the first chip again: #ed shows.
const { launch, fileUrl } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const { consoleCodes, gridText } = require(require('path').join(__dirname, '..', 'tools', 'page.js'));
const fs = require('fs'), path = require('path'), { execFileSync } = require('child_process');
const LA = require(path.join(__dirname, '..', 'compiler', 'layout.json'));
const SAMPLES = ['fizzbuzz', 'primes', 'fib', 'stars', 'hanoi', 'sort', 'tree', 'caesar', 'collatz', 'bank', 'counter', 'animals'];   // gen_css.py's order
const grid = text => { const cols = LA.cols, rows = LA.rows, cells = new Array(cols * rows).fill(32); let q = 0;
  for (const ch of text) { if (ch === '\n') q = (Math.floor(q / cols) + 1) * cols % (cols * rows); else { cells[q] = ch.charCodeAt(0); q = (q + 1) % (cols * rows); } }
  return gridText(cells, rows, cols); };
(async () => {
  const [pg, ...names] = process.argv.slice(2);
  const todo = names.length ? names : ['hanoi', 'bank', 'caesar'];
  const b = await launch(); const p = await b.newPage({ viewport: { width: 1300, height: 950 } });
  await p.goto(fileUrl(pg), { timeout: 600000 }); await p.waitForTimeout(3000);
  let pass = 0;
  for (const name of todo) {
    const k = SAMPLES.indexOf(name) + 1, file = path.join(__dirname, '..', 'samples', name + '.js');
    const src = fs.readFileSync(file, 'utf8').replace(/\n$/, '');
    await p.click(`label[for=pk${k}]`); await p.waitForTimeout(300);
    const shown = await p.evaluate(() => [...document.querySelectorAll('.ed')].filter(e => e.getClientRects().length).map(e => e.className));
    const text = await p.evaluate(k => document.querySelector('.ed' + k).innerText.replace(/ /g, ' ').replace(/\n$/, ''), k);
    const want = grid(execFileSync('node', [file], { encoding: 'utf8' }));
    const t = Date.now(); await p.click('.runbtn'); let r;
    while (Date.now() - t < 240000) {
      await p.waitForTimeout(200);
      r = await p.evaluate(() => { const c = getComputedStyle(document.querySelector('#cpu')); return { halted: +c.getPropertyValue('--isHALT') === 1, steps: +c.getPropertyValue('--steps') }; });
      if (r.halted) break;
    }
    const got = gridText(await consoleCodes(p));
    const ok = shown.length === 1 && shown[0].includes('ed' + k) && text === src && got === want;
    if (ok) pass++;
    console.log(JSON.stringify({ name, shown, editorOk: text === src, haltMs: Date.now() - t, steps: r.steps, ok }) + (got === want ? '' : '\ngot:\n' + got + '\nwant:\n' + want));
    await p.click('.runbtn'); await p.waitForTimeout(500);      // Edit
  }
  await p.click('label[for=pk0]'); await p.waitForTimeout(300);
  const back = await p.evaluate(() => [...document.querySelectorAll('.ed')].filter(e => e.getClientRects().length).map(e => e.id || e.className));
  const ok0 = back.length === 1 && back[0] === 'ed';
  console.log(JSON.stringify({ name: '#ed again', shown: back, ok: ok0 }));
  console.log(`${pass + ok0}/${todo.length + 1} pass`);
  await b.close();
})();
