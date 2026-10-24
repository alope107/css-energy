// repl_ui.js page.xhtml session.js... — the REPL on the real page (harness only): pick the REPL, empty its editor to one
// prompt line, type each session's lines like a user (Enter after each, the last one too), wait for the run, and read the
// transcript the page shows back: each line's prompt and text, and the output rows the display lays out, in the order they
// stand on the page. Compared with the oracle's transcript (tests/repl_expect.js: session.tr).
// WAIT=1 waits for each entry's run before typing the next (as a user would) and prints how long each took.
const { launch, fileUrl } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const fs = require('fs'), path = require('path');
const nbsp = s => s.replace(/ +/g, (m, i) => i === 0 || i + m.length === s.length ? ' '.repeat(m.length) : ' '.repeat(m.length - 1) + ' ');
(async () => {
  const [pg, ...files] = process.argv.slice(2);
  const b = await launch(); const p = await b.newPage({ viewport: { width: 1300, height: 1400 } });
  await p.goto(fileUrl(pg), { timeout: 600000 }); await p.waitForTimeout(+(process.env.INITWAIT || 2000));
  const R = await p.evaluate(() => [...document.querySelectorAll('.picker label')].find(l => l.textContent === 'REPL').htmlFor);
  await p.click(`label[for=${R}]`);
  const ed = `.ed${R.slice(2)}`;
  const state = () => p.evaluate(() => { const d = getComputedStyle(document.querySelector('.rdisp'));
    return { rg: +d.getPropertyValue('--rg'), rn: +d.getPropertyValue('--rn'), end: +d.getPropertyValue('--mkE') }; });
  // the transcript as it shows: [top, text] for each prompted line and each output row, sorted by top
  const read = () => p.evaluate(ed => {
    const items = [], divs = [...document.querySelector(ed).children].filter(d => d.localName === 'div');
    for (let k = 1; k <= divs.length; k++) {
      const pm = document.querySelector('.rpm' + k);
      if (!pm || getComputedStyle(pm).display === 'none') continue;
      const pr = getComputedStyle(pm, '::before').content.replace(/"/g, '');
      items.push([pm.getBoundingClientRect().top, ((pr === '>' ? '> ' : '... ') + divs[k - 1].innerText.replace(/ /g, ' ').replace(/\n/g, '')).trimEnd()]);
    }
    for (const row of document.querySelectorAll('.rrow')) {
      if (getComputedStyle(row).display === 'none') continue;
      const cs = [...row.querySelectorAll('.rc')];
      const t = cs.map(c => { const v = +getComputedStyle(c.firstChild).getPropertyValue('--rcd'); return v >= 32 && v < 127 ? String.fromCharCode(v) : ' '; }).join('').trimEnd();
      items.push([cs[0].getBoundingClientRect().top, t]);
    }
    return items.sort((x, y) => x[0] - y[0]).map(x => x[1]).join('\n');
  }, ed);
  // the run for n lines (n + 1 with the prompt) is shown: the gate open, the latched count n + 1, the end marked, and steady
  async function settle(n, t0) {
    let last = null, since = 0;
    while (Date.now() - t0 < +(process.env.MAXMS || 120000)) {
      await p.waitForTimeout(100); const s = await state();
      const ok = s.rg === 1 && s.rn === n + 1 && s.end > 0, key = JSON.stringify(s);
      if (ok && key === last) { if (Date.now() - since > 300) return Date.now() - t0; } else { since = Date.now(); last = ok ? key : null; }
    }
    return -1;
  }
  let allok = true;
  for (const f of files) {
    const lines = fs.readFileSync(f, 'utf8').replace(/\n$/, '').split('\n');
    const want = fs.readFileSync(f.replace(/\.js$/, '.tr'), 'utf8').replace(/\n$/, '');
    await p.evaluate(ed => { const e = document.querySelector(ed); e.innerHTML = '<div><br/></div>'; }, ed);
    await p.waitForTimeout(300);
    const first = await p.$(`${ed} > div`); const bb = await first.boundingBox(); await p.mouse.click(bb.x + 20, bb.y + bb.height - 8);
    const t0 = Date.now(); let ms = 0;
    for (let i = 0; i < lines.length; i++) {
      await p.keyboard.insertText(nbsp(lines[i])); await p.keyboard.press('Enter');
      if (process.env.WAIT) console.log(JSON.stringify({ label: path.basename(f), line: i + 1, ms: await settle(i + 1, Date.now()) }));
    }
    if (!process.env.WAIT) ms = await settle(lines.length, t0);
    const got = await read(), ok = got === want;
    allok &= ok;
    console.log(JSON.stringify({ label: path.basename(f), ms, ok }));
    if (!ok) console.log('got:\n' + got + '\nwant:\n' + want);
  }
  console.log(allok ? `${files.length}/${files.length} pass` : 'FAILURES');
  await b.close();
})();
