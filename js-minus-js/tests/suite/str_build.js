// strings built anywhere: + and += on strings, numbers, bools
var s = "a" + "b";
var n = 42;
var t = s + n;
t += "!";
console.log(s, t, t.length);
var u = n + " is " + (n > 40) + ", " + (n < 0);
console.log(u);
var w = "";
for (var i = 0; i < 6; i++) w += i % 2 ? "o" : "x";
console.log(w);
function wrap(x) { return "[" + x + "]"; }
var v = wrap(wrap(3)) + wrap("q");
console.log(v, v.length);
var e = "";
e = e + e;
console.log(e.length, "-" + e + "-", 1 + 2 + "3", "1" + 2 + 3);
