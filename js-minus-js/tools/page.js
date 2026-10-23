// page.js — what the harnesses read from and type into a js-minus-js page (harness only).

// The console's character codes, cell by cell: each `.oc > b`'s parent is 1048576 px plus the code wide.
const consoleCodes = p => p.evaluate(() => [...document.querySelectorAll('.oc > b')].map(e => Math.round(e.parentElement.getBoundingClientRect().width) - 1048576));

// codes -> `rows` lines of `cols` characters (printable ASCII; anything else shows as a space), each right-trimmed;
// the console's size from the memory map
const LA = require(require('path').join(__dirname, '..', 'compiler', 'layout.json'));
const gridRows = (codes, rows = LA.rows, cols = LA.cols) => { const r = []; for (let i = 0; i < rows; i++) r.push(codes.slice(i * cols, (i + 1) * cols).map(c => c >= 32 && c < 127 ? String.fromCharCode(c) : ' ').join('').replace(/\s+$/, '')); return r; };
// … joined, with trailing blank lines trimmed: the form expected outputs are compared in
const gridText = (codes, rows, cols) => gridRows(codes, rows, cols).join('\n').replace(/\s+$/, '');

// Replace the editor's text with `lines`, typed like a user: select all, delete, then each line (Enter between).
// Typing (or pasting) a run of spaces into the editor (white-space: nowrap) makes Chrome write U+00A0 for all of it at
// either end of a line and for all but its last space inside, so none collapses (readback/ui_rb.py nbsp). insertText
// inserts plain spaces instead, which collapse: "a b  c" read back as "a b c", and indentation was lost.
const nbsp = s => s.replace(/ +/g, (m, i) => i === 0 || i + m.length === s.length ? '\u00a0'.repeat(m.length) : '\u00a0'.repeat(m.length - 1) + ' ');
async function typeLines(p, lines) {
  await p.click('#ed'); await p.keyboard.press('Control+A'); await p.keyboard.press('Delete');
  for (let i = 0; i < lines.length; i++) { if (i) await p.keyboard.press('Enter'); await p.keyboard.insertText(nbsp(lines[i])); }
}

module.exports = { consoleCodes, gridRows, gridText, typeLines };
