// editor_input.js page.xhtml [case …] — the editor under user input (harness only). Each case loads the page, edits the
// editor like a user, presses Run and waits for the compile. It checks what matters: the scan latched what the editor
// shows. Latch row r must equal visual row r of the editor, where each character is placed by its on-screen position.
// Also: lines Chrome nests in another (its editing, formatted pastes) read as they show, a pasted code block (<pre>) shows
// as one line and the page says so (.merged), a line break inside a line (Shift+Enter) makes the page say a row isn't
// read (.unread), a selection's highlight stays still while editing, and formatted text
// pasted from other apps reads as it shows. Cases marked known are reported but don't fail the run. EXP=grid also runs
// the TO_HALT cases to HALT.
const { launch, fileUrl } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const { consoleCodes, gridText, typeLines } = require(require('path').join(__dirname, '..', 'tools', 'page.js'));
const fs = require('fs'), path = require('path');

const FIZZ = fs.readFileSync(path.join(__dirname, 'fizz.js'), 'utf8').replace(/\n$/, '').split('\n');

// the cases EXP also runs to HALT (FizzBuzz, whose output is EXP)
const TO_HALT = ['enter after line 1', 'select all, paste a formatted program (VS Code)'];

// put the caret at the end of the line showing `text`, or at column `col` of it
async function caretAt(p, text, col) {
  const r = await p.evaluate(([text, col]) => {
    const w = document.createTreeWalker(document.querySelector('#ed'), NodeFilter.SHOW_TEXT);
    for (let n; (n = w.nextNode());) { const i = n.data.replace(/\u00a0/g, ' ').indexOf(text); if (i < 0) continue;
      const rg = document.createRange(); const o = i + (col === undefined ? text.length : col); rg.setStart(n, o); rg.setEnd(n, o);
      const b = rg.getClientRects()[0] || rg.getBoundingClientRect(); return { x: b.left, y: (b.top + b.bottom) / 2 }; }
    return null; }, [text, col]);
  if (!r) throw new Error(`no line shows ${JSON.stringify(text)}`);
  await p.mouse.click(r.x + 1, r.y);
}
const keys = async (p, ...ks) => { for (const k of ks) await p.keyboard.press(k); };
// put `text` on the clipboard as plain text only, as another app would (copied from a textarea), keeping the caret
async function clipPlain(p, text) {
  await p.evaluate(text => { const sel = getSelection(); window.__keep = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
    const t = document.createElement('textarea'); t.id = '__clip'; t.value = text; document.body.append(t); t.select(); }, text);
  await keys(p, 'Control+C');
  await p.evaluate(() => { document.querySelector('#__clip').remove(); document.querySelector('#ed').focus();
    if (window.__keep) { const sel = getSelection(); sel.removeAllRanges(); sel.addRange(window.__keep); } });
}
const TWO = '  if (i == 7) { console.log(77); }\n  if (i == 8) { console.log(88); }';
// put HTML on the clipboard with its plain text, as copying formatted text from another app does
async function clipRich(p, html, text) {
  await p.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  await p.evaluate(([html, text]) => navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }),
    'text/plain': new Blob([text], { type: 'text/plain' }) })]), [html, text]);
}
const esc = t => t.replace(/&/g, '&amp;').replace(/</g, '&lt;');
const [T1, T2] = TWO.split('\n');
// what VS Code puts on the clipboard: a styled div (its font, white-space: pre) holding a div per line (an empty one
// holds a <br>)
const vscode = lines => `<meta charset='utf-8'><div style="color: #cccccc;background-color: #1f1f1f;font-family: 'Droid Sans Mono', monospace;font-weight: normal;font-size: 14px;line-height: 19px;white-space: pre;">` +
  lines.map(l => l ? `<div><span style="color: #c586c0;">${esc(l.slice(0, 4))}</span><span style="color: #cccccc;">${esc(l.slice(4))}</span></div>` : '<div><br></div>').join('') + '</div>';
const VSCODE = vscode([T1, T2]);
// a code block on a web page: a <pre> (a block that isolates its text, UA style) with highlighting spans
const PRE = `<pre class="language-js" style="background: #f6f8fa; padding: 16px; font-size: 85%;"><code><span style="color: #cf222e;">var</span> k = <span style="color: #0550ae;">3</span>;</code></pre>`;
const PRE2 = `<pre class="language-js"><code>${esc(TWO)}</code></pre>`;     // two lines: a newline in the text
// Google Docs: paragraphs in a <b>, each line a styled span
const GDOCS = `<meta charset="utf-8"><b style="font-weight:normal;" id="docs-internal-guid-1"><p dir="ltr" style="line-height:1.38;margin-top:0pt;margin-bottom:0pt;"><span style="font-size:11pt;font-family:Arial,sans-serif;white-space:pre-wrap;">${esc(T1)}</span></p><p dir="ltr" style="line-height:1.38;margin-top:0pt;margin-bottom:0pt;"><span style="font-size:11pt;font-family:Arial,sans-serif;white-space:pre-wrap;">${esc(T2)}</span></p></b>`;

