// suite_expect.js dir — run every dir/*.js under Node (in tests/jsctx.js's context: putc, fetch, read, window, timers, alert) and
// write dir/*.out: the oracle is real JavaScript.
// An .out is rewritten only when it changes: the checks in the Makefile are out of date when one is newer than them.
const fs = require('fs'), path = require('path'), vm = require('vm');
const dir = process.argv[2];
// an uncaught error as the machine reports it (README: a ReferenceError without the name, which it doesn't keep,
// and "x is not a function" without the callee's text)
const uncaught = e => e.name === 'ReferenceError' ? 'Uncaught ReferenceError\n' : e.name !== 'TypeError' ? 'NODE-ERROR ' + e.message + '\n'
  : `Uncaught TypeError: ${e.message.endsWith('is not a function') ? 'not a function' : e.message}\n`;
for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.js')).sort()) {
  let out = '';
  const jsctx = require('./jsctx.js'), ctx = jsctx(t => { out += t; });
  try { jsctx.run(ctx, fs.readFileSync(path.join(dir, f), 'utf8'), 2000); }
  catch (e) { out += uncaught(e); }
  const o = path.join(dir, f.replace(/\.js$/, '.out'));
  if (!fs.existsSync(o) || fs.readFileSync(o, 'utf8') !== out) fs.writeFileSync(o, out);
}
