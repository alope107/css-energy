// oracle.js in.json out.json — run many programs under Node in one process (the fuzzers' oracle, harness only).
// in.json: [{src, prelude?}], out.json: [{out, bad, error?, syntax?}] (bad: see below). `syntax` is set when Node rejects the source as a
// syntax error (checked on the source alone, without the prelude); `error` for any other exception (a timeout, a
// runtime TypeError, ...). console.log, putc, fetch and read are shimmed as in tests/suite_expect.js.
const fs = require('fs'), vm = require('vm'), net = require('../../net/shim.js');
const progs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const res = progs.map(({ src, prelude, timeout }) => {
  try { new vm.Script(src); } catch (e) { return { out: '', syntax: e.message }; }
  let out = '', bad = false;
  // bad: an argument our machine cannot print as Node does (README Limits): an object, an array, null, undefined, a non-integer
  const odd = x => x === undefined || x === null || typeof x === 'object' || typeof x === 'function' || (typeof x === 'number' && !Number.isInteger(x));
  const ctx = { console: { log: (...a) => { if (a.some(odd)) bad = true; out += a.map(String).join(' ') + '\n'; if (out.length > 1e5) throw new Error('output limit'); } },
                putc: c => { out += String.fromCharCode(c); }, ...net() };
  try { vm.runInNewContext((prelude || '') + '\n' + src, ctx, { timeout: timeout || 500 }); }
  catch (e) { return { out, bad, error: String(e && e.message || e) }; }
  return { out, bad };
});
fs.writeFileSync(process.argv[3], JSON.stringify(res));
