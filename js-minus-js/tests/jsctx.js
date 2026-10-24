// jsctx.js — the context the Node oracles run a program in (harness only): what a browser gives the machine's programs.
// print(text) collects the output; check(args) sees console.log's / alert's arguments (the fuzz oracle's `bad`).
// window is the global object; timers run when the program is done (drain), by due time and then in the order they were
// set, as the machine's nexttimer runs them; alert prints its message (the page has no dialogs). run() runs a program in
// it: the context has a microtask queue of its own, which empties after the program and after each timer's callback, as
// a browser's does (the machine's nexttask).
const vm = require('vm');
const { show } = require('./jsprint.js');
module.exports = function ctx(print, check = () => {}) {
  const timers = []; let now = 0, nid = 1;
  const add = (fn, ms, rep) => { ms = Number.isInteger(ms) && ms > 0 ? ms : 0; if (rep && ms < 1) ms = 1;
    timers.push({ due: now + ms, fn, ms: rep ? ms : 0, id: nid }); return nid++; };
  const clear = id => { for (const t of timers) if (t.id === id) t.fn = null; };
  const c = { console: { log: (...a) => { check(a); print(a.map(show).join(' ') + '\n'); } }, putc: ch => print(String.fromCharCode(ch)),
              alert: x => { check([x]); print(show(x) + '\n'); }, setTimeout: (fn, ms) => add(fn, ms, 0), setInterval: (fn, ms) => add(fn, ms, 1),
              clearTimeout: clear, clearInterval: clear, ...require('../net/shim.js')() };
  c.window = c;
  c.drain = (run = f => f()) => {                     // (not a global: the oracle calls it after the program)
    for (let n = 0; n < 100000; n++) {
      let b = null; for (const t of timers) if (t.fn && (!b || t.due < b.due)) b = t;
      if (!b) return;
      now = b.due; const fn = b.fn; if (b.ms) b.due += b.ms; else b.fn = null; run(fn);
    }
  };
  return c;
};
// src run in context c (and its timers): each evaluation in the context is followed by its microtasks (microtaskMode)
module.exports.run = (c, src, timeout) => {
  const drain = c.drain; delete c.drain;
  const v = vm.createContext(c, { microtaskMode: 'afterEvaluate' });
  vm.runInContext(src, v, { timeout });
  drain(fn => { v.__task = fn; try { vm.runInContext('__task()', v, { timeout }); } finally { delete v.__task; } });
};
