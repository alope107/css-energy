// oracle.js in.json out.json — run many programs under Node in one process (the fuzzers' oracle, harness only).
// in.json: [{src, prelude?}], out.json: [{out, bad, error?, syntax?}] (bad: see below). `syntax` is set when Node rejects the source as a
// syntax error (checked on the source alone, without the prelude); `error` for any other exception (a timeout, a
// runtime TypeError, ...). The context: tests/jsctx.js, as tests/suite_expect.js's.
const fs = require('fs'), vm = require('vm'), { odd } = require('../jsprint.js');
const progs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
process.on('unhandledRejection', () => {});          // (a program's: the machine differs there, which the comparison reports)
const res = progs.map(({ src, prelude, timeout }) => {
  try { new vm.Script(src); } catch (e) { return { out: '', syntax: e.message }; }
  let out = '', bad = false;
  // bad: an argument our machine cannot print as Node does (README Limits; tests/jsprint.js)
  const jsctx = require('../jsctx.js');
  const ctx = jsctx(t => { out += t; if (out.length > 1e5) throw new Error('output limit'); }, a => { if (a.some(x => odd(x))) bad = true; });
  try { jsctx.run(ctx, (prelude || '') + '\n' + src, timeout || 500); }
  catch (e) { return { out, bad, error: String(e && e.message || e) }; }
  return { out, bad };
});
fs.writeFileSync(process.argv[3], JSON.stringify(res));