const CASES = {
  'initial': async () => {},
  'enter after line 1': async p => { await caretAt(p, 'var i = 1;'); await keys(p, 'End', 'Enter'); },
  'enter after line 1, type a line': async p => { await caretAt(p, 'var i = 1;'); await keys(p, 'End', 'Enter'); await p.keyboard.insertText('var j = 2;'); },
  'enter at a line start': async p => { await caretAt(p, 'while', 0); await keys(p, 'Home', 'Enter'); },
  'split a line, rejoin it': async p => { await caretAt(p, 'while', 6); await keys(p, 'Enter', 'Backspace'); },
  'join two lines': async p => { await caretAt(p, '  i = i + 1;', 0); await keys(p, 'Home', 'Backspace'); },
  'backspace at the start of the first line': async p => { await caretAt(p, 'var i = 1;', 0); await keys(p, 'Home', 'Backspace'); },
  'join line 0 and the next': async p => { await caretAt(p, 'var i = 1;'); await keys(p, 'End', 'Delete'); },
  'type with blank lines': async p => { await typeLines(p, ['var a = 1;', '', 'var b = 2;', '', '', 'console.log(a + b);']); },
  'arrow into blank lines, type there': { shows: ['var a = 1;', 'var c = 3;', 'var b = 2;', 'var d = 4;', '', 'console.log(a + b);'], edit: async p => {
    await typeLines(p, ['var a = 1;', '', 'var b = 2;', '', '', 'console.log(a + b);']); await keys(p, 'Control+Home', 'ArrowDown');
    await p.keyboard.insertText('var c = 3;'); await keys(p, 'ArrowDown', 'ArrowDown'); await p.keyboard.insertText('var d = 4;'); } },
  'copy two lines, paste mid-program': async p => {
    await caretAt(p, '  else if (i % 3', 0); await keys(p, 'Home', 'Shift+ArrowDown', 'Shift+ArrowDown', 'Control+C');
    await caretAt(p, '  i = i + 1;', 0); await keys(p, 'Home', 'Control+V'); },
  'cut all, paste back': async p => { await p.click('#ed'); await keys(p, 'Control+A', 'Control+X', 'Control+V'); },
  'clear and retype': async p => { await typeLines(p, FIZZ); },
  'clear, type one line': async p => { await typeLines(p, ['var a = "hi"; console.log(a);']); },     // line 0 alone
  'paste plain lines at a line start': async p => { await caretAt(p, '  i = i + 1;', 0); await keys(p, 'Home'); await clipPlain(p, TWO + '\n'); await keys(p, 'Control+V'); },
  'paste plain lines into an empty line': async p => { await caretAt(p, '  i = i + 1;'); await keys(p, 'End', 'Enter'); await clipPlain(p, TWO); await keys(p, 'Control+V'); },
  'clear, paste a plain program': async p => { await p.click('#ed'); await keys(p, 'Control+A', 'Delete'); await clipPlain(p, FIZZ.join('\n')); await keys(p, 'Control+V'); },
  'type indented lines': async p => { await caretAt(p, '  i = i + 1;'); await keys(p, 'End', 'Enter'); await p.keyboard.type('    var k  =  3;'); },
  'clear, retype, enter after line 1': async p => { await typeLines(p, FIZZ); await caretAt(p, 'var i = 1;'); await keys(p, 'End', 'Enter'); },
  'paste lines into an empty line': async p => {
    await caretAt(p, '  else if (i % 3', 0); await keys(p, 'Home', 'Shift+ArrowDown', 'Control+C');
    await caretAt(p, '  i = i + 1;'); await keys(p, 'End', 'Enter', 'Control+V'); },
  'shift+enter': { unread: true, edit: async p => { await caretAt(p, '  i = i + 1;'); await keys(p, 'End', 'Shift+Enter'); await p.keyboard.insertText('var j = 2;'); } },
  // formatted text: the editor shows it in its own font and style (what was pasted can't restyle it), so it reads as shown
  'paste formatted code (VS Code)': async p => { await caretAt(p, '  i = i + 1;', 0); await keys(p, 'Home'); await clipRich(p, VSCODE, TWO + '\n'); await keys(p, 'Control+V'); },
  'paste formatted code into an empty line (VS Code)': async p => { await caretAt(p, '  i = i + 1;'); await keys(p, 'End', 'Enter'); await clipRich(p, VSCODE, TWO); await keys(p, 'Control+V'); },
  'paste formatted code mid-line (VS Code)': async p => { await caretAt(p, '  i = i + 1;', 4); await clipRich(p, VSCODE, TWO); await keys(p, 'Control+V'); },
  'select all, paste a formatted program (VS Code)': async p => { await p.click('#ed'); await keys(p, 'Control+A'); await clipRich(p, vscode(FIZZ), FIZZ.join('\n')); await keys(p, 'Control+V'); },
  "paste a code block (a web page's <pre>)": async p => { await caretAt(p, '  i = i + 1;'); await keys(p, 'End', 'Enter'); await clipRich(p, PRE2, TWO); await keys(p, 'Control+V'); },
  "paste a formatted line (a web page's <pre>)": async p => { await caretAt(p, '  i = i + 1;'); await keys(p, 'End', 'Enter'); await clipRich(p, PRE, 'var k = 3;'); await keys(p, 'Control+V'); },
  'paste formatted lines (Google Docs)': async p => { await caretAt(p, '  i = i + 1;', 0); await keys(p, 'Home'); await clipRich(p, GDOCS, TWO); await keys(p, 'Control+V'); },
};

