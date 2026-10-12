function f(x) { console.log("f", x); return x; }
f(0) && f(1);
f(1) || f(2);
f(0) || f(3) && f(4);
var r = f(5) && f(0) && f(6);
console.log(r);
