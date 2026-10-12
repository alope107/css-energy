// suite_expect.js dir — run every dir/*.js under Node (putc shimmed) and write dir/*.out: the oracle is real JavaScript
const fs = require('fs'), path = require('path'), vm = require('vm');
const dir = process.argv[2];
for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.js')).sort()) {
  let out = '';
  const ctx = { console: { log: (...a) => { out += a.map(String).join(' ') + '\n'; } }, putc: c => { out += String.fromCharCode(c); } };
  try { vm.runInNewContext(fs.readFileSync(path.join(dir, f), 'utf8'), ctx, { timeout: 2000 }); }
  catch (e) { out += 'NODE-ERROR ' + e.message + '\n'; }
  fs.writeFileSync(path.join(dir, f.replace(/\.js$/, '.out')), out);
}
