// repl_ui.js repl.xhtml session.js... — the REPL's page (harness only): empty its editor (so the session starts over), type each
// session's lines like a user (Enter after each, the last one too), wait for the run, and read the transcript the page shows
// back: each line's prompt and text, and the output rows the display lays out, in the order they stand on the page. Compared
// with the oracle's transcript (tests/repl_expect.js: session.tr).
// WAIT=1 waits for each entry's run before typing the next (as a user would: each run then runs only the new entry, on the
// memory the last one left) and prints how long each took; without it the lines go in at once (each Enter stops the run
// going on, and the last one runs the session from its start).
const { launch, fileUrl } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const fs = require('fs'), path = require('path');
const nbsp = s => s.replace(/ +/g, (m, i) => i === 0 || i + m.length === s.length ? ' '.repeat(m.length) : ' '.repeat(m.length - 1) + ' ');
(async () => {
  const [pg, ...files] = process.argv.slice(2);
  const b = await launch(); const p = await b.newPage({ viewport: { width: 1300, height: 1400 } });
  await p.goto(fileUrl(pg), { timeout: 600000 }); await p.waitForTimeout(+(process.env.INITWAIT || 2000));
  const ed = '#ed';
  // (err: the compiler finished with an error: an entry still open, so nothing runs for that line)
  const state = () => p.evaluate(() => { const d = getComputedStyle(document.querySelector('.rdisp')), c = getComputedStyle(document.querySelector('.cstv'));
    return { rg: +d.getPropertyValue('--rg'), rn: +d.getPropertyValue('--rn'), end: +d.getPropertyValue('--mkE'), ccgo: +d.getPropertyValue('--ccgo'),
             err: +c.getPropertyValue('--csd') === 1 && +c.getPropertyValue('--cse') > 0 }; });
  // the transcript as it shows: [top, text] for each prompted line and each output row, sorted by top. Line 0 is the editor's
  // own text, lines 1 ... its divs (typed lines: Enter at a line's end makes the next div)
  const read = () => p.evaluate(ed => {
    const e = document.querySelector(ed), items = [];
    const divs = [...e.children].filter(d => d.localName === 'div');
    const text0 = [...e.childNodes].filter(n => n.nodeType === 3 || (n.nodeType === 1 && n.localName !== 'div')).map(n => n.textContent).join('');
    const lines = [text0, ...divs.map(d => d.innerText.replace(/\n/g, ''))];
    for (let k = 0; k < lines.length; k++) {
      const pm = document.querySelector('.rpm' + k);
      if (!pm || getComputedStyle(pm).display === 'none') continue;
      const pr = getComputedStyle(pm, '::before').content.replace(/"/g, '');
      items.push([pm.getBoundingClientRect().top, ((pr === '>' ? '> ' : '... ') + lines[k].replace(/ /g, ' ')).trimEnd()]);
    }
    for (const row of document.querySelectorAll('.rrow')) {
      if (getComputedStyle(row).display === 'none') continue;
      const cs = [...row.querySelectorAll('.rc')];
      const t = cs.map(c => { const v = +getComputedStyle(c.firstChild).getPropertyValue('--rcd'); return v >= 32 && v < 127 ? String.fromCharCode(v) : ' '; }).join('').trimEnd();
      items.push([cs[0].getBoundingClientRect().top, t]);
    }
    return items.sort((x, y) => x[0] - y[0]).map(x => x[1]).join('\n');
  }, ed);
  // the run for n lines is shown (the gate open, the latched line count n, the end marked), or its compile failed (anyok: an
  // entry still open), and steady
  async function settle(n, t0, anyok) {
    let last = null, since = 0;
    while (Date.now() - t0 < +(process.env.MAXMS || 120000)) {
      await p.waitForTimeout(100); const s = await state();
      const ok = (s.rg === 1 && s.rn === n && s.end > 0) || (anyok && s.ccgo === 1 && s.err), key = JSON.stringify(s);
      if (ok && key === last) { if (Date.now() - since > 300) return Date.now() - t0; } else { since = Date.now(); last = ok ? key : null; }
    }
    return -1;
  }
  // the page's demo session first: its lines are line 0 and every div but the last, the prompt
  await settle(await p.evaluate(ed => [...document.querySelector(ed).children].filter(d => d.localName === 'div').length, ed), Date.now());
  let allok = true;
  for (const f of files) {
    const lines = fs.readFileSync(f, 'utf8').replace(/\n$/, '').split('\n');
    const want = fs.readFileSync(f.replace(/\.js$/, '.tr'), 'utf8').replace(/\n$/, '');
    // an empty editor (one row: fewer lines than the last run read, so the session starts over), then the lines typed. (Not
    // Ctrl+A and Backspace: Chrome leaves <div><br></div>, and the lines typed then start at row 1, after an empty line 0)
    await p.evaluate(ed => { const e = document.querySelector(ed); e.innerHTML = ''; e.focus(); }, ed);
    if (process.env.WAIT) await settle(0, Date.now());
    const t0 = Date.now(); let ms = 0;
    for (let i = 0; i < lines.length; i++) {
      await p.keyboard.insertText(nbsp(lines[i])); await p.keyboard.press('Enter');
      if (process.env.WAIT) console.log(JSON.stringify({ label: path.basename(f), line: i + 1, ms: await settle(i + 1, Date.now(), i + 1 < lines.length) }));
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
