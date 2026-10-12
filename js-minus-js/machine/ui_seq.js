// ui_seq.js page.xhtml [prog expected]... — act like a user (harness only): wait for the scan, Run the initial program,
// then for each further program: Edit, retype the editor, Run, and check the console (or the status, for 'ERR:text').
const { chromium } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const fs = require('fs'), path = require('path');
(async () => {
  const [pg, ...rest] = process.argv.slice(2);
  const b = await chromium.launch({ args: ['--no-sandbox', '--no-proxy-server', '--disable-gpu', ...(process.env.FLAGS ? process.env.FLAGS.split(' ') : [])] });
  const p = await b.newPage(process.env.FLAGS ? { viewport: null } : { viewport: { width: 1300, height: 950 } });
  const t0 = Date.now(); await p.goto('file://' + path.resolve(pg), { timeout: 600000 }); console.log('load ms', Date.now() - t0);
  const st = () => p.evaluate(() => { const c = getComputedStyle(document.querySelector('#cpu')); return { steps: +c.getPropertyValue('--steps'), kind: +c.getPropertyValue('--kind'),
    status: getComputedStyle(document.querySelector('.cstv'), '::before').content.replace(/"/g, ''), n: getComputedStyle(document.querySelector('.cstv')).getPropertyValue('--csn') }; });
  const out = () => p.evaluate(() => { const codes = [...document.querySelectorAll('.oc > b')].map(e => Math.round(e.parentElement.getBoundingClientRect().width) - 1048576);
    const rows = []; for (let i = 0; i < 16; i++) rows.push(codes.slice(i * 8, i * 8 + 8).map(c => c >= 32 && c < 127 ? String.fromCharCode(c) : ' ').join('').replace(/\s+$/, '')); return rows.join('\n').replace(/\s+$/, ''); });
  async function run(label, want) {
    const t = Date.now(); await p.click('.runbtn'); let r, comp = null;
    while (Date.now() - t < 240000) { await p.waitForTimeout(100); r = await st(); if (comp === null && /compiled|error/.test(r.status)) comp = Date.now() - t; if (r.kind === 97 || /error/.test(r.status)) break; }
    const o = await out(); let ok;
    if (want.startsWith('ERR:')) ok = r.status.includes(want.slice(4)); else ok = o === want.replace(/\s+$/, '');
    console.log(JSON.stringify({ label, compiledMs: comp, haltMs: Date.now() - t, steps: r.steps, status: r.status, words: r.n, ok }));
    if (!ok) { console.log('got:\n' + o); console.log(await p.evaluate(() => { const ls = [...document.querySelectorAll('.ls')].slice(0, 9);
      const lat = [...document.querySelectorAll('.probe')].filter(e => e.getClientRects().length).map(pr => [...pr.querySelectorAll('.row i')].map(i => { const v = +getComputedStyle(i).getPropertyValue('--lv'); return v > 0 ? String.fromCharCode(v) : '.'; }).join('').replace(/[ .]+$/, ''));
      return 'editor: ' + JSON.stringify(document.querySelector('#ed').innerText) + '\nlatches:\n' + lat.join('\n'); })); }
  }
  async function type(file) {
    await p.click('.runbtn'); await p.waitForTimeout(300);           // Edit
    await p.click('#ed'); await p.keyboard.press('Control+A'); await p.keyboard.press('Delete');
    const lines = fs.readFileSync(file, 'utf8').replace(/\n$/, '').split('\n');
    for (let i = 0; i < lines.length; i++) { if (i) await p.keyboard.press('Enter'); await p.keyboard.insertText(lines[i]); }
    await p.waitForTimeout(+(process.env.TYPEWAIT || 500));
  }
  await p.waitForTimeout(+(process.env.INITWAIT || 3000));
  await run('initial', process.env.EXP1 ? fs.readFileSync(process.env.EXP1, 'utf8') : 'ERR:compiled');
  for (let i = 0; i < rest.length; i += 2) { await type(rest[i]); const w = rest[i + 1].startsWith('ERR:') ? rest[i + 1] : fs.readFileSync(rest[i + 1], 'utf8'); await run(path.basename(rest[i]), w); }
  await b.close();
})();
