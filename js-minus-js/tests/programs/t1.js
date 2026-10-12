// functions, recursion, forward calls, params and locals
var n = 10;
function fib(k) { if (k < 2) { return k; } return fib(k - 1) + fib(k - 2); }
console.log(fib(n));
console.log(sq(7) - 9);
function sq(x) { var y = x * x; return y; }
function add3(a, b, c) { var s = a + b; s = s + c; return s; }
console.log(add3(1, 20, 300));
