// repl_expect.js dir — run every dir/*.js as Node's REPL would take it, typed a line at a time, and write dir/*.out: the
// oracle for the page's REPL (README REPL). Lines gather into an entry until it parses (an unfinished one, "Unexpected end
// of input", takes the next line, Node's "..."); each entry runs in one context (tests/jsctx.js's: putc, window, alert), and
// its completion value is printed as the REPL prints it: util.inspect, strings quoted. A REPL test is a session, so it
// holds no timers (the machine runs them after the last entry, Node's REPL after each) and no uncaught errors (the machine
// stops there, Node's REPL takes the next entry). An .out is rewritten only when it changes.
const fs = require('fs'), path = require('path'), vm = require('vm'), util = require('util');
const dir = process.argv[2];
for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.js')).sort()) {
  let out = '', entry = '';
  const ctx = vm.createContext(require('./jsctx.js')(t => { out += t; })); delete ctx.drain;
  for (const line of fs.readFileSync(path.join(dir, f), 'utf8').replace(/\n$/, '').split('\n')) {
    entry += line + '\n';
    let s;
    try { s = new vm.Script(entry); }
    catch (e) { if (/Unexpected end of input/.test(e.message)) continue; out += `NODE-ERROR ${e.message}\n`; entry = ''; continue; }
    if (!entry.trim()) { entry = ''; continue; }      // (an empty line: no entry, no value)
    try { const v = s.runInContext(ctx, { timeout: 2000 }); out += util.inspect(v) + '\n'; }     // (after the entry's own output)
    catch (e) { out += `NODE-ERROR ${e.message}\n`; }
    entry = '';
  }
  const o = path.join(dir, f.replace(/\.js$/, '.out'));
  if (!fs.existsSync(o) || fs.readFileSync(o, 'utf8') !== out) fs.writeFileSync(o, out);
}
