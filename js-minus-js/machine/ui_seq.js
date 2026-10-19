// ui_seq.js page.xhtml [prog expected]... — act like a user (harness only): wait for the scan, Run the initial program,
// then for each further program: Edit, retype the editor, Run, and check the console (or the status, for 'ERR:text').
// NETROOT=dir: serve dir with the network gateway (net/server.js) and open the page there (http, not file:), with
// responsive iframes on (Chrome 155+ has them by default): the NET instruction's modem needs both.
const { launch, fileUrl, envArgs } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const { consoleCodes, gridText, typeLines } = require(require('path').join(__dirname, '..', 'tools', 'page.js'));
const fs = require('fs'), path = require('path');
(async () => {
  const [pg, ...rest] = process.argv.slice(2);
  const NR = process.env.NETROOT;
  const srv = NR && await require(path.join(__dirname, '..', 'net', 'server.js')).serve(path.resolve(NR), 0);
  const b = await launch({ extraArgs: [...envArgs('FLAGS'), ...(NR ? ['--enable-blink-features=ResponsiveIframes'] : [])] });
  const p = await b.newPage(process.env.FLAGS ? { viewport: null } : { viewport: { width: 1300, height: 950 } });
  const at = NR ? `http://127.0.0.1:${srv.address().port}/${path.relative(NR, pg)}` : fileUrl(pg);
  const t0 = Date.now(); await p.goto(at, { timeout: 600000 }); console.log('load ms', Date.now() - t0);
  const st = () => p.evaluate(() => { const c = getComputedStyle(document.querySelector('#cpu')); return { steps: +c.getPropertyValue('--steps'), kind: +c.getPropertyValue('--kind'),
    halted: +c.getPropertyValue('--isHALT') === 1,
    status: getComputedStyle(document.querySelector('.cstv'), '::before').content.replace(/"/g, ''), n: getComputedStyle(document.querySelector('.cstv')).getPropertyValue('--csn') }; });
  const out = async () => gridText(await consoleCodes(p));
  async function run(label, want) {
    const t = Date.now(); await p.click('.runbtn'); let r, comp = null;
    while (Date.now() - t < 240000) { await p.waitForTimeout(100); r = await st(); if (comp === null && /compiled|error/.test(r.status)) comp = Date.now() - t; if (r.halted || /error/.test(r.status)) break; }
    const o = await out(); let ok;
    if (want.startsWith('ERR:')) ok = r.status.includes(want.slice(4)); else ok = o === want.replace(/\s+$/, '');
    console.log(JSON.stringify({ label, compiledMs: comp, haltMs: Date.now() - t, steps: r.steps, status: r.status, words: r.n, ok }));
    if (!ok) { console.log('got:\n' + o); console.log(await p.evaluate(() => { const ls = [...document.querySelectorAll('.ls')].slice(0, 9);
      const lat = [...document.querySelectorAll('.probe')].filter(e => e.getClientRects().length).map(pr => [...pr.querySelectorAll('.row i')].map(i => { const v = +getComputedStyle(i).getPropertyValue('--lv'); return v > 0 ? String.fromCharCode(v) : '.'; }).join('').replace(/[ .]+$/, ''));
      return 'editor: ' + JSON.stringify(document.querySelector('#ed').innerText) + '\nlatches:\n' + lat.join('\n'); })); }
  }
  async function type(file) {
    await p.click('.runbtn'); await p.waitForTimeout(300);           // Edit
    await typeLines(p, fs.readFileSync(file, 'utf8').replace(/\n$/, '').split('\n'));
    await p.waitForTimeout(+(process.env.TYPEWAIT || 500));
  }
  await p.waitForTimeout(+(process.env.INITWAIT || 3000));
  await run('initial', process.env.EXP1 ? fs.readFileSync(process.env.EXP1, 'utf8') : 'ERR:compiled');
  for (let i = 0; i < rest.length; i += 2) { await type(rest[i]); const w = rest[i + 1].startsWith('ERR:') ? rest[i + 1] : fs.readFileSync(rest[i + 1], 'utf8'); await run(path.basename(rest[i]), w); }
  await b.close(); if (srv) srv.close();
})();
