// jsctx.js — the context the Node oracles run a program in (harness only): what a browser gives the machine's programs.
// print(text) collects the output; check(args) sees console.log's / alert's arguments (the fuzz oracle's `bad`).
// window is the global object; timers run when the program is done (drain), by due time and then in the order they were
// set, as the machine's nexttimer runs them; alert prints its message (the page has no dialogs).
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
  c.drain = () => {                                   // (not a global: the oracle calls it after the program)
    for (let n = 0; n < 100000; n++) {
      let b = null; for (const t of timers) if (t.fn && (!b || t.due < b.due)) b = t;
      if (!b) return;
      now = b.due; const fn = b.fn; if (b.ms) b.due += b.ms; else b.fn = null; fn();
    }
  };
  return c;
};
