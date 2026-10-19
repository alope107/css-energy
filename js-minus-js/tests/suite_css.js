// suite_css.js page.xhtml [name...] — level 3 driver (harness script): for each test, Run off, write the program's
// codes into the latch cells, Run on, wait for the chain's done anchor, read every code/data overlay, compare.
// SHARDS=N runs the tests in N browsers at once (make l3 does), each taking the next test as it finishes one; the lines
// print in the suite's order. The verdicts don't depend on it; the ms column does (the default, 1, for timing).
const { launch, fileUrl } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const fs = require('fs'), path = require('path');
(async () => {
  const page = path.resolve(process.argv[2]); const exp = JSON.parse(fs.readFileSync(page + '.exp.json', 'utf8'));
  const base = exp._base || 4096; delete exp._base;
  const only = process.argv.slice(3); const names = Object.keys(exp).filter(n => !only.length || only.includes(n));
  const shards = Math.max(1, Math.min(+(process.env.SHARDS || 1), names.length));
  const lines = []; let printed = 0, next = 0, pass = 0; const fails = [];
  const flush = () => { while (printed < names.length && lines[printed] !== undefined) console.log(lines[printed++]); };
  async function shard() {
    const b = await launch({ args: ['--no-sandbox', '--disable-gpu'] });
    const p = await b.newPage(); const t0 = Date.now();
    await p.goto(fileUrl(page), { timeout: 900000 }); console.log('load', Date.now() - t0, 'ms');
    for (let i; (i = next++) < names.length;) { lines[i] = await test(p, names[i]); flush(); }
    await b.close();
  }
  async function test(p, name) {
    const e = exp[name];
    const r = await p.evaluate(async ([lines, base]) => {
      const frame = () => new Promise(r => requestAnimationFrame(r));
      const run = document.getElementById('run'); run.checked = false; await frame();
      const rows = document.querySelectorAll('.rows > .row');
      rows.forEach((row, k) => { const ln = lines[k] || []; row.querySelectorAll(':scope > i').forEach((c, j) => c.style.setProperty('--lv', j < ln.length ? ln[j] : 0)); });
      await frame(); await frame();
      const t = performance.now(); run.checked = true;
      const vis = el => el.getClientRects().length > 0;
      let info = 0, ok = 0;
      while (performance.now() - t < 60000) {
        await frame();
        const d = [...document.querySelectorAll('.fin')].find(vis);
        info = d ? d.querySelector('.di').getBoundingClientRect().width : 0;
        if (info % 2 === 1) { ok = d.querySelector('.dn').getBoundingClientRect().width; break; }
      }
      const ms = performance.now() - t; const code = {}, data = {};
      for (const el of document.querySelectorAll('.ov, .ovd, .ovs, .ovn, .ovk')) {
        if (!el.getClientRects().length) continue; const an = getComputedStyle(el).anchorName;
        if (an && an !== 'none') (el.classList.contains('ov') ? code : data)[+an.slice(3) + base] = Math.round(el.getBoundingClientRect().width) - 1048576;
      }
      return { ms, info, ok, code, data };
    }, [e.lines, base]);
    const err = Math.floor(r.info / 2) % 512;
    const diff = [];
    for (const [kind, want, got] of [['code', e.code, r.code], ['data', e.data, r.data]])
      for (const a of new Set([...Object.keys(want), ...Object.keys(got)])) if (want[a] !== got[a]) diff.push(`${kind}[${a}] want ${want[a]} got ${got[a]}`);
    // a program the compiler must reject: any error code (a token no variant accepts reports 99, not the specific code)
    const good = r.info % 2 === 1 && (e.err ? err !== 0 : err === 0 && diff.length === 0);
    if (good) pass++; else fails.push(name);
    return `${good ? 'ok  ' : 'FAIL'} ${name.padEnd(22)} ${Math.round(r.ms)} ms  err ${err}${e.err ? ' (want ' + e.err + ')' : ''}  words ${Math.floor(r.info / 1024)}` + (good ? '' : '  ' + diff.slice(0, 4).join('; '));
  }
  await Promise.all(Array.from({ length: shards }, shard));
  fails.sort((a, b) => names.indexOf(a) - names.indexOf(b));
  console.log(`${pass}/${names.length} pass` + (fails.length ? '  FAILED: ' + fails.join(' ') : ''));
})();