// the editor as the user sees it: rows of 24 px, columns of 10 px, from each character's box
const visualRows = p => p.evaluate(() => {
  const ed = document.querySelector('#ed'), cs = getComputedStyle(ed), b = ed.getBoundingClientRect();
  const x0 = b.left + parseFloat(cs.borderLeftWidth) + parseFloat(cs.paddingLeft), y0 = b.top + parseFloat(cs.borderTopWidth) + parseFloat(cs.paddingTop);
  const rows = []; const w = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT); const rg = document.createRange();
  for (let n; (n = w.nextNode());) for (let i = 0; i < n.data.length; i++) {
    if (n.data[i] === '\n') continue; rg.setStart(n, i); rg.setEnd(n, i + 1); const r = rg.getClientRects()[0]; if (!r) continue;
    const row = Math.floor(((r.top + r.bottom) / 2 - y0) / 24), col = Math.round((r.left - x0) / 10);
    (rows[row] = rows[row] || [])[col] = n.data[i] === '\u00a0' ? ' ' : n.data[i]; }   // the font reads U+00A0 as a space
  // only the first 64 columns are read (the faint line in the editor marks the edge)
  return [...rows].map(r => r ? [...r].slice(0, 64).map(c => c || ' ').join('').replace(/\s+$/, '') : ''); });

// what the scan latched: one row per probe; a hidden probe (no such line) reads as spaces
const latchRows = p => p.evaluate(() => [...document.querySelectorAll('.probe')].map(pr => !pr.getClientRects().length ? '' :
  [...pr.querySelectorAll('.row i')].map(i => { const v = +getComputedStyle(i).getPropertyValue('--lv'); return v >= 32 && v < 127 ? String.fromCharCode(v) : ' '; }).join('').replace(/\s+$/, '')));

const trimEnd = rows => { const r = [...rows]; while (r.length && !r.at(-1)) r.pop(); return r; };
const status = p => p.evaluate(() => getComputedStyle(document.querySelector('.cstv'), '::before').content.replace(/"/g, ''));

async function runCase(b, page, name, c, exp, log = console.log) {
  const { edit, known, unread, shows } = typeof c === 'function' ? { edit: c } : c;
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } });
  await p.goto(fileUrl(page), { timeout: 600000 }); await p.waitForTimeout(500);
  await edit(p); await p.waitForTimeout(200);
  const nested = await p.evaluate(() => !!document.querySelector('#ed div div'));
  const merged = await p.evaluate(() => !!document.querySelector('#ed pre'));
  const shown = sel => p.evaluate(sel => { const e = document.querySelector(sel); return !!e && e.getBoundingClientRect().height > 0 && e.getClientRects().length > 0; }, sel);
  const warned = await shown('.merged'), unreadNote = await shown('.unread');
  const seen = trimEnd(await visualRows(p));
  const t = Date.now(); await p.click('.runbtn'); let st = '';
  while (Date.now() - t < 60000) { await p.waitForTimeout(100); st = await status(p); if (/compiled|error/.test(st)) break; }
  const read = trimEnd(await latchRows(p));
  const wysiwyg = JSON.stringify(seen) === JSON.stringify(read);
  let out = null;
  if (exp && TO_HALT.includes(name)) {
    while (Date.now() - t < 120000 && !(await p.evaluate(() => +getComputedStyle(document.querySelector('#cpu')).getPropertyValue('--isHALT') === 1))) await p.waitForTimeout(200);
    out = gridText(await consoleCodes(p)) === exp.replace(/\s+$/, '');
  }
  // a line holding a <br> shows a row the scan doesn't read: then the page must say so (.unread), and only then
  const ok = (unread ? unreadNote : wysiwyg && !unreadNote) && warned === merged && out !== false && (!shows || JSON.stringify(seen) === JSON.stringify(shows));
  log(JSON.stringify({ case: name, ok, known: !!known, wysiwyg, nested, merged, warned, unreadNote, status: st.replace(/ +counter\(\w+\) +/g, ' n '), ...(out === null ? {} : { output: out }) }));
  if (!wysiwyg) log('  editor shows:\n' + seen.map((r, i) => `  ${String(i).padStart(2)}|${r}`).join('\n') + '\n  scan read:\n' + read.map((r, i) => `  ${String(i).padStart(2)}|${r}`).join('\n'));
  await p.close();
  return { ok, known: !!known };
}

