// suite_expect.js dir — run every dir/*.js under Node (putc, fetch and read shimmed: net/shim.js) and write dir/*.out: the oracle is real JavaScript.
// An .out is rewritten only when it changes: the checks in the Makefile are out of date when one is newer than them.
const fs = require('fs'), path = require('path'), vm = require('vm'), { show } = require('./jsprint.js');
const dir = process.argv[2];
// an uncaught error as the machine reports it (README: a ReferenceError without the name, which it doesn't keep)
const uncaught = e => e.name === 'ReferenceError' ? 'Uncaught ReferenceError\n' : e.name === 'TypeError' ? `Uncaught TypeError: ${e.message}\n` : 'NODE-ERROR ' + e.message + '\n';
for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.js')).sort()) {
  let out = '';
  const ctx = { console: { log: (...a) => { out += a.map(show).join(' ') + '\n'; } }, putc: c => { out += String.fromCharCode(c); }, ...require('../net/shim.js')() };
  ctx.window = ctx;                                   // (a browser's global object)
  try { vm.runInNewContext(fs.readFileSync(path.join(dir, f), 'utf8'), ctx, { timeout: 2000 }); }
  catch (e) { out += uncaught(e); }
  const o = path.join(dir, f.replace(/\.js$/, '.out'));
  if (!fs.existsSync(o) || fs.readFileSync(o, 'utf8') !== out) fs.writeFileSync(o, out);
}
