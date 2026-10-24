// repl_expect.js dir — run every dir/*.js as Node's REPL would take it, typed a line at a time, and write dir/*.out and
// dir/*.tr: the oracle for the page's REPL (README REPL). Lines gather into an entry until it parses (an unfinished one,
// "Unexpected end of input", takes the next line, Node's "..."); each entry runs in one context (tests/jsctx.js's: putc,
// window, alert), and its completion value is printed as the REPL prints it: util.inspect, strings quoted. A REPL test is a
// session, so it holds no timers (the machine runs them after the last entry, Node's REPL after each) and no uncaught errors
// (the machine stops there, Node's REPL takes the next entry). .out is the output; .tr the transcript as the page shows it:
// each line after its prompt ("> " where an entry starts, "... " where one goes on), each entry's output under its last
// line, cut into rows of the REPL's console (layout.json repl_cols). A file is rewritten only when it changes.
const fs = require('fs'), path = require('path'), vm = require('vm'), util = require('util');
const COLS = require(path.join(__dirname, '..', 'compiler', 'layout.json')).repl_cols;
const write = (f, t) => { if (!fs.existsSync(f) || fs.readFileSync(f, 'utf8') !== t) fs.writeFileSync(f, t); };
const rows = t => t.replace(/\n$/, '').split('\n').flatMap(l => l.length ? l.match(new RegExp(`.{1,${COLS}}`, 'g')) : ['']);
const dir = process.argv[2];
for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.js')).sort()) {
  let out = '', entry = '', tr = '';
  const ctx = vm.createContext(require('./jsctx.js')(t => { out += t; })); delete ctx.drain;
  for (const line of fs.readFileSync(path.join(dir, f), 'utf8').replace(/\n$/, '').split('\n')) {
    tr += (entry ? '... ' : '> ') + line + '\n';
    entry += line + '\n';
    let s;
    try { s = new vm.Script(entry); }
    catch (e) { if (/Unexpected end of input/.test(e.message)) continue; out += `NODE-ERROR ${e.message}\n`; entry = ''; continue; }
    if (!entry.trim()) { entry = ''; continue; }      // (an empty line: no entry, no value)
    const o0 = out.length;
    try { const v = s.runInContext(ctx, { timeout: 2000 }); out += util.inspect(v) + '\n'; }     // (after the entry's own output)
    catch (e) { out += `NODE-ERROR ${e.message}\n`; }
    tr += rows(out.slice(o0)).join('\n') + '\n';
    entry = '';
  }
  write(path.join(dir, f.replace(/\.js$/, '.out')), out);
  write(path.join(dir, f.replace(/\.js$/, '.tr')), tr + '>\n');
}
