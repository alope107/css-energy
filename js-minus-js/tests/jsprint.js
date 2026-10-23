// jsprint.js — console.log's form of one argument (as Node prints it: a string as it is, an array or object through
// util.inspect), and whether our machine can print it the same way (README Limits). For the oracles (harness only).
const util = require('util');
const show = x => typeof x === 'string' ? x : util.inspect(x);      // (console.log's form: -0 is -0, a function [Function: f])
// odd: an argument our machine cannot print as Node does: a function; an array or object that holds one,
// or itself (circular), or more than one integer key (Node sorts them), or a string with both quotes or an unusual
// character; or that Node prints on several lines (more than 6 elements, or wider than 72)
function odd(x, top = true, seen = new Set()) {
  if (x === undefined || x === null || typeof x === 'boolean') return false;
  if (typeof x === 'function') return true;
  if (typeof x === 'number') return false;
  if (typeof x === 'string') return !top && ((x.includes("'") && x.includes('"')) || /[^\x20-\x7e\n\t]/.test(x));
  if (seen.has(x)) return true;
  seen.add(x);
  const ks = Object.keys(x);
  if (!Array.isArray(x) && ks.filter(k => /^\d+$/.test(k)).length > 1) return true;
  if (ks.some(k => odd(x[k], false, seen))) return true;
  seen.delete(x);
  return top && util.inspect(x).includes('\n');
}
module.exports = { show, odd };
