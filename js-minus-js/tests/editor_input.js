// editor_input.js page.xhtml [case …] — the editor under user input (harness only). Each case loads the page, edits the
// editor like a user, presses Run and waits for the compile. It checks what matters: the scan latched what the editor
// shows. Latch row r must equal visual row r of the editor, where each character is placed by its on-screen position.
// Also: the page warns when Chrome has nested lines (.nested), and a selection's highlight stays still while editing.
// Cases marked known make Chrome nest lines: they pass when the merged line is read as shown and .nested says so.
// They're reported but don't fail the run. EXP=grid also runs 'enter after line 1' to HALT.
const { launch, fileUrl } = require(require('path').join(__dirname, '..', 'tools', 'browser.js'));
const { consoleCodes, gridText, typeLines } = require(require('path').join(__dirname, '..', 'tools', 'page.js'));
const fs = require('fs'), path = require('path');

const FIZZ = fs.readFileSync(path.join(__dirname, 'fizz.js'), 'utf8').replace(/\n$/, '').split('\n');

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

const CASES = {
  'initial': async () => {},
  'enter after line 1': async p => { await caretAt(p, 'var i = 1;'); await keys(p, 'End', 'Enter'); },
  'enter after line 1, type a line': async p => { await caretAt(p, 'var i = 1;'); await keys(p, 'End', 'Enter'); await p.keyboard.insertText('var j = 2;'); },
  'enter at a line start': async p => { await caretAt(p, 'while', 0); await keys(p, 'Home', 'Enter'); },
  'split a line, rejoin it': async p => { await caretAt(p, 'while', 6); await keys(p, 'Enter', 'Backspace'); },
  'join two lines': async p => { await caretAt(p, '  i = i + 1;', 0); await keys(p, 'Home', 'Backspace'); },
  'delete the blank first line': async p => { await caretAt(p, 'var i = 1;', 0); await keys(p, 'Home', 'Backspace'); },
  'copy two lines, paste mid-program': async p => {
    await caretAt(p, '  else if (i % 3', 0); await keys(p, 'Home', 'Shift+ArrowDown', 'Shift+ArrowDown', 'Control+C');
    await caretAt(p, '  i = i + 1;', 0); await keys(p, 'Home', 'Control+V'); },
  'cut all, paste back': async p => { await p.click('#ed'); await keys(p, 'Control+A', 'Control+X', 'Control+V'); },
  'clear and retype': async p => { await typeLines(p, FIZZ); },
  'paste plain lines at a line start': async p => { await caretAt(p, '  i = i + 1;', 0); await keys(p, 'Home'); await clipPlain(p, TWO + '\n'); await keys(p, 'Control+V'); },
  'paste plain lines into an empty line': { known: true, edit: async p => { await caretAt(p, '  i = i + 1;'); await keys(p, 'End', 'Enter'); await clipPlain(p, TWO); await keys(p, 'Control+V'); } },
  'clear, paste a plain program': async p => { await p.click('#ed'); await keys(p, 'Control+A', 'Delete'); await clipPlain(p, FIZZ.join('\n')); await keys(p, 'Control+V'); },
  'type indented lines': async p => { await caretAt(p, '  i = i + 1;'); await keys(p, 'End', 'Enter'); await p.keyboard.type('    var k  =  3;'); },
  'clear, retype, enter after line 1': { known: true, edit: async p => { await typeLines(p, FIZZ); await caretAt(p, 'var i = 1;'); await keys(p, 'End', 'Enter'); } },
  'paste lines into an empty line': { known: true, edit: async p => {
    await caretAt(p, '  else if (i % 3', 0); await keys(p, 'Home', 'Shift+ArrowDown', 'Control+C');
    await caretAt(p, '  i = i + 1;'); await keys(p, 'End', 'Enter', 'Control+V'); } },
  'shift+enter': { known: true, edit: async p => { await caretAt(p, 'var i = 1;'); await keys(p, 'End', 'Shift+Enter'); await p.keyboard.insertText('var j = 2;'); } },
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

async function runCase(b, page, name, c, exp) {
  const { edit, known } = typeof c === 'function' ? { edit: c } : c;
  const p = await b.newPage({ viewport: { width: 1300, height: 950 } });
  await p.goto(fileUrl(page), { timeout: 600000 }); await p.waitForTimeout(500);
  await edit(p); await p.waitForTimeout(200);
  const nested = await p.evaluate(() => !!document.querySelector('#ed div div'));
  const warned = await p.evaluate(() => { const e = document.querySelector('.nested'); return !!e && e.getClientRects().length > 0; });
  const seen = trimEnd(await visualRows(p));
  const t = Date.now(); await p.click('.runbtn'); let st = '';
  while (Date.now() - t < 60000) { await p.waitForTimeout(100); st = await status(p); if (/compiled|error/.test(st)) break; }
  const read = trimEnd(await latchRows(p));
  const wysiwyg = JSON.stringify(seen) === JSON.stringify(read);
  let out = null;
  if (exp && name === 'enter after line 1') {
    while (Date.now() - t < 120000 && !(await p.evaluate(() => +getComputedStyle(document.querySelector('#cpu')).getPropertyValue('--isHALT') === 1))) await p.waitForTimeout(200);
    out = gridText(await consoleCodes(p)) === exp.replace(/\s+$/, '');
  }
  const ok = wysiwyg && warned === nested && out !== false;
  console.log(JSON.stringify({ case: name, ok, known: !!known, wysiwyg, nested, warned, status: st.replace(/ +counter\(\w+\) +/g, ' n '), ...(out === null ? {} : { output: out }) }));
  if (!wysiwyg) console.log('  editor shows:\n' + seen.map((r, i) => `  ${String(i).padStart(2)}|${r}`).join('\n') + '\n  scan read:\n' + read.map((r, i) => `  ${String(i).padStart(2)}|${r}`).join('\n'));
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

(async () => {
  const [page, ...only] = process.argv.slice(2);
  const exp = process.env.EXP ? fs.readFileSync(process.env.EXP, 'utf8') : null;
  const b = await launch({});
  const res = [];
  for (const [name, c] of Object.entries(CASES)) if (!only.length || only.includes(name)) res.push(await runCase(b, page, name, c, exp));
  if (!only.length || only.includes('highlight while editing')) res.push(await highlightCase(b, page));
  await b.close();
  const must = res.filter(r => !r.known), kn = res.filter(r => r.known);
  console.log(`editor input: ${must.filter(r => r.ok).length}/${must.length} ok, known gaps ${kn.filter(r => r.ok).length}/${kn.length} ok`);
  process.exit(must.every(r => r.ok) ? 0 : 1);
})();
