// page.js — small probes the harness scripts of both projects run on a loaded page (harness only).

// Frames drawn in `ms` of page time: requestAnimationFrame callbacks, counted inside the page.
const countFrames = (p, ms) => p.evaluate(d => new Promise(r => { let n = 0; const t0 = performance.now(); (function f() { n++; if (performance.now() - t0 < d) requestAnimationFrame(f); else r(n) })() }), ms);

// Raw computed values (strings) of the custom properties --<name> on the first element matching `sel`.
// Convert in the caller: +'' is 0 but parseFloat('') is NaN, and some checks rely on the difference.
const vars = (p, sel, names) => p.evaluate(([sel, names]) => { const c = getComputedStyle(document.querySelector(sel)); return names.map(n => c.getPropertyValue('--' + n)) }, [sel, names]);

// Call `test()` every `interval` ms until it returns a truthy value or `timeout` ms pass. Returns
// {value, ms}: the last value and the time from the call (value is falsy on timeout).
async function pollUntil(p, test, { interval = 250, timeout = 30000 } = {}) {
  const t0 = Date.now(); let value;
  while (true) {
    await p.waitForTimeout(interval);
    value = await test();
    if (value || Date.now() - t0 >= timeout) return { value, ms: Date.now() - t0 };
  }
}

module.exports = { countFrames, vars, pollUntil };
