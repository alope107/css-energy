// ui_run.js page.xhtml [prog2.js expected2.txt] — drive the typed-program page like a user (harness only):
// wait for the scan, press Run, time to HALT, read the console; then Edit, type another program, Run again.
const { launch, fileUrl, envArgs } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const { consoleCodes, gridText, typeLines } = require(require('path').join(__dirname, '..', 'tools', 'page.js'));
const fs = require('fs');
(async () => {
  const [pg, prog2, exp2] = process.argv.slice(2);
  const b = await launch({ extraArgs: envArgs('FLAGS') });
  const p = await b.newPage(process.env.FLAGS ? { viewport: null } : { viewport: { width: 1300, height: 950 } });
  const t0 = Date.now(); await p.goto(fileUrl(pg), { timeout: 600000 }); console.log('load ms', Date.now() - t0);
  const cpu = () => p.evaluate(() => { const c = getComputedStyle(document.querySelector('#cpu')); const s = getComputedStyle(document.querySelector('.cstv'), '::before');
    return { steps: +c.getPropertyValue('--steps'), kind: +c.getPropertyValue('--kind'), halted: +c.getPropertyValue('--isHALT') === 1, run: +c.getPropertyValue('--run'), ccok: +c.getPropertyValue('--ccok'), status: s.content }; });
  const consoleText = async () => gridText(await consoleCodes(p));
  async function runOnce(label, want) {
    const t = Date.now(); await p.click('.runbtn'); let r, first = null, comp = null;
    while (Date.now() - t < 300000) { await p.waitForTimeout(100); r = await cpu();
      if (comp === null && /compiled|error/.test(r.status)) comp = Date.now() - t;
      if (first === null && r.steps > 0) first = Date.now() - t; if (r.halted || /error/.test(r.status)) break; }
    const out = await consoleText();
    console.log(JSON.stringify({ label, compiledMs: comp, firstStepMs: first, haltMs: Date.now() - t, steps: r.steps, status: r.status, ok: want === undefined ? null : out === want.replace(/\s+$/, '') }));
    if (want !== undefined && out !== want.replace(/\s+$/, '')) console.log('got:\n' + out + '\nwant:\n' + want);
  }
  await p.waitForTimeout(+(process.env.INITWAIT || 3000));
  console.log('before run', JSON.stringify(await cpu()));
  await runOnce('initial', process.env.EXP1 ? fs.readFileSync(process.env.EXP1, 'utf8') : undefined);
  if (prog2) {
    await p.click('.runbtn'); await p.waitForTimeout(500); console.log('edit mode', JSON.stringify(await cpu()), 'console after edit:', JSON.stringify(await consoleText()));
    await typeLines(p, fs.readFileSync(prog2, 'utf8').replace(/\n$/, '').split('\n'));
    await p.waitForTimeout(+(process.env.SCANWAIT || 3500));
    await runOnce('typed', fs.readFileSync(exp2, 'utf8'));
  }
  await b.close();
})();
