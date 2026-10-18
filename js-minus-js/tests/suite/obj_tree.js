// a binary tree built recursively
function mk(d) {
  if (d == 0) return null;
  return {l: mk(d - 1), r: mk(d - 1), d: d};
}
function count(t) {
  if (!t) return 0;
  return 1 + count(t.l) + count(t.r);
}
function sum(t) {
  if (t === null) return 0;
  return t.d + sum(t.l) + sum(t.r);
}
var t = mk(4);
console.log(count(t), sum(t));
t.l.r = {l: null, r: null, d: 100};
console.log(count(t), sum(t));
