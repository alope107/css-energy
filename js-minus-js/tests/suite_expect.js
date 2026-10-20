// suite_expect.js dir — run every dir/*.js under Node (putc shimmed) and write dir/*.out: the oracle is real JavaScript.
// An .out is rewritten only when it changes: the checks in the Makefile are out of date when one is newer than them.
const fs = require('fs'), path = require('path'), vm = require('vm'), { show } = require('./jsprint.js');
const dir = process.argv[2];
for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.js')).sort()) {
  let out = '';
  const ctx = { console: { log: (...a) => { out += a.map(show).join(' ') + '\n'; } }, putc: c => { out += String.fromCharCode(c); } };
  try { vm.runInNewContext(fs.readFileSync(path.join(dir, f), 'utf8'), ctx, { timeout: 2000 }); }
  catch (e) { out += 'NODE-ERROR ' + e.message + '\n'; }
  const o = path.join(dir, f.replace(/\.js$/, '.out'));
  if (!fs.existsSync(o) || fs.readFileSync(o, 'utf8') !== out) fs.writeFileSync(o, out);
}
