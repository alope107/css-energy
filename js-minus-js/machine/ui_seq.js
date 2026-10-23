// ui_seq.js page.xhtml [prog expected]... — act like a user (harness only): wait for the scan, Run the initial program,
// then for each further program: Edit, retype the editor, Run, and check the console (or the status, for 'ERR:text').
// SHARDS=N runs the programs in N browsers at once (make l5 does), each starting as above and then taking the next
// program as it finishes one, the longest source first (compiling is most of a program's time, so the slowest don't
// start last); their lines print in the arguments' order. The verdicts don't depend on it; compiledMs and haltMs do
// (the default, 1, for timing, keeps the arguments' order).
// NETROOT=dir: serve dir with the network gateway (net/server.js) and open the page there over http, not file: (the NET
// instruction's modem needs both; each page gets its own gateway session).
const { launch, fileUrl, envArgs } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const { consoleCodes, gridText, typeLines } = require(require('path').join(__dirname, '..', 'tools', 'page.js'));
const fs = require('fs'), path = require('path');
(async () => {
  const [pg, ...rest] = process.argv.slice(2);
  const progs = []; for (let i = 0; i < rest.length; i += 2) progs.push([rest[i], rest[i + 1]]);
  const shards = Math.max(1, Math.min(+(process.env.SHARDS || 1), progs.length));
  const size = progs.map(([f]) => fs.statSync(f).size);
  const order = progs.map((_, i) => i).sort((a, b) => shards > 1 && size[b] - size[a] || a - b);
  const blocks = []; let printed = 0, next = 0;
  const flush = () => { while (printed < progs.length && blocks[printed] !== undefined) { if (blocks[printed]) console.log(blocks[printed]); printed++; } };
  const NR = process.env.NETROOT;
  const srv = NR && await require(path.join(__dirname, '..', 'net', 'server.js')).serve(path.resolve(NR), 0, {}, { log: process.env.NETLOG ? (...a) => console.log('net', ...a) : undefined });
  const at = NR ? `http://127.0.0.1:${srv.address().port}/${path.relative(NR, pg)}` : fileUrl(pg);
  async function session() {
    const b = await launch({ extraArgs: envArgs('FLAGS') });
    const p = await b.newPage(process.env.FLAGS ? { viewport: null } : { viewport: { width: 1300, height: 950 } });
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
      const lines = [JSON.stringify({ label, compiledMs: comp, haltMs: Date.now() - t, steps: r.steps, status: r.status, words: r.n, ok })];
      if (!ok) { lines.push('got:\n' + o); lines.push(await p.evaluate(() => { const ls = [...document.querySelectorAll('.ls')].slice(0, 9);
        const lat = [...document.querySelectorAll('.probe')].filter(e => e.getClientRects().length).map(pr => [...pr.querySelectorAll('.row i')].map(i => { const v = +getComputedStyle(i).getPropertyValue('--lv'); return v > 0 ? String.fromCharCode(v) : '.'; }).join('').replace(/[ .]+$/, ''));
        return 'editor: ' + JSON.stringify(document.querySelector('#ed').innerText) + '\nlatches:\n' + lat.join('\n'); })); }
      return lines.join('\n');
    }
    async function type(file) {
      await p.click('.runbtn'); await p.waitForTimeout(300);           // Edit
      await typeLines(p, fs.readFileSync(file, 'utf8').replace(/\n$/, '').split('\n'));
      await p.waitForTimeout(+(process.env.TYPEWAIT || 500));
    }
    await p.waitForTimeout(+(process.env.INITWAIT || 3000));
    console.log(await run('initial', process.env.EXP1 ? fs.readFileSync(process.env.EXP1, 'utf8') : 'ERR:compiled'));
    for (let k; (k = next++) < progs.length;) {
      const i = order[k], [file, exp] = progs[i]; await type(file);
      blocks[i] = await run(path.basename(file), exp.startsWith('ERR:') ? exp : fs.readFileSync(exp, 'utf8')); flush();
    }
    await b.close();
  }
  await Promise.all(Array.from({ length: shards }, session));
  if (srv) srv.close();
})();
