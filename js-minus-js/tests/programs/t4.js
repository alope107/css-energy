// locals shadowing globals, return without value, nested calls, recursion with accumulator
var g = 5;
function f(g) { var h = g + 1; return h * 2; }
function noret(a) { var b = a; return; }
function acc(n, s) { if (n == 0) { return s; } return acc(n - 1, s + n); }
console.log(f(g) + g);
console.log(noret(3));
console.log(acc(20, 0));
function pr(n) { var i = 0; for (i = 0; i < n; i++) { putc(42); } putc(10); return 0; }
pr(5);
pr(acc(3, 0));