// a selection's highlight while editing: count screencast frames in which the highlighted pixels change
async function highlightCase(b, page) {
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } });
  await p.goto(fileUrl(page), { timeout: 600000 }); await p.waitForTimeout(1500);
  await p.click('#ed'); await p.keyboard.press('Control+A'); await p.waitForTimeout(300);
  const box = await p.evaluate(() => { const r = document.querySelector('#ed').getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: 660, h: 260 }; });
  const cdp = await p.context().newCDPSession(p); const frames = [];
  cdp.on('Page.screencastFrame', f => { frames.push(f.data); cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {}); });
  await cdp.send('Page.startScreencast', { format: 'png', everyNthFrame: 1 }); await p.waitForTimeout(2500); await cdp.send('Page.stopScreencast');
  const changed = await p.evaluate(async ({ frames, box }) => {
    const c = new OffscreenCanvas(box.w, box.h), x = c.getContext('2d', { willReadFrequently: true }); let prev = null, n = 0;
    for (const f of frames) {
      const im = await new Promise(r => { const i = new Image(); i.onload = () => r(i); i.src = 'data:image/png;base64,' + f; });
      x.drawImage(im, box.x, box.y, box.w, box.h, 0, 0, box.w, box.h); const d = x.getImageData(0, 0, box.w, box.h).data; const m = new Uint8Array(box.w * box.h);
      for (let k = 0; k < m.length; k++) m[k] = d[4 * k + 2] > 150 && d[4 * k + 2] - d[4 * k] > 60 ? 1 : 0;   // selection blue
      if (prev) { let s = 0; for (let k = 0; k < m.length; k++) s += m[k] !== prev[k]; if (s > 20) n++; } prev = m; }
    return n; }, { frames, box });
  console.log(JSON.stringify({ case: 'highlight while editing', ok: changed === 0, known: false, frames: frames.length, changedFrames: changed }));
  await p.close();
  return { ok: changed === 0, known: false };
}

// SHARDS=N runs the cases in N browsers at once (make l5-input does), each taking the next case as it finishes one; the
// lines print in the cases' order. The highlight case counts frames, so it runs after them, alone.
(async () => {
  const [page, ...only] = process.argv.slice(2);
  const exp = process.env.EXP ? fs.readFileSync(process.env.EXP, 'utf8') : null;
  const cases = Object.entries(CASES).filter(([name]) => !only.length || only.includes(name));
  const shards = Math.max(1, Math.min(+(process.env.SHARDS || 1), cases.length));
  const res = [], logs = []; let printed = 0, next = 0;
  const flush = () => { while (printed < cases.length && logs[printed] && res[printed]) { logs[printed].forEach(l => console.log(l)); printed++; } };
  const browsers = await Promise.all(Array.from({ length: shards }, () => launch({})));
  await Promise.all(browsers.map(async b => {
    for (let i; (i = next++) < cases.length;) { logs[i] = []; res[i] = await runCase(b, page, ...cases[i], exp, l => logs[i].push(l)); flush(); }
  }));
  const b = browsers.pop(); await Promise.all(browsers.map(x => x.close()));
  if (!only.length || only.includes('highlight while editing')) res.push(await highlightCase(b, page));
  await b.close();
  const must = res.filter(r => !r.known), kn = res.filter(r => r.known);
  console.log(`editor input: ${must.filter(r => r.ok).length}/${must.length} ok, known gaps ${kn.filter(r => r.ok).length}/${kn.length} ok`);
  process.exit(must.every(r => r.ok) ? 0 : 1);
})();
